import { Room, RoomEvent, Track } from 'livekit-client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Button from '../components/Button'
import Modal from '../components/Modal'
import botImageDark from '../utils/dark/bot1.png'
import botImageLight from '../utils/white/bot1.png'
import { useTheme } from '../utils/useTheme'
import '../css/InterviewRoom.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const RING_RADIUS = 62
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS
const MAX_SCORE = 10

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
  partial?: boolean  // true while user is still speaking (interim transcript)
  committedText?: string  // user only: finalized segments accumulated so far this turn
}

type Phase =
  | 'loading'
  | 'voice-connecting'
  | 'voice-active'
  | 'answering'
  | 'submitting'
  | 'results'
  | 'terminated'
  | 'already-completed'
  | 'error'

function fmtTime(secs: number): string {
  const m = Math.floor(secs / 60).toString().padStart(2, '0')
  const s = (secs % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--color-primary)'
  if (score >= 5) return 'var(--color-primary-dark)'
  return 'var(--color-text-primary)'
}

function InterviewRoom() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const theme = useTheme()
  const botImage = theme === 'light' ? botImageLight : botImageDark
  const [phase, setPhase] = useState<Phase>('loading')
  const [questions, setQuestions] = useState<QuestionItem[]>([])
  const [answers, setAnswers] = useState<string[]>([])
  const [timer, setTimer] = useState(1800)
  const [totalTimer, setTotalTimer] = useState(1800)
  const [results, setResults] = useState<Results | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [showEndInterviewModal, setShowEndInterviewModal] = useState(false)
  const [interviewType, setInterviewType] = useState('')
  const [messages, setMessages] = useState<ConversationMessage[]>([])
  const [audioBlocked, setAudioBlocked] = useState(false)

  const [enableFailCases, setEnableFailCases] = useState(true)
  const [terminatedReason, setTerminatedReason] = useState<string | null>(null)

  const answersRef = useRef<string[]>([])
  const questionsRef = useRef<QuestionItem[]>([])
  const isSubmittingRef = useRef(false)
  const isTerminatedRef = useRef(false)
  const enableFailCasesRef = useRef(true)
  const phaseRef = useRef<Phase>('loading')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isOralRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const roomRef = useRef<Room | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const concludeFailedRef = useRef(false)

  const isOral = interviewType.toLowerCase().includes('oral') || interviewType.toLowerCase().includes('voice')

  useEffect(() => { answersRef.current = answers }, [answers])
  useEffect(() => { questionsRef.current = questions }, [questions])
  useEffect(() => { enableFailCasesRef.current = enableFailCases }, [enableFailCases])
  useEffect(() => { phaseRef.current = phase }, [phase])
  useEffect(() => {
    isOralRef.current =
      interviewType.toLowerCase().includes('oral') || interviewType.toLowerCase().includes('voice')
  }, [interviewType])

  useEffect(() => {
    if (messages.length > 0) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
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
  // Leave / cheat detection
  // ---------------------------------------------------------------------------

  const handleUserLeft = useCallback(async (reason?: string) => {
    if (isTerminatedRef.current) return
    isTerminatedRef.current = true
    if (timerRef.current) clearInterval(timerRef.current)
    eventSourceRef.current?.close()
    eventSourceRef.current = null
    roomRef.current?.disconnect()
    setTerminatedReason(reason ?? 'User left the interview, interview automatically closed.')
    setPhase('terminated')
    try {
      await fetch(`${API_BASE}/api/interviews/${interviewId}/report-leave`, { method: 'POST' })
    } catch { /* fire-and-forget */ }
  }, [interviewId])

  const handleEndInterviewClick = useCallback(() => {
    // Test mode: end the room normally (no auto-fail warning) so devs can iterate freely.
    if (!enableFailCasesRef.current) {
      roomRef.current?.disconnect()
      return
    }
    setShowEndInterviewModal(true)
  }, [])

  const handleConfirmEndInterview = useCallback(() => {
    setShowEndInterviewModal(false)
    void handleUserLeft('You ended the interview early — this round has been marked as failed.')
  }, [handleUserLeft])

  // Tab switch / window blur
  useEffect(() => {
    const onVisibility = () => {
      if (!enableFailCasesRef.current) return
      if (document.hidden && (phaseRef.current === 'answering' || phaseRef.current === 'voice-active')) {
        void handleUserLeft()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [handleUserLeft])

  // Page close / refresh / navigation
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!enableFailCasesRef.current) return
      if (phaseRef.current !== 'answering' && phaseRef.current !== 'voice-active') return
      e.preventDefault()
      e.returnValue = ''
      const blob = new Blob(['{}'], { type: 'application/json' })
      navigator.sendBeacon(`${API_BASE}/api/interviews/${interviewId}/report-leave`, blob)
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [interviewId])

  // ---------------------------------------------------------------------------
  // Written interview submit
  // ---------------------------------------------------------------------------

  const doSubmit = useCallback(async (triggeredByTimer = false) => {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    if (timerRef.current) clearInterval(timerRef.current)
    setPhase('submitting')

    try {
      const body = {
        fetch_from_db: false,
        test_mode: localStorage.getItem('russell_test_mode') === '1',
        event_type: triggeredByTimer ? 'timer_end' : 'submit',
        interview_type: 'written',
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
        body: JSON.stringify({
          fetch_from_db: true,
          answers: [],
          test_mode: localStorage.getItem('russell_test_mode') === '1',
          event_type: 'normal_completion',
          interview_type: 'oral',
        }),
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
      const testMode = localStorage.getItem('russell_test_mode') === '1'
      const res = await fetch(
        `${API_BASE}/api/interviews/${interviewId}/voice-interview?test_mode=${testMode}`,
        { method: 'POST' },
      )
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
          const msg = JSON.parse(new TextDecoder().decode(payload)) as { role: string; text?: string; event?: string; reason?: string; passed?: boolean }
          if (!msg.role) return

          // --- control events ---
          if (msg.role === 'control') {
            if (msg.event === 'interview_ended') {
              // Agent concluded the interview — make the candidate leave the room
              // so RoomEvent.Disconnected fires and triggers the processing/SSE flow.
              if (msg.passed === false) {
                concludeFailedRef.current = true
              }
              roomRef.current?.disconnect()
              return
            } else if (msg.event === 'terminated') {
              void handleUserLeft(msg.reason ?? undefined)
            } else if (msg.event === 'user_speaking') {
              // Create a partial bubble immediately so the user sees activity,
              // but only if the candidate isn't already mid-turn (same bubble continues).
              setMessages((prev) => {
                const last = prev[prev.length - 1]
                if (last?.role === 'user') return prev  // continuing same turn
                return [...prev, { role: 'user' as const, text: '', partial: true, committedText: '' }]
              })
            } else if (msg.event === 'interrupted') {
              // TTS stopped mid-speech — freeze the streaming bubble exactly where
              // it was cut off instead of leaving it marked "streaming" until the
              // next turn finalizes it out of order.
              setMessages((prev) => {
                const streamingIdx = prev.map(m => m.role === 'assistant' && m.streaming).lastIndexOf(true)
                if (streamingIdx === -1) return prev
                return prev.map((m, i) => (i === streamingIdx ? { ...m, streaming: false } : m))
              })
            }
            return
          }

          if (!msg.text) return

          if (msg.role === 'user_chunk') {
            // Interim transcript for the segment currently being spoken. Deepgram may
            // emit several FINAL segments back-to-back while the candidate keeps talking
            // (no agent turn in between) — as long as the last bubble is still 'user',
            // this is the same turn, so we append onto its committed text instead of
            // replacing the whole bubble.
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'user') {
                const base = last.committedText ?? ''
                const merged = base ? `${base} ${msg.text}` : msg.text!
                return prev.map((m, i) =>
                  i === prev.length - 1 ? { ...m, text: merged, partial: true } : m
                )
              }
              return [...prev, { role: 'user' as const, text: msg.text!, partial: true, committedText: '' }]
            })
          } else if (msg.role === 'user') {
            // Final authoritative segment — append to the same bubble if the candidate
            // is still mid-turn (last message is also 'user'); otherwise start a new one.
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'user') {
                const base = last.committedText ?? ''
                const committed = base ? `${base} ${msg.text}` : msg.text!
                return prev.map((m, i) =>
                  i === prev.length - 1
                    ? { ...m, text: committed, partial: false, committedText: committed }
                    : m
                )
              }
              return [...prev, { role: 'user' as const, text: msg.text!, partial: false, committedText: msg.text! }]
            })
          } else if (msg.role === 'assistant_chunk') {
            // Append chunk to the current streaming bubble, or open a new one
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'assistant' && last.streaming) {
                return prev.map((m, i) =>
                  i === prev.length - 1 ? { ...m, text: m.text + msg.text! } : m
                )
              }
              return [...prev, { role: 'assistant' as const, text: msg.text!, streaming: true }]
            })
          } else if (msg.role === 'assistant') {
            // Finalize the streaming bubble — search backwards since a user message
            // may have arrived between the last chunk and this completion event
            setMessages((prev) => {
              const streamingIdx = prev.map(m => m.role === 'assistant' && m.streaming).lastIndexOf(true)
              if (streamingIdx !== -1) {
                return prev.map((m, i) =>
                  i === streamingIdx ? { ...m, text: msg.text!, streaming: false } : m
                )
              }
              return [...prev, { role: 'assistant' as const, text: msg.text!, streaming: false }]
            })
          }
        } catch {
          // ignore malformed data
        }
      })

      // When room disconnects, either show terminated screen (fail) or wait for backend then score (pass)
      lkRoom.on(RoomEvent.Disconnected, () => {
        if (isTerminatedRef.current) return  // handleUserLeft already took over
        if (timerRef.current) clearInterval(timerRef.current)

        // Agent concluded with passed=false — interview is already marked Failed in DB.
        if (concludeFailedRef.current) {
          isTerminatedRef.current = true
          setTerminatedReason('Your interview has been concluded by the interviewer.')
          setPhase('terminated')
          return
        }

        setPhase('submitting')

        const es = new EventSource(
          `${API_BASE}/api/interviews/${interviewId}/status-stream`,
        )
        eventSourceRef.current = es

        es.addEventListener('done', () => {
          es.close()
          eventSourceRef.current = null
          if (!isTerminatedRef.current) void scoreFromDb()
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
      body: JSON.stringify({ return_questions: true, test_mode: localStorage.getItem('russell_test_mode') === '1' }),
      signal: controller.signal,
    })
      .then((res) => {
        if (res.status === 409) {
          setPhase('already-completed')
          return null
        }
        if (!res.ok)
          return res.json().then((d) => {
            throw new Error((d as { detail?: string }).detail ?? `Error ${res.status}`)
          })
        return res.json()
      })
      .then((data) => {
        if (data === null || controller.signal.aborted) return
        const type = (data.interview_type ?? '') as string
        setInterviewType(type)
        const oral =
          type.toLowerCase().includes('oral') || type.toLowerCase().includes('voice')
        isOralRef.current = oral
        const failCases = (data.enable_fail_cases ?? true) as boolean
        setEnableFailCases(failCases)
        enableFailCasesRef.current = failCases
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
          doSubmit(true)
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
      setShowConfirmModal(true)
      return
    }
    void doSubmit()
  }, [answers, questions.length, doSubmit])

  const handleConfirmSubmit = useCallback(() => {
    setShowConfirmModal(false)
    void doSubmit()
  }, [doSubmit])

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
                onClick={handleEndInterviewClick}
              >
                End Interview
              </Button>
            </div>
          </div>

          <Modal isOpen={showEndInterviewModal} onClose={() => setShowEndInterviewModal(false)}>
            <div className="ir-confirm-dialog">
              <h2 className="ir-confirm-title">End this interview now?</h2>
              <p className="ir-confirm-body">
                Leaving this interview round will result in immediate failure. If you proceed, this
                round will be terminated and recorded as Failed with a score of 0. This can't be
                undone.
              </p>
              <div className="ir-confirm-actions">
                <Button variant="secondary" onClick={() => setShowEndInterviewModal(false)}>
                  Go Back
                </Button>
                <Button variant="primary" onClick={handleConfirmEndInterview}>
                  End Interview
                </Button>
              </div>
            </div>
          </Modal>
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
              <Button variant="primary" onClick={handleSubmitClick}>
                Submit Answers
              </Button>
            </div>
          </div>

          <Modal isOpen={showConfirmModal} onClose={() => setShowConfirmModal(false)}>
            <div className="ir-confirm-dialog">
              <h2 className="ir-confirm-title">Submit with unanswered questions?</h2>
              <p className="ir-confirm-body">
                You've answered {answeredCount} of {questions.length} questions. Unanswered
                questions will be scored as blank. This can't be undone.
              </p>
              <div className="ir-confirm-actions">
                <Button variant="secondary" onClick={() => setShowConfirmModal(false)}>
                  Go Back
                </Button>
                <Button variant="primary" onClick={handleConfirmSubmit}>
                  Submit Anyway
                </Button>
              </div>
            </div>
          </Modal>
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

      {/* ── Terminated (cheating / leave detection) ── */}
      {phase === 'terminated' && (
        <div className="ir-center">
          <BackButton />
          <p className="ir-error-text" style={{ color: 'var(--color-alert)' }}>Interview Terminated</p>
          <p className="ir-status-sub" style={{ marginTop: '8px' }}>
            {terminatedReason ?? 'This interview has been closed.'}
          </p>
        </div>
      )}

      {/* ── Already completed (interview was closed before this page load) ── */}
      {phase === 'already-completed' && (
        <div className="ir-center">
          <BackButton />
          <p className="ir-status-text">Interview Session Ended</p>
          <p className="ir-status-sub">
            This interview has already been completed. Return to your applications to view your results.
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
                <div
                  className="ir-overall-accent-bar"
                  style={{ width: `${(results.overall_score / MAX_SCORE) * 100}%` }}
                />
                <div className="ir-overall-left">
                  <span className="ir-overall-label">Overall Score</span>
                  <span className="ir-overall-sub">{results.total_graded} questions graded</span>
                </div>
                <div className="ir-overall-score-row">
                  <span className="ir-overall-score">{results.overall_score.toFixed(1)}</span>
                  <span className="ir-overall-out">/ {MAX_SCORE}</span>
                </div>
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
