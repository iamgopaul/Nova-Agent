// Canonicalize the Tailwind classes that tailwindcss-intellisense flags as
// "can be written as ...". They compile to the same CSS; this just clears
// the IDE hint noise. Conservative — only touches patterns we're 100 % sure
// about. Safe to re-run.
import fs from "node:fs"
import path from "node:path"

const FRONTEND = path.dirname(new URL(import.meta.url).pathname).replace(/^\/(\w):/, "$1:") + "/.."

function* walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === ".next") continue
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(full)
    else if (/\.(tsx?|jsx?)$/.test(entry.name)) yield full
  }
}

// 1. Opacity arbitrary values: /[0.04] → /4, /[0.10] → /10, /[0.1] → /10
// Pattern after a slash inside class strings: /[0.NN] or /[0.N]
const opacityRe = /\/\[0\.(\d{1,2})\]/g
const opacityRepl = (_m, digits) => {
  // digits is "04", "10", "1", "5", etc.
  if (digits.length === 1) return `/${digits}0` // "1" → "10", "5" → "50"
  if (digits[0] === "0")   return `/${digits[1]}` // "04" → "4", "09" → "9"
  return `/${digits}` // "10" → "10", "15" → "15"
}

// 2. z-[N] → z-N for the standard tailwind z-index ladder
const zRe = /\bz-\[(\d{1,3})\]/g
const zRepl = (_m, n) => `z-${n}`

// 3. min-h-[100dvh] / h-[100dvh] → min-h-dvh / h-dvh
const dvhRe = /\b(min-)?h-\[100dvh\]/g
const dvhRepl = (_m, prefix) => `${prefix || ""}h-dvh`

// 4. bg-gradient-to-X → bg-linear-to-X (Tailwind v4 canonical name)
const gradientRe = /\bbg-gradient-to-(t|tr|r|br|b|bl|l|tl)\b/g
const gradientRepl = (_m, dir) => `bg-linear-to-${dir}`

// 5. shadow/etc. arbitrary values with `_/_` should use `/` directly
//    e.g. shadow-[...oklch(0.72_0.14_220_/_0.10)] → ...oklch(0.72_0.14_220/0.10)
const oklchSlashRe = /(oklch\([^)]*?)_\/_(\d)/g
const oklchSlashRepl = (_m, head, n) => `${head}/${n}`

const transforms = [
  [opacityRe, opacityRepl],
  [zRe, zRepl],
  [dvhRe, dvhRepl],
  [gradientRe, gradientRepl],
  [oklchSlashRe, oklchSlashRepl],
]

let touched = 0
let totalReplacements = 0

for (const file of walk(FRONTEND)) {
  let src = fs.readFileSync(file, "utf8")
  let changed = false
  let fileReplacements = 0
  for (const [re, repl] of transforms) {
    const before = src
    src = src.replace(re, repl)
    if (src !== before) {
      changed = true
      fileReplacements += (before.match(re) || []).length
    }
  }
  if (changed) {
    fs.writeFileSync(file, src)
    touched += 1
    totalReplacements += fileReplacements
    console.log(`  ${path.relative(FRONTEND, file)}: ${fileReplacements} replacements`)
  }
}

console.log(`\nDone — ${touched} files touched, ${totalReplacements} replacements.`)
