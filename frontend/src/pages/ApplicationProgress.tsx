import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Button from '../components/Button'
import { runAts } from '../api/applications'
import '../css/ApplicationProgress.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

interface RoundInfo {
  interview_round_id: string
  interview_id: string | null
  title: string
  round_order: number
  status: string | null
  feedback: string | null
  result: number | null
  scheduled_at: string | null
  completed_at: string | null
  avg_score: number | null
}

interface StagesData {
  application_id: string
  rounds: RoundInfo[]
  current_round_id: string | null
  ats_status: 'pending' | 'pass' | 'fail'
  ats_reason: string | null
  ats_role_assessment: string | null
  ats_experience_assessment: string | null
  ats_skills_matched: string[]
  ats_skills_missing: string[]
  ats_projects_assessment: string | null
  application_status: string | null
  job_role_title: string | null
  experience_level_name: string | null
  company: string | null
}

interface QuestionItem {
  question_id: string
  question_text: string
  candidate_answer: string | null
  score: number | null
  notes: string | null
}

function scoreVerdict(result: number | null): 'pass' | 'fail' | null {
  if (result == null) return null
  return result >= 6 ? 'pass' : 'fail'
}

function isRoundCompleted(round: RoundInfo): boolean {
  const s = (round.status ?? '').toLowerCase()
  return s === 'pass' || s === 'failed' || s === 'completed'
}

function getRoundBadgeClass(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (isRoundCompleted(round)) {
    if (s === 'pass') return 'ap-stage-badge--pass'
    if (s === 'failed' || s === 'fail') return 'ap-stage-badge--fail'
    const v = scoreVerdict(round.result)
    if (v === 'pass') return 'ap-stage-badge--pass'
    if (v === 'fail') return 'ap-stage-badge--fail'
    return 'ap-stage-badge--pass'
  }
  if (s === 'in progress') return 'ap-stage-badge--in-progress'
  if (s === 'scheduled') return 'ap-stage-badge--scheduled'
  return 'ap-stage-badge--not-started'
}

function isRoundNotNeeded(round: RoundInfo): boolean {
  return (round.status ?? '').toLowerCase() === 'not needed'
}

function getRoundLabel(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (s === 'pass') return 'Passed'
  if (s === 'failed' || s === 'fail') return 'Failed'
  if (s === 'completed') {
    const v = scoreVerdict(round.result)
    if (v === 'pass') return 'Passed'
    if (v === 'fail') return 'Failed'
    return 'Completed'
  }
  if (s === 'in progress') return 'In Progress'
  if (s === 'scheduled') return 'Pending'
  if (s === 'not needed') return 'Not Needed'
  return 'Not Started'
}

function getScoreColor(score: number): string {
  if (score >= 7) return 'var(--color-primary)'
  if (score >= 4) return 'var(--color-primary-dark)'
  return 'var(--color-text-primary)'
}

