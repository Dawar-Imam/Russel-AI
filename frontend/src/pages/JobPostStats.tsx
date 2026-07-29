import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  deleteScheduledInterview,
  fetchCandidatePanel,
  fetchInterviewQA,
  fetchJobStats,
  fetchRoundCandidates,
  type CandidatePanelResponse,
  type EvaluationQuestionItem,
  type JobStatsResponse,
  type RoundCandidateItem,
} from '../api/jobs'
import '../css/JobPostStats.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

const RECRUITER_ID = sessionStorage.getItem('recruiterId') ?? ''

// Same substring convention used across the backend (question_pregeneration_service.py,
// scheduling_service._require_oral_round) — scheduling only applies to oral/voice
// rounds, never written-test rounds.
function isOralRoundType(roundTypeName: string): boolean {
  const lowered = roundTypeName.toLowerCase()
  return lowered.includes('oral') || lowered.includes('voice')
}

function ivStatusClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'pass') return 'jps-iv--pass'
  if (s === 'failed') return 'jps-iv--failed'
  if (s === 'in progress' || s === 'in_progress') return 'jps-iv--inprogress'
  if (s === 'scheduled') return 'jps-iv--scheduled'
  if (s === 'not needed') return 'jps-iv--notneeded'
  return 'jps-iv--default'
}

function jobStatusClass(status: string): string {
  const s = status.toLowerCase()
  if (s === 'active') return 'jps-jobstatus--active'
  if (s === 'closed' || s === 'expired') return 'jps-jobstatus--closed'
  if (s === 'draft') return 'jps-jobstatus--draft'
  return 'jps-jobstatus--default'
}

function isCompleted(status: string | null): boolean {
  if (!status) return false
  const s = status.toLowerCase()
  return s === 'pass' || s === 'failed'
}

function expYears(min: number | null, max: number | null): string | null {
  if (min == null && max == null) return null
  if (min != null && max != null) return `${min}–${max} years`
  if (min != null) return `${min}+ years`
  return `Up to ${max} years`
}

