import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'
import Tag from './Tag'
import Modal from './Modal'
import type { JobListItem } from '../api/jobs'
import { checkAtsEligibility } from '../api/applications'
import '../css/JobApplyDialog.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

type DialogPhase = 'idle' | 'checking-ats' | 'ats-warning' | 'applying'

interface JobApplyDialogProps {
  job: JobListItem | null
  candidateId: string
  isOpen: boolean
  onClose: () => void
}

function JobApplyDialog({ job, candidateId, isOpen, onClose }: JobApplyDialogProps) {
  const navigate = useNavigate()
  const [phase, setPhase] = useState<DialogPhase>('idle')
  const [atsReason, setAtsReason] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const isCancelled = useRef(false)

  useEffect(() => {
    if (isOpen) {
      isCancelled.current = false
    }
  }, [isOpen])

  function resetState() {
    setPhase('idle')
    setAtsReason(null)
    setError(null)
  }

  function handleClose() {
    isCancelled.current = true
    resetState()
    onClose()
  }

  async function submitApplication() {
    if (isCancelled.current || !job) return
    setPhase('applying')
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/applications/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_posting_id: job.id,
          candidate_id: candidateId,
        }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as { detail?: string }).detail ?? `Server error ${res.status}`)
      }
      const { application_id } = (await res.json()) as { application_id: string }
      if (isCancelled.current) return
      handleClose()
      navigate(`/interview-stages/${application_id}`)
    } catch (err) {
      if (isCancelled.current) return
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setPhase('idle')
    }
  }

  async function handleApplyClick() {
    if (!job) return
    if (!candidateId) {
      navigate('/auth', { state: { pendingJobId: job.id } })
      return
    }
    setPhase('checking-ats')
    setError(null)
    try {
      const ats = await checkAtsEligibility(job.id, candidateId)
      if (isCancelled.current) return
      if (!ats.eligible) {
        setAtsReason(ats.reason)
        setPhase('ats-warning')
        return
      }
    } catch {
      if (isCancelled.current) return
    }
    await submitApplication()
  }

  const isLoading = phase === 'checking-ats' || phase === 'applying'

  if (!job) return null

  return (
    <Modal isOpen={isOpen} onClose={handleClose}>
      <div className="job-apply-dialog">
        <div className="job-apply-main">
          <span className="job-apply-company">{job.company}</span>
          <h2 className="job-apply-title">{`${job.experience_level_name} ${job.job_role_title}`}</h2>
          <div className="job-apply-description-wrap">
            <p className="job-apply-description">{job.description}</p>
          </div>
        </div>

        <div className="job-apply-side">
          {job.required_skills.length > 0 && (
            <div className="job-apply-field">
              <span className="job-apply-label">Required Skills</span>
              <div className="tag-list job-apply-skills-list">
                {job.required_skills.map((skill) => (
                  <Tag key={skill} variant="info">
                    {skill}
                  </Tag>
                ))}
              </div>
            </div>
          )}

          {job.salary_range && (
            <div className="job-apply-field">
              <span className="job-apply-label">Salary Range</span>
              <p className="job-apply-meta-value">{job.salary_range}</p>
            </div>
          )}

          {job.location && (
            <div className="job-apply-field">
              <span className="job-apply-label">Location</span>
              <p className="job-apply-meta-value">{job.location}</p>
            </div>
          )}

          {job.job_type && (
            <div className="job-apply-field">
              <span className="job-apply-label">Job Type</span>
              <p className="job-apply-meta-value">{job.job_type}</p>
            </div>
          )}

          {phase === 'ats-warning' && atsReason && (
            <div className="job-apply-ats-warning">
              <span className="job-apply-ats-icon">⚠</span>
              <div className="job-apply-ats-body">
                <p className="job-apply-ats-heading">You may not meet all requirements</p>
                <p className="job-apply-ats-reason">{atsReason}</p>
              </div>
            </div>
          )}

          {error && <p className="job-apply-error">{error}</p>}

          <div className="job-apply-actions">
            {phase === 'ats-warning' ? (
              <>
                <Button
                  type="button"
                  variant="primary"
                  className="job-apply-submit"
                  onClick={() => void submitApplication()}
                  disabled={isLoading}
                >
                  Apply Anyway
                </Button>
                <button type="button" className="job-apply-cancel" onClick={handleClose}>
                  Cancel
                </button>
              </>
            ) : (
              <Button
                type="button"
                variant="primary"
                className="job-apply-submit"
                onClick={() => void handleApplyClick()}
                disabled={isLoading}
              >
                {phase === 'checking-ats'
                  ? 'Checking eligibility…'
                  : phase === 'applying'
                    ? 'Applying…'
                    : 'Apply to Job'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default JobApplyDialog