function ApplicationProgress() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const navigate = useNavigate()

  const [testMode, setTestMode] = useState(() => localStorage.getItem('russell_test_mode') === '1')
  const [data, setData] = useState<StagesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [atsError, setAtsError] = useState(false)
  const [selectedRoundId, setSelectedRoundId] = useState<string | null>(null)
  const [roundQuestions, setRoundQuestions] = useState<Record<string, QuestionItem[]>>({})
  const [loadingQuestions, setLoadingQuestions] = useState<Record<string, boolean>>({})
  const atsTriggered = useRef(false)
  const fetchedRounds = useRef<Set<string>>(new Set())

  function toggleTestMode() {
    setTestMode(prev => {
      const next = !prev
      localStorage.setItem('russell_test_mode', next ? '1' : '0')
      return next
    })
  }

  function fetchRoundQuestions(round: RoundInfo) {
    if (!round.interview_id || fetchedRounds.current.has(round.interview_round_id)) return
    fetchedRounds.current.add(round.interview_round_id)
    setLoadingQuestions(prev => ({ ...prev, [round.interview_round_id]: true }))
    fetch(`${API_BASE}/api/applications/${applicationId}/interviews/${round.interview_id}/questions`)
      .then(res => res.ok ? res.json() as Promise<QuestionItem[]> : Promise.resolve([]))
      .then(items => setRoundQuestions(prev => ({ ...prev, [round.interview_round_id]: items })))
      .catch(() => setRoundQuestions(prev => ({ ...prev, [round.interview_round_id]: [] })))
      .finally(() => setLoadingQuestions(prev => ({ ...prev, [round.interview_round_id]: false })))
  }

  const currentRound = data?.rounds.find(r => r.interview_round_id === data.current_round_id)
  const allRoundsCompleted =
    data != null && data.ats_status === 'pass' &&
    (!data.current_round_id || currentRound?.status === 'Completed')

  const failedRound = data?.rounds.find(r => (r.status ?? '').toLowerCase() === 'failed')
  const isTerminal = data != null && data.ats_status === 'pass' &&
    (failedRound != null || (allRoundsCompleted && data.rounds.length > 0))
  const latestRound = isTerminal
    ? (failedRound ?? [...(data?.rounds ?? [])].reverse().find(r => r.status != null) ?? null)
    : null

  function getOutcomeInfo(): { title: string } {
    const appStatus = data?.application_status
    if (appStatus === 'HIRED') return { title: 'Congratulations! You have been hired.' }
    if (appStatus === 'REJECTED') return { title: 'Your application was not successful.' }
    if (failedRound) return { title: `You did not pass the ${failedRound.title} round.` }
    if (allRoundsCompleted && data && data.rounds.length > 0)
      return { title: 'You have completed all interview rounds.' }
    return { title: 'Interview process complete.' }
  }

  useEffect(() => {
    if (!applicationId) return
    fetch(`${API_BASE}/api/applications/${applicationId}/interview-stages`)
      .then(res => {
        if (!res.ok) throw new Error(`Server error ${res.status}`)
        return res.json() as Promise<StagesData>
      })
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load stages'))
      .finally(() => setLoading(false))
  }, [applicationId])

  // Set default selected breadcrumb once data loads
  useEffect(() => {
    if (!data || selectedRoundId !== null) return
    if (data.ats_status !== 'pass') {
      setSelectedRoundId('ats')
    } else if (data.current_round_id) {
      setSelectedRoundId(data.current_round_id)
    } else {
      const last = data.rounds[data.rounds.length - 1]
      setSelectedRoundId(last?.interview_round_id ?? 'ats')
    }
  }, [data, selectedRoundId])

  useEffect(() => {
    if (!applicationId || !data || data.ats_status !== 'pending' || atsTriggered.current) return
    atsTriggered.current = true
    runAts(applicationId)
      .then(result => {
        setData(prev =>
          prev
            ? {
                ...prev,
                ats_status: result.eligible ? 'pass' : 'fail',
                ats_reason: result.reason,
                ats_role_assessment: result.role_assessment,
                ats_experience_assessment: result.experience_assessment,
                ats_skills_matched: result.skills_matched,
                ats_skills_missing: result.skills_missing,
                ats_projects_assessment: result.projects_assessment,
              }
            : prev
        )
      })
      .catch(() => setAtsError(true))
  }, [applicationId, data])

  // Fetch questions when a completed round is selected
  useEffect(() => {
    if (!data || !selectedRoundId || selectedRoundId === 'ats') return
    const round = data.rounds.find(r => r.interview_round_id === selectedRoundId)
    if (round && isRoundCompleted(round)) fetchRoundQuestions(round)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRoundId, data])

  // True when the panel is showing a completed round's Q&A (× button should appear)
  const qaRound = (selectedRoundId && selectedRoundId !== 'ats')
    ? data?.rounds.find(r => r.interview_round_id === selectedRoundId && isRoundCompleted(r)) ?? null
    : null
  const isQAView = qaRound !== null

  function closeQA() { setSelectedRoundId(null) }

  function renderQABlock(round: RoundInfo) {
    const verdictKey = scoreVerdict(round.result) ?? 'pending'
    const questions = roundQuestions[round.interview_round_id] ?? []
    const questionsLoading = loadingQuestions[round.interview_round_id] ?? false
    return (
      <div className="ap-detail-qa">
        <div className="ap-detail-meta">
          <div className="ap-detail-meta-item">
            <span className="ap-detail-meta-label">Verdict</span>
            <span className={`ap-detail-meta-value ap-detail-meta-value--${verdictKey}`}>
              {verdictKey === 'pass' ? 'Passed' : verdictKey === 'fail' ? 'Failed' : 'Completed'}
            </span>
          </div>
          {round.avg_score != null && (
            <div className="ap-detail-meta-item">
              <span className="ap-detail-meta-label">Avg. Score</span>
              <span className="ap-detail-meta-value">{round.avg_score.toFixed(1)} / 10</span>
            </div>
          )}
        </div>
        {round.feedback && <p className="ap-detail-feedback">{round.feedback}</p>}
        {questionsLoading ? (
          <p className="ap-qa-loading">Loading questions…</p>
        ) : questions.length > 0 ? (
          <div className="ap-qa-section">
            <p className="ap-qa-section-label">Interview Q&amp;A</p>
            <div className="ap-qa-list">
              {questions.map((q, qi) => (
                <div key={q.question_id} className="ap-qa-item">
                  <div className="ap-qa-header">
                    <span className="ap-qa-num">Q{qi + 1}</span>
                    {q.score != null && (
                      <span className="ap-qa-score" style={{ color: getScoreColor(q.score) }}>
                        {q.score}/10
                      </span>
                    )}
                  </div>
                  <p className="ap-qa-question">{q.question_text}</p>
                  {q.candidate_answer ? (
                    <p className="ap-qa-answer">{q.candidate_answer}</p>
                  ) : (
                    <p className="ap-qa-answer ap-qa-answer--empty">No answer recorded</p>
                  )}
                  {q.notes && <p className="ap-qa-notes">{q.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  function renderAtsBreakdown() {
    if (!data) return null
    const hasBreakdown =
      data.ats_role_assessment ||
      data.ats_experience_assessment ||
      data.ats_projects_assessment ||
      data.ats_skills_matched.length > 0 ||
      data.ats_skills_missing.length > 0
    if (!hasBreakdown) return null
    return (
      <div className="ap-ats-breakdown">
        {data.job_role_title && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Job Role</span>
            <span className="ap-ats-item-value">
              {data.experience_level_name ? `${data.experience_level_name} ` : ''}
              {data.job_role_title}
            </span>
          </div>
        )}
        {data.ats_role_assessment && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Role Fit</span>
            <p className="ap-ats-item-value">{data.ats_role_assessment}</p>
          </div>
        )}
        {data.ats_experience_assessment && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Experience Fit</span>
            <p className="ap-ats-item-value">{data.ats_experience_assessment}</p>
          </div>
        )}
        {data.ats_projects_assessment && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Projects &amp; Experience</span>
            <p className="ap-ats-item-value">{data.ats_projects_assessment}</p>
          </div>
        )}
        {data.ats_skills_matched.length > 0 && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Skills Matched</span>
            <div className="ap-ats-tag-list">
              {data.ats_skills_matched.map(skill => (
                <span key={skill} className="ap-ats-tag ap-ats-tag--matched">{skill}</span>
              ))}
            </div>
          </div>
        )}
        {data.ats_skills_missing.length > 0 && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Skills Missing</span>
            <div className="ap-ats-tag-list">
              {data.ats_skills_missing.map(skill => (
                <span key={skill} className="ap-ats-tag ap-ats-tag--missing">{skill}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    )
  }

  function renderDetailContent() {
    if (!data) return null

    // ATS failed / error
    if (data.ats_status === 'fail' || atsError) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening Failed</p>
          {data.ats_reason && <p className="ap-detail-msg-body">{data.ats_reason}</p>}
          {renderAtsBreakdown()}
        </div>
      )
    }

    // ATS pending
    if (data.ats_status === 'pending') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening in progress…</p>
          <p className="ap-detail-msg-body">Please check back shortly.</p>
        </div>
      )
    }

    // Nothing selected (after closing Q&A)
    if (!selectedRoundId) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">Select a round</p>
          <p className="ap-detail-msg-body">Click an interview round on the left to view its Q&amp;A and status.</p>
        </div>
      )
    }

    // ATS breadcrumb selected
    if (selectedRoundId === 'ats') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening Passed</p>
          {data.ats_reason && <p className="ap-detail-msg-body">{data.ats_reason}</p>}
          {renderAtsBreakdown()}
        </div>
      )
    }

    // Round breadcrumb selected
    const round = data.rounds.find(r => r.interview_round_id === selectedRoundId)
    if (!round) return null

    const s = (round.status ?? '').toLowerCase()

    if (s === 'in progress') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title} interview in progress</p>
        </div>
      )
    }

    if (isRoundNotNeeded(round)) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title}</p>
          <p className="ap-detail-msg-body">Not needed — a prior round was not passed.</p>
        </div>
      )
    }

    if (!isRoundCompleted(round)) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title}</p>
          <p className="ap-detail-msg-body">This round hasn't started yet.</p>
        </div>
      )
    }

    // Completed — Q&A
    return renderQABlock(round)
  }

  return (
    <main className="app-progress-page">
      <div className="app-progress-body">

        {/* Heading row */}
        <div className="app-progress-heading-row">
          <h1 className="app-progress-heading">Application Progress</h1>
          <div className="app-progress-heading-actions">
            <button
              className={`test-mode-toggle${testMode ? ' test-mode-toggle--on' : ''}`}
              onClick={toggleTestMode}
              title="Toggle test mode to jump to any interview round"
            >
              <span className="test-mode-toggle-track">
                <span className="test-mode-toggle-thumb" />
              </span>
              <span className="test-mode-toggle-label">Test Mode</span>
            </button>
            {data && !isTerminal && !allRoundsCompleted && data.ats_status !== 'fail' && !atsError && (
              <Button
                variant="primary"
                className="app-progress-cta"
                onClick={() => {
                  if (currentRound?.interview_id) {
                    navigate(`/interview-room/${currentRound.interview_id}`)
                  }
                }}
                disabled={!data.current_round_id || data.ats_status === 'pending'}
              >
                {data.ats_status === 'pending' ? 'ATS Screening…' : 'Go To Interview Room'}
              </Button>
            )}
          </div>
        </div>

        {loading && <p className="stages-status-text">Loading…</p>}
        {error && <p className="stages-status-text stages-error">{error}</p>}

        {data && (
          <>
            {/* Horizontal bubble timeline */}
            <div className="app-progress-timeline">
              <div className="stage-bubble-wrapper">
                <div className={`stage-bubble${data.ats_status === 'pending' ? ' stage-bubble--ats-pending' : ''}`}>
                  {data.ats_status === 'pending' && 'ATS\nChecking…'}
                  {data.ats_status === 'pass' && 'ATS\nPass'}
                  {data.ats_status === 'fail' && 'ATS\nFailed'}
                </div>
                {data.ats_status === 'pending' && (
                  <span className="stage-current-label">ATS Checking…</span>
                )}
                {data.ats_status === 'fail' && (
                  <span className="stage-current-label stage-current-label--static">ATS Failed</span>
                )}
              </div>
              {data.rounds.map(round => (
                <div key={round.interview_round_id} className="stage-bubble-wrapper">
                  <div className="stage-bubble">{round.title}</div>
                  {!isTerminal && data.ats_status === 'pass' && round.interview_round_id === data.current_round_id && (
                    <span className="stage-current-label">Current Round</span>
                  )}
                </div>
              ))}
            </div>

            {/* Left / right pane row */}
            <div className="ap-content-row">

              {/* Left pane: job card + breadcrumbs */}
              <div className="ap-left-pane">

                {/* Job card */}
                {(data.job_role_title || data.company) && (
                  <div className="ap-job-card">
                    {data.job_role_title && (
                      <span className="ap-job-role">{data.job_role_title}</span>
                    )}
                    {data.experience_level_name && (
                      <span className="ap-job-level">{data.experience_level_name}</span>
                    )}
                    {data.company && (
                      <span className="ap-job-company">{data.company}</span>
                    )}
                    <span className="ap-job-rounds">
                      {data.rounds.length} Round{data.rounds.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                )}

                {/* Outcome banner — shown once the interview process is terminal */}
                {isTerminal && (
                  <div className="ap-outcome-block">
                    <p className="ap-outcome-block-title">{getOutcomeInfo().title}</p>
                    {latestRound?.status && (
                      <span className={`ap-stage-badge ${getRoundBadgeClass(latestRound)}`}>
                        {latestRound.title}: {getRoundLabel(latestRound)}
                      </span>
                    )}
                    {latestRound?.feedback && (
                      <p className="ap-outcome-block-feedback">{latestRound.feedback}</p>
                    )}
                  </div>
                )}

                {/* Breadcrumbs */}
                <div className="ap-breadcrumbs">
                  <span className="ap-breadcrumbs-label">Interview Rounds</span>
                  <button
                    className={`ap-crumb${selectedRoundId === 'ats' ? ' ap-crumb--active' : ''}`}
                    onClick={() => setSelectedRoundId('ats')}
                  >
                    ATS Screening
                  </button>
                  {data.rounds.map(round => (
                    <button
                      key={round.interview_round_id}
                      className={`ap-crumb${selectedRoundId === round.interview_round_id ? ' ap-crumb--active' : ''}`}
                      onClick={() => setSelectedRoundId(round.interview_round_id)}
                    >
                      {round.title}
                    </button>
                  ))}
                </div>

              </div>

              {/* Right pane: blurred detail panel */}
              <div className="ap-right-pane">
                <div className="ap-detail-panel">
                  {isQAView && (
                    <div className="ap-panel-close-row">
                      <button className="ap-panel-close-btn" onClick={closeQA} title="Close Q&A">×</button>
                    </div>
                  )}
                  <div className="ap-panel-body">
                    {renderDetailContent()}
                  </div>
                </div>
              </div>

              {/* Rightmost: test-mode jump panel — only when test mode on */}
              {testMode && (
                <div className="ap-test-panel">
                  <span className="ap-test-panel-label">Jump to round</span>
                  <div className="ap-test-panel-list">
                    {data.rounds.map(round =>
                      round.interview_id && (
                        <button
                          key={round.interview_round_id}
                          className="ap-test-panel-btn"
                          onClick={() => navigate(`/interview-room/${round.interview_id}`)}
                        >
                          {round.title}
                        </button>
                      )
                    )}
                  </div>
                </div>
              )}

            </div>

          </>
        )}

      </div>
    </main>
  )
}

export default ApplicationProgress
