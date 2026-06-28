import { useNavigate } from 'react-router-dom'
import Button from './Button'
import type { MyApplicationItem } from '../api/applications'
import '../css/ApplicationCard.css'

const STATUS_LABELS: Record<string, string> = {
  ATS_PENDING: 'ATS Pending',
  ATS_PASS: 'ATS Passed',
  ATS_FAIL: 'ATS Failed',
  IN_PROGRESS: 'In Progress',
  INTERVIEW_PASS: 'Interview Passed',
  INTERVIEW_FAILED: 'Interview Failed',
  HIRED: 'Hired',
  REJECTED: 'Rejected',
}

const STATUS_VARIANTS: Record<string, string> = {
  ATS_PENDING: 'pending',
  ATS_PASS: 'pass',
  ATS_FAIL: 'fail',
  IN_PROGRESS: 'progress',
  INTERVIEW_PASS: 'pass',
  INTERVIEW_FAILED: 'fail',
  HIRED: 'hired',
  REJECTED: 'rejected',
}

function buildStatusLabel(status: string, roundTitle: string | null): string {
  if ((status === 'INTERVIEW_PASS' || status === 'INTERVIEW_FAILED') && roundTitle) {
    const outcome = status === 'INTERVIEW_PASS' ? 'Passed' : 'Failed'
    return `${roundTitle} ${outcome}`
  }
  return STATUS_LABELS[status] ?? status
}

interface ApplicationCardProps {
  application: MyApplicationItem
}

function ApplicationCard({ application: app }: ApplicationCardProps) {
  const navigate = useNavigate()
  const statusLabel = buildStatusLabel(app.status, app.latest_interview_round_title)
  const statusVariant = STATUS_VARIANTS[app.status] ?? 'pending'

  return (
    <article className="app-card">
      <div className="app-card-content">
        <h2 className="app-card-title">{`${app.experience_level_name} ${app.job_role_title}`}</h2>
        <p className="app-card-description">{app.description}</p>
        <span className="app-card-company">{app.company}</span>
        <div className="app-card-meta">
          {app.job_type && (
            <div className="app-card-meta-item">
              <span className="app-card-meta-label">Type</span>
              <span className="app-card-meta-value">{app.job_type}</span>
            </div>
          )}
          {app.location && (
            <div className="app-card-meta-item">
              <span className="app-card-meta-label">Location</span>
              <span className="app-card-meta-value">{app.location}</span>
            </div>
          )}
          {app.salary_range && (
            <div className="app-card-meta-item">
              <span className="app-card-meta-label">Salary</span>
              <span className="app-card-meta-value">{app.salary_range}</span>
            </div>
          )}
          <div className="app-card-meta-item">
            <span className="app-card-meta-label">Status</span>
            <span className={`app-card-status app-card-status--${statusVariant}`}>{statusLabel}</span>
          </div>
        </div>
      </div>
      <Button
        variant="secondary"
        className="app-card-action"
        onClick={() => navigate(`/application-progress/${app.application_id}`)}
      >
        Check Application
      </Button>
    </article>
  )
}

export default ApplicationCard
