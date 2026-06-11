import { Link } from 'react-router-dom'
import JobCard from '../components/JobCard'
import BackButton from '../components/BackButton'
import { JOB_POSTS } from '../data/jobs'
import logo from '../utils/logo.png'
import '../css/Jobs.css'

function Jobs() {
  return (
    <main className="jobs-page">
      <BackButton />
      <header className="jobs-header">
        <Link to="/" className="jobs-brand">
          <span className="jobs-brand-title">
            <span className="jobs-brand-primary">Russel</span>
            <span className="jobs-brand-accent">.AI</span>
          </span>
          <img src={logo} alt="Russel.AI logo" className="jobs-logo" />
        </Link>
        <h1 className="jobs-heading">Open Positions</h1>
      </header>

      <div className="jobs-list">
        {JOB_POSTS.map((job) => (
          <JobCard key={job.id} job={job} />
        ))}
      </div>
    </main>
  )
}

export default Jobs
