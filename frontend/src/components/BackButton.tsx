import { useNavigate } from 'react-router-dom'
import '../css/BackButton.css'

function BackButton() {
  const navigate = useNavigate()

  return (
    <button type="button" className="back-button" onClick={() => navigate(-1)} aria-label="Go back">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M15 18l-6-6 6-6" />
      </svg>
      Back
    </button>
  )
}

export default BackButton
