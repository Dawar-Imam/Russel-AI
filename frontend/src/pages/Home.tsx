import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import logoDark from '../utils/dark/logo.png'
import logoLight from '../utils/white/logo.png'
import { useTheme } from '../utils/useTheme'
import '../css/Home.css'

function readDashboardRoute(): string | null {
  const userType = sessionStorage.getItem('userType')
  if (userType === 'candidate' && sessionStorage.getItem('candidateId')) return '/my-applications'
  if (userType === 'recruiter' && sessionStorage.getItem('recruiterId')) return '/recruiter-dashboard'
  return null
}

function Home() {
  const navigate = useNavigate()
  const theme = useTheme()
  const logo = theme === 'light' ? logoLight : logoDark
  const [dashboardRoute, setDashboardRoute] = useState<string | null>(readDashboardRoute)

  useEffect(() => {
    function syncAuth() {
      setDashboardRoute(readDashboardRoute())
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
            <Button variant="secondary" className="home-view-jobs-btn" onClick={() => navigate('/jobs')}>
              View Jobs
            </Button>
          </div>

          {dashboardRoute && (
            <Button
              variant="secondary"
              className="home-dashboard-btn"
              onClick={() => navigate(dashboardRoute)}
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
