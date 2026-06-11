import { useState } from 'react'
import Button from './Button'
import JobApplyDialog from './JobApplyDialog'
import type { JobPost } from '../data/jobs'
import '../css/JobCard.css'

interface JobCardProps {
  job: JobPost
}

function JobCard({ job }: JobCardProps) {
  const [isDialogOpen, setIsDialogOpen] = useState(false)

  return (
    <article className="job-card">
      <div className="job-card-content">
        <h2 className="job-card-title">{job.title}</h2>
        <p className="job-card-description">{job.description}</p>
        <span className="job-card-company">{job.company}</span>
      </div>
      <Button variant="primary" className="job-card-apply" onClick={() => setIsDialogOpen(true)}>
        Apply
      </Button>

      <JobApplyDialog job={job} isOpen={isDialogOpen} onClose={() => setIsDialogOpen(false)} />
    </article>
  )
}

export default JobCard
