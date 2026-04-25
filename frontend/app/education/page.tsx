"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import {
  BookOpen, CheckCircle2, ChevronDown, ChevronUp, FileText, History,
  Loader2, Sparkles, Trash2, Trophy, Upload, X, XCircle
} from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

type Difficulty = "elementary" | "middle" | "high" | "college" | "bachelors" | "masters" | "doctorate"
type Mode = "quiz" | "exam"

type PublicQuestion = {
  id: string
  tier?: "easy" | "medium" | "hard"
  type: "multiple_choice" | "short_answer"
  question: string
  options?: string[]
}

const HIGHER_LEVELS = new Set(["bachelors", "masters", "doctorate"])

type GenerateResponse = {
  quiz_id: string
  title: string
  lesson: string
  questions: PublicQuestion[]
  grading: unknown
}

type GradeResultItem = {
  id: string
  type: string
  question: string
  score: number
  max: number
  detail: string
  correct_index?: number | null
}

type GradeResult = {
  percent: number
  earned: number
  total_points: number
  results: GradeResultItem[]
  feedback: {
    summary: string
    strengths: string[]
    improve: string[]
    encouragement: string
  }
}

type QuizHistoryEntry = {
  id: string
  date: string
  topic: string
  difficulty: string
  mode: string
  percent: number
  earned: number
  total: number
  title: string
  questions: PublicQuestion[]
  answers: Record<string, string>
  results: GradeResultItem[]
  feedback: GradeResult["feedback"]
}

const HISTORY_KEY = "gaaia.educationHistory.v1"

function loadHistory(): QuizHistoryEntry[] {
  if (typeof window === "undefined") return []
  try {
    const raw = window.localStorage.getItem(HISTORY_KEY)
    if (!raw) return []
    return JSON.parse(raw) as QuizHistoryEntry[]
  } catch { return [] }
}

function saveHistory(entries: QuizHistoryEntry[]) {
  if (typeof window === "undefined") return
  try { window.localStorage.setItem(HISTORY_KEY, JSON.stringify(entries)) } catch { /* quota */ }
}

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  elementary: "Elementary",
  middle: "Middle school",
  high: "High school",
  college: "College / Associate",
  bachelors: "Bachelor's degree",
  masters: "Master's degree",
  doctorate: "Doctorate / PhD",
}

function TierBadge({ tier }: { tier?: "easy" | "medium" | "hard" }) {
  if (!tier) return null
  const styles = {
    easy:   "text-sky-300/80 bg-sky-500/10 border-sky-500/20",
    medium: "text-amber-300/80 bg-amber-500/10 border-amber-500/20",
    hard:   "text-red-300/80 bg-red-500/10 border-red-500/20",
  }
  return (
    <span className={cn(
      "inline-flex items-center px-1.5 py-0.5 rounded-md border text-[9px] font-bold uppercase tracking-widest",
      styles[tier],
    )}>
      {tier}
    </span>
  )
}

function ScoreBadge({ percent, size = "md" }: { percent: number; size?: "sm" | "md" }) {
  const color =
    percent >= 80 ? "text-emerald-300 bg-emerald-500/15 border-emerald-500/30" :
    percent >= 60 ? "text-amber-300 bg-amber-500/15 border-amber-500/30" :
                   "text-red-300 bg-red-500/15 border-red-500/30"
  return (
    <div className={cn(
      "rounded-xl border font-bold tabular-nums flex items-center justify-center",
      size === "md" ? "w-16 h-16 text-2xl" : "w-10 h-10 text-sm",
      color,
    )}>
      {percent}%
    </div>
  )
}

