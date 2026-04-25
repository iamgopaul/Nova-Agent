"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { BookOpen, CheckCircle2, Loader2, Sparkles, Trophy } from "lucide-react"
import { AppShell } from "@/components/app-shell"
import { cn } from "@/lib/utils"

type Difficulty = "elementary" | "middle" | "high" | "college"
type Mode = "quiz" | "exam"

type PublicQuestion = {
  id: string
  type: "multiple_choice" | "short_answer"
  question: string
  options?: string[]
}

type GenerateResponse = {
  quiz_id: string
  title: string
  lesson: string
  questions: PublicQuestion[]
  grading: unknown
}

type GradeResult = {
  percent: number
  earned: number
  total_points: number
  results: Array<{
    id: string
    type: string
    question: string
    score: number
    max: number
    detail: string
    correct_index?: number | null
  }>
  feedback: {
    summary: string
    strengths: string[]
    improve: string[]
    encouragement: string
  }
}

export default function EducationPage() {
  const router = useRouter()
  const [userReady, setUserReady] = useState(false)

  const [topic, setTopic] = useState("")
  const [mode, setMode] = useState<Mode>("quiz")
  const [difficulty, setDifficulty] = useState<Difficulty>("high")
  const [numQuestions, setNumQuestions] = useState(6)
  const [focus, setFocus] = useState("")

  const [generating, setGenerating] = useState(false)
  const [grading, setGrading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [quizBundle, setQuizBundle] = useState<GenerateResponse | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [grade, setGrade] = useState<GradeResult | null>(null)

  useEffect(() => {
    fetch("/api/auth/me")
      .then(r => {
        if (!r.ok) {
          router.replace("/login")
          return
        }
        setUserReady(true)
      })
      .catch(() => router.replace("/login"))
  }, [router])

  const resetAttempt = useCallback(() => {
    setAnswers({})
    setGrade(null)
    setError(null)
  }, [])

  const handleGenerate = async () => {
    const t = topic.trim()
    if (t.length < 2) {
      setError("Enter a topic (at least a few words).")
      return
    }
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
          topic: t,
          mode,
          difficulty,
          num_questions: numQuestions,
          focus: focus.trim() || null,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        setError(typeof data?.detail === "string" ? data.detail : "Could not generate quiz.")
        return
      }
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
      if (!res.ok) {
        setError(typeof data?.detail === "string" ? data.detail : "Could not grade submission.")
        return
      }
      setGrade(data as GradeResult)
    } catch {
      setError("Network error while grading.")
    } finally {
      setGrading(false)
    }
  }

  if (!userReady) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#0a0a10] text-white/30 text-sm">
        Loading…
      </div>
    )
  }

  return (
    <AppShell title="Education" titleColor="text-rose-400">
      <div className="relative flex flex-col h-full min-h-0 overflow-hidden">
        <div className="pointer-events-none absolute inset-0 z-0">
          <div className="absolute inset-0 bg-gradient-to-br from-rose-500/[0.07] via-fuchsia-500/[0.04] to-transparent" />
        </div>

        <div className="relative z-[1] flex flex-col flex-1 min-h-0 overflow-y-auto scrollbar-thin">
          <div className="max-w-3xl mx-auto w-full px-5 py-6 space-y-8 pb-24">
            <header className="space-y-2">
              <div className="flex items-center gap-2 text-rose-400/90">
                <BookOpen className="w-5 h-5" />
                <span className="text-xs font-bold uppercase tracking-widest">Learn</span>
              </div>
              <h1 className="text-xl font-semibold text-white/90">Nova Education</h1>
              <p className="text-sm text-white/45 leading-relaxed">
                Nova writes a short lesson, builds a quiz or exam from your topic, then scores your answers and
                explains what to review next — all on your machine via Ollama.
              </p>
            </header>

            {/* Builder */}
            <section className="rounded-2xl border border-white/[0.08] bg-[#0d0d14]/80 p-5 space-y-4">
              <div className="flex items-center gap-2 text-white/70 text-sm font-medium">
                <Sparkles className="w-4 h-4 text-rose-400" />
                Create a lesson & assessment
              </div>
              <label className="block space-y-1.5">
                <span className="text-[11px] uppercase tracking-wide text-white/35">Topic</span>
                <textarea
                  value={topic}
                  onChange={e => setTopic(e.target.value)}
                  rows={3}
                  placeholder="e.g. Photosynthesis, World War II timelines, Python list comprehensions…"
                  className="w-full rounded-xl border border-white/[0.1] bg-black/30 px-3 py-2.5 text-sm text-white/85 placeholder:text-white/25 focus:outline-none focus:ring-1 focus:ring-rose-500/40 resize-y min-h-[88px]"
                />
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className="space-y-1.5">
                  <span className="text-[11px] uppercase tracking-wide text-white/35">Format</span>
                  <select
                    value={mode}
                    onChange={e => setMode(e.target.value as Mode)}
                    className="w-full rounded-lg border border-white/[0.1] bg-black/30 px-3 py-2 text-sm text-white/80"
                  >
                    <option value="quiz">Quiz (shorter)</option>
                    <option value="exam">Exam (formal)</option>
                  </select>
                </label>
                <label className="space-y-1.5">
                  <span className="text-[11px] uppercase tracking-wide text-white/35">Level</span>
                  <select
                    value={difficulty}
                    onChange={e => setDifficulty(e.target.value as Difficulty)}
                    className="w-full rounded-lg border border-white/[0.1] bg-black/30 px-3 py-2 text-sm text-white/80"
                  >
                    <option value="elementary">Elementary</option>
                    <option value="middle">Middle school</option>
                    <option value="high">High school</option>
                    <option value="college">College</option>
                  </select>
                </label>
              </div>
              <label className="block space-y-2">
                <span className="text-[11px] uppercase tracking-wide text-white/35">
                  Number of questions ({numQuestions})
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
                <span className="text-[11px] uppercase tracking-wide text-white/35">Focus (optional)</span>
                <input
                  value={focus}
                  onChange={e => setFocus(e.target.value)}
                  placeholder="e.g. emphasize calculations, no spoilers past chapter 3…"
                  className="w-full rounded-lg border border-white/[0.1] bg-black/30 px-3 py-2 text-sm text-white/80 placeholder:text-white/25"
                />
              </label>
              <div className="flex flex-wrap gap-2 pt-1">
                <button
                  type="button"
                  disabled={generating}
                  onClick={() => void handleGenerate()}
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold transition-colors",
                    "bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-40 disabled:pointer-events-none",
                  )}
                >
                  {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                  {generating ? "Generating…" : "Generate lesson & questions"}
                </button>
                {quizBundle && (
                  <button
                    type="button"
                    onClick={() => {
                      setQuizBundle(null)
                      resetAttempt()
                    }}
                    className="px-3 py-2.5 rounded-xl text-xs text-white/40 hover:text-white/70 border border-white/[0.08] hover:bg-white/[0.04]"
                  >
                    Clear
                  </button>
                )}
              </div>
            </section>

            {error && (
              <div className="rounded-xl border border-red-500/25 bg-red-950/30 px-4 py-3 text-sm text-red-300">
                {error}
              </div>
            )}

            {quizBundle && (
              <>
                <section className="rounded-2xl border border-white/[0.08] bg-[#0d0d14]/80 p-5 space-y-3">
                  <h2 className="text-sm font-semibold text-white/80">{quizBundle.title}</h2>
                  <div className="text-sm text-white/65 leading-relaxed whitespace-pre-wrap">{quizBundle.lesson}</div>
                </section>

                <section className="space-y-4">
                  <h2 className="text-sm font-semibold text-white/80 flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-rose-400" />
                    Your answers
                  </h2>
                  {quizBundle.questions.map((q, idx) => (
                    <div
                      key={q.id}
                      className="rounded-xl border border-white/[0.07] bg-[#0a0a12]/90 p-4 space-y-3"
                    >
                      <p className="text-[11px] text-white/30 font-medium">Question {idx + 1}</p>
                      <p className="text-sm text-white/80 leading-relaxed">{q.question}</p>
                      {q.type === "multiple_choice" && q.options && q.options.length > 0 ? (
                        <div className="space-y-2">
                          {q.options.map((opt, i) => (
                            <label
                              key={i}
                              className={cn(
                                "flex items-center gap-2.5 rounded-lg border px-3 py-2 cursor-pointer transition-colors",
                                answers[q.id] === String(i)
                                  ? "border-rose-500/40 bg-rose-500/10"
                                  : "border-white/[0.06] hover:border-white/15",
                              )}
                            >
                              <input
                                type="radio"
                                name={`mcq-${q.id}`}
                                checked={answers[q.id] === String(i)}
                                onChange={() => setAnswers(prev => ({ ...prev, [q.id]: String(i) }))}
                                className="accent-rose-500"
                              />
                              <span className="text-sm text-white/75">{opt}</span>
                            </label>
                          ))}
                        </div>
                      ) : (
                        <textarea
                          value={answers[q.id] ?? ""}
                          onChange={e => setAnswers(prev => ({ ...prev, [q.id]: e.target.value }))}
                          rows={3}
                          placeholder="Type your answer…"
                          className="w-full rounded-lg border border-white/[0.1] bg-black/40 px-3 py-2 text-sm text-white/85 placeholder:text-white/25 focus:outline-none focus:ring-1 focus:ring-rose-500/35"
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
                      "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold",
                      "bg-fuchsia-700 hover:bg-fuchsia-600 text-white disabled:opacity-40",
                    )}
                  >
                    {grading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trophy className="w-4 h-4" />}
                    {grading ? "Grading…" : "Submit for grading"}
                  </button>
                  <button
                    type="button"
                    onClick={resetAttempt}
                    className="px-3 py-2.5 rounded-xl text-xs text-white/40 hover:text-white/70 border border-white/[0.08]"
                  >
                    Reset answers
                  </button>
                </div>
              </>
            )}

            {grade && (
              <section className="rounded-2xl border border-emerald-500/20 bg-emerald-950/10 p-5 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-14 h-14 rounded-2xl bg-emerald-500/15 flex items-center justify-center text-emerald-300 text-xl font-bold border border-emerald-500/30">
                    {grade.percent}%
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-white/90">Results</p>
                    <p className="text-xs text-white/40">
                      {grade.earned} / {grade.total_points} points (automated + model feedback)
                    </p>
                  </div>
                </div>
                <ul className="space-y-2 text-sm">
                  {grade.results.map(r => (
                    <li
                      key={r.id}
                      className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-1 rounded-lg bg-black/25 px-3 py-2 border border-white/[0.05]"
                    >
                      <span className="text-white/55 line-clamp-2">{r.question}</span>
                      <span className="text-emerald-300/90 shrink-0 text-xs font-medium">
                        {r.score} / {r.max} — {r.detail}
                      </span>
                    </li>
                  ))}
                </ul>
                {(grade.feedback.summary || grade.feedback.encouragement) && (
                  <div className="space-y-2 text-sm text-white/70 leading-relaxed border-t border-white/[0.06] pt-4">
                    {grade.feedback.summary && <p>{grade.feedback.summary}</p>}
                    {grade.feedback.strengths.length > 0 && (
                      <div>
                        <p className="text-[11px] uppercase text-emerald-400/80 mb-1">Strengths</p>
                        <ul className="list-disc pl-5 space-y-0.5">
                          {grade.feedback.strengths.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {grade.feedback.improve.length > 0 && (
                      <div>
                        <p className="text-[11px] uppercase text-amber-400/80 mb-1">To improve</p>
                        <ul className="list-disc pl-5 space-y-0.5">
                          {grade.feedback.improve.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {grade.feedback.encouragement && (
                      <p className="text-white/50 italic pt-1">{grade.feedback.encouragement}</p>
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
