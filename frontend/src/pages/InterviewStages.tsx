import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Button from '../components/Button'
import BackButton from '../components/BackButton'
import '../css/InterviewStages.css'

const API_BASE = 'http://localhost:8000'

interface RoundInfo {
  interview_round_id: string
  interview_id: string | null
  title: string
  round_order: number
  status: string | null
}

interface StagesData {
  application_id: string
  rounds: RoundInfo[]
  current_round_id: string | null
}

function InterviewStages() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const navigate = useNavigate()

  const [data, setData] = useState<StagesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const currentRound = data?.rounds.find(
    (r) => r.interview_round_id === data.current_round_id,
  )
  const allCompleted =
    data != null && (!data.current_round_id || currentRound?.status === 'completed')

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

  return (
    <main className="interview-stages-page">
      <BackButton />
      <h1 className="interview-stages-heading">Interview Stages</h1>

      {loading && <p className="stages-status-text">Loading interview stages…</p>}

      {error && <p className="stages-status-text stages-error">{error}</p>}

      {data && (
        <div className="interview-stages-list">
          {data.rounds.map((round) => (
            <div key={round.interview_round_id} className="stage-bubble-wrapper">
              <div className="stage-bubble">{round.title}</div>
              {round.interview_round_id === data.current_round_id && (
                <span className="stage-current-label">Current Round</span>
              )}
            </div>
          ))}
        </div>
      )}

      {allCompleted ? (
        <p className="stages-completed-text">All interview rounds have been completed.</p>
      ) : (
        <Button
          variant="primary"
          className="interview-stages-cta"
          onClick={() => {
            if (currentRound?.interview_id) {
              navigate(`/interview-room/${currentRound.interview_id}`)
            }
          }}
          disabled={!data || !data.current_round_id}
        >
          Go To Interview Room
        </Button>
      )}
    </main>
  )
}

export default InterviewStages