function HistoryCard({
  entry,
  onDelete,
}: {
  entry: QuizHistoryEntry
  onDelete: (id: string) => void
}) {
  const [open, setOpen] = useState(false)
  const date = new Date(entry.date).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })

  return (
    <div className="rounded-xl border border-white/[0.07] bg-black/20 overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.02] transition-colors"
      >
        <ScoreBadge percent={entry.percent} size="sm" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white/80 truncate">{entry.title}</p>
          <p className="text-[11px] text-white/35 mt-0.5">
            {date} · {DIFFICULTY_LABELS[entry.difficulty as Difficulty] ?? entry.difficulty} · {entry.earned}/{entry.total} pts
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={e => { e.stopPropagation(); onDelete(entry.id) }}
            className="p-1 rounded-lg text-white/25 hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          {open ? <ChevronUp className="w-4 h-4 text-white/30" /> : <ChevronDown className="w-4 h-4 text-white/30" />}
        </div>
      </button>

      {open && (
        <div className="border-t border-white/[0.05] px-4 py-3 space-y-2.5">
          {entry.results.map(r => {
            const q = entry.questions.find(q => q.id === r.id)
            const isCorrect = r.score >= r.max
            const userAnswerIdx = entry.answers[r.id]
            const userAnswerText = q?.options && userAnswerIdx !== undefined
              ? q.options[Number(userAnswerIdx)]
              : (entry.answers[r.id] ?? "—")
            const correctText = q?.options && r.correct_index != null
              ? q.options[r.correct_index]
              : null

            return (
              <div key={r.id} className={cn(
                "rounded-lg px-3 py-2.5 border text-xs",
                isCorrect
                  ? "border-emerald-500/20 bg-emerald-500/[0.05]"
                  : "border-red-500/20 bg-red-500/[0.05]"
              )}>
                <p className="text-white/70 font-medium mb-1.5">{r.question}</p>
                <div className="space-y-1">
                  <p className={cn("flex items-start gap-1.5", isCorrect ? "text-emerald-300/80" : "text-red-300/80")}>
                    {isCorrect ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" /> : <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />}
                    <span>Your answer: {userAnswerText || "—"}</span>
                  </p>
                  {!isCorrect && correctText && (
                    <p className="flex items-start gap-1.5 text-emerald-300/80 pl-5">
                      <span>✓ Correct: {correctText}</span>
                    </p>
                  )}
                  {!isCorrect && r.type === "short_answer" && (
                    <p className="text-white/35 pl-5">{r.detail}</p>
                  )}
                </div>
              </div>
            )
          })}

          {entry.feedback.summary && (
            <p className="text-xs text-white/40 italic pt-1">{entry.feedback.summary}</p>
          )}
        </div>
      )}
    </div>
  )
}

