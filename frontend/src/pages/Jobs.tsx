import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import JobCard from '../components/JobCard'
import JobApplyDialog from '../components/JobApplyDialog'
import BackButton from '../components/BackButton'
import logo from '../utils/logo.png'
import { fetchJobs, type JobFilters, type JobListItem } from '../api/jobs'
import '../css/Jobs.css'

const JOB_TYPES = ['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']

function Jobs() {
  const location = useLocation()

  const [candidateId] = useState<string>(() => {
    const fromState = (location.state as { candidateId?: string } | null)?.candidateId
    if (fromState) {
      sessionStorage.setItem('candidateId', fromState)
      return fromState
    }
    return sessionStorage.getItem('candidateId') ?? ''
  })

  const pendingJobId = (location.state as { pendingJobId?: string } | null)?.pendingJobId

  const [allJobs, setAllJobs] = useState<JobListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedJob, setSelectedJob] = useState<JobListItem | null>(null)

  const [filters, setFilters] = useState<JobFilters>({})
  const [locationInput, setLocationInput] = useState('')
  const [salaryInput, setSalaryInput] = useState('')

  const jobRoleOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const j of allJobs) {
      if (!seen.has(j.job_role_id)) seen.set(j.job_role_id, j.job_role_title)
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [allJobs])

  const filteredJobs = useMemo(() => {
    let result = allJobs
    if (filters.job_role_id) {
      result = result.filter((j) => j.job_role_id === filters.job_role_id)
    }
    if (filters.job_type) {
      result = result.filter((j) => j.job_type === filters.job_type)
    }
    if (filters.location) {
      const q = filters.location.toLowerCase()
      result = result.filter((j) => j.location?.toLowerCase().includes(q))
    }
    if (filters.salary_range) {
      const q = filters.salary_range.toLowerCase()
      result = result.filter((j) => j.salary_range?.toLowerCase().includes(q))
    }
    return result
  }, [allJobs, filters])

  useEffect(() => {
    fetchJobs()
      .then((data) => {
        setAllJobs(data)
        if (pendingJobId) {
          const job = data.find((j) => j.id === pendingJobId)
          if (job) setSelectedJob(job)
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load jobs'))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleLocationChange(value: string) {
    setLocationInput(value)
    setFilters((f) => ({ ...f, location: value.trim() || undefined }))
  }

  function handleSalaryChange(value: string) {
    setSalaryInput(value)
    setFilters((f) => ({ ...f, salary_range: value.trim() || undefined }))
  }

  function clearFilters() {
    setLocationInput('')
    setSalaryInput('')
    setFilters({})
  }

  const hasActiveFilters =
    !!filters.job_role_id || !!filters.location || !!filters.job_type || !!filters.salary_range

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

      {/* Filter panel */}
      <div className="jobs-filter-panel">
        <div className="jobs-filter-header">
          <span className="jobs-filter-title">Filters</span>
          <span className="jobs-filter-count">
            {loading ? '–' : `${filteredJobs.length} position${filteredJobs.length !== 1 ? 's' : ''}`}
          </span>
        </div>
        <div className="jobs-filter-row">
          <div className="jobs-filter-field">
            <label className="jobs-filter-label" htmlFor="filter-role">Role</label>
            <select
              id="filter-role"
              className="jobs-filter-select"
              value={filters.job_role_id ?? ''}
              onChange={(e) =>
                setFilters((f) => ({
                  ...f,
                  job_role_id: e.target.value ? Number(e.target.value) : undefined,
                }))
              }
            >
              <option value="">All roles</option>
              {jobRoleOptions.map(([id, title]) => (
                <option key={id} value={id}>
                  {title}
                </option>
              ))}
            </select>
          </div>

          <div className="jobs-filter-field">
            <label className="jobs-filter-label" htmlFor="filter-type">Job Type</label>
            <select
              id="filter-type"
              className="jobs-filter-select"
              value={filters.job_type ?? ''}
              onChange={(e) =>
                setFilters((f) => ({ ...f, job_type: e.target.value || undefined }))
              }
            >
              <option value="">All types</option>
              {JOB_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>

          <div className="jobs-filter-field2">
            <label className="jobs-filter-label" htmlFor="filter-location">Location</label>
            <input
              id="filter-location"
              className="jobs-filter-input"
              type="text"
              placeholder="e.g. London, Remote"
              value={locationInput}
              onChange={(e) => handleLocationChange(e.target.value)}
            />
          </div>

          <div className="jobs-filter-field2">
            <label className="jobs-filter-label" htmlFor="filter-salary">Salary</label>
            <input
              id="filter-salary"
              className="jobs-filter-input"
              type="text"
              placeholder="e.g. 80k"
              value={salaryInput}
              onChange={(e) => handleSalaryChange(e.target.value)}
            />
          </div>
        </div>

        {hasActiveFilters && (
          <div className="jobs-filter-active-row">
            <button className="jobs-filter-clear" onClick={clearFilters} type="button">
              ✕ Clear filters
            </button>
          </div>
        )}
      </div>

      <div className="jobs-scroll-area">
        {loading ? (
          <p className="jobs-state-text">Loading jobs…</p>
        ) : error ? (
          <p className="jobs-state-error">{error}</p>
        ) : filteredJobs.length === 0 ? (
          <p className="jobs-state-text">
            {hasActiveFilters
              ? 'No jobs match your filters. Try adjusting or clearing them.'
              : 'No open positions at the moment. Check back soon.'}
          </p>
        ) : (
          <div className="jobs-list">
            {filteredJobs.map((job) => (
              <JobCard key={job.id} job={job} onApply={() => setSelectedJob(job)} />
            ))}
          </div>
        )}
      </div>

      <JobApplyDialog
        job={selectedJob}
        candidateId={candidateId}
        isOpen={selectedJob !== null}
        onClose={() => setSelectedJob(null)}
      />
    </main>
  )
}

export default Jobs
