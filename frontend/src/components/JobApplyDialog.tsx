import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'
import Tag from './Tag'
import Modal from './Modal'
import type { JobPost } from '../data/jobs'
import '../css/JobApplyDialog.css'

// Hardcoded for dev — will come from auth session later
const CANDIDATE_ID = 'b0000001-0000-0000-0000-000000000001'
const API_BASE = 'http://localhost:8000'

interface JobApplyDialogProps {
  job: JobPost
  isOpen: boolean
  onClose: () => void
}

function JobApplyDialog({ job, isOpen, onClose }: JobApplyDialogProps) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleApply() {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/applications/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_posting_id: job.jobPostingId,
          candidate_id: CANDIDATE_ID,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail ?? `Server error ${res.status}`)
      }
      const { application_id } = await res.json()
      onClose()
      navigate(`/interview-stages/${application_id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <div className="job-apply-dialog">
        <div className="job-apply-main">
          <span className="job-apply-company">{job.company}</span>
          <h2 className="job-apply-title">{job.title}</h2>
          <p className="job-apply-description">{job.description}</p>
        </div>

        <div className="job-apply-side">
          <div className="job-apply-field">
            <span className="job-apply-label">Required Skills</span>
            <div className="tag-list">
              {job.requiredSkills.map((skill) => (
                <Tag key={skill} variant="info">
                  {skill}
                </Tag>
              ))}
            </div>
          </div>

          <div className="job-apply-field">
            <span className="job-apply-label">Minimum Experience</span>
            <p className="job-apply-experience">{job.minExperience}</p>
          </div>

          {error && <p className="job-apply-error">{error}</p>}

          <Button
            type="button"
            variant="primary"
            className="job-apply-submit"
            onClick={handleApply}
            disabled={loading}
          >
            {loading ? 'Applying…' : 'Apply to Job'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default JobApplyDialog
