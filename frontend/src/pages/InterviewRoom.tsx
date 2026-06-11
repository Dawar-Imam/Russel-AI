import BackButton from '../components/BackButton'
import '../css/InterviewRoom.css'

function InterviewRoom() {
  return (
    <main className="interview-room-page">
      <BackButton />
      <h1 className="interview-room-heading">Interview Room</h1>
      <p className="interview-room-subtitle">Your interview session will begin here.</p>
    </main>
  )
}

export default InterviewRoom
