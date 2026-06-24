import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import logo from '../utils/logo.png'
import '../css/Home.css'

function Home() {
  const navigate = useNavigate()
  const [isCandidate, setIsCandidate] = useState(
    () => sessionStorage.getItem('userType') === 'candidate' && !!sessionStorage.getItem('candidateId'),
  )

  useEffect(() => {
    function syncAuth() {
      setIsCandidate(
        sessionStorage.getItem('userType') === 'candidate' && !!sessionStorage.getItem('candidateId'),
      )
    }
    window.addEventListener('auth-change', syncAuth)
    return () => window.removeEventListener('auth-change', syncAuth)
  }, [])

  return (
    <main className="home-page">
      <div className="home-content">
        <div className="home-brand">
          <h1 className="home-title">
            <span className="home-title-primary">Russel</span>
            <span className="home-title-accent">.AI</span>
          </h1>
          <img src={logo} alt="Russel.AI logo" className="home-logo" />
        </div>

        <p className="home-subtitle">Smart interviews, smart selection</p>

        <div className="home-actions">
          <div className="home-actions-row">
            <Button variant="primary" onClick={() => navigate('/auth')}>
              Sign In / Sign Up
            </Button>
            <Button variant="secondary" onClick={() => navigate('/jobs')}>
              View Jobs
            </Button>
          </div>

          {isCandidate && (
            <Button
              variant="secondary"
              className="home-dashboard-btn"
              onClick={() => navigate('/my-applications')}
            >
              Dashboard
            </Button>
          )}
        </div>
      </div>
    </main>
  )
}

export default Home
