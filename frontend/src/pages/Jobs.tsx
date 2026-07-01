import { useEffect, useMemo, useState } from 'react'
import { useLocation } from 'react-router-dom'
import JobCard from '../components/JobCard'
import JobApplyDialog from '../components/JobApplyDialog'
import FilterPanel, { type FilterState } from '../components/FilterPanel'
import { fetchJobs, type JobListItem } from '../api/jobs'
import '../css/Jobs.css'

function parseSalaryBounds(salaryRange: string | null): [number, number] | null {
  if (!salaryRange) return null
  const normalized = salaryRange.replace(/\$/g, '').replace(/,/g, '').replace(/k/gi, '000')
  const nums = normalized.match(/\d+/g)?.map(Number) ?? []
  if (nums.length === 0) return null
  if (nums.length === 1) return [nums[0], nums[0]]
  return [Math.min(...nums), Math.max(...nums)]
}

function Jobs() {
  const location = useLocation()

  const [candidateId, setCandidateId] = useState<string>(() => {
    const fromState = (location.state as { candidateId?: string } | null)?.candidateId
    if (fromState) {
      sessionStorage.setItem('candidateId', fromState)
      return fromState
    }
    return sessionStorage.getItem('candidateId') ?? ''
  })

  useEffect(() => {
    function syncAuth() {
      setCandidateId(sessionStorage.getItem('candidateId') ?? '')
    }
    window.addEventListener('auth-change', syncAuth)
    return () => window.removeEventListener('auth-change', syncAuth)
  }, [])

  const pendingJobId = (location.state as { pendingJobId?: string } | null)?.pendingJobId

  const [allJobs, setAllJobs] = useState<JobListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedJob, setSelectedJob] = useState<JobListItem | null>(null)

  const [filters, setFilters] = useState<FilterState>({})
  const [locationInput, setLocationInput] = useState('')
  const [salaryMin, setSalaryMin] = useState('')
  const [salaryMax, setSalaryMax] = useState('')
  const [salaryError, setSalaryError] = useState<string | null>(null)

  const jobRoleOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const j of allJobs) {
      if (!seen.has(j.job_role_id)) seen.set(j.job_role_id, j.job_role_title)
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [allJobs])

  const experienceLevelOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const j of allJobs) {
      if (!seen.has(j.experience_level_id)) seen.set(j.experience_level_id, j.experience_level_name)
    }
    return [...seen.entries()].sort((a, b) => a[0] - b[0])
  }, [allJobs])

  const filteredJobs = useMemo(() => {
    let result = allJobs
    if (filters.job_role_id != null) {
      result = result.filter((j) => Number(j.job_role_id) === Number(filters.job_role_id))
    }
    if (filters.experience_level_id != null) {
      result = result.filter((j) => Number(j.experience_level_id) === Number(filters.experience_level_id))
    }
    if (filters.job_type) {
      const qt = filters.job_type.trim().toLowerCase()
      result = result.filter((j) => j.job_type.trim().toLowerCase() === qt)
    }
    if (filters.location) {
      const q = filters.location.toLowerCase()
      result = result.filter((j) => j.location?.trim().toLowerCase().includes(q))
    }
    if (!salaryError) {
      if (salaryMin !== '') {
        const min = Number(salaryMin)
        result = result.filter((j) => {
          const bounds = parseSalaryBounds(j.salary_range)
          return bounds !== null && bounds[1] >= min
        })
      }
      if (salaryMax !== '') {
        const max = Number(salaryMax)
        result = result.filter((j) => {
          const bounds = parseSalaryBounds(j.salary_range)
          return bounds !== null && bounds[0] <= max
        })
      }
    }
    return result
  }, [allJobs, filters, salaryMin, salaryMax, salaryError])

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetchJobs({ candidate_id: candidateId || undefined })
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
  }, [candidateId])

  function handleLocationChange(value: string) {
    setLocationInput(value)
    setFilters((f) => ({ ...f, location: value.trim() || undefined }))
  }

  function handleSalaryMinChange(value: string) {
    setSalaryMin(value)
    if (value !== '' && salaryMax !== '' && Number(value) > Number(salaryMax)) {
      setSalaryError('Min must not exceed max')
    } else {
      setSalaryError(null)
    }
  }

  function handleSalaryMaxChange(value: string) {
    setSalaryMax(value)
    if (salaryMin !== '' && value !== '' && Number(salaryMin) > Number(value)) {
      setSalaryError('Min must not exceed max')
    } else {
      setSalaryError(null)
    }
  }

  function clearFilters() {
    setLocationInput('')
    setSalaryMin('')
    setSalaryMax('')
    setSalaryError(null)
    setFilters({})
  }

  const hasActiveFilters =
    filters.job_role_id != null ||
    filters.experience_level_id != null ||
    !!filters.location ||
    !!filters.job_type ||
    salaryMin !== '' ||
    salaryMax !== ''

  return (
    <main className="jobs-page">
      <header className="jobs-header">
        <div className="jobs-brand">
          <span className="jobs-brand-primary">Russel</span>
          <span className="jobs-brand-accent">.AI</span>
        </div>
        <h1 className="jobs-heading">Open Positions</h1>
      </header>

      <div className="jobs-content">
        <FilterPanel
          jobRoleOptions={jobRoleOptions}
          experienceLevelOptions={experienceLevelOptions}
          filters={filters}
          locationInput={locationInput}
          salaryMin={salaryMin}
          salaryMax={salaryMax}
          salaryError={salaryError}
          hasActiveFilters={hasActiveFilters}
          count={filteredJobs.length}
          countLabel="position"
          loading={loading}
          onFiltersChange={(update) => setFilters((f) => ({ ...f, ...update }))}
          onLocationChange={handleLocationChange}
          onSalaryMinChange={handleSalaryMinChange}
          onSalaryMaxChange={handleSalaryMaxChange}
          onClearFilters={clearFilters}
        />

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
