import { useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import BackButton from '../components/BackButton'
import '../css/InterviewStages.css'

interface InterviewStage {
  id: string
  label: string
}

const INTERVIEW_STAGES: InterviewStage[] = [
  { id: 'written', label: 'Technical Written Round' },
  { id: 'code', label: 'Technical Code Round' },
  { id: 'voice', label: 'Voice Agent Interview Round' },
]

const ACTIVE_STAGE_ID = 'written'

function InterviewStages() {
  const navigate = useNavigate()

  return (
    <main className="interview-stages-page">
      <BackButton />
      <h1 className="interview-stages-heading">Interview Stages</h1>

      <div className="interview-stages-list">
        {INTERVIEW_STAGES.map((stage) => (
          <div key={stage.id} className="stage-bubble-wrapper">
            <div className="stage-bubble">{stage.label}</div>
            {stage.id === ACTIVE_STAGE_ID && (
              <span className="stage-current-label">Current Round</span>
            )}
          </div>
        ))}
      </div>

      <Button variant="primary" className="interview-stages-cta" onClick={() => navigate('/interview-room')}>
        Go To Interview Room
      </Button>
    </main>
  )
}

export default InterviewStages
