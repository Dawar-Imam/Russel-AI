import { Room, RoomEvent, Track } from 'livekit-client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Button from '../components/Button'
import botImage from '../utils/bot1.png'
import '../css/InterviewRoom.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const RING_RADIUS = 62
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS

interface QuestionItem {
  iq_id: string
  question_text: string
}

interface GradedAnswer {
  question_text: string
  candidate_answer: string
  score: number
  notes: string
}

interface Results {
  overall_score: number
  total_graded: number
  graded_answers: GradedAnswer[]
}

interface ConversationMessage {
  role: 'user' | 'assistant'
  text: string
  streaming?: boolean
  fullText?: string
}

type Phase =
  | 'loading'
  | 'voice-connecting'
  | 'voice-active'
  | 'answering'
  | 'submitting'
  | 'results'
  | 'error'

function fmtTime(secs: number): string {
  const m = Math.floor(secs / 60).toString().padStart(2, '0')
  const s = (secs % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--color-primary)'
  if (score >= 5) return 'var(--color-navy-text)'
  return '#e05c5c'
}

function InterviewRoom() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const [phase, setPhase] = useState<Phase>('loading')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [timer, setTimer] = useState(1800)
  const [totalTimer, setTotalTimer] = useState(1800)
  const [results, setResults] = useState<Results | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showMandatoryWarn, setShowMandatoryWarn] = useState(false)
  const [interviewType, setInterviewType] = useState('')
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [audioBlocked, setAudioBlocked] = useState(false)

  const answersRef = useRef<string[]>([])
  const questionsRef = useRef<QuestionItem[]>([])
  const isSubmittingRef = useRef(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const warnTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isOralRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const roomRef = useRef<Room | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const isOral = interviewType.toLowerCase() === 'oral' || interviewType.toLowerCase().includes('voice')

  useEffect(() => { answersRef.current = answers }, [answers])
  useEffect(() => { questionsRef.current = questions }, [questions])
  useEffect(() => { setShowMandatoryWarn(false) }, [answers])
  useEffect(() => {
    isOralRef.current =
      interviewType.toLowerCase() === 'oral' || interviewType.toLowerCase().includes('voice')
  }, [interviewType])

  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  // Typewriter effect: advance streaming AI messages 3 chars per 18ms
  useEffect(() => {
    const last = messages[messages.length - 1]
    if (!last?.streaming || !last.fullText) return
    if (last.text.length >= last.fullText.length) {
      setMessages((prev) =>
        prev.map((m, i) => (i === prev.length - 1 ? { ...m, streaming: false } : m))
      )
      return
    }
    const t = setTimeout(() => {
      setMessages((prev) =>
        prev.map((m, i) =>
          i === prev.length - 1 && m.streaming
            ? { ...m, text: m.fullText!.slice(0, m.text.length + 3) }
            : m
        )
      )
    }, 18)
    return () => clearTimeout(t)
  }, [messages])

  // Cleanup LiveKit room and SSE on unmount
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
      eventSourceRef.current?.close()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [])

  // ---------------------------------------------------------------------------
  // Written interview submit
  // ---------------------------------------------------------------------------

  const doSubmit = useCallback(async () => {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    if (timerRef.current) clearInterval(timerRef.current)
    setPhase('submitting')

    try {
      const body = {
        fetch_from_db: false,
        answers: questionsRef.current.map((q, i) => ({
          iq_id: q.iq_id,
          candidate_answer: answersRef.current[i] ?? '',
        })),
      }
      const res = await fetch(`${API_BASE}/api/interviews/${interviewId}/score-answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error((d as { detail?: string }).detail ?? `Server error ${res.status}`)
      }
      const data: Results = await res.json()
      setResults(data)
      setPhase('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
      setPhase('error')
    }
  }, [interviewId])

  // ---------------------------------------------------------------------------
  // Voice interview helpers
  // ---------------------------------------------------------------------------

  const scoreFromDb = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/interviews/${interviewId}/score-answers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fetch_from_db: true, answers: [] }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error((d as { detail?: string }).detail ?? `Server error ${res.status}`)
      }
      const data: Results = await res.json()
      setResults(data)
      setPhase('results')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scoring failed')
      setPhase('error')
    }
  }, [interviewId])

  const startVoiceInterview = useCallback(async () => {
    setPhase('voice-connecting')
    try {
      // Start voice interview — backend creates room and launches agent
      const res = await fetch(`${API_BASE}/api/interviews/${interviewId}/voice-interview`, {
        method: 'POST',
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        throw new Error((d as { detail?: string }).detail ?? `Server error ${res.status}`)
      }
      const { url, token } = (await res.json()) as { url: string; token: string }

      // Connect to LiveKit room
      const lkRoom = new Room()
      roomRef.current = lkRoom

      // Attach agent audio tracks to the DOM so the browser can play them
      lkRoom.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach() as HTMLAudioElement
          document.body.appendChild(el)
        }
      })
      lkRoom.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((el) => el.remove())
      })

      // Handle browser autoplay policy — show Enable Audio button when blocked
      lkRoom.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        setAudioBlocked(!lkRoom.canPlaybackAudio)
      })

      // Receive live transcript messages from the agent via data channel
      lkRoom.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(payload)) as { role: string; text: string }
          if (!msg.role || !msg.text) return
          if (msg.role === 'user') {
            // Append consecutive user chunks into the same bubble
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'user') {
                return prev.map((m, i) =>
                  i === prev.length - 1 ? { ...m, text: m.text + ' ' + msg.text } : m
                )
              }
              return [...prev, { role: 'user' as const, text: msg.text }]
            })
          } else {
            // AI message: start empty and stream it in via typewriter effect
            setMessages((prev) => [
              ...prev,
              { role: 'assistant' as const, text: '', streaming: true, fullText: msg.text },
            ])
          }
        } catch {
          // ignore malformed data
        }
      })

      // When room disconnects, wait for backend processing then score
      lkRoom.on(RoomEvent.Disconnected, () => {
        if (timerRef.current) clearInterval(timerRef.current)
        setPhase('submitting')

        const es = new EventSource(
          `${API_BASE}/api/interviews/${interviewId}/status-stream`,
        )
        eventSourceRef.current = es

        es.addEventListener('done', () => {
          es.close()
          eventSourceRef.current = null
          void scoreFromDb()
        })

        es.addEventListener('timeout', () => {
          es.close()
          eventSourceRef.current = null
          setError('Interview processing timed out. Please try again.')
          setPhase('error')
        })

        es.onerror = () => {
          es.close()
          eventSourceRef.current = null
          setError('Connection error while processing your interview.')
          setPhase('error')
        }
      })

      await lkRoom.connect(url, token)
      await lkRoom.localParticipant.setMicrophoneEnabled(true)
      // Check audio playback status immediately after connect
      setAudioBlocked(!lkRoom.canPlaybackAudio)
      setPhase('voice-active')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start voice interview')
      setPhase('error')
    }
  }, [interviewId, scoreFromDb])

  // ---------------------------------------------------------------------------
  // Load questions (always first step)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (!interviewId) return
    const controller = new AbortController()

    fetch(`${API_BASE}/api/interviews/${interviewId}/generate-questions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ return_questions: true }),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok)
          return res.json().then((d) => {
            throw new Error((d as { detail?: string }).detail ?? `Error ${res.status}`)
          })
        return res.json()
      })
      .then((data) => {
        if (controller.signal.aborted) return
        const type = (data.interview_type ?? '') as string
        setInterviewType(type)
        const oral =
          type.toLowerCase() === 'oral' || type.toLowerCase().includes('voice')
        isOralRef.current = oral
        setTimer(data.timer_seconds)
        setTotalTimer(data.timer_seconds)

        if (oral) {
          void startVoiceInterview()
        } else {
          setQuestions(data.questions)
          setAnswers(new Array((data.questions as QuestionItem[]).length).fill(''))
          setPhase('answering')
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        setError(err instanceof Error ? err.message : 'Failed to load questions')
        setPhase('error')
      })

    return () => controller.abort()
  // startVoiceInterview is stable; interviewId is the only real dep here
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interviewId])

  // ---------------------------------------------------------------------------
  // Written interview timer
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (phase !== 'answering') return
    timerRef.current = setInterval(() => {
      setTimer((prev) => {
        if (prev <= 1) {
          doSubmit()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [phase, doSubmit])

  // ---------------------------------------------------------------------------
  // Voice interview timer (auto-disconnect when time's up)
  // ---------------------------------------------------------------------------

  useEffect(() => {
    if (phase !== 'voice-active') return
    timerRef.current = setInterval(() => {
      setTimer((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current)
          roomRef.current?.disconnect()
          return 0
        }
        return prev - 1
      })
    }, 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [phase])

  // ---------------------------------------------------------------------------
  // Written submit handlers
  // ---------------------------------------------------------------------------

  const handleSubmitClick = useCallback(() => {
    if (answers.filter((a) => a.trim().length > 0).length < questions.length) {
      setShowMandatoryWarn(false)
      requestAnimationFrame(() => {
        setShowMandatoryWarn(true)
        if (warnTimerRef.current) clearTimeout(warnTimerRef.current)
        warnTimerRef.current = setTimeout(() => setShowMandatoryWarn(false), 6000)
      })
      return
    }
    void doSubmit()
  }, [answers, questions.length, doSubmit])

  // ---------------------------------------------------------------------------
  // Derived display values
  // ---------------------------------------------------------------------------

  const answeredCount = answers.filter((a) => a.trim().length > 0).length
  const isUrgent = timer > 0 && timer <= Math.floor(totalTimer / 5)
  const ringProgress = totalTimer > 0 ? timer / totalTimer : 0
  const ringOffset = RING_CIRCUMFERENCE * (1 - ringProgress)

  const timerCircle = (
    <div className={`ir-timer-circle${isUrgent ? ' ir-timer-circle--urgent' : ''}`}>
      <svg className="ir-progress-ring" viewBox="0 0 140 140" aria-hidden="true">
        <circle className="ir-ring-track" cx="70" cy="70" r={RING_RADIUS} fill="none" strokeWidth="6" />
        <circle
          className="ir-ring-progress"
          cx="70" cy="70" r={RING_RADIUS}
          fill="none" strokeWidth="6" strokeLinecap="round"
          strokeDasharray={RING_CIRCUMFERENCE}
          strokeDashoffset={ringOffset}
          transform="rotate(-90 70 70)"
        />
      </svg>
      <span className="ir-timer-text">{fmtTime(timer)}</span>
    </div>
  )

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <main className="ir-page">

      {/* ── Loading: generating questions ── */}
      {phase === 'loading' && (
        <div className="ir-center">
          <BackButton />
          <div className="ir-spinner" />
          <p className="ir-status-text">Generating your interview questions…</p>
          <p className="ir-status-sub">This may take a moment</p>
        </div>
      )}

      {/* ── Loading: connecting to voice room ── */}
      {phase === 'voice-connecting' && (
        <div className="ir-center">
          <div className="ir-spinner" />
          <p className="ir-status-text">Starting voice interview…</p>
          <p className="ir-status-sub">Connecting to interview room</p>
        </div>
      )}

      {/* ── Answering: ORAL / voice layout ── */}
      {phase === 'voice-active' && (
        <div className="ir-answering-root">
          <div className="ir-back-float">
            <BackButton />
          </div>
          <h1 className="ir-heading">Interview Room</h1>

          <div className="ir-oral-body">
            {/* Left — live transcript */}
            <div className="ir-conversation-panel">
              <div className="ir-conversation-header">Live Transcript</div>
              <div className="ir-conversation-messages">
                {messages.length === 0 ? (
                  <p className="ir-conversation-empty">Listening…</p>
                ) : (
                  messages.map((msg, i) => (
                    <div key={i} className={`ir-message ir-message--${msg.role}`}>
                      <span className="ir-message-label">
                        {msg.role === 'assistant' ? 'Russel' : 'You'}
                      </span>
                      <div className="ir-message-bubble">
                        {msg.text}
                        {msg.streaming && <span className="ir-cursor">▋</span>}
                      </div>
                    </div>
                  ))
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Right — bot, timer, end button */}
            <div className="ir-bot-area">
              <img src={botImage} alt="AI Interviewer" className="ir-bot-image" />
              {audioBlocked && (
                <Button
                  variant="primary"
                  onClick={() => { void roomRef.current?.startAudio() }}
                >
                  Enable Audio
                </Button>
              )}
              {timerCircle}
              <Button
                variant="secondary"
                className="ir-end-interview-btn"
                onClick={() => roomRef.current?.disconnect()}
              >
                End Interview
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Answering: WRITTEN layout ── */}
      {phase === 'answering' && !isOral && (
        <div className="ir-answering-root">
          <div className="ir-back-float">
            <BackButton />
          </div>

          <h1 className="ir-heading">Interview Room</h1>

          <div className="ir-answering-body">
            <div className="ir-form-container">
              <div className="ir-questions-list">
                {questions.map((q, i) => (
                  <div key={i} className="ir-question-card">
                    <div className="ir-question-header">
                      <span className="ir-question-num">Q{i + 1}</span>
                      <p className="ir-question-text">{q.question_text}</p>
                    </div>
                    <textarea
                      className="ir-answer-textarea"
                      placeholder="Type your answer here…"
                      value={answers[i] ?? ''}
                      rows={5}
                      onChange={(e) => {
                        const updated = [...answers]
                        updated[i] = e.target.value
                        setAnswers(updated)
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="ir-bottom-bar">
            <div className={`ir-answered-badge${isUrgent ? ' ir-answered-badge--urgent' : ''}`}>
              <svg width="13" height="14" viewBox="0 0 13 14" fill="none" aria-hidden="true" className="ir-badge-icon">
                <rect x="1" y="2" width="11" height="11.5" rx="1.5" stroke="currentColor" strokeWidth="1.3"/>
                <path d="M4 0.5 C4 0.5 4.5 0.5 5 0.5 H8 C8.5 0.5 9 0.5 9 1.5 V2.5 H4 V1.5 C4 0.9 4 0.5 4 0.5Z" fill="currentColor"/>
                <line x1="3.5" y1="5.5" x2="9.5" y2="5.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                <line x1="3.5" y1="8" x2="9.5" y2="8" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
                <line x1="3.5" y1="10.5" x2="7" y2="10.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
              </svg>
              {answeredCount}&thinsp;/&thinsp;{questions.length} answered
            </div>

            {timerCircle}

            <div className="ir-bottom-submit">
              {showMandatoryWarn && (
                <p className="ir-submit-warn">All questions are mandatory to answer before submission.</p>
              )}
              <Button variant="primary" onClick={handleSubmitClick}>
                Submit Answers
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Processing / Scoring ── */}
      {phase === 'submitting' && (
        <div className="ir-center">
          <div className="ir-spinner" />
          <p className="ir-status-text">
            {isOral ? 'Processing your interview…' : 'Scoring your answers…'}
          </p>
          <p className="ir-status-sub">
            {isOral
              ? 'Extracting and scoring your answers — this may take a moment'
              : 'AI is evaluating your responses'}
          </p>
        </div>
      )}

      {/* ── Error ── */}
      {phase === 'error' && (
        <div className="ir-center">
          <BackButton />
          <p className="ir-error-text">{error}</p>
        </div>
      )}

      {/* ── Results ── */}
      {phase === 'results' && results && (
        <div className="ir-answering-root">
          <div className="ir-back-float">
            <BackButton />
          </div>

          <h1 className="ir-heading">Interview Complete</h1>

          <div className="ir-answering-body ir-answering-body--no-bar">
            <div className="ir-form-container">
              <div className="ir-overall-card">
                <span className="ir-overall-label">Overall Score</span>
                <div className="ir-overall-score-row">
                  <span className="ir-overall-score">{results.overall_score.toFixed(1)}</span>
                  <span className="ir-overall-out">/ 10</span>
                </div>
                <span className="ir-overall-sub">{results.total_graded} questions graded</span>
              </div>

              <div className="ir-graded-list">
                {results.graded_answers.map((ga, i) => (
                  <div key={i} className="ir-graded-card">
                    <div className="ir-graded-header">
                      <div className="ir-graded-num-wrap">
                        <span className="ir-graded-num">Q{i + 1}</span>
                        <p className="ir-graded-question">{ga.question_text}</p>
                      </div>
                      <span
                        className="ir-graded-score-badge"
                        style={{ color: scoreColor(ga.score) }}
                      >
                        {ga.score}<span className="ir-graded-score-denom">/10</span>
                      </span>
                    </div>

                    <div className="ir-graded-section">
                      <span className="ir-graded-section-label">Your Answer</span>
                      <p className="ir-graded-answer">
                        {ga.candidate_answer || '(no answer provided)'}
                      </p>
                    </div>

                    {ga.notes && (
                      <div className="ir-graded-section ir-graded-section--feedback">
                        <span className="ir-graded-section-label">Feedback</span>
                        <p className="ir-graded-notes">{ga.notes}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

export default InterviewRoom
