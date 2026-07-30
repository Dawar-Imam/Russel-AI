import { Room, RoomEvent, Track } from 'livekit-client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import BackButton from '../components/BackButton'
import Button from '../components/Button'
import Modal from '../components/Modal'
import ParticipantCard from '../components/ParticipantCard'
import '../css/InterviewRoom.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const RING_RADIUS = 62
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS
const MAX_SCORE = 10

interface QuestionItem {
  iq_id: string
  question_text: string
  question_type: string
  options?: string[] | null
  candidate_answer?: string | null
}

interface GradedAnswer {
  question_text: string
  candidate_answer: string
  score: number
  notes: string
  is_correct: boolean
}

interface Results {
  overall_score: number
  total_graded: number
  graded_answers: GradedAnswer[]
  improvement_recommendations?: string
  result: string  // "Pass" | "Failed" — backend-computed, matches passing_threshold
  total_questions: number
  passed_questions: number
  passing_threshold: number
  // Set instead of real scores when the application went stale mid-interview — an ATS
  // rerun was dispatched and this round's answers were never graded.
  redirect_application_id?: string | null
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
  | 'not-started'
  | 'error'

function fmtTime(secs: number): string {
  const m = Math.floor(secs / 60).toString().padStart(2, '0')
  const s = (secs % 60).toString().padStart(2, '0')
  return `${m}:${s}`
}

async function fetchVoiceInterviewToken(
  interviewId: string,
  testMode: boolean,
): Promise<{ url: string; token: string }> {
  // /join covers both cases: a scheduled interview whose AI agent already pre-joined
  // the room (mints a token for that existing room), and an on-demand/unscheduled
  // round (falls back to creating everything fresh, same as the old /voice-interview
  // call did) — so this one endpoint works for both flows.
  const res = await fetch(
    `${API_BASE}/api/interviews/${interviewId}/join?test_mode=${testMode}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const d = await res.json().catch(() => ({}))
    const detail = (d as { detail?: string | { message?: string; application_id?: string } }).detail
    const message = typeof detail === 'string' ? detail : detail?.message
    throw new Error(message ?? `Server error ${res.status}`)
  }
  return res.json() as Promise<{ url: string; token: string }>
}

function scoreColor(score: number): string {
  if (score >= 8) return 'var(--color-primary)'
  if (score >= 5) return 'var(--color-primary-dark)'
  return 'var(--color-text-primary)'
}

function InterviewRoom() {
  const { interviewId } = useParams<{ interviewId: string }>()
  const navigate = useNavigate()
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
  const [userSpeaking, setUserSpeaking] = useState(false)
  const [assistantSpeaking, setAssistantSpeaking] = useState(false)
  // Remote participants currently in the LiveKit room (the AI interviewer, and any future
  // additional participant e.g. a recruiter) — kept in sync via ParticipantConnected/
  // ParticipantDisconnected so cards appear/disappear automatically without extra logic.
  const [remoteParticipants, setRemoteParticipants] = useState<{ sid: string; name: string }[]>([])

  const [enableFailCases, setEnableFailCases] = useState(true)
  const [applicationId, setApplicationId] = useState<string | null>(null)
  const [terminatedReason, setTerminatedReason] = useState<string | null>(null)
  // 'deleted' (no-show/expired link) gets distinct copy from the generic
  // already-completed case — both land on the same 'already-completed' phase.
  const [alreadyCompletedCode, setAlreadyCompletedCode] = useState<string | null>(null)
  const [autoSubmitted, setAutoSubmitted] = useState(false)

  const answersRef = useRef<string[]>([])
  const questionsRef = useRef<QuestionItem[]>([])
  const isSubmittingRef = useRef(false)
  const isTerminatedRef = useRef(false)
  // Set the instant `beforeunload` fires (refresh, close tab, external navigation) — a
  // `visibilitychange` to 'hidden' also fires as part of that same teardown, and without
  // this guard it would look identical to a genuine tab-switch-away and wrongly terminate
  // the interview on a plain refresh.
  const isUnloadingRef = useRef(false)
  const enableFailCasesRef = useRef(true)
  const phaseRef = useRef<Phase>('loading')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isOralRef = useRef(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const roomRef = useRef<Room | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const saveAnswerTimersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({})

  // Assistant reply is buffered until the agent's audio actually starts
  // coming out of the speakers, then revealed 1s after that signal — so the
  // transcript doesn't visually "get ahead" of the voice.
  const assistantSpeakingPrevRef = useRef(false)
  const assistantRevealedRef = useRef(false)
  const assistantBufferRef = useRef('')
  const assistantRevealTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Highest generation number seen so far. The agent's LLM occasionally
  // self-revises mid-turn — the session cancels the superseded attempt's
  // audio, but its chunks may have already been published. Each chunk is
  // tagged with the generation of the attempt it belongs to, so a lower
  // generation than what we've already seen is a discarded draft, not new text.
  const assistantGenerationRef = useRef(0)

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


  // Cleanup LiveKit room and SSE on unmount — also the catch-all leave-detector for
  // ways of leaving that don't fire a real page unload (browser back/forward button,
  // any other in-app navigation away from this route): those unmount this component
  // via React Router without ever triggering the beforeunload/visibilitychange
  // listeners below, so without this the round would just stay 'In Progress' forever.
  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
      eventSourceRef.current?.close()
      if (timerRef.current) clearInterval(timerRef.current)
      if (assistantRevealTimeoutRef.current) clearTimeout(assistantRevealTimeoutRef.current)
      Object.values(saveAnswerTimersRef.current).forEach(clearTimeout)
      if (localStorage.getItem('russell_test_mode') === '1') {
        void fetch(`${API_BASE}/api/interviews/${interviewId}/clear-test-cache`, { method: 'POST' })
      }
      if (
        enableFailCasesRef.current &&
        !isTerminatedRef.current &&
        (phaseRef.current === 'answering' || phaseRef.current === 'voice-active')
      ) {
        isTerminatedRef.current = true
        void fetch(`${API_BASE}/api/interviews/${interviewId}/report-leave`, { method: 'POST' })
          .catch(() => { /* fire-and-forget — component is already gone */ })
      }
    }
  }, [interviewId])

  // ---------------------------------------------------------------------------
  // Per-answer autosave — immediate for MCQ picks, debounced for free-text, so a
  // refresh/crash/network drop never loses progress typed so far.
  // ---------------------------------------------------------------------------

  const saveAnswer = useCallback((iqId: string, value: string) => {
    if (phaseRef.current !== 'answering') return
    void fetch(`${API_BASE}/api/interviews/${interviewId}/save-answer`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ iq_id: iqId, candidate_answer: value }),
    }).catch(() => { /* fire-and-forget — the next save or final submit carries the latest value */ })
  }, [interviewId])

  const saveAnswerDebounced = useCallback((index: number, iqId: string, value: string) => {
    if (saveAnswerTimersRef.current[index]) clearTimeout(saveAnswerTimersRef.current[index])
    saveAnswerTimersRef.current[index] = setTimeout(() => saveAnswer(iqId, value), 800)
  }, [saveAnswer])

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

  // Tab switch / window blur — ignored while the page is actually unloading (refresh,
  // close, external navigation), since that also flips document.hidden but isn't the
  // candidate switching away while staying in the interview.
  useEffect(() => {
    const onVisibility = () => {
      if (isUnloadingRef.current) return
      if (!enableFailCasesRef.current) return
      if (document.hidden && (phaseRef.current === 'answering' || phaseRef.current === 'voice-active')) {
        void handleUserLeft()
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [handleUserLeft])

  // Page close / refresh / navigation — no longer reports a leave here: a hard refresh
  // fires this same event, and the interview must survive a refresh untouched. Real
  // in-app navigation away is still caught by the unmount cleanup below.
  useEffect(() => {
    const onBeforeUnload = () => {
      isUnloadingRef.current = true
    }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [])

  // ---------------------------------------------------------------------------
  // Written interview submit
  // ---------------------------------------------------------------------------

  const doSubmit = useCallback(async (triggeredByTimer = false) => {
    if (isSubmittingRef.current) return
    isSubmittingRef.current = true
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    if (triggeredByTimer) setAutoSubmitted(true)
    setPhase('submitting')

    try {
      const body = {
        fetch_from_db: false,
        test_mode: localStorage.getItem('russell_test_mode') === '1',
        event_type: triggeredByTimer ? 'timer_end' : 'submit',
        interview_type: 'written',
        // Snapshotted at call time — includes whatever's currently in the answer
        // boxes even if the candidate was mid-keystroke when the timer hit 0.
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
      if (data.redirect_application_id) {
        navigate(`/application-progress/${data.redirect_application_id}`)
        return
      }
      setResults(data)
      setPhase('results')
    } catch (err) {
      isSubmittingRef.current = false
      setError(err instanceof Error ? err.message : 'Submission failed')
      setPhase('error')
    }
  }, [interviewId, navigate])

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
      const { url, token } = await fetchVoiceInterviewToken(interviewId!, testMode)

      // Connect to LiveKit room
      const lkRoom = new Room()
      roomRef.current = lkRoom

      // Participant roster — the AI interviewer joins as a separate remote participant;
      // tracking connect/disconnect here (rather than assuming exactly one remote
      // participant) means the card grid rearranges itself automatically if anyone
      // joins/leaves, with no per-participant special-casing.
      // NOTE: the agent already joined the room server-side before this client ever
      // connects, so ParticipantConnected will never fire for it here (that event only
      // fires for participants who join *after* us) — its card has to come from
      // room.remoteParticipants, read only once connect() below has actually resolved.
      lkRoom.on(RoomEvent.ParticipantConnected, (p) => {
        setRemoteParticipants((prev) => [...prev, { sid: p.sid, name: p.name || p.identity }])
      })
      lkRoom.on(RoomEvent.ParticipantDisconnected, (p) => {
        setRemoteParticipants((prev) => prev.filter((r) => r.sid !== p.sid))
      })

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

      // Live speaking indicator — LiveKit computes audio levels for every
      // published track (local mic + remote agent audio), so we can tell who's
      // actively talking right now without any custom VAD/analyser code.
      lkRoom.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const localSid = lkRoom.localParticipant.sid
        setUserSpeaking(speakers.some((p) => p.sid === localSid))
        const speaking = speakers.some((p) => p.sid !== localSid)
        setAssistantSpeaking(speaking)

        // Rising edge: speaker audio just started. If we're holding buffered
        // assistant text for this turn, reveal it 1s from now.
        if (
          speaking &&
          !assistantSpeakingPrevRef.current &&
          !assistantRevealedRef.current &&
          assistantRevealTimeoutRef.current === null
        ) {
          assistantRevealTimeoutRef.current = setTimeout(() => {
            assistantRevealTimeoutRef.current = null
            assistantRevealedRef.current = true
            const text = assistantBufferRef.current
            if (!text) return
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'assistant' && last.streaming) {
                return prev.map((m, i) => (i === prev.length - 1 ? { ...m, text } : m))
              }
              return [...prev, { role: 'assistant' as const, text, streaming: true }]
            })
          }, 500)
        }
        assistantSpeakingPrevRef.current = speaking
      })

      // Receive live transcript messages from the agent via data channel
      lkRoom.on(RoomEvent.DataReceived, (payload: Uint8Array) => {
        try {
          const msg = JSON.parse(new TextDecoder().decode(payload)) as { role: string; text?: string; event?: string; reason?: string; passed?: boolean; generation?: number }
          if (!msg.role) return

          // --- control events ---
          if (msg.role === 'control') {
            if (msg.event === 'interview_ended') {
              // Agent concluded the interview (passed or failed) — make the candidate
              // leave the room so RoomEvent.Disconnected fires and triggers the
              // processing/SSE/scoring flow the same way regardless of outcome.
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
              assistantRevealedRef.current = false
              assistantBufferRef.current = ''
              if (assistantRevealTimeoutRef.current) {
                clearTimeout(assistantRevealTimeoutRef.current)
                assistantRevealTimeoutRef.current = null
              }
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
            const generation = msg.generation ?? 0
            if (generation < assistantGenerationRef.current) {
              // Belongs to a self-revision the backend already discarded
              // (its audio never played) — drop it instead of appending.
              return
            }
            if (generation > assistantGenerationRef.current) {
              // A newer attempt supersedes whatever we were buffering/showing.
              assistantGenerationRef.current = generation
              assistantBufferRef.current = msg.text!
            } else {
              assistantBufferRef.current += msg.text!
            }
            if (!assistantRevealedRef.current) return
            const text = assistantBufferRef.current
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (last?.role === 'assistant' && last.streaming) {
                return prev.map((m, i) => (i === prev.length - 1 ? { ...m, text } : m))
              }
              return [...prev, { role: 'assistant' as const, text, streaming: true }]
            })
          } else if (msg.role === 'assistant') {
            // Turn is over — reset the reveal state for the next assistant turn.
            const wasRevealed = assistantRevealedRef.current
            assistantRevealedRef.current = false
            assistantBufferRef.current = ''
            assistantGenerationRef.current = Math.max(assistantGenerationRef.current, msg.generation ?? 0)
            if (assistantRevealTimeoutRef.current) {
              clearTimeout(assistantRevealTimeoutRef.current)
              assistantRevealTimeoutRef.current = null
            }
            // Finalize the streaming bubble — search backwards since a user message
            // may have arrived between the last chunk and this completion event
            setMessages((prev) => {
              const streamingIdx = prev.map(m => m.role === 'assistant' && m.streaming).lastIndexOf(true)
              if (wasRevealed && streamingIdx !== -1) {
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

      // When room disconnects, wait for backend post-processing then score —
      // regardless of whether the agent concluded the interview as passed or
      // failed. Only a candidate-initiated leave (handleUserLeft) skips scoring.
      lkRoom.on(RoomEvent.Disconnected, () => {
        if (isTerminatedRef.current) return  // handleUserLeft already took over
        if (timerRef.current) clearInterval(timerRef.current)

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

        es.addEventListener('failed', (e) => {
          es.close()
          eventSourceRef.current = null
          let reason = 'Interview processing failed.'
          try {
            const data = JSON.parse((e as MessageEvent).data) as { reason?: string }
            if (data.reason) reason = data.reason
          } catch { /* ignore malformed payload */ }
          setError(reason)
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
      // The AI interviewer is already in the room by this point (backend joins it before
      // handing us this token) — read it from remoteParticipants now that we're actually
      // connected, rather than relying on ParticipantConnected (which won't fire for it).
      setRemoteParticipants(
        Array.from(lkRoom.remoteParticipants.values()).map((p) => ({ sid: p.sid, name: p.name || p.identity })),
      )
      await lkRoom.localParticipant.setMicrophoneEnabled(true, {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      })
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
        if (res.status === 409)
          return res.json().then((d) => {
            const detail = (d as { detail?: { application_id?: string; code?: string } }).detail
            if (detail?.application_id) setApplicationId(detail.application_id)
            setAlreadyCompletedCode(detail?.code ?? null)
            setPhase('already-completed')
            return null
          })
        if (res.status === 425)
          return res.json().then((d) => {
            // Candidate followed the join link before the round's scheduled_at —
            // see backend InterviewNotStartedError.
            const detail = (d as { detail?: { application_id?: string } }).detail
            if (detail?.application_id) setApplicationId(detail.application_id)
            setPhase('not-started')
            return null
          })
        if (res.status === 410)
          return res.json().then((d) => {
            const detail = (d as { detail?: { code?: string; application_id?: string } }).detail
            // Deleted after a recruiter's ATS-rerun fail (see backend
            // InterviewDeletedPostFailError) — redirect straight to application progress,
            // no error state, no retry. Distinct from 409 (still active) and from a plain
            // 404 (bad/unknown interview_id), which fall through to the generic error path.
            if (detail?.application_id) navigate(`/application-progress/${detail.application_id}`)
            return null
          })
        if (!res.ok)
          return res.json().then((d) => {
            throw new Error((d as { detail?: string }).detail ?? `Error ${res.status}`)
          })
        return res.json()
      })
      .then((data) => {
        if (data === null || controller.signal.aborted) return
        if (data.application_id) setApplicationId(data.application_id as string)
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
          setAnswers((data.questions as QuestionItem[]).map((q) => q.candidate_answer ?? ''))
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

    // Deadline-based, not a per-tick decrement: setInterval side effects (calling
    // doSubmit from inside a setState updater, as this used to) are unreliable —
    // React updater functions must stay pure, and browsers throttle/pause
    // setInterval in backgrounded or minimized tabs, so a naive "subtract 1 every
    // tick" counter can drift and never actually reach 0. Recomputing the
    // remaining time from a fixed wall-clock deadline on every tick means that
    // whenever a tick DOES fire — even a late one after the tab regains focus —
    // it still detects expiry correctly and submits.
    const deadline = Date.now() + timer * 1000

    const tick = () => {
      const remainingMs = deadline - Date.now()
      const remainingSec = Math.max(0, Math.ceil(remainingMs / 1000))
      setTimer(remainingSec)
      if (remainingMs <= 0) {
        if (timerRef.current) {
          clearInterval(timerRef.current)
          timerRef.current = null
        }
        void doSubmit(true)
      }
    }

    timerRef.current = setInterval(tick, 1000)
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
        timerRef.current = null
      }
    }
  // `timer` is intentionally read once (as the starting point) rather than
  // listed as a dep — re-running this effect every tick would recreate the
  // interval every second instead of running a single deadline-based countdown.
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
          <div className="ir-spinner" />
          <p className="ir-status-text">Fetching your Interview Questions</p>
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
          <h1 className="ir-heading">Interview Room</h1>

          <div className="ir-oral-body">
            {/* Left — live transcript */}
            <div className="ir-conversation-panel">
              <div className="ir-conversation-header">Live Transcript</div>
              <div className="ir-conversation-messages">
                {messages.length === 0 ? (
                  <p className="ir-conversation-empty">Listening…</p>
                ) : (
                  messages.map((msg, i) => {
                    const isLast = i === messages.length - 1
                    const showMic = isLast && msg.role === 'user' && userSpeaking
                    const showSpeaker = isLast && msg.role === 'assistant' && assistantSpeaking
                    return (
                      <div key={i} className={`ir-message ir-message--${msg.role}`}>
                        <span className="ir-message-label">
                          {msg.role === 'assistant' ? 'Russel' : 'You'}
                        </span>
                        <div className="ir-message-bubble">
                          {msg.text}
                          {msg.streaming && <span className="ir-cursor">▋</span>}
                          {showMic && (
                            <span className="ir-live-icon ir-mic-icon" title="Speaking" aria-hidden="true">
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                                <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
                                <path d="M5 11a7 7 0 0 0 14 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                <line x1="12" y1="18" x2="12" y2="22" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                              </svg>
                            </span>
                          )}
                          {showSpeaker && (
                            <span className="ir-live-icon ir-speaker-icon" title="Speaking" aria-hidden="true">
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
                                <path d="M4 9v6h4l5 5V4L8 9H4Z" fill="currentColor" />
                                <path d="M16.5 8.5a5 5 0 0 1 0 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                                <path d="M19 6a9 9 0 0 1 0 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                              </svg>
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Right — participant stage (top) + timer/controls (bottom) */}
            <div className="ir-right-panel">
              <div className="ir-stage">
                <div className="ir-participant-grid">
                  <ParticipantCard name="You" isLocal isSpeaking={userSpeaking} />
                  {remoteParticipants.map((p) => (
                    <ParticipantCard key={p.sid} name={p.name} isSpeaking={assistantSpeaking} />
                  ))}
                </div>
              </div>

              <div className="ir-right-bottom">
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
                    {q.question_type === 'mcq' && q.options && q.options.length > 0 ? (
                      <div className="ir-mcq-options" role="radiogroup">
                        {q.options.map((opt, optIdx) => (
                          <label key={optIdx} className="ir-mcq-option">
                            <input
                              type="radio"
                              name={`ir-mcq-${q.iq_id}`}
                              value={opt}
                              checked={(answers[i] ?? '') === opt}
                              onChange={() => {
                                const updated = [...answers]
                                updated[i] = opt
                                setAnswers(updated)
                                saveAnswer(q.iq_id, opt)
                              }}
                            />
                            <span>{opt}</span>
                          </label>
                        ))}
                      </div>
                    ) : (
                      <textarea
                        className="ir-answer-textarea"
                        placeholder="Type your answer here…"
                        value={answers[i] ?? ''}
                        rows={5}
                        onChange={(e) => {
                          const updated = [...answers]
                          updated[i] = e.target.value
                          setAnswers(updated)
                          saveAnswerDebounced(i, q.iq_id, e.target.value)
                        }}
                      />
                    )}
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
            {autoSubmitted
              ? 'Time expired — submitting your answers…'
              : isOral ? 'Processing your interview…' : 'Scoring your answers…'}
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
          <BackButton to={applicationId ? `/application-progress/${applicationId}` : undefined} />
          <p className="ir-error-text" style={{ color: 'var(--color-alert)' }}>Interview Terminated</p>
          <p className="ir-status-sub" style={{ marginTop: '8px' }}>
            {terminatedReason ?? 'This interview has been closed.'}
          </p>
        </div>
      )}

      {/* ── Already completed / deleted (interview was closed before this page load) ── */}
      {phase === 'already-completed' && (
        <div className="ir-center">
          <BackButton to={applicationId ? `/application-progress/${applicationId}` : undefined} />
          <p className="ir-status-text">
            {alreadyCompletedCode === 'deleted' ? 'Interview Deleted' : 'Interview Session Ended'}
          </p>
          <p className="ir-status-sub">
            {alreadyCompletedCode === 'deleted'
              ? "This interview wasn't joined in time and has been deleted. Return to your applications for next steps."
              : 'This interview has already been completed. Return to your applications to view your results.'}
          </p>
        </div>
      )}

      {/* ── Not started yet (candidate followed the join link too early) ── */}
      {phase === 'not-started' && (
        <div className="ir-center">
          <BackButton to={applicationId ? `/application-progress/${applicationId}` : undefined} />
          <p className="ir-status-text">Interview Not Started</p>
          <p className="ir-status-sub">
            This interview hasn't started yet. Please come back at your scheduled time.
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
              {autoSubmitted && (
                <p className="ir-timeup-banner">
                  Time expired — your interview has been submitted automatically.
                </p>
              )}

              {isOral || results.total_questions === 0 ? (
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
              ) : (
                <div className="ir-overall-card ir-overall-card--pass-summary">
                  <div
                    className={`ir-overall-accent-bar${results.result === 'Pass' ? '' : ' ir-overall-accent-bar--fail'}`}
                    style={{ width: `${(results.passed_questions / results.total_questions) * 100}%` }}
                  />
                  <div className="ir-overall-left">
                    <span className="ir-overall-label">Passed Questions</span>
                    <span className="ir-overall-sub">
                      Passing Criteria: at least {results.passing_threshold} question
                      {results.passing_threshold === 1 ? '' : 's'} must be passed.
                    </span>
                  </div>
                  <div className="ir-overall-right">
                    <div className="ir-overall-score-row">
                      <span className="ir-overall-score">{results.passed_questions}</span>
                      <span className="ir-overall-out">out of {results.total_questions}</span>
                    </div>
                    <span
                      className={`ir-final-result-badge${results.result === 'Pass' ? ' ir-final-result-badge--pass' : ' ir-final-result-badge--fail'}`}
                    >
                      {results.result === 'Pass' ? 'PASS' : 'FAIL'}
                    </span>
                  </div>
                </div>
              )}

              {results.improvement_recommendations && (
                <div className="ir-recommendations-card">
                  <span className="ir-graded-section-label">Improvement Recommendations</span>
                  <p className="ir-recommendations-text">{results.improvement_recommendations}</p>
                </div>
              )}

              <div className="ir-graded-list">
                {results.graded_answers.map((ga, i) => (
                  <div key={i} className="ir-graded-card">
                    <div className="ir-graded-header">
                      <div className="ir-graded-num-wrap">
                        <span className="ir-graded-num">Q{i + 1}</span>
                        <p className="ir-graded-question">{ga.question_text}</p>
                      </div>
                      <div className="ir-graded-score-wrap">
                        <span
                          className="ir-graded-score-badge"
                          style={{ color: scoreColor(ga.score) }}
                        >
                          {ga.score}<span className="ir-graded-score-denom">/10</span>
                        </span>
                        <span
                          className={`ir-correctness-badge${ga.is_correct ? ' ir-correctness-badge--correct' : ' ir-correctness-badge--incorrect'}`}
                        >
                          {ga.is_correct ? 'PASS' : 'FAIL'}
                        </span>
                      </div>
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
