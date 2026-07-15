import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Button from '../components/Button'
import { runAts } from '../api/applications'
import '../css/InterviewStages.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

interface RoundInfo {
  interview_round_id: string
  interview_id: string | null
  title: string
  round_order: number
  status: string | null
  feedback: string | null
  result: string | null
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
}

function formatDuration(isoDate: string | null): string {
  if (!isoDate) return '—'
  const diff = Date.now() - new Date(isoDate).getTime()
  const days = Math.floor(diff / 86400000)
  if (days < 1) return 'Less than a day'
  if (days === 1) return '1 day'
  return `${days} days`
}

function getAtsBadgeClass(status: string): string {
  if (status === 'pass') return 'ap-stage-badge--pass'
  if (status === 'fail') return 'ap-stage-badge--fail'
  return 'ap-stage-badge--pending'
}

function getAtsLabel(status: string): string {
  if (status === 'pass') return 'Pass'
  if (status === 'fail') return 'Failed'
  return 'Checking…'
}

function getRoundBadgeClass(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (s === 'completed') {
    const r = (round.result ?? '').toLowerCase()
    if (r.includes('pass')) return 'ap-stage-badge--pass'
    if (r.includes('fail')) return 'ap-stage-badge--fail'
    return 'ap-stage-badge--pass'
  }
  if (s === 'in progress') return 'ap-stage-badge--in-progress'
  if (s === 'scheduled') return 'ap-stage-badge--scheduled'
  return 'ap-stage-badge--not-started'
}

function getRoundLabel(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (s === 'completed') {
    const r = (round.result ?? '').toLowerCase()
    if (r.includes('pass')) return 'Passed'
    if (r.includes('fail')) return 'Failed'
    return 'Completed'
  }
  if (s === 'in progress') return 'In Progress'
  if (s === 'scheduled') return 'Pending'
  return 'Not Started'
}

