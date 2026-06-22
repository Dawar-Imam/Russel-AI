import Button from './Button'
import type { JobListItem } from '../api/jobs'
import '../css/JobCard.css'

interface JobCardProps {
  job: JobListItem
  onApply: () => void
}

function JobCard({ job, onApply }: JobCardProps) {
  return (
    <article className="job-card">
      <div className="job-card-content">
        <h2 className="job-card-title">{job.designation}</h2>
        <p className="job-card-description">{job.description}</p>
        <span className="job-card-company">{job.company}</span>
        <div className="job-card-meta">
          {job.job_type && (
            <div className="job-card-meta-item">
              <span className="job-card-meta-label">Type</span>
              <span className="job-card-meta-value">{job.job_type}</span>
            </div>
          )}
          {job.location && (
            <div className="job-card-meta-item">
              <span className="job-card-meta-label">Location</span>
              <span className="job-card-meta-value">{job.location}</span>
            </div>
          )}
          {job.salary_range && (
            <div className="job-card-meta-item">
              <span className="job-card-meta-label">Salary</span>
              <span className="job-card-meta-value">{job.salary_range}</span>
            </div>
          )}
        </div>
      </div>
      <Button variant="primary" className="job-card-apply" onClick={onApply}>
        Apply
      </Button>
    </article>
  )
}

export default JobCard