function JobPostStats() {
  const { jobId } = useParams<{ jobId: string }>()

  const [stats, setStats] = useState<JobStatsResponse | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState<string | null>(null)

  const [selectedRound, setSelectedRound] = useState<number | null>(null)
  const [candidates, setCandidates] = useState<RoundCandidateItem[]>([])
  const [candidatesLoading, setCandidatesLoading] = useState(false)

  // Candidate dialog
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogCandidate, setDialogCandidate] = useState<RoundCandidateItem | null>(null)
  const [panel, setPanel] = useState<CandidatePanelResponse | null>(null)
  const [panelLoading, setPanelLoading] = useState(false)

  // Selected interview round inside dialog (for Q&A details box)
  const [selectedProgressId, setSelectedProgressId] = useState<string | null>(null)
  const [qaCache, setQaCache] = useState<Record<string, EvaluationQuestionItem[]>>({})
  const [qaLoading, setQaLoading] = useState<string | null>(null)

  // Deleting a scheduled (not-yet-started) interview.
  const [deletingInterviewId, setDeletingInterviewId] = useState<string | null>(null)

  // Kept in sync with selectedRound so the WS handler below (which only depends on
  // jobId, to avoid reconnecting on every round click) can read the current round.
  const selectedRoundRef = useRef<number | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)

  useEffect(() => {
    if (!jobId) return
    setStatsLoading(true)
    fetchJobStats(jobId)
      .then(setStats)
      .catch((err: unknown) => setStatsError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setStatsLoading(false))
  }, [jobId])

  useEffect(() => {
    selectedRoundRef.current = selectedRound
  }, [selectedRound])

  function refetchSelectedRound() {
    const roundOrder = selectedRoundRef.current
    if (roundOrder === null || !jobId) return
    fetchRoundCandidates(jobId, roundOrder)
      .then(setCandidates)
      .catch(() => {})
  }

  // Live updates: reconnecting WebSocket (same pattern as ApplicationProgress.tsx's
  // candidate-side one) that re-fetches the currently open round's candidates when
  // the backend announces a Calendar-driven schedule/unschedule for this job.
  useEffect(() => {
    if (!jobId) return
    let cancelled = false

    function connect() {
      if (cancelled) return
      const ws = new WebSocket(`${WS_BASE}/ws/jobs/${jobId}`)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          if (payload?.event === 'interview_scheduled' || payload?.event === 'interview_unscheduled') {
            refetchSelectedRound()
          }
        } catch {
          // Ignore malformed payloads — the REST fetch remains the source of truth.
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onclose = () => {
        if (cancelled) return
        const attempt = reconnectAttemptsRef.current
        reconnectAttemptsRef.current = attempt + 1
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        reconnectTimerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  function handleSelectRound(roundOrder: number) {
    if (selectedRound === roundOrder) {
      setSelectedRound(null)
      setCandidates([])
      return
    }
    setSelectedRound(roundOrder)
    setCandidatesLoading(true)
    fetchRoundCandidates(jobId!, roundOrder)
      .then(setCandidates)
      .catch(() => setCandidates([]))
      .finally(() => setCandidatesLoading(false))
  }

  // Recruiter creates the interview event by hand in their own Google Calendar — this
  // just opens a prefilled event-creation link in a new tab, using whatever Google
  // account is already signed in in their browser. No RusselAI OAuth consent is
  // needed for this (that flow now only runs once, at recruiter signup — see Auth.tsx —
  // to register the webhook watch, and must never gate this button). The candidate's
  // interview-room join link in the description is the only signal the Calendar
  // webhook handler (backend/app/api/endpoints/google_calendar.py) uses to match the
  // event the recruiter eventually creates back to this interview.
  function handleScheduleClick(candidate: RoundCandidateItem) {
    const joinUrl = `${window.location.origin}/interview-room/${candidate.interview_id}`
    const params = new URLSearchParams({
      action: 'TEMPLATE',
      text: `Interview - ${candidate.name}`,
      details: `Join your interview here: ${joinUrl}`,
      add: candidate.email,
    })
    window.open(`https://calendar.google.com/calendar/render?${params.toString()}`, '_blank')
  }

  function handleDeleteInterview(candidate: RoundCandidateItem) {
    if (!RECRUITER_ID) return
    if (!window.confirm(`Remove the scheduled time for ${candidate.name}'s interview? They can be rescheduled afterward.`)) return
    setDeletingInterviewId(candidate.interview_id)
    deleteScheduledInterview(candidate.interview_id, RECRUITER_ID)
      .then(() => {
        // Backend only clears the schedule (scheduled_at/google_event_id/etc) — the
        // candidate/application record itself is untouched, so update this row in
        // place instead of removing it from the list.
        setCandidates((prev) =>
          prev.map((c) =>
            c.interview_id === candidate.interview_id
              ? { ...c, scheduled_at: null, scheduled_timezone: null }
              : c,
          ),
        )
      })
      .catch((err: unknown) => window.alert(err instanceof Error ? err.message : 'Failed to delete interview'))
      .finally(() => setDeletingInterviewId(null))
  }

  function handleOpenCandidate(candidate: RoundCandidateItem) {
    setDialogCandidate(candidate)
    setDialogOpen(true)
    setPanel(null)
    setSelectedProgressId(null)
    setPanelLoading(true)
    fetchCandidatePanel(jobId!, candidate.application_id, candidate.interview_id)
      .then(setPanel)
      .catch(() => setPanel(null))
      .finally(() => setPanelLoading(false))
  }

  function handleCloseDialog() {
    setDialogOpen(false)
    setDialogCandidate(null)
    setPanel(null)
    setSelectedProgressId(null)
  }

  function handleSelectProgress(interviewId: string | null) {
    if (!interviewId) return
    setSelectedProgressId(interviewId)
    if (qaCache[interviewId] !== undefined) return
    setQaLoading(interviewId)
    fetchInterviewQA(interviewId)
      .then((qa) => setQaCache((prev) => ({ ...prev, [interviewId]: qa })))
      .catch(() => setQaCache((prev) => ({ ...prev, [interviewId]: [] })))
      .finally(() => setQaLoading(null))
  }

  const selectedQA = selectedProgressId ? (qaCache[selectedProgressId] ?? null) : null

  return (
    <main className="jps-page">
      <header className="jps-header">
        <h1 className="jps-heading">Job Stats</h1>
      </header>

      <div className="jps-content">
        {statsLoading ? (
          <p className="jps-state-text">Loading…</p>
        ) : statsError ? (
          <p className="jps-state-error">{statsError}</p>
        ) : stats ? (
          <>
            {/* ── Left: job info card (~60%) ── */}
            <aside className="jps-left">
              <div className="jps-job-card">

                {/* Details + Description */}
                <div className="jps-card-body">
                  <div className="jps-card-skills-col">
                    {/* Job attributes, stacked above Required Skills */}
                    <div className="jps-card-stats">
                      <div className="jps-card-stat">
                        <span className="jps-attr-label">Job Role</span>
                        <span className="jps-attr-value">{stats.job_title}</span>
                      </div>
                      <div className="jps-card-stat">
                        <span className="jps-attr-label">Status</span>
                        <span className={`jps-jobstatus ${jobStatusClass(stats.status)}`}>{stats.status}</span>
                      </div>
                      <div className="jps-card-stat">
                        <span className="jps-attr-label">Interview Rounds</span>
                        <span className="jps-attr-value">{stats.rounds.length}</span>
                      </div>
                      <div className="jps-card-stat">
                        <span className="jps-attr-label">Total Applicants</span>
                        <span className="jps-attr-value">{stats.total_applicants}</span>
                      </div>
                      <div className="jps-card-stat">
                        <span className="jps-attr-label">Total Selected</span>
                        <span className="jps-attr-value jps-attr-value--green">{stats.hired_count}</span>
                      </div>
                    </div>

                    <div className="jps-card-stats-divider" />

                    <span className="jps-col-label">Required Skills</span>
                    {stats.required_skills.length > 0 ? (
                      <div className="jps-skills-wrap">
                        {stats.required_skills.map((s) => (
                          <span key={s} className="jps-skill-tag">{s}</span>
                        ))}
                      </div>
                    ) : (
                      <p className="jps-state-sm">No required skills listed.</p>
                    )}
                  </div>
                  <div className="jps-card-col-sep" />
                  <div className="jps-card-desc-col">
                    <span className="jps-col-label">Description</span>
                    <p className="jps-desc-text">{stats.description}</p>
                  </div>
                </div>

              </div>
            </aside>

            {/* ── Right: interview rounds (~40%) ── */}
            <section className="jps-right">
              <h2 className="jps-rounds-heading">Interview Rounds</h2>

              {stats.rounds.length === 0 ? (
                <p className="jps-state-text">No interview rounds configured.</p>
              ) : (
                <div className="jps-rounds-list">
                  {stats.rounds.map((round) => {
                    const isSelected = selectedRound === round.round_order
                    return (
                      <div
                        key={round.round_order}
                        className={`jps-round-block ${isSelected ? 'jps-round-block--active' : ''}`}
                      >
                        <button className="jps-round-row" onClick={() => handleSelectRound(round.round_order)}>
                          <span className="jps-round-num">{round.round_order}</span>
                          <span className="jps-round-name">{round.round_type_name}</span>
                          <span className="jps-round-count">
                            {round.applicants_count} {round.applicants_count === 1 ? 'candidate' : 'candidates'}
                          </span>
                          {round.failing_criteria !== null && (
                            <span className="jps-round-threshold">{round.failing_criteria}% pass</span>
                          )}
                          <span className="jps-round-chevron">{isSelected ? '▲' : '▼'}</span>
                        </button>

                        {isSelected && (
                          <div className="jps-candidates-area">
                            {!isOralRoundType(round.round_type_name) && (
                              <p className="jps-state-sm jps-no-schedule-note">
                                Scheduling isn't available for written-test rounds — candidates start these on their own.
                              </p>
                            )}

                            {candidatesLoading ? (
                              <p className="jps-state-sm">Loading candidates…</p>
                            ) : candidates.length === 0 ? (
                              <p className="jps-state-sm">No candidates in this round yet.</p>
                            ) : (
                              <ul className="jps-candidates-list">
                                {candidates.map((c) => (
                                  <li key={c.interview_id} className="jps-candidate-row" onClick={() => handleOpenCandidate(c)}>
                                    <div className="jps-cand-avatar">{c.name.charAt(0).toUpperCase()}</div>
                                    <span className="jps-cand-name">{c.name}</span>
                                    {c.status.toLowerCase() === 'scheduled' && c.scheduled_at && (
                                      <span className="jps-cand-scheduled-at">
                                        {new Date(c.scheduled_at).toLocaleString(undefined, {
                                          month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
                                        })}
                                      </span>
                                    )}
                                    {c.status.toLowerCase() === 'scheduled' && isOralRoundType(round.round_type_name) && (
                                      <button
                                        type="button"
                                        className="jps-schedule-btn"
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          handleScheduleClick(c)
                                        }}
                                      >
                                        {c.scheduled_at ? 'Reschedule via Calendar' : 'Schedule via Calendar'}
                                      </button>
                                    )}
                                    {c.status.toLowerCase() === 'scheduled' && c.scheduled_at && new Date(c.scheduled_at) > new Date() && (
                                      <button
                                        type="button"
                                        className="jps-delete-btn"
                                        disabled={deletingInterviewId === c.interview_id}
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          handleDeleteInterview(c)
                                        }}
                                      >
                                        {deletingInterviewId === c.interview_id ? 'Deleting…' : 'Delete'}
                                      </button>
                                    )}
                                    <span className={`jps-iv-badge ${ivStatusClass(c.status)}`}>{c.status}</span>
                                  </li>
                                ))}
                              </ul>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )}

              {/* ── Candidate dialog: confined to this pane only ── */}
              {dialogOpen && dialogCandidate && (
                <div className="jps-backdrop" onClick={handleCloseDialog}>
                  <div className="jps-dialog" onClick={(e) => e.stopPropagation()}>

                    {/* Header */}
                    <div className="jps-dialog-header">
                      <div>
                        <span className="jps-dialog-eyebrow">Candidate Detail</span>
                        <h3 className="jps-dialog-title">{dialogCandidate.name}</h3>
                      </div>
                      <div className="jps-dialog-header-right">
                        <span className={`jps-iv-badge ${ivStatusClass(dialogCandidate.status)}`}>{dialogCandidate.status}</span>
                        <button className="jps-close-btn" onClick={handleCloseDialog} aria-label="Close">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                            <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                          </svg>
                        </button>
                      </div>
                    </div>

                    {/* Body */}
                    {panelLoading ? (
                      <div className="jps-dialog-body jps-dialog-body--center">
                        <p className="jps-state-text">Loading candidate data…</p>
                      </div>
                    ) : panel ? (
                      <div className="jps-dialog-body">

                        {/* Interview Progress */}
                        <div className="jps-dialog-progress">
                          <span className="jps-section-label">Interview Progress</span>

                          {/* Horizontal round cards row */}
                          <div className="jps-progress-cards-row">
                            {panel.progress.map((p) => {
                              const completed = isCompleted(p.status)
                              const isActive = selectedProgressId === p.interview_id
                              return (
                                <button
                                  key={p.round_order}
                                  className={`jps-progress-card ${isActive ? 'jps-progress-card--active' : ''} ${completed ? 'jps-progress-card--clickable' : ''}`}
                                  onClick={() => completed && p.interview_id ? handleSelectProgress(p.interview_id) : undefined}
                                  disabled={!completed}
                                >
                                  <span className="jps-pc-num">{p.round_order}</span>
                                  <span className="jps-pc-name">{p.round_type_name}</span>
                                  {p.status ? (
                                    <span className={`jps-iv-badge ${ivStatusClass(p.status)}`}>{p.status}</span>
                                  ) : (
                                    <span className="jps-iv-badge jps-iv--default">Not started</span>
                                  )}
                                  {p.result !== null && (
                                    <span className="jps-pc-score">{p.result.toFixed(1)}</span>
                                  )}
                                </button>
                              )
                            })}
                          </div>

                          {/* Details box */}
                          <div className="jps-qa-box">
                            {!selectedProgressId ? (
                              <p className="jps-qa-placeholder">
                                {panel.progress.some((p) => isCompleted(p.status))
                                  ? 'Click a completed round above to view questions and scores.'
                                  : 'No completed rounds yet. Q&A will appear here once an interview is completed.'}
                              </p>
                            ) : qaLoading === selectedProgressId ? (
                              <p className="jps-state-sm">Loading Q&A…</p>
                            ) : !selectedQA || selectedQA.length === 0 ? (
                              <p className="jps-state-sm">No questions recorded for this round.</p>
                            ) : (
                              <ol className="jps-qa-list">
                                {selectedQA.map((q, i) => (
                                  <li key={i} className="jps-qa-item">
                                    <div className="jps-qa-q-row">
                                      <span className="jps-qa-num">Q{i + 1}</span>
                                      <span className="jps-qa-qtext">{q.question_text}</span>
                                      {q.score !== null && (
                                        <span className="jps-qa-score">{q.score}/10</span>
                                      )}
                                    </div>
                                    {q.candidate_answer && (
                                      <p className="jps-qa-answer">{q.candidate_answer}</p>
                                    )}
                                    {q.notes && <p className="jps-qa-notes">{q.notes}</p>}
                                  </li>
                                ))}
                              </ol>
                            )}
                          </div>
                        </div>

                        <div className="jps-dialog-divider" />

                        {/* Candidate Info */}
                        <div className="jps-dialog-info">
                          <span className="jps-section-label">Candidate Information</span>

                          <div className="jps-info-fields">
                            {panel.candidate.job_role && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">Job Role</span>
                                <span className="jps-info-value">{panel.candidate.job_role}</span>
                              </div>
                            )}
                            {panel.candidate.experience_level && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">Experience Level</span>
                                <span className="jps-info-value">{panel.candidate.experience_level}</span>
                              </div>
                            )}
                            {expYears(panel.candidate.experience_years_min, panel.candidate.experience_years_max) && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">Experience</span>
                                <span className="jps-info-value">
                                  {expYears(panel.candidate.experience_years_min, panel.candidate.experience_years_max)}
                                </span>
                              </div>
                            )}
                            <div className="jps-info-field">
                              <span className="jps-info-label">Email</span>
                              <span className="jps-info-value jps-info-value--muted">{panel.candidate.email}</span>
                            </div>
                            {panel.candidate.phone && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">Phone</span>
                                <span className="jps-info-value">{panel.candidate.phone}</span>
                              </div>
                            )}
                            {panel.candidate.linkedin_url && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">LinkedIn</span>
                                <a
                                  href={panel.candidate.linkedin_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="jps-info-link"
                                >
                                  {panel.candidate.linkedin_url.replace(/^https?:\/\/(www\.)?/i, '')}
                                </a>
                              </div>
                            )}
                            {panel.candidate.current_location && (
                              <div className="jps-info-field">
                                <span className="jps-info-label">Location</span>
                                <span className="jps-info-value">{panel.candidate.current_location}</span>
                              </div>
                            )}
                            {panel.candidate.bio && (
                              <div className="jps-info-field jps-info-field--full">
                                <span className="jps-info-label">Bio</span>
                                <p className="jps-info-bio">{panel.candidate.bio}</p>
                              </div>
                            )}
                          </div>

                          {panel.candidate.skills.length > 0 && (
                            <div className="jps-info-skills">
                              <span className="jps-info-label">Skills</span>
                              <div className="jps-skills-wrap">
                                {panel.candidate.skills.map((sk) => (
                                  <span key={sk.name} className="jps-skill-tag">
                                    {sk.name}
                                    {sk.proficiency_level && (
                                      <span className="jps-skill-level">{sk.proficiency_level}</span>
                                    )}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>

                      </div>
                    ) : (
                      <div className="jps-dialog-body jps-dialog-body--center">
                        <p className="jps-state-text">Failed to load candidate data.</p>
                      </div>
                    )}

                  </div>
                </div>
              )}
            </section>
          </>
        ) : null}
      </div>
    </main>
  )
}

export default JobPostStats
