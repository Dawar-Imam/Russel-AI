import { useMemo } from 'react'
import CustomSelect from './CustomSelect'
import '../css/FilterPanel.css'

const JOB_TYPES = ['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']
const APP_STATUSES = ['ATS_PENDING', 'ATS_PASS', 'ATS_FAIL', 'IN_PROGRESS', 'HIRED', 'REJECTED']
const STATUS_LABELS: Record<string, string> = {
  ATS_PENDING: 'ATS Pending',
  ATS_PASS: 'ATS Passed',
  ATS_FAIL: 'ATS Failed',
  IN_PROGRESS: 'In Progress',
  HIRED: 'Hired',
  REJECTED: 'Rejected',
}

export interface FilterState {
  job_role_id?: number
  experience_level_id?: number
  job_type?: string
  location?: string
  status?: string
}

interface FilterPanelProps {
  jobRoleOptions: [number, string][]
  experienceLevelOptions: [number, string][]
  filters: FilterState
  locationInput: string
  salaryMin: string
  salaryMax: string
  salaryError: string | null
  hasActiveFilters: boolean
  count: number
  countLabel: string
  loading: boolean
  showStatus?: boolean
  onFiltersChange: (update: Partial<FilterState>) => void
  onLocationChange: (value: string) => void
  onSalaryMinChange: (value: string) => void
  onSalaryMaxChange: (value: string) => void
  onClearFilters: () => void
}

function FilterPanel({
  jobRoleOptions,
  experienceLevelOptions,
  filters,
  locationInput,
  salaryMin,
  salaryMax,
  salaryError,
  hasActiveFilters,
  count,
  countLabel,
  loading,
  showStatus = false,
  onFiltersChange,
  onLocationChange,
  onSalaryMinChange,
  onSalaryMaxChange,
  onClearFilters,
}: FilterPanelProps) {
  const roleOptions = useMemo(
    () => [
      { value: '', label: 'All roles' },
      ...jobRoleOptions.map(([id, title]) => ({ value: String(id), label: title })),
    ],
    [jobRoleOptions],
  )

  const levelOptions = useMemo(
    () => [
      { value: '', label: 'All levels' },
      ...experienceLevelOptions.map(([id, name]) => ({ value: String(id), label: name })),
    ],
    [experienceLevelOptions],
  )

  const jobTypeOptions = useMemo(
    () => [
      { value: '', label: 'All types' },
      ...JOB_TYPES.map((t) => ({ value: t, label: t })),
    ],
    [],
  )

  const statusOptions = useMemo(
    () => [
      { value: '', label: 'All statuses' },
      ...APP_STATUSES.map((s) => ({ value: s, label: STATUS_LABELS[s] })),
    ],
    [],
  )

  return (
    <div className="filter-panel">
      <div className="filter-panel-header">
        <span className="filter-panel-title">Filters</span>
        <span className="filter-panel-count">
          {loading ? '–' : `${count} ${countLabel}${count !== 1 ? 's' : ''}`}
        </span>
      </div>

      <div className="filter-panel-row">
        <div className="filter-panel-field">
          <label className="filter-panel-label" htmlFor="fp-role">Role</label>
          <CustomSelect
            id="fp-role"
            value={String(filters.job_role_id ?? '')}
            options={roleOptions}
            placeholder="All roles"
            onChange={(v) => onFiltersChange({ job_role_id: v ? Number(v) : undefined })}
          />
        </div>

        <div className="filter-panel-field">
          <label className="filter-panel-label" htmlFor="fp-level">Experience Level</label>
          <CustomSelect
            id="fp-level"
            value={String(filters.experience_level_id ?? '')}
            options={levelOptions}
            placeholder="All levels"
            onChange={(v) => onFiltersChange({ experience_level_id: v ? Number(v) : undefined })}
          />
        </div>

        <div className="filter-panel-field">
          <label className="filter-panel-label" htmlFor="fp-type">Job Type</label>
          <CustomSelect
            id="fp-type"
            value={filters.job_type ?? ''}
            options={jobTypeOptions}
            placeholder="All types"
            onChange={(v) => onFiltersChange({ job_type: v || undefined })}
          />
        </div>

        {showStatus && (
          <div className="filter-panel-field">
            <label className="filter-panel-label" htmlFor="fp-status">Status</label>
            <CustomSelect
              id="fp-status"
              value={filters.status ?? ''}
              options={statusOptions}
              placeholder="All statuses"
              onChange={(v) => onFiltersChange({ status: v || undefined })}
            />
          </div>
        )}

        <div className="filter-panel-field">
          <label className="filter-panel-label" htmlFor="fp-location">Location</label>
          <input
            id="fp-location"
            className="filter-panel-input"
            type="text"
            placeholder="e.g. London, Remote"
            value={locationInput}
            onChange={(e) => onLocationChange(e.target.value)}
          />
        </div>

        <div className="filter-panel-field">
          <label className="filter-panel-label">Salary Range (USD)</label>
          <div className="filter-panel-salary-inputs">
            <div className="filter-panel-salary-wrapper">
              <span className="filter-panel-salary-prefix">$</span>
              <input
                className="filter-panel-input filter-panel-salary-input"
                type="number"
                min="0"
                step="1000"
                placeholder="Min"
                value={salaryMin}
                onChange={(e) => onSalaryMinChange(e.target.value)}
              />
            </div>
            <span className="filter-panel-salary-sep">—</span>
            <div className="filter-panel-salary-wrapper">
              <span className="filter-panel-salary-prefix">$</span>
              <input
                className="filter-panel-input filter-panel-salary-input"
                type="number"
                min="0"
                step="1000"
                placeholder="Max"
                value={salaryMax}
                onChange={(e) => onSalaryMaxChange(e.target.value)}
              />
            </div>
          </div>
          {salaryError && <span className="filter-panel-error">{salaryError}</span>}
        </div>
      </div>

      {hasActiveFilters && (
        <div className="filter-panel-active-row">
          <button className="filter-panel-clear" onClick={onClearFilters} type="button">
            ✕ Clear filters
          </button>
        </div>
      )}
    </div>
  )
}

export default FilterPanel
