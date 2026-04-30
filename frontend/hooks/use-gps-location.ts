"use client"

import { useEffect } from "react"

const STORAGE_KEY = "gaaia_user_location"
const MAX_AGE_MS = 30 * 60 * 1000 // refresh every 30 min

export function useGpsLocation() {
  useEffect(() => {
    if (typeof window === "undefined" || !navigator.geolocation) return

    // Avoid refetching if we have a fresh cached value
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const cached = JSON.parse(raw)
        if (cached?.city && Date.now() - (cached.savedAt ?? 0) < MAX_AGE_MS) return
      }
    } catch {
      // ignore parse errors
    }

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          const res = await fetch("/api/geo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
          })
          if (!res.ok) return
          const data = await res.json()
          if (data.city) {
            localStorage.setItem(
              STORAGE_KEY,
              JSON.stringify({ ...data, savedAt: Date.now() })
            )
          }
        } catch {
          // silently ignore — location is best-effort
        }
      },
      () => {
        // permission denied or unavailable — ignore
      },
      { timeout: 8000, maximumAge: MAX_AGE_MS }
    )
  }, [])
}
