import { useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import logo from '../utils/logo.png'
import '../css/Home.css'

function Home() {
  const navigate = useNavigate()

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
          <Button variant="primary" onClick={() => navigate('/auth')}>
            Sign In / Sign Up
          </Button>
          <Button variant="secondary" onClick={() => navigate('/jobs')}>
            View Jobs
          </Button>
        </div>
      </div>
    </main>
  )
}

export default Home
