import { useEffect, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import Input from '../components/Input'
import Select from '../components/Select'
import BackButton from '../components/BackButton'
import logo from '../utils/logo.png'
import { fetchSignupMetadata, type ExperienceLevel, type JobRole } from '../api/auth'
import { fetchRecruiterJobs, postJob, type JobListItem } from '../api/jobs'
import '../css/RecruiterDashboard.css'

const JOB_TYPES = ['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']

function RecruiterDashboard() {
  const navigate = useNavigate()
  const location = useLocation()

  const recruiterId: string =
    (location.state as { recruiterId?: string } | null)?.recruiterId ??
    sessionStorage.getItem('recruiterId') ??
    ''

  useEffect(() => {
    if (!recruiterId) navigate('/auth')
  }, [recruiterId, navigate])

  const [jobs, setJobs] = useState<JobListItem[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)
  const [jobsError, setJobsError] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])
  const [experienceLevels, setExperienceLevels] = useState<ExperienceLevel[]>([])
  const [rolesLoading, setRolesLoading] = useState(false)

  // Post job form state
  const [jobRoleId, setJobRoleId] = useState<number | ''>('')
  const [experienceLevelId, setExperienceLevelId] = useState<number | ''>('')
  const [jobDescription, setJobDescription] = useState('')
  const [jobLocation, setJobLocation] = useState('')
  const [jobType, setJobType] = useState('')
  const [salaryRange, setSalaryRange] = useState('')
  const [expiresAt, setExpiresAt] = useState('')

  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)

  useEffect(() => {
    if (!recruiterId) return
    setJobsLoading(true)
    fetchRecruiterJobs(recruiterId)
      .then(setJobs)
      .catch((err: unknown) => setJobsError(err instanceof Error ? err.message : 'Failed to load jobs'))
      .finally(() => setJobsLoading(false))
  }, [recruiterId])

  function handleOpenForm() {
    setShowForm(true)
    if (jobRoles.length > 0) return
    setRolesLoading(true)
    fetchSignupMetadata()
      .then(({ job_roles, experience_levels }) => {
        setJobRoles(job_roles)
        setExperienceLevels(experience_levels)
      })
      .catch(() => {})
      .finally(() => setRolesLoading(false))
  }

  function handleCloseForm() {
    setShowForm(false)
    setPostError(null)
    setJobRoleId('')
    setExperienceLevelId('')
    setJobDescription('')
    setJobLocation('')
    setJobType('')
    setSalaryRange('')
    setExpiresAt('')
  }

  async function handlePostJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (jobRoleId === '' || experienceLevelId === '' || !jobType) return
    setPosting(true)
    setPostError(null)
    try {
      await postJob({
        recruiter_id: recruiterId,
        job_role_id: jobRoleId as number,
        experience_level_id: experienceLevelId as number,
        description: jobDescription,
        location: jobLocation,
        job_type: jobType,
        salary_range: salaryRange || undefined,
        expires_at: expiresAt || undefined,
      })
      handleCloseForm()
      const updated = await fetchRecruiterJobs(recruiterId)
      setJobs(updated)
    } catch (err: unknown) {
      setPostError(err instanceof Error ? err.message : 'Failed to post job')
    } finally {
      setPosting(false)
    }
  }

  function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
  }

  if (!recruiterId) return null

  return (
    <main className="rd-page">
      <BackButton />
      <div className="rd-scroll-area">
      <header className="rd-header">
        <Link to="/" className="rd-brand">
          <span className="rd-brand-title">
            <span className="rd-brand-primary">Russel</span>
            <span className="rd-brand-accent">.AI</span>
          </span>
          <img src={logo} alt="Russel.AI logo" className="rd-logo" />
        </Link>
        <div className="rd-header-row">
          <h1 className="rd-heading">Recruiter Dashboard</h1>
          <Button variant="primary" onClick={handleOpenForm}>
            Post a Job
          </Button>
        </div>
      </header>

      {showForm && (
        <section className="rd-form-section">
          <div className="rd-form-card">
            <div className="rd-form-header">
              <h2 className="rd-form-title">Post a New Job</h2>
              <button type="button" className="rd-form-close" onClick={handleCloseForm} aria-label="Close">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            <form className="rd-form" onSubmit={handlePostJob}>
              <div className="rd-form-row">
                <div className="field">
                  <span className="field-label">Job Category</span>
                  {rolesLoading ? (
                    <p className="rd-loading-text">Loading…</p>
                  ) : (
                    <Select
                      value={jobRoleId}
                      onChange={(e: ChangeEvent<HTMLSelectElement>) => setJobRoleId(Number(e.target.value))}
                    >
                      <option value="" disabled>Select a category</option>
                      {jobRoles.map((r) => (
                        <option key={r.id} value={r.id}>{r.title}</option>
                      ))}
                    </Select>
                  )}
                </div>

                <div className="field">
                  <span className="field-label">Experience Level</span>
                  {rolesLoading ? (
                    <p className="rd-loading-text">Loading…</p>
                  ) : (
                    <Select
                      value={experienceLevelId}
                      onChange={(e: ChangeEvent<HTMLSelectElement>) => setExperienceLevelId(Number(e.target.value))}
                    >
                      <option value="" disabled>Select a level</option>
                      {experienceLevels.map((l) => (
                        <option key={l.id} value={l.id}>{l.name}</option>
                      ))}
                    </Select>
                  )}
                </div>
              </div>

              <label className="field">
                <span className="field-label">Job Description</span>
                <textarea
                  className="rd-textarea"
                  placeholder="Describe the role, responsibilities, and requirements…"
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  required
                  rows={4}
                />
              </label>

              <div className="rd-form-row">
                <label className="field">
                  <span className="field-label">Location</span>
                  <Input
                    type="text"
                    placeholder="e.g. New York, NY"
                    value={jobLocation}
                    onChange={(e) => setJobLocation(e.target.value)}
                    required
                  />
                </label>

                <div className="field">
                  <span className="field-label">Job Type</span>
                  <Select
                    value={jobType}
                    onChange={(e: ChangeEvent<HTMLSelectElement>) => setJobType(e.target.value)}
                  >
                    <option value="" disabled>Select type</option>
                    {JOB_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </Select>
                </div>
              </div>

              <div className="rd-form-row">
                <label className="field">
                  <span className="field-label">Salary Range <span className="rd-optional">(optional)</span></span>
                  <Input
                    type="text"
                    placeholder="e.g. $80k–$100k/year"
                    value={salaryRange}
                    onChange={(e) => setSalaryRange(e.target.value)}
                  />
                </label>

                <label className="field">
                  <span className="field-label">Expires On <span className="rd-optional">(optional)</span></span>
                  <Input
                    type="date"
                    value={expiresAt}
                    onChange={(e) => setExpiresAt(e.target.value)}
                  />
                </label>
              </div>

              {postError && <p className="rd-error">{postError}</p>}

              <div className="rd-form-actions">
                <Button type="button" variant="secondary" onClick={handleCloseForm}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" disabled={posting || jobRoleId === '' || experienceLevelId === '' || !jobType}>
                  {posting ? 'Posting…' : 'Post Job'}
                </Button>
              </div>
            </form>
          </div>
        </section>
      )}

      <section className="rd-jobs-section">
        <h2 className="rd-section-title">Your Job Postings</h2>

        {jobsLoading ? (
          <p className="rd-loading-text">Loading your jobs…</p>
        ) : jobsError ? (
          <p className="rd-error">{jobsError}</p>
        ) : jobs.length === 0 ? (
          <div className="rd-empty">
            <p className="rd-empty-text">No jobs posted yet.</p>
            <p className="rd-empty-sub">Click "Post a Job" to publish your first listing.</p>
          </div>
        ) : (
          <div className="rd-jobs-list">
            {jobs.map((job) => (
              <article key={job.id} className="rd-job-card">
                <div className="rd-job-main">
                  <span className="rd-job-company">{job.company}</span>
                  <h3 className="rd-job-title">{`${job.experience_level_name} ${job.job_role_title}`}</h3>
                  <p className="rd-job-desc">{job.description}</p>
                </div>
                <div className="rd-job-meta">
                  <span className="rd-job-badge">{job.job_type}</span>
                  <span className="rd-job-meta-item">{job.location}</span>
                  {job.salary_range && <span className="rd-job-meta-item">{job.salary_range}</span>}
                  <span className="rd-job-meta-date">Posted {formatDate(job.posted_at)}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
      </div>
    </main>
  )
}

export default RecruiterDashboard
