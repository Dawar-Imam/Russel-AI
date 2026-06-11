import { useNavigate } from 'react-router-dom'
import Button from './Button'
import Tag from './Tag'
import Modal from './Modal'
import type { JobPost } from '../data/jobs'
import '../css/JobApplyDialog.css'

interface JobApplyDialogProps {
  job: JobPost
  isOpen: boolean
  onClose: () => void
}

function JobApplyDialog({ job, isOpen, onClose }: JobApplyDialogProps) {
  const navigate = useNavigate()

  function handleApply() {
    onClose()
    navigate('/interview-stages')
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

          <Button type="button" variant="primary" className="job-apply-submit" onClick={handleApply}>
            Apply to Job
          </Button>
        </div>
      </div>
    </Modal>
  )
}

export default JobApplyDialog
