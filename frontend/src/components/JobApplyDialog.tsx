import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Button from './Button'
import Tag from './Tag'
import Modal from './Modal'
import type { JobListItem } from '../api/jobs'
import '../css/JobApplyDialog.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

interface JobApplyDialogProps {
  job: JobListItem | null
  candidateId: string
  isOpen: boolean
  onClose: () => void
}

function JobApplyDialog({ job, candidateId, isOpen, onClose }: JobApplyDialogProps) {
  const navigate = useNavigate()
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [cvFile, setCvFile] = useState<File | null>(null)
  const cvInputRef = useRef<HTMLInputElement>(null)

  const isCancelled = useRef(false)

  useEffect(() => {
    if (isOpen) {
      isCancelled.current = false
    }
  }, [isOpen])

  function resetState() {
    setApplying(false)
    setError(null)
    setCvFile(null)
    if (cvInputRef.current) cvInputRef.current.value = ''
  }

  function handleClose() {
    isCancelled.current = true
    resetState()
    onClose()
  }

  async function handleApplyClick() {
    if (!job) return
    if (!candidateId) {
      navigate('/auth', { state: { pendingJobId: job.id } })
      return
    }
    if (isCancelled.current) return
    setApplying(true)
    setError(null)
    try {
      const formData = new FormData()
      formData.append('job_posting_id', job.id)
      formData.append('candidate_id', candidateId)
      if (cvFile) {
        formData.append('cv', cvFile)
      }

      const res = await fetch(`${API_BASE}/api/applications/apply`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error((data as { detail?: string }).detail ?? `Server error ${res.status}`)
      }
      const { application_id } = (await res.json()) as { application_id: string }
      if (isCancelled.current) return
      handleClose()
      navigate(`/application-progress/${application_id}`)
    } catch (err) {
      if (isCancelled.current) return
      setError(err instanceof Error ? err.message : 'Something went wrong')
      setApplying(false)
    }
  }

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

          <div className="job-apply-field">
            <span className="job-apply-label">
              CV / Resume <span className="job-apply-optional">(optional — updates your profile)</span>
            </span>
            <label className="job-apply-cv-label">
              <input
                ref={cvInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="job-apply-cv-input"
                onChange={(e) => setCvFile(e.target.files?.[0] ?? null)}
              />
              <span className="job-apply-cv-btn">
                {cvFile ? (
                  <>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="job-apply-cv-icon">
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    {cvFile.name}
                  </>
                ) : (
                  <>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="job-apply-cv-icon">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    Upload CV (PDF, DOCX, TXT)
                  </>
                )}
              </span>
            </label>
          </div>

          {error && <p className="job-apply-error">{error}</p>}

          <div className="job-apply-actions">
            <Button
              type="button"
              variant="primary"
              className="job-apply-submit"
              onClick={() => void handleApplyClick()}
              disabled={applying}
            >
              {applying ? 'Applying…' : 'Apply to Job'}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}

export default JobApplyDialog
