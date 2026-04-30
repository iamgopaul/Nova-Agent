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
          // Step 1: reverse geocode lat/lon → city/region/country
          const geoRes = await fetch("/api/geo", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
          })
          if (!geoRes.ok) return
          const data = await geoRes.json()
          if (!data.city) return

          const locationString = [data.city, data.region, data.country]
            .filter(Boolean)
            .join(", ")

          // Step 2: cache locally for immediate use (sent as X-User-Location header)
          localStorage.setItem(
            STORAGE_KEY,
            JSON.stringify({ ...data, savedAt: Date.now() })
          )

          // Step 3: persist as a server-side memory fact so the model knows it
          // for weather, time, and local queries — survives across sessions
          await fetch("/api/memory/facts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              key: "location",
              value: locationString,
              source: "browser_gps",
            }),
          })
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
