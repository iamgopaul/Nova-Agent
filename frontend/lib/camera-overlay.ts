/**
 * Map normalised detection boxes (0–1 relative to full camera frame) to CSS pixel
 * coordinates on top of a displayed <video> using the same layout as `object-fit: cover`.
 *
 * Without this, boxes drift when the video aspect ratio does not match the container
 * (MediaPipe uses the full frame; the screen crops with letterboxing inside cover).
 */

export type NormBox = { x: number; y: number; w: number; h: number }

export type DisplayRect = { x: number; y: number; w: number; h: number }

/**
 * @param mirrorX – set true when the preview is mirrored (typical front camera selfie UX).
 *   Detection still runs on the unmirrored JPEG; we flip coordinates to match the display.
 */
export function mapNormBoxToDisplayPixels(
  box: NormBox,
  videoEl: HTMLVideoElement,
  displayW: number,
  displayH: number,
  mirrorX: boolean,
): DisplayRect {
  const vw = videoEl.videoWidth
  const vh = videoEl.videoHeight
  if (!vw || !vh || displayW <= 0 || displayH <= 0) {
    return {
      x: box.x * displayW,
      y: box.y * displayH,
      w: box.w * displayW,
      h: box.h * displayH,
    }
  }

  const scale = Math.max(displayW / vw, displayH / vh)
  const scaledW = vw * scale
  const scaledH = vh * scale
  const offsetX = (displayW - scaledW) / 2
  const offsetY = (displayH - scaledH) / 2

  let x = box.x * vw * scale + offsetX
  let y = box.y * vh * scale + offsetY
  const w = box.w * vw * scale
  const h = box.h * vh * scale

  if (mirrorX) {
    x = displayW - x - w
  }

  return { x, y, w, h }
}

const DIGIT_DISPLAY: Record<string, string> = {
  thumb: "Thumb",
  index: "Index",
  middle: "Middle",
  ring: "Ring",
  pinky: "Pinky",
}

/**
 * Readable per-digit label, e.g. `"Left thumb"` → `"Left: Thumb"`.
 * If handedness is unknown (`Hand thumb`), shows only the digit name.
 */
export function fingerSegmentDisplayLabel(label: string): string {
  const m = /^(Left|Right|Hand)\s+(thumb|index|middle|ring|pinky)\b/i.exec((label || "").trim())
  if (!m) {
    return label
  }
  const sideRaw = m[1].toLowerCase()
  const sideLabel = sideRaw === "left" ? "Left" : sideRaw === "right" ? "Right" : ""
  const digit = DIGIT_DISPLAY[m[2].toLowerCase()] ?? m[2]
  return sideLabel ? `${sideLabel}: ${digit}` : digit
}
