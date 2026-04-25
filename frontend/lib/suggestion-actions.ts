/**
 * Intercepts chat follow-up chip clicks so we perform real actions (download, web search)
 * instead of only re-prompting the model with a huge quoted context.
 */

import type { Message } from "@/components/chat/message-bubble"

function findLatestAssistantImageUrl(messages: Message[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m.role !== "assistant") {
      continue
    }
    if (m.imageUrls && m.imageUrls.length > 0) {
      const u = [...m.imageUrls].reverse().find(Boolean)
      if (u) {
        return u
      }
    }
    if (m.imageUrl) {
      return m.imageUrl
    }
    const sections = m.storySections
    if (sections?.length) {
      for (let j = sections.length - 1; j >= 0; j--) {
        const url = sections[j].imageUrl
        if (url) {
          return url
        }
      }
    }
  }
  return null
}

function blobToPngBlob(blob: Blob): Promise<Blob> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    const u = URL.createObjectURL(blob)
    img.onload = () => {
      try {
        const c = document.createElement("canvas")
        c.width = img.naturalWidth
        c.height = img.naturalHeight
        const ctx = c.getContext("2d")
        if (!ctx) {
          URL.revokeObjectURL(u)
          reject(new Error("no canvas context"))
          return
        }
        ctx.drawImage(img, 0, 0)
        c.toBlob(
          b => {
            URL.revokeObjectURL(u)
            if (b) {
              resolve(b)
            } else {
              reject(new Error("toBlob failed"))
            }
          },
          "image/png",
          1.0,
        )
      } catch (e) {
        URL.revokeObjectURL(u)
        reject(e)
      }
    }
    img.onerror = () => {
      URL.revokeObjectURL(u)
      reject(new Error("image load failed"))
    }
    img.src = u
  })
}

async function downloadImageUrl(
  url: string,
  options: { wantPng: boolean; wantJpeg: boolean },
) {
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`Image fetch failed (${res.status})`)
  }
  const blob = await res.blob()
  let out = blob
  let name = "nova-image"
  if (options.wantPng && blob.type !== "image/png") {
    out = await blobToPngBlob(blob)
    name = "nova-image.png"
  } else if (options.wantJpeg) {
    const img = new Image()
    const u = URL.createObjectURL(blob)
    try {
      await new Promise<void>((ok, err) => {
        img.onload = () => ok()
        img.onerror = () => err(new Error("jpeg src"))
        img.src = u
      })
      const c = document.createElement("canvas")
      c.width = img.naturalWidth
      c.height = img.naturalHeight
      const ctx = c.getContext("2d")
      if (!ctx) {
        throw new Error("no ctx")
      }
      ctx.drawImage(img, 0, 0)
      out = await new Promise<Blob>((resolve, reject) => {
        c.toBlob(b => (b ? resolve(b) : reject(new Error("toBlob"))), "image/jpeg", 0.92)
      })
      name = "nova-image.jpg"
    } finally {
      URL.revokeObjectURL(u)
    }
  } else {
    if (blob.type === "image/png") {
      name = "nova-image.png"
    } else if (blob.type === "image/jpeg") {
      name = "nova-image.jpg"
    } else if (blob.type === "image/webp") {
      name = "nova-image.webp"
    } else {
      name = "nova-image.png"
    }
  }

  const a = document.createElement("a")
  const href = URL.createObjectURL(out)
  a.href = href
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(href), 3000)
}

export type SuggestionActionResult = "consumed" | "direct-send" | "passthrough"

/**
 * - **Download / save as PNG|JPEG|…** — fetches the last generated image in the thread and
 *   saves it (PNG conversion via canvas when the chip asks for PNG).
 * - **Show me photos / Search for images** — return `direct-send` with the raw chip text
 *   so the user message is a clean search (no 300-line "Regarding your previous" quote).
 */
export function tryHandleSuggestionAction(
  suggestion: string,
  messages: Message[],
  onDirectSend: (text: string) => void,
): SuggestionActionResult {
  const s = suggestion.trim()
  const low = s.toLowerCase()

  // Direct web-image intents — a short user message works better than a wrapped quote.
  if (
    /^(show me|search for|find|look up)\s+(?:some\s+)?(photos?|images?|pictures?|reference)/i.test(s) ||
    /^search (?:the |google |for )?(?:for )?(?:images?|photos?|pictures?)\s+of/i.test(s)
  ) {
    onDirectSend(s)
    return "direct-send"
  }

  const wantsImageDownload =
    /\b(save|download|export)\b/i.test(s) &&
    (/\b(png|jpe?g|webp|gif)\b/i.test(s) || /\bimage\s+as\b/i.test(low) || /\bthe\s+final\s+image\b/i.test(low))

  if (wantsImageDownload) {
    const url = findLatestAssistantImageUrl(messages)
    if (url) {
      const wantPng = /\bpng\b/i.test(s)
      const wantJpeg = /\bjpe?g\b|\bjpg\b|\bjpeg\b/i.test(s) && !wantPng
      void downloadImageUrl(url, {
        wantPng,
        wantJpeg,
      }).catch(e => {
        console.warn("[suggestion-actions] download failed", e)
      })
      return "consumed"
    }
  }

  return "passthrough"
}
