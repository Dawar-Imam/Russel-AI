import '../css/ParticipantCard.css'

interface ParticipantCardProps {
  name: string
  isLocal?: boolean
  isSpeaking?: boolean
}

function ParticipantCard({ name, isLocal, isSpeaking }: ParticipantCardProps) {
  const displayName = isLocal ? 'You' : name
  const initial = displayName.trim().charAt(0).toUpperCase() || '?'

  return (
    <div className={`pc-card${isSpeaking ? ' pc-card--speaking' : ''}`}>
      <div className="pc-avatar">{initial}</div>
      <span className="pc-name">{displayName}</span>
    </div>
  )
}

export default ParticipantCard