function InterviewStages() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const navigate = useNavigate()

  const [data, setData] = useState<StagesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openStages, setOpenStages] = useState<Set<string>>(new Set())
  const atsTriggered = useRef(false)

  function toggleStage(id: string) {
    setOpenStages(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const currentRound = data?.rounds.find(
    (r) => r.interview_round_id === data.current_round_id,
  )
  const allRoundsCompleted =
    data != null && data.ats_status === 'pass' &&
    (!data.current_round_id || currentRound?.status === 'Completed')

  useEffect(() => {
    if (!applicationId) return
    fetch(`${API_BASE}/api/applications/${applicationId}/interview-stages`)
      .then((res) => {
        if (!res.ok) throw new Error(`Server error ${res.status}`)
        return res.json() as Promise<StagesData>
      })
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stages'))
      .finally(() => setLoading(false))
  }, [applicationId])

  useEffect(() => {
    if (!applicationId || !data || data.ats_status !== 'pending' || atsTriggered.current) return
    atsTriggered.current = true
    runAts(applicationId)
      .then((result) => {
        setData((prev) =>
          prev
            ? { ...prev, ats_status: result.final_verdict === 'PASS' ? 'pass' : 'fail', ats_reason: result.verdict_summary }
            : prev,
        )
      })
      .catch(() => {})
  }, [applicationId, data])

  const atsOpen = openStages.has('ats')

  return (
    <main className="interview-stages-page">
      <div className="interview-stages-body">
        <h1 className="interview-stages-heading">Application Progress</h1>

        {loading && <p className="stages-status-text">Loading…</p>}
        {error && <p className="stages-status-text stages-error">{error}</p>}

        {data && (
          <>
            {/* Bubble timeline */}
            <div className="interview-stages-list">
              <div className="stage-bubble-wrapper">
                <div
                  className={`stage-bubble${data.ats_status === 'pending' ? ' stage-bubble--ats-pending' : ''}`}
                >
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

              {data.rounds.map((round) => (
                <div key={round.interview_round_id} className="stage-bubble-wrapper">
                  <div className="stage-bubble">{round.title}</div>
                  {data.ats_status === 'pass' && round.interview_round_id === data.current_round_id && (
                    <span className="stage-current-label">Current Round</span>
                  )}
                </div>
              ))}
            </div>

            {/* Stage accordion list */}
            <div className="ap-stages-list">

              {/* ATS row */}
              <div className={`ap-stage${atsOpen ? ' ap-stage--open' : ''}`}>
                <button
                  className={`ap-stage-btn${atsOpen ? ' ap-stage-btn--open' : ''}`}
                  onClick={() => toggleStage('ats')}
                >
                  <span className="ap-stage-index">01</span>
                  <span className="ap-stage-title">ATS Screening</span>
                  <span className={`ap-stage-badge ${getAtsBadgeClass(data.ats_status)}`}>
                    {getAtsLabel(data.ats_status)}
                  </span>
                  <span className="ap-stage-chevron">›</span>
                </button>

                {atsOpen && (
                  <div className="ap-stage-panel">
                    {data.ats_status === 'pending' ? (
                      <p className="ap-stage-detail-reason ap-stage-detail-value--pending">
                        ATS screening is in progress. Please check back shortly.
                      </p>
                    ) : (
                      <>
                        <div className="ap-stage-detail-grid">
                          <div className="ap-stage-detail-item">
                            <span className="ap-stage-detail-label">Verdict</span>
                            <span className={`ap-stage-detail-value ap-stage-detail-value--${data.ats_status}`}>
                              {data.ats_status === 'pass' ? 'Passed' : 'Failed'}
                            </span>
                          </div>
                        </div>
                        {data.ats_reason && (
                          <p className="ap-stage-detail-reason">{data.ats_reason}</p>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Interview round rows */}
              {data.rounds.map((round, i) => {
                const isOpen = openStages.has(round.interview_round_id)
                const isCompleted = (round.status ?? '').toLowerCase() === 'completed'
                const resultLower = (round.result ?? '').toLowerCase()
                const verdictKey = resultLower.includes('pass')
                  ? 'pass'
                  : resultLower.includes('fail')
                  ? 'fail'
                  : 'pending'

                return (
                  <div
                    key={round.interview_round_id}
                    className={`ap-stage${isOpen ? ' ap-stage--open' : ''}`}
                  >
                    <button
                      className={`ap-stage-btn${isOpen ? ' ap-stage-btn--open' : ''}`}
                      onClick={() => toggleStage(round.interview_round_id)}
                    >
                      <span className="ap-stage-index">{String(i + 2).padStart(2, '0')}</span>
                      <span className="ap-stage-title">{round.title}</span>
                      <span className={`ap-stage-badge ${getRoundBadgeClass(round)}`}>
                        {getRoundLabel(round)}
                      </span>
                      <span className="ap-stage-chevron">›</span>
                    </button>

                    {isOpen && (
                      <div className="ap-stage-panel">
                        {!isCompleted ? (
                          <div className="ap-stage-detail-grid">
                            <div className="ap-stage-detail-item">
                              <span className="ap-stage-detail-label">Status</span>
                              <span className="ap-stage-detail-value ap-stage-detail-value--pending">
                                {round.status === 'In Progress' ? 'In Progress' : 'Pending'}
                              </span>
                            </div>
                            <div className="ap-stage-detail-item">
                              <span className="ap-stage-detail-label">Duration</span>
                              <span className="ap-stage-detail-value">
                                {formatDuration(round.scheduled_at)}
                              </span>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="ap-stage-detail-grid">
                              <div className="ap-stage-detail-item">
                                <span className="ap-stage-detail-label">Verdict</span>
                                <span className={`ap-stage-detail-value ap-stage-detail-value--${verdictKey}`}>
                                  {round.result ?? 'Completed'}
                                </span>
                              </div>
                              {round.avg_score != null && (
                                <div className="ap-stage-detail-item">
                                  <span className="ap-stage-detail-label">Avg. Score</span>
                                  <span className="ap-stage-detail-value">
                                    {round.avg_score.toFixed(1)} / 10
                                  </span>
                                </div>
                              )}
                            </div>
                            {round.feedback && (
                              <p className="ap-stage-detail-reason">{round.feedback}</p>
                            )}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </>
        )}

        {allRoundsCompleted ? (
          <p className="stages-completed-text">All interview rounds have been completed.</p>
        ) : (
          data && data.ats_status !== 'fail' && (
            <Button
              variant="primary"
              className="interview-stages-cta"
              onClick={() => {
                if (currentRound?.interview_id) {
                  navigate(`/interview-room/${currentRound.interview_id}`)
                }
              }}
              disabled={!data || !data.current_round_id || data.ats_status === 'pending'}
            >
              {data.ats_status === 'pending' ? 'ATS Screening…' : 'Go To Interview Room'}
            </Button>
          )
        )}
      </div>
    </main>
  )
}

export default InterviewStages
