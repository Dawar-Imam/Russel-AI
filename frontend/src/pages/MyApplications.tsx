import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import ApplicationCard from '../components/ApplicationCard'
import FilterPanel, { type FilterState } from '../components/FilterPanel'
import { fetchMyApplications, type MyApplicationItem } from '../api/applications'
import '../css/MyApplications.css'

function parseSalaryBounds(salaryRange: string | null): [number, number] | null {
  if (!salaryRange) return null
  const normalized = salaryRange.replace(/\$/g, '').replace(/,/g, '').replace(/k/gi, '000')
  const nums = normalized.match(/\d+/g)?.map(Number) ?? []
  if (nums.length === 0) return null
  if (nums.length === 1) return [nums[0], nums[0]]
  return [Math.min(...nums), Math.max(...nums)]
}

function MyApplications() {
  const location = useLocation()
  const navigate = useNavigate()

  const [candidateId] = useState<string>(() => {
    const fromState = (location.state as { candidateId?: string } | null)?.candidateId
    if (fromState) {
      sessionStorage.setItem('candidateId', fromState)
      return fromState
    }
    return sessionStorage.getItem('candidateId') ?? ''
  })

  const [allApplications, setAllApplications] = useState<MyApplicationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [filters, setFilters] = useState<FilterState>({})
  const [locationInput, setLocationInput] = useState('')
  const [salaryMin, setSalaryMin] = useState('')
  const [salaryMax, setSalaryMax] = useState('')
  const [salaryError, setSalaryError] = useState<string | null>(null)

  const jobRoleOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const a of allApplications) {
      if (!seen.has(a.job_role_id)) seen.set(a.job_role_id, a.job_role_title)
    }
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [allApplications])

  const experienceLevelOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const a of allApplications) {
      if (!seen.has(a.experience_level_id)) seen.set(a.experience_level_id, a.experience_level_name)
    }
    return [...seen.entries()].sort((a, b) => a[0] - b[0])
  }, [allApplications])

  const filtered = useMemo(() => {
    let result = allApplications
    if (filters.job_role_id != null) {
      result = result.filter((a) => Number(a.job_role_id) === Number(filters.job_role_id))
    }
    if (filters.experience_level_id != null) {
      result = result.filter((a) => Number(a.experience_level_id) === Number(filters.experience_level_id))
    }
    if (filters.job_type) {
      const qt = filters.job_type.trim().toLowerCase()
      result = result.filter((a) => a.job_type.trim().toLowerCase() === qt)
    }
    if (filters.location) {
      const q = filters.location.toLowerCase()
      result = result.filter((a) => a.location?.trim().toLowerCase().includes(q))
    }
    if (filters.status) {
      result = result.filter((a) => a.status === filters.status)
    }
    if (!salaryError) {
      if (salaryMin !== '') {
        const min = Number(salaryMin)
        result = result.filter((a) => {
          const bounds = parseSalaryBounds(a.salary_range)
          return bounds !== null && bounds[1] >= min
        })
      }
      if (salaryMax !== '') {
        const max = Number(salaryMax)
        result = result.filter((a) => {
          const bounds = parseSalaryBounds(a.salary_range)
          return bounds !== null && bounds[0] <= max
        })
      }
    }
    return result
  }, [allApplications, filters, salaryMin, salaryMax, salaryError])

  useEffect(() => {
    if (!candidateId) {
      setLoading(false)
      setError('You must be signed in as a candidate to view your applications.')
      return
    }
    fetchMyApplications(candidateId)
      .then(setAllApplications)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load applications'))
      .finally(() => setLoading(false))
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
    !!filters.status ||
    salaryMin !== '' ||
    salaryMax !== ''

  return (
    <main className="my-apps-page">
      <header className="my-apps-header">
        <h1 className="my-apps-heading">Dashboard</h1>
      </header>

      <div className="my-apps-content">
        <FilterPanel
          jobRoleOptions={jobRoleOptions}
          experienceLevelOptions={experienceLevelOptions}
          filters={filters}
          locationInput={locationInput}
          salaryMin={salaryMin}
          salaryMax={salaryMax}
          salaryError={salaryError}
          hasActiveFilters={hasActiveFilters}
          count={filtered.length}
          countLabel="application"
          loading={loading}
          showStatus
          onFiltersChange={(update) => setFilters((f) => ({ ...f, ...update }))}
          onLocationChange={handleLocationChange}
          onSalaryMinChange={handleSalaryMinChange}
          onSalaryMaxChange={handleSalaryMaxChange}
          onClearFilters={clearFilters}
        />

        <div className="my-apps-scroll-area">
          {loading ? (
            <p className="my-apps-state-text">Loading your applications…</p>
          ) : error ? (
            <p className="my-apps-state-error">{error}</p>
          ) : allApplications.length === 0 ? (
            <p className="my-apps-state-text">You haven't applied to any jobs yet.</p>
          ) : filtered.length === 0 ? (
            <p className="my-apps-state-text">No applications match your filters. Try adjusting or clearing them.</p>
          ) : (
            <div className="my-apps-list">
              {filtered.map((app) => (
                <ApplicationCard key={app.application_id} application={app} />
              ))}
            </div>
          )}
        </div>
      </div>

    </main>
  )
}

export default MyApplications