export default function EducationPage() {
  const router = useRouter()
  const [userReady, setUserReady] = useState(false)

  const [topic, setTopic] = useState("")
  const [mode, setMode] = useState<Mode>("quiz")
  const [difficulty, setDifficulty] = useState<Difficulty>("high")
  const [degreeField, setDegreeField] = useState("")
  const [numQuestions, setNumQuestions] = useState(6)
  const [focus, setFocus] = useState("")

  const [generating, setGenerating] = useState(false)
  const [grading, setGrading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [docContext, setDocContext] = useState<string | null>(null)
  const [docContextFilename, setDocContextFilename] = useState<string | null>(null)
  const [loadingContext, setLoadingContext] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [quizBundle, setQuizBundle] = useState<GenerateResponse | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [grade, setGrade] = useState<GradeResult | null>(null)

  const [history, setHistory] = useState<QuizHistoryEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    setHistory(loadHistory())
    fetch("/api/auth/me")
      .then(r => {
        if (!r.ok) { router.replace("/login"); return }
        setUserReady(true)
      })
      .catch(() => router.replace("/login"))
  }, [router])

  const resetAttempt = useCallback(() => {
    setAnswers({})
    setGrade(null)
    setError(null)
  }, [])

  const handleDocUpload = async (file: File) => {
    setLoadingContext(true)
    setError(null)
    try {
      const form = new FormData()
      form.append("file", file)
      const res = await fetch("/api/education/extract-context", { method: "POST", body: form })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setError(typeof data?.detail === "string" ? data.detail : "Could not extract document text."); return }
      setDocContext(data.text as string)
      setDocContextFilename(file.name)
    } catch {
      setError("Network error while extracting document.")
    } finally {
      setLoadingContext(false)
    }
  }

  const handleGenerate = async () => {
    const t = topic.trim()
    if (t.length < 2) { setError("Enter a topic (at least a few words)."); return }
    setError(null)
    setGenerating(true)
    setQuizBundle(null)
    setGrade(null)
    setAnswers({})
    try {
      const res = await fetch("/api/education/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: t, mode, difficulty, num_questions: numQuestions,
          focus: focus.trim() || null, document_context: docContext || null,
          degree_field: (HIGHER_LEVELS.has(difficulty) && degreeField.trim()) ? degreeField.trim() : null,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setError(typeof data?.detail === "string" ? data.detail : "Could not generate quiz."); return }
      setQuizBundle(data as GenerateResponse)
    } catch {
      setError("Network error while generating.")
    } finally {
      setGenerating(false)
    }
  }

  const handleGrade = async () => {
    if (!quizBundle) return
    setError(null)
    setGrading(true)
    try {
      const res = await fetch("/api/education/grade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ quiz: quizBundle, answers }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) { setError(typeof data?.detail === "string" ? data.detail : "Could not grade submission."); return }
      const result = data as GradeResult
      setGrade(result)

      // Save to history
      const entry: QuizHistoryEntry = {
        id: quizBundle.quiz_id + "-" + Date.now(),
        date: new Date().toISOString(),
        topic: topic.trim(),
        difficulty,
        mode,
        percent: result.percent,
        earned: result.earned,
        total: result.total_points,
        title: quizBundle.title,
        questions: quizBundle.questions,
        answers: { ...answers },
        results: result.results,
        feedback: result.feedback,
      }
      const updated = [entry, ...loadHistory()].slice(0, 50)
      saveHistory(updated)
      setHistory(updated)
    } catch {
      setError("Network error while grading.")
    } finally {
      setGrading(false)
    }
  }

  const handleDeleteHistory = (id: string) => {
    const updated = history.filter(e => e.id !== id)
    setHistory(updated)
    saveHistory(updated)
  }

  const handleClearHistory = () => {
    setHistory([])
    saveHistory([])
  }

  if (!userReady) {
    return (
      <div className="h-screen flex items-center justify-center text-white/30 text-sm" style={{ backgroundColor: "var(--surface-1)" }}>
        Loading…
      </div>
    )
  }

  return (
    <AppShell title="Education" titleColor="text-rose-400">
      <div className="relative flex flex-col h-full min-h-0 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 z-0 page-gradient-education" />

        <div className="relative z-[1] flex flex-col flex-1 min-h-0 overflow-y-auto scrollbar-thin">
          <div className="max-w-3xl mx-auto w-full px-5 py-6 space-y-7 pb-24">

            {/* Header */}
            <header className="flex items-start justify-between gap-4">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 text-rose-400/90">
                  <BookOpen className="w-4 h-4" />
                  <span className="text-[10px] font-bold uppercase tracking-widest">Learn</span>
                </div>
                <h1 className="text-xl font-semibold text-white/90">GAAIA Education</h1>
                <p className="text-sm text-white/40 leading-relaxed max-w-lg">
                  GAAIA writes a short lesson, builds a quiz or exam, then scores your answers and explains what to review next.
                </p>
              </div>
              {history.length > 0 && (
                <button
                  onClick={() => setShowHistory(v => !v)}
                  className={cn(
                    "shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-xl border text-xs font-medium transition-colors",
                    showHistory
                      ? "border-rose-500/30 bg-rose-500/10 text-rose-300"
                      : "border-white/[0.08] text-white/40 hover:text-white/70 hover:bg-white/[0.04]"
                  )}
                >
                  <History className="w-3.5 h-3.5" />
                  History ({history.length})
                </button>
              )}
            </header>

            {/* History panel */}
            {showHistory && history.length > 0 && (
              <section className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold text-white/50 uppercase tracking-widest">Past quizzes</p>
                  <button
                    onClick={handleClearHistory}
                    className="flex items-center gap-1 text-[11px] text-red-400/60 hover:text-red-400 transition-colors"
                  >
                    <Trash2 className="w-3 h-3" />
                    Clear all
                  </button>
                </div>
                <div className="space-y-2">
                  {history.map(entry => (
                    <HistoryCard key={entry.id} entry={entry} onDelete={handleDeleteHistory} />
                  ))}
                </div>
              </section>
            )}

            {/* Builder card */}
            <section className="rounded-2xl border border-rose-500/15 bg-rose-500/[0.04] p-5 space-y-4">
              <div className="flex items-center gap-2 text-white/65 text-sm font-semibold">
                <Sparkles className="w-4 h-4 text-rose-400" />
                Create a lesson &amp; assessment
              </div>

              <label className="block space-y-1.5">
                <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">Topic</span>
                <textarea
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  rows={3}
                  placeholder="e.g. Photosynthesis, World War II timelines, Python list comprehensions…"
                  className="w-full rounded-xl border border-white/[0.09] bg-black/25 px-3.5 py-2.5 text-sm text-white/85 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-rose-500/40 focus:border-rose-500/30 resize-y min-h-[88px] transition-colors"
                />
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="space-y-1.5">
                  <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">Format</span>
                  <select
                    value={mode}
                    onChange={e => setMode(e.target.value as Mode)}
                    className="w-full rounded-lg border border-white/[0.09] bg-black/25 px-3 py-2 text-sm text-white/80 focus:outline-none focus:ring-1 focus:ring-rose-500/40"
                  >
                    <option value="quiz">Quiz (shorter)</option>
                    <option value="exam">Exam (formal)</option>
                  </select>
                </label>
                <label className="space-y-1.5">
                  <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">Level</span>
                  <select
                    value={difficulty}
                    onChange={e => setDifficulty(e.target.value as Difficulty)}
                    className="w-full rounded-lg border border-white/[0.09] bg-black/25 px-3 py-2 text-sm text-white/80 focus:outline-none focus:ring-1 focus:ring-rose-500/40"
                  >
                    <option value="elementary">Elementary</option>
                    <option value="middle">Middle school</option>
                    <option value="high">High school</option>
                    <option value="college">College / Associate</option>
                    <option value="bachelors">Bachelor&apos;s degree</option>
                    <option value="masters">Master&apos;s degree</option>
                    <option value="doctorate">Doctorate / PhD</option>
                  </select>
                </label>
              </div>

              {/* Degree field — shown for bachelor's/master's/doctorate */}
              {HIGHER_LEVELS.has(difficulty) && (
                <label className="block space-y-1.5">
                  <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">
                    Your degree / major <span className="normal-case font-normal text-white/20">(helps target questions to your field)</span>
                  </span>
                  <input
                    value={degreeField}
                    onChange={e => setDegreeField(e.target.value)}
                    placeholder="e.g. Computer Science, Mechanical Engineering, Finance, Biology…"
                    className="w-full rounded-lg border border-white/[0.09] bg-black/25 px-3 py-2 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-rose-500/40 focus:border-rose-500/30 transition-colors"
                  />
                </label>
              )}

              <label className="block space-y-2">
                <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">
                  Questions — {numQuestions}
                </span>
                <input
                  type="range"
                  min={3}
                  max={15}
                  value={numQuestions}
                  onChange={e => setNumQuestions(Number(e.target.value))}
                  className="w-full accent-rose-500"
                />
              </label>

              <label className="block space-y-1.5">
                <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">Focus (optional)</span>
                <input
                  value={focus}
                  onChange={e => setFocus(e.target.value)}
                  placeholder="e.g. emphasize calculations, no spoilers past chapter 3…"
                  className="w-full rounded-lg border border-white/[0.09] bg-black/25 px-3 py-2 text-sm text-white/80 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-rose-500/40 focus:border-rose-500/30 transition-colors"
                />
              </label>

              {/* Document upload (optional) */}
              <div className="space-y-1.5">
                <span className="text-[10px] uppercase tracking-widest font-semibold text-white/30">
                  Source document <span className="normal-case font-normal text-white/20">(optional — quiz will be based on its content)</span>
                </span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.txt,.md"
                  className="hidden"
                  onChange={e => { const f = e.target.files?.[0]; if (f) void handleDocUpload(f) }}
                />
                {docContext ? (
                  <div className="flex items-center gap-2 rounded-lg border border-rose-500/20 bg-rose-500/[0.06] px-3 py-2">
                    <FileText className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span className="text-xs text-white/65 truncate flex-1">{docContextFilename}</span>
                    <span className="text-[10px] text-white/30 shrink-0">{Math.round((docContext.length / 1000))}k chars</span>
                    <button
                      type="button"
                      onClick={() => { setDocContext(null); setDocContextFilename(null); if (fileInputRef.current) fileInputRef.current.value = "" }}
                      className="text-white/30 hover:text-white/70 transition-colors"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    disabled={loadingContext}
                    onClick={() => fileInputRef.current?.click()}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-white/[0.12] hover:border-rose-500/30 hover:bg-rose-500/[0.04] text-white/35 hover:text-white/65 text-xs transition-all disabled:opacity-40 disabled:pointer-events-none"
                  >
                    {loadingContext ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                    {loadingContext ? "Extracting text…" : "Upload PDF or TXT"}
                  </button>
                )}
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  disabled={generating}
                  onClick={() => void handleGenerate()}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all",
                    "bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white",
                    "shadow-[0_0_20px_oklch(0.65_0.19_15_/_0.25)] hover:shadow-[0_0_28px_oklch(0.65_0.19_15_/_0.35)]",
                    "disabled:opacity-40 disabled:pointer-events-none",
                  )}
                >
                  {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {generating ? "Generating…" : "Generate lesson & questions"}
                </button>
                {quizBundle && (
                  <button
                    type="button"
                    onClick={() => { setQuizBundle(null); resetAttempt() }}
                    className="px-3 py-2.5 rounded-xl text-xs text-white/35 hover:text-white/65 border border-white/[0.08] hover:bg-white/[0.04] transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
            </section>

            {/* Error */}
            {error && (
              <div className="rounded-xl border border-red-500/25 bg-red-950/25 px-4 py-3 text-sm text-red-300/90">
                {error}
              </div>
            )}

            {/* Lesson content */}
            {quizBundle && (
              <>
                <section className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 space-y-3">
                  <h2 className="text-sm font-semibold text-white/85">{quizBundle.title}</h2>
                  <div className="text-sm text-white/60 leading-relaxed whitespace-pre-wrap">{quizBundle.lesson}</div>
                </section>

                <section className="space-y-3.5">
                  <h2 className="text-sm font-semibold text-white/75 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-rose-400" />
                    Your answers
                  </h2>
                  {quizBundle.questions.map((q, idx) => (
                    <div
                      key={q.id}
                      className="rounded-xl border border-white/[0.07] bg-black/20 p-4 space-y-3"
                    >
                      <div className="flex items-center gap-2">
                        <p className="text-[10px] text-rose-400/60 font-bold uppercase tracking-widest">Q{idx + 1}</p>
                        <TierBadge tier={q.tier} />
                      </div>
                      <p className="text-sm text-white/80 leading-relaxed whitespace-pre-wrap">{q.question}</p>
                      {q.type === "multiple_choice" && q.options && q.options.length > 0 ? (
                        <div className="space-y-2">
                          {q.options.map((opt, i) => (
                            <label
                              key={i}
                              className={cn(
                                "flex items-center gap-2.5 rounded-lg border px-3 py-2.5 cursor-pointer transition-all",
                                answers[q.id] === String(i)
                                  ? "border-rose-500/45 bg-rose-500/10 text-white/90"
                                  : "border-white/[0.06] hover:border-white/15 hover:bg-white/[0.02]",
                              )}
                            >
                              <input
                                type="radio"
                                name={`mcq-${q.id}`}
                                checked={answers[q.id] === String(i)}
                                onChange={() => setAnswers(prev => ({ ...prev, [q.id]: String(i) }))}
                                className="accent-rose-500"
                              />
                              <span className="text-sm">{opt}</span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <textarea
                          value={answers[q.id] ?? ""}
                          onChange={e => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                          rows={3}
                          placeholder="Type your answer…"
                          className="w-full rounded-lg border border-white/[0.09] bg-black/30 px-3 py-2 text-sm text-white/85 placeholder:text-white/20 focus:outline-none focus:ring-1 focus:ring-rose-500/35 transition-colors"
                        />
                      )}
                    </div>
                  ))}
                </section>

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={grading}
                    onClick={() => void handleGrade()}
                    className={cn(
                      "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-all",
                      "bg-fuchsia-700 hover:bg-fuchsia-600 active:scale-[0.98] text-white",
                      "shadow-[0_0_20px_oklch(0.60_0.20_330_/_0.25)]",
                      "disabled:opacity-40 disabled:pointer-events-none",
                    )}
                  >
                    {grading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trophy className="w-4 h-4" />}
                    {grading ? "Grading…" : "Submit for grading"}
                  </button>
                  <button
                    type="button"
                    onClick={resetAttempt}
                    className="px-3 py-2.5 rounded-xl text-xs text-white/35 hover:text-white/65 border border-white/[0.08] hover:bg-white/[0.04] transition-colors"
                  >
                    Reset answers
                  </button>
                </div>
              </>
            )}

            {/* Grade results */}
            {grade && quizBundle && (
              <section className="rounded-2xl border border-white/[0.08] bg-white/[0.02] p-5 space-y-4">
                {/* Score header */}
                <div className="flex items-center gap-4">
                  <ScoreBadge percent={grade.percent} size="md" />
                  <div>
                    <p className="text-sm font-semibold text-white/90">Results</p>
                    <p className="text-xs text-white/40 mt-0.5">
                      {grade.earned} / {grade.total_points} points
                    </p>
                  </div>
                </div>

                {/* Per-question breakdown */}
                <div className="space-y-2">
                  {grade.results.map(r => {
                    const q = quizBundle.questions.find(q => q.id === r.id)
                    const isCorrect = r.score >= r.max
                    const userAnswerIdx = answers[r.id]
                    const userAnswerText = q?.options && userAnswerIdx !== undefined
                      ? q.options[Number(userAnswerIdx)]
                      : (answers[r.id] || "—")
                    const correctText = q?.options && r.correct_index != null
                      ? q.options[r.correct_index]
                      : null

                    return (
                      <div
                        key={r.id}
                        className={cn(
                          "rounded-xl border p-3.5 space-y-2 text-sm",
                          isCorrect
                            ? "border-emerald-500/20 bg-emerald-500/[0.04]"
                            : "border-red-500/20 bg-red-500/[0.04]"
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 space-y-1.5">
                            {q?.tier && <TierBadge tier={q.tier} />}
                            <p className="text-white/75 leading-snug whitespace-pre-wrap">{r.question}</p>
                          </div>
                          <span className={cn(
                            "shrink-0 text-xs font-bold tabular-nums px-2 py-0.5 rounded-full",
                            isCorrect ? "text-emerald-300 bg-emerald-500/15" : "text-red-300 bg-red-500/15"
                          )}>
                            {r.score}/{r.max}
                          </span>
                        </div>

                        <div className="space-y-1 text-xs pl-0.5">
                          <p className={cn("flex items-start gap-1.5", isCorrect ? "text-emerald-300/80" : "text-red-300/80")}>
                            {isCorrect
                              ? <CheckCircle2 className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                              : <XCircle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                            }
                            <span>Your answer: <span className="text-white/60">{userAnswerText}</span></span>
                          </p>

                          {!isCorrect && correctText && (
                            <p className="flex items-start gap-1.5 text-emerald-300/80 pl-5">
                              <span>Correct answer: <span className="font-medium">{correctText}</span></span>
                            </p>
                          )}

                          {!isCorrect && r.type === "short_answer" && r.detail && r.detail !== "Incorrect option." && (
                            <p className="text-white/35 pl-5">{r.detail}</p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>

                {/* Feedback */}
                {(grade.feedback.summary || grade.feedback.encouragement) && (
                  <div className="space-y-3 text-sm text-white/60 leading-relaxed border-t border-white/[0.06] pt-4">
                    {grade.feedback.summary && <p>{grade.feedback.summary}</p>}
                    {grade.feedback.strengths.length > 0 && (
                      <div>
                        <p className="text-[10px] uppercase tracking-widest text-emerald-400/80 font-bold mb-1.5">Strengths</p>
                        <ul className="list-disc pl-5 space-y-1">
                          {grade.feedback.strengths.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      </div>
                    )}
                    {grade.feedback.improve.length > 0 && (
                      <div>
                        <p className="text-[10px] uppercase tracking-widest text-amber-400/80 font-bold mb-1.5">To improve</p>
                        <ul className="list-disc pl-5 space-y-1">
                          {grade.feedback.improve.map((s, i) => <li key={i}>{s}</li>)}
                        </ul>
                      </div>
                    )}
                    {grade.feedback.encouragement && (
                      <p className="text-white/40 italic pt-1">{grade.feedback.encouragement}</p>
                    )}
                  </div>
                )}
              </section>
            )}

          </div>
        </div>
      </div>
    </AppShell>
  )
}
