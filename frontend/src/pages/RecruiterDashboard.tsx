import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import Select from '../components/Select'
import TaxonomySelect from '../components/TaxonomySelect'
import Modal from '../components/Modal'
import InfoTooltip from '../components/InfoTooltip'
import FilterPanel, { type FilterState } from '../components/FilterPanel'
import { createJobRole, createSkill, fetchSignupMetadata, searchJobRoles, searchSkills, type ExperienceLevel } from '../api/auth'
import type { TaxonomyOption } from '../components/TaxonomySelect'
import {
  fetchInterviewRoundTypes,
  fetchJobRounds,
  fetchRecruiterJobs,
  postJob,
  type InterviewRoundType,
  type JobInterviewRoundItem,
  type JobListItem,
} from '../api/jobs'
import '../css/RecruiterDashboard.css'

interface SelectedRound {
  uid: string
  round_type_id: number
  name: string
  failing_criteria: string
}

interface ATSCriterionState {
  section: string
  label: string
  enabled: boolean
  weight: string
}

const ATS_SECTION_DEFS: { section: string; label: string; defaultWeight: number }[] = [
  { section: 'experience', label: 'Experience', defaultWeight: 30 },
  { section: 'skills', label: 'Skills', defaultWeight: 35 },
  { section: 'projects', label: 'Projects', defaultWeight: 20 },
  { section: 'certifications', label: 'Certifications', defaultWeight: 5 },
  { section: 'education', label: 'Education', defaultWeight: 5 },
  { section: 'achievements', label: 'Achievements', defaultWeight: 5 },
]

function defaultAtsCriteria(): ATSCriterionState[] {
  return ATS_SECTION_DEFS.map((d) => ({ section: d.section, label: d.label, enabled: true, weight: String(d.defaultWeight) }))
}

const ATS_SECTION_LABELS: Record<string, string> = Object.fromEntries(ATS_SECTION_DEFS.map((d) => [d.section, d.label]))

const JOB_TYPES = ['Full-time', 'Part-time', 'Remote', 'Contract', 'Hybrid']

function parseSalaryBounds(salaryRange: string | null): [number, number] | null {
  if (!salaryRange) return null
  const normalized = salaryRange.replace(/\$/g, '').replace(/,/g, '').replace(/k/gi, '000')
  const nums = normalized.match(/\d+/g)?.map(Number) ?? []
  if (nums.length === 0) return null
  if (nums.length === 1) return [nums[0], nums[0]]
  return [Math.min(...nums), Math.max(...nums)]
}

function formatSalaryRange(min: string, max: string): string | undefined {
  const hasMin = min.trim() !== ''
  const hasMax = max.trim() !== ''
  if (!hasMin && !hasMax) return undefined
  if (hasMin && hasMax) return `$${Number(min).toLocaleString()}–$${Number(max).toLocaleString()}`
  if (hasMin) return `$${Number(min).toLocaleString()}+`
  return `Up to $${Number(max).toLocaleString()}`
}

function blockNonNumericKey(e: KeyboardEvent<HTMLInputElement>) {
  if (['e', 'E', '+', '-'].includes(e.key)) e.preventDefault()
}

function validateJobCategoryText(text: string): string | null {
  if (text.trim() === '') return null
  return /\d/.test(text) ? 'Job category cannot contain numbers.' : null
}

function validateQualifyThreshold(value: string): string | null {
  if (value.trim() === '') return 'Qualify threshold is required.'
  const n = Number(value)
  return Number.isNaN(n) || n < 0 || n > 100 ? 'Must be between 0 and 100.' : null
}

function todayIso() {
  return new Date().toISOString().split('T')[0]
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

function RecruiterDashboard() {
  const navigate = useNavigate()
  const location = useLocation()

  const recruiterId: string =
    (location.state as { recruiterId?: string } | null)?.recruiterId ??
    sessionStorage.getItem('recruiterId') ??
    ''

  useEffect(() => {
    if (!recruiterId) navigate('/')
  }, [recruiterId, navigate])

  const [jobs, setJobs] = useState<JobListItem[]>([])
  const [jobsLoading, setJobsLoading] = useState(true)
  const [jobsError, setJobsError] = useState<string | null>(null)

  const [showForm, setShowForm] = useState(false)

  const [experienceLevels, setExperienceLevels] = useState<ExperienceLevel[]>([])
  const [roundTypes, setRoundTypes] = useState<InterviewRoundType[]>([])
  const [metaLoading, setMetaLoading] = useState(false)

  // Draft form state — persists across open/close; cleared only after successful post
  const [jobRole, setJobRole] = useState<TaxonomyOption | null>(null)
  const [jobCategoryInputText, setJobCategoryInputText] = useState('')
  const [jobCategoryError, setJobCategoryError] = useState<string | null>(null)
  const [experienceLevelId, setExperienceLevelId] = useState<number | ''>('')
  const [jobDescription, setJobDescription] = useState('')
  const [jobLocation, setJobLocation] = useState('')
  const [jobType, setJobType] = useState('')
  const [formSalaryMin, setFormSalaryMin] = useState('')
  const [formSalaryMax, setFormSalaryMax] = useState('')
  const [formSalaryError, setFormSalaryError] = useState<string | null>(null)
  const [expiresAt, setExpiresAt] = useState('')
  const [selectedSkills, setSelectedSkills] = useState<TaxonomyOption[]>([])
  const [selectedRounds, setSelectedRounds] = useState<SelectedRound[]>([])
  const [selectedRoundTypeId, setSelectedRoundTypeId] = useState<string>('')
  const [atsCriteria, setAtsCriteria] = useState<ATSCriterionState[]>(defaultAtsCriteria())
  const [qualifyThreshold, setQualifyThreshold] = useState('65')
  const [qualifyThresholdError, setQualifyThresholdError] = useState<string | null>(null)
  const [overqualifyThreshold, setOverqualifyThreshold] = useState('')
  const [autoRejectOverqualified, setAutoRejectOverqualified] = useState(false)
  const [posting, setPosting] = useState(false)
  const [postError, setPostError] = useState<string | null>(null)
  const [attemptedPost, setAttemptedPost] = useState(false)
  const [expiresAtError, setExpiresAtError] = useState<string | null>(null)

  const jobRoleId: number | '' = jobRole ? jobRole.value : ''

  const dragIndexRef = useRef<number | null>(null)

  // Job detail dialog
  const [detailJob, setDetailJob] = useState<JobListItem | null>(null)
  const [detailRounds, setDetailRounds] = useState<JobInterviewRoundItem[]>([])
  const [detailRoundsLoading, setDetailRoundsLoading] = useState(false)

  // Filter state
  const [filters, setFilters] = useState<FilterState>({})
  const [locationInput, setLocationInput] = useState('')
  const [salaryMin, setSalaryMin] = useState('')
  const [salaryMax, setSalaryMax] = useState('')
  const [salaryError, setSalaryError] = useState<string | null>(null)

  const jobRoleOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const j of jobs) if (!seen.has(j.job_role_id)) seen.set(j.job_role_id, j.job_role_title)
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [jobs])

  const experienceLevelOptions = useMemo(() => {
    const seen = new Map<number, string>()
    for (const j of jobs) if (!seen.has(j.experience_level_id)) seen.set(j.experience_level_id, j.experience_level_name)
    return [...seen.entries()].sort((a, b) => a[0] - b[0])
  }, [jobs])

  const filteredJobs = useMemo(() => {
    let result = jobs
    if (filters.job_role_id != null) result = result.filter((j) => Number(j.job_role_id) === Number(filters.job_role_id))
    if (filters.experience_level_id != null) result = result.filter((j) => Number(j.experience_level_id) === Number(filters.experience_level_id))
    if (filters.job_type) { const qt = filters.job_type.trim().toLowerCase(); result = result.filter((j) => j.job_type.trim().toLowerCase() === qt) }
    if (filters.location) { const q = filters.location.toLowerCase(); result = result.filter((j) => j.location?.trim().toLowerCase().includes(q)) }
    if (!salaryError) {
      if (salaryMin !== '') { const min = Number(salaryMin); result = result.filter((j) => { const b = parseSalaryBounds(j.salary_range); return b !== null && b[1] >= min }) }
      if (salaryMax !== '') { const max = Number(salaryMax); result = result.filter((j) => { const b = parseSalaryBounds(j.salary_range); return b !== null && b[0] <= max }) }
    }
    // Active jobs first (each group already ordered by recency from the API), non-active below.
    return [...result].sort((a, b) => {
      const aActive = a.status === 'active' ? 0 : 1
      const bActive = b.status === 'active' ? 0 : 1
      if (aActive !== bActive) return aActive - bActive
      return new Date(b.posted_at).getTime() - new Date(a.posted_at).getTime()
    })
  }, [jobs, filters, salaryMin, salaryMax, salaryError])

  const hasActiveFilters =
    filters.job_role_id != null || filters.experience_level_id != null ||
    !!filters.location || !!filters.job_type || salaryMin !== '' || salaryMax !== ''

  useEffect(() => {
    if (!recruiterId) return
    setJobsLoading(true)
    fetchRecruiterJobs(recruiterId)
      .then(setJobs)
      .catch((err: unknown) => setJobsError(err instanceof Error ? err.message : 'Failed to load jobs'))
      .finally(() => setJobsLoading(false))
  }, [recruiterId])

  // ── Post job form ─────────────────────────────────────────────────────────

  function handleOpenForm() {
    setShowForm(true)
    if (experienceLevels.length > 0) return
    setMetaLoading(true)
    Promise.all([fetchSignupMetadata(), fetchInterviewRoundTypes()])
      .then(([meta, rts]) => {
        setExperienceLevels(meta.experience_levels)
        setRoundTypes(rts)
      })
      .catch(() => {})
      .finally(() => setMetaLoading(false))
  }

  async function loadJobRoleOptions(query: string): Promise<TaxonomyOption[]> {
    const roles = await searchJobRoles(query)
    return roles.map((r) => ({ value: r.id, label: r.title }))
  }

  async function createJobRoleOption(name: string): Promise<TaxonomyOption> {
    const role = await createJobRole(name)
    return { value: role.id, label: role.title }
  }

  async function loadSkillOptions(query: string): Promise<TaxonomyOption[]> {
    if (jobRoleId === '') return []
    const skills = await searchSkills(Number(jobRoleId), query)
    return skills.map((s) => ({ value: s.id, label: s.name }))
  }

  async function createSkillOption(name: string): Promise<TaxonomyOption> {
    const skill = await createSkill(name, jobRoleId === '' ? null : Number(jobRoleId))
    return { value: skill.id, label: skill.name }
  }

  function handleCloseForm() {
    setShowForm(false)
    setPostError(null)
  }

  function handleResetForm() {
    setJobRole(null); setJobCategoryInputText(''); setJobCategoryError(null)
    setExperienceLevelId(''); setJobDescription(''); setJobLocation('')
    setJobType(''); setFormSalaryMin(''); setFormSalaryMax(''); setFormSalaryError(null)
    setExpiresAt(''); setExpiresAtError(null); setSelectedSkills([])
    setSelectedRounds([]); setSelectedRoundTypeId(''); setPostError(null); setAttemptedPost(false)
    setAtsCriteria(defaultAtsCriteria())
    setQualifyThreshold('65'); setQualifyThresholdError(null)
    setOverqualifyThreshold(''); setAutoRejectOverqualified(false)
  }

  function handleToggleAtsSection(section: string) {
    setAtsCriteria((prev) => prev.map((c) => (c.section === section ? { ...c, enabled: !c.enabled } : c)))
  }

  function handleAtsWeightChange(section: string, value: string) {
    setAtsCriteria((prev) => prev.map((c) => (c.section === section ? { ...c, weight: value } : c)))
  }

  function handleJobCategoryInputChange(value: string, actionMeta: { action: string }) {
    if (actionMeta.action !== 'input-change') return
    setJobCategoryInputText(value)
    if (jobCategoryError) setJobCategoryError(validateJobCategoryText(value))
  }

  function handleJobCategoryBlur() {
    setJobCategoryError(validateJobCategoryText(jobCategoryInputText))
  }

  function handleQualifyThresholdBlur() {
    setQualifyThresholdError(validateQualifyThreshold(qualifyThreshold))
  }

  function handleExpiresAtChange(value: string) {
    setExpiresAt(value)
    if (value && value < todayIso()) {
      setExpiresAtError('Expiry date must be today or in the future.')
    } else {
      setExpiresAtError(null)
    }
  }

  function handleFormSalaryMinChange(value: string) {
    setFormSalaryMin(value)
    setFormSalaryError(value !== '' && formSalaryMax !== '' && Number(value) > Number(formSalaryMax) ? 'Min must not exceed max' : null)
  }

  function handleFormSalaryMaxChange(value: string) {
    setFormSalaryMax(value)
    setFormSalaryError(formSalaryMin !== '' && value !== '' && Number(formSalaryMin) > Number(value) ? 'Min must not exceed max' : null)
  }

  function handleAddRound() {
    if (!selectedRoundTypeId) return
    const rt = roundTypes.find((r) => r.id === Number(selectedRoundTypeId))
    if (!rt) return
    setSelectedRounds((prev) => [...prev, { uid: crypto.randomUUID(), round_type_id: rt.id, name: rt.name, failing_criteria: '50' }])
    setSelectedRoundTypeId('')
  }

  function handleRemoveRound(uid: string) {
    setSelectedRounds((prev) => prev.filter((r) => r.uid !== uid))
  }

  function handleFailingCriteriaChange(uid: string, value: string) {
    const num = Number(value)
    const clamped = value === '' ? '' : String(Math.min(100, Math.max(0, num)))
    setSelectedRounds((prev) => prev.map((r) => (r.uid === uid ? { ...r, failing_criteria: clamped } : r)))
  }

  function handleDragStart(index: number) { dragIndexRef.current = index }

  function handleDragOver(e: React.DragEvent, index: number) {
    e.preventDefault()
    const from = dragIndexRef.current
    if (from === null || from === index) return
    setSelectedRounds((prev) => {
      const next = [...prev]
      const [item] = next.splice(from, 1)
      next.splice(index, 0, item)
      dragIndexRef.current = index
      return next
    })
  }

  function handleDragEnd() { dragIndexRef.current = null }

  async function handlePostJob(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttemptedPost(true)
    const jobCategoryErr = jobRoleId === '' ? validateJobCategoryText(jobCategoryInputText) : null
    setJobCategoryError(jobCategoryErr)
    const qualifyErr = validateQualifyThreshold(qualifyThreshold)
    setQualifyThresholdError(qualifyErr)
    if (
      jobRoleId === '' ||
      jobCategoryErr ||
      experienceLevelId === '' ||
      !jobType ||
      !jobDescription.trim() ||
      !jobLocation.trim() ||
      !formSalaryMin.trim() ||
      !formSalaryMax.trim() ||
      formSalaryError ||
      expiresAtError ||
      qualifyErr ||
      selectedRounds.length === 0 ||
      !atsValid
    ) return
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
        salary_range: formatSalaryRange(formSalaryMin, formSalaryMax),
        expires_at: expiresAt || undefined,
        skill_ids: selectedSkills.map((s) => s.value),
        interview_rounds: selectedRounds.map((r, i) => ({
          round_type_id: r.round_type_id,
          round_order: i + 1,
          failing_criteria: r.failing_criteria !== '' ? Math.min(100, Math.max(0, Number(r.failing_criteria))) : null,
        })),
        ats_criteria: atsEnabledCriteria.map((c) => ({ section: c.section, weight: Number(c.weight) || 0 })),
        qualify_threshold: qualifyThreshold !== '' ? Math.min(100, Math.max(0, Number(qualifyThreshold))) : undefined,
        overqualify_threshold: overqualifyThreshold !== '' ? Math.max(0, Number(overqualifyThreshold)) : undefined,
        auto_reject_overqualified: overqualifyThreshold !== '' ? autoRejectOverqualified : false,
      })
      setShowForm(false)
      handleResetForm()
      setJobs(await fetchRecruiterJobs(recruiterId))
    } catch (err: unknown) {
      setPostError(err instanceof Error ? err.message : 'Failed to post job')
    } finally {
      setPosting(false)
    }
  }

  // ── Job detail dialog ─────────────────────────────────────────────────────

  function handleOpenDetail(job: JobListItem) {
    setDetailJob(job)
    setDetailRounds([])
    setDetailRoundsLoading(true)
    fetchJobRounds(job.id)
      .then(setDetailRounds)
      .catch(() => {})
      .finally(() => setDetailRoundsLoading(false))
  }

  function handleCloseDetail() { setDetailJob(null); setDetailRounds([]) }

  // ── Filter bar ─────────────────────────────────────────────────────────────

  function handleLocationChange(value: string) {
    setLocationInput(value)
    setFilters((f) => ({ ...f, location: value.trim() || undefined }))
  }

  function handleSalaryMinChange(value: string) {
    setSalaryMin(value)
    setSalaryError(value !== '' && salaryMax !== '' && Number(value) > Number(salaryMax) ? 'Min must not exceed max' : null)
  }

  function handleSalaryMaxChange(value: string) {
    setSalaryMax(value)
    setSalaryError(salaryMin !== '' && value !== '' && Number(salaryMin) > Number(value) ? 'Min must not exceed max' : null)
  }

  function clearFilters() {
    setLocationInput(''); setSalaryMin(''); setSalaryMax(''); setSalaryError(null); setFilters({})
  }

  if (!recruiterId) return null

  const atsEnabledCriteria = atsCriteria.filter((c) => c.enabled)
  const atsTotalWeight = atsEnabledCriteria.reduce((sum, c) => sum + (Number(c.weight) || 0), 0)
  const atsValid = atsEnabledCriteria.length > 0 && atsTotalWeight === 100

  return (
    <main className="rd-page">
      <header className="rd-header">
        <h1 className="rd-heading">Recruiter Dashboard</h1>
        <button className="rd-post-job-btn" onClick={handleOpenForm} aria-label="Post a Job">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          Post a Job
        </button>
      </header>

      <div className="rd-content">
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
          countLabel="job"
          loading={jobsLoading}
          onFiltersChange={(update) => setFilters((f) => ({ ...f, ...update }))}
          onLocationChange={handleLocationChange}
          onSalaryMinChange={handleSalaryMinChange}
          onSalaryMaxChange={handleSalaryMaxChange}
          onClearFilters={clearFilters}
        />

        <div className="rd-scroll-area">
          {jobsLoading ? (
            <p className="rd-state-text">Loading your jobs…</p>
          ) : jobsError ? (
            <p className="rd-state-error">{jobsError}</p>
          ) : jobs.length === 0 ? (
            <div className="rd-empty">
              <p className="rd-empty-text">No jobs posted yet.</p>
              <p className="rd-empty-sub">Click "Post a Job" to publish your first listing.</p>
            </div>
          ) : filteredJobs.length === 0 ? (
            <p className="rd-state-text">No jobs match your filters. Try adjusting or clearing them.</p>
          ) : (
            <div className="rd-jobs-grid">
              {filteredJobs.map((job) => (
                <article
                  key={job.id}
                  className="rd-job-card"
                  onClick={() => handleOpenDetail(job)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => e.key === 'Enter' && handleOpenDetail(job)}
                >
                  <div className="rd-job-main">
                    <div className="rd-job-card-top">
                      <span className="rd-job-company">{job.company}</span>
                      <span className={`rd-status-badge rd-status-badge--${job.status}`}>{job.status}</span>
                    </div>
                    <h3 className="rd-job-title">{`${job.experience_level_name} ${job.job_role_title}`}</h3>
                    <p className="rd-job-desc">{job.description}</p>
                  </div>
                  <div className="rd-job-footer">
                    <div className="rd-job-tags">
                      <span className="rd-badge">{job.job_type}</span>
                      {job.salary_range && <span className="rd-badge rd-badge--salary">{job.salary_range}</span>}
                    </div>
                    <div className="rd-job-meta-row">
                      <span className="rd-job-location">{job.location}</span>
                      <span className="rd-job-date">Posted {formatDate(job.posted_at)}</span>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Post Job Dialog ── */}
      <Modal isOpen={showForm} onClose={handleCloseForm}>
        <div className="rd-post-dialog">
          {/* Header */}
          <div className="rd-dialog-header">
            <div className="rd-dialog-header-text">
              <span className="rd-dialog-eyebrow">New Listing</span>
              <h2 className="rd-dialog-title">Post a Job</h2>
            </div>
            <button type="button" className="rd-close-btn" onClick={handleCloseForm} aria-label="Close">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          {/* Two-column body */}
          <form className="rd-form" onSubmit={handlePostJob}>
            <div className="rd-form-cols">
              {/* Left — job details */}
              <div className="rd-form-left">
                <div className="rd-field-group">
                  <div className="rd-field">
                    <label className="rd-label">Job Category<span className="required-star"> *</span></label>
                    {metaLoading ? <p className="rd-state-text">Loading…</p> : (
                      <TaxonomySelect
                        loadOptions={loadJobRoleOptions}
                        onCreateOption={createJobRoleOption}
                        value={jobRole}
                        onChange={(opt) => {
                          setJobRole(opt)
                          setSelectedSkills([])
                          setJobCategoryInputText('')
                          setJobCategoryError(null)
                        }}
                        onInputChange={handleJobCategoryInputChange}
                        onBlur={handleJobCategoryBlur}
                        placeholder="Search or type to add a category…"
                      />
                    )}
                    {jobCategoryError && (
                      <span className="rd-field-error">{jobCategoryError}</span>
                    )}
                    {attemptedPost && jobRoleId === '' && !jobCategoryError && (
                      <span className="rd-field-error">Job category is required.</span>
                    )}
                  </div>
                  <div className="rd-field">
                    <label className="rd-label">Experience Level<span className="required-star"> *</span></label>
                    {metaLoading ? <p className="rd-state-text">Loading…</p> : (
                      <Select value={experienceLevelId} onChange={(e: ChangeEvent<HTMLSelectElement>) => setExperienceLevelId(Number(e.target.value))}>
                        <option value="" disabled>Select a level</option>
                        {experienceLevels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                      </Select>
                    )}
                    {attemptedPost && experienceLevelId === '' && (
                      <span className="rd-field-error">Experience level is required.</span>
                    )}
                  </div>
                </div>

                <div className="rd-field">
                  <label className="rd-label">Description<span className="required-star"> *</span></label>
                  <textarea
                    className="rd-textarea"
                    placeholder="Describe the role, responsibilities, and requirements…"
                    value={jobDescription}
                    onChange={(e) => setJobDescription(e.target.value)}
                    required
                    rows={5}
                  />
                  {attemptedPost && !jobDescription.trim() && (
                    <span className="rd-field-error">Description is required.</span>
                  )}
                </div>

                <div className="rd-field-group">
                  <div className="rd-field">
                    <label className="rd-label">Location<span className="required-star"> *</span></label>
                    <input className="rd-input" type="text" placeholder="e.g. New York, NY" value={jobLocation} onChange={(e) => setJobLocation(e.target.value)} required />
                    {attemptedPost && !jobLocation.trim() && (
                      <span className="rd-field-error">Location is required.</span>
                    )}
                  </div>
                  <div className="rd-field">
                    <label className="rd-label">Job Type<span className="required-star"> *</span></label>
                    <Select value={jobType} onChange={(e: ChangeEvent<HTMLSelectElement>) => setJobType(e.target.value)}>
                      <option value="" disabled>Select type</option>
                      {JOB_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </Select>
                    {attemptedPost && !jobType && (
                      <span className="rd-field-error">Job type is required.</span>
                    )}
                  </div>
                </div>

                <div className="rd-field">
                  <label className="rd-label">Salary Range<span className="required-star"> *</span></label>
                  <div className="rd-salary-row">
                    <div className="rd-salary-field">
                      <span className="rd-salary-prefix">$</span>
                      <input className="rd-input rd-salary-input" type="number" min="0" max="10000000" step="1000" placeholder="Min" value={formSalaryMin} onChange={(e) => handleFormSalaryMinChange(e.target.value)} onKeyDown={blockNonNumericKey} />
                    </div>
                    <span className="rd-salary-sep">—</span>
                    <div className="rd-salary-field">
                      <span className="rd-salary-prefix">$</span>
                      <input className="rd-input rd-salary-input" type="number" min="0" max="10000000" step="1000" placeholder="Max" value={formSalaryMax} onChange={(e) => handleFormSalaryMaxChange(e.target.value)} onKeyDown={blockNonNumericKey} />
                    </div>
                  </div>
                  {formSalaryError && <span className="rd-field-error">{formSalaryError}</span>}
                  {attemptedPost && !formSalaryError && (!formSalaryMin.trim() || !formSalaryMax.trim()) && (
                    <span className="rd-field-error">Salary range is required.</span>
                  )}
                </div>

                <div className="rd-field">
                  <label className="rd-label">Expires On <span className="rd-optional">(optional)</span></label>
                  <input
                    className="rd-input"
                    type="date"
                    value={expiresAt}
                    min={todayIso()}
                    onChange={(e) => handleExpiresAtChange(e.target.value)}
                  />
                  {expiresAtError && <span className="rd-field-error">{expiresAtError}</span>}
                </div>

                <div className="rd-field">
                  <label className="rd-label">Required Skills <span className="rd-optional">(optional)</span></label>
                  <TaxonomySelect
                    key={jobRoleId || 'none'}
                    isMulti
                    loadOptions={loadSkillOptions}
                    onCreateOption={createSkillOption}
                    value={selectedSkills}
                    onChange={setSelectedSkills}
                    placeholder={jobRoleId === '' ? 'Select a job category first…' : 'Search or type to add skills…'}
                    isDisabled={metaLoading || jobRoleId === ''}
                    controlShouldRenderValue={false}
                  />
                  {selectedSkills.length > 0 && (
                    <div className="rd-skill-tags">
                      {selectedSkills.map((opt) => (
                        <span key={opt.value} className="rd-skill-tag">
                          {opt.label}
                          <button
                            type="button"
                            className="rd-skill-tag-remove"
                            onClick={() => setSelectedSkills((prev) => prev.filter((s) => s.value !== opt.value))}
                            aria-label={`Remove ${opt.label}`}
                          >✕</button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Divider */}
              <div className="rd-form-divider" />

              {/* Right — interview rounds */}
              <div className="rd-form-right">
                <div className="rd-rounds-header">
                  <span className="rd-label">ATS Evaluation Sections<span className="required-star"> *</span></span>
                  <span className="rd-rounds-count">{atsTotalWeight}% total</span>
                </div>
                <ol className="rd-rounds-list">
                  {atsCriteria.map((c) => (
                    <li key={c.section} className="rd-round-item">
                      <input
                        type="checkbox"
                        checked={c.enabled}
                        onChange={() => handleToggleAtsSection(c.section)}
                      />
                      <span className="rd-round-name">{c.label}</span>
                      {c.enabled && (
                        <div className="rd-round-threshold">
                          <input
                            className="rd-threshold-input"
                            type="number" min="0" max="100"
                            value={c.weight}
                            onChange={(e) => handleAtsWeightChange(c.section, e.target.value)}
                            onKeyDown={blockNonNumericKey}
                          />
                          <span className="rd-threshold-suffix">%</span>
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
                {attemptedPost && atsEnabledCriteria.length === 0 && (
                  <span className="rd-field-error">Select at least one ATS section</span>
                )}
                {attemptedPost && atsEnabledCriteria.length > 0 && atsTotalWeight !== 100 && (
                  <span className="rd-field-error">Weights must total 100%</span>
                )}

                <ol className="rd-rounds-list">
                  <li className="rd-round-item">
                    <span className="rd-round-name">
                      Qualify threshold
                      <InfoTooltip text="Minimum weighted score required to pass ATS." />
                    </span>
                    <div className="rd-round-threshold">
                      <input
                        className="rd-threshold-input"
                        type="number" min="0" max="100"
                        value={qualifyThreshold}
                        onChange={(e) => setQualifyThreshold(e.target.value)}
                        onBlur={handleQualifyThresholdBlur}
                        onKeyDown={blockNonNumericKey}
                      />
                      <span className="rd-threshold-suffix">%</span>
                    </div>
                  </li>
                  {qualifyThresholdError && (
                    <li className="rd-round-item">
                      <span className="rd-field-error">{qualifyThresholdError}</span>
                    </li>
                  )}
                  <li className="rd-round-item">
                    <span className="rd-round-name">
                      Overqualify threshold (optional)
                      <InfoTooltip text="A multiplier, not a percentage — enter 2 to flag candidates with 2× (double) the required years, 1.5 for 1.5×, and so on. Leave blank to never flag overqualification." />
                    </span>
                    <div className="rd-round-threshold">
                      <input
                        className="rd-threshold-input"
                        type="number" min="0" step="0.1"
                        placeholder="e.g. 2"
                        value={overqualifyThreshold}
                        onChange={(e) => setOverqualifyThreshold(e.target.value)}
                        onKeyDown={blockNonNumericKey}
                      />
                      <span className="rd-threshold-suffix">×</span>
                    </div>
                  </li>
                  {overqualifyThreshold !== '' && (
                    <li className="rd-round-item">
                      <input
                        type="checkbox"
                        checked={autoRejectOverqualified}
                        onChange={() => setAutoRejectOverqualified((v) => !v)}
                      />
                      <span className="rd-round-name">Auto-reject overqualified candidates</span>
                    </li>
                  )}
                </ol>
                <p className="rd-threshold-hint">
                  Qualify threshold = minimum weighted score to pass ATS. Overqualify threshold is a multiplier, not a percentage — enter 2 to flag candidates with 2× (double) the required years, 1.5 for 1.5×, and so on. Leave blank to never flag overqualification.
                </p>

                <div className="rd-rounds-header">
                  <span className="rd-label">Interview Rounds<span className="required-star"> *</span></span>
                  <span className="rd-rounds-count">{selectedRounds.length} added</span>
                </div>
                {attemptedPost && selectedRounds.length === 0 && (
                  <span className="rd-field-error">At least one interview round is required.</span>
                )}

                <div className="rd-rounds-add-row">
                  <select
                    className="rd-rounds-select"
                    value={selectedRoundTypeId}
                    onChange={(e) => setSelectedRoundTypeId(e.target.value)}
                    disabled={metaLoading}
                  >
                    <option value="">Select round type…</option>
                    {roundTypes.map((rt) => <option key={rt.id} value={rt.id}>{rt.name}</option>)}
                  </select>
                  <button type="button" className="rd-add-btn" onClick={handleAddRound} disabled={!selectedRoundTypeId}>
                    Add
                  </button>
                </div>

                {selectedRounds.length === 0 ? (
                  <div className="rd-rounds-empty-state">
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="rd-rounds-empty-icon">
                      <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                    <p className="rd-rounds-empty-text">No rounds yet.</p>
                    <p className="rd-rounds-empty-sub">Candidates will proceed directly to hiring.</p>
                  </div>
                ) : (
                  <ol className="rd-rounds-list">
                    {selectedRounds.map((round, index) => (
                      <li
                        key={round.uid}
                        className="rd-round-item"
                        draggable
                        onDragStart={() => handleDragStart(index)}
                        onDragOver={(e) => handleDragOver(e, index)}
                        onDragEnd={handleDragEnd}
                      >
                        <span className="rd-round-drag" aria-hidden>⠿</span>
                        <span className="rd-round-badge">{index + 1}</span>
                        <span className="rd-round-name">{round.name}</span>
                        <div className="rd-round-threshold">
                          <input
                            className="rd-threshold-input"
                            type="number" min="0" max="100"
                            value={round.failing_criteria}
                            onChange={(e) => handleFailingCriteriaChange(round.uid, e.target.value)}
                            onKeyDown={blockNonNumericKey}
                          />
                          <span className="rd-threshold-suffix">%</span>
                        </div>
                        <button type="button" className="rd-round-remove" onClick={() => handleRemoveRound(round.uid)} aria-label="Remove">✕</button>
                      </li>
                    ))}
                  </ol>
                )}

                <p className="rd-threshold-hint">% = minimum score to pass this round</p>
              </div>
            </div>

            {postError && <p className="rd-field-error rd-post-error">{postError}</p>}

            <div className="rd-form-actions">
              <Button type="button" variant="secondary" onClick={handleCloseForm}>Discard</Button>
              <Button type="submit" variant="primary" disabled={posting || !!formSalaryError || !!expiresAtError || !!jobCategoryError || !!qualifyThresholdError}>
                {posting ? 'Publishing…' : 'Publish Job'}
              </Button>
            </div>
          </form>
        </div>
      </Modal>

      {/* ── Job Detail Dialog ── */}
      <Modal isOpen={detailJob !== null} onClose={handleCloseDetail}>
        {detailJob && (
          <div className="rd-detail-dialog">
            {/* Header */}
            <div className="rd-dialog-header">
              <div className="rd-dialog-header-text">
                <span className="rd-dialog-eyebrow">{detailJob.company}</span>
                <h2 className="rd-dialog-title">{`${detailJob.experience_level_name} ${detailJob.job_role_title}`}</h2>
              </div>
              <div className="rd-dialog-header-actions">
                <button
                  type="button"
                  className="rd-stats-btn-inline"
                  onClick={() => {
                    handleCloseDetail()
                    navigate(`/job-stats/${detailJob!.id}`)
                  }}
                >
                  Check Job Stats
                </button>
                <button type="button" className="rd-close-btn" onClick={handleCloseDetail} aria-label="Close">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Two-column body */}
            <div className="rd-detail-cols">
              {/* Left — description */}
              <div className="rd-detail-left">
                <div className="rd-detail-tags">
                  <span className="rd-badge">{detailJob.job_type}</span>
                  {detailJob.salary_range && <span className="rd-badge rd-badge--salary">{detailJob.salary_range}</span>}
                </div>
                <p className="rd-detail-description">{detailJob.description}</p>
              </div>

              {/* Divider */}
              <div className="rd-form-divider" />

              {/* Right — meta + rounds */}
              <div className="rd-detail-right">
                <div className="rd-detail-meta">
                  <div className="rd-meta-item">
                    <span className="rd-label">Location</span>
                    <span className="rd-meta-value">{detailJob.location}</span>
                  </div>
                  {detailJob.expires_at && (
                    <div className="rd-meta-item">
                      <span className="rd-label">Expires</span>
                      <span className="rd-meta-value">{formatDate(detailJob.expires_at)}</span>
                    </div>
                  )}
                  <div className="rd-meta-item">
                    <span className="rd-label">Posted</span>
                    <span className="rd-meta-value">{formatDate(detailJob.posted_at)}</span>
                  </div>
                </div>

                {detailJob.required_skills.length > 0 && (
                  <div className="rd-detail-skills-section">
                    <span className="rd-label">Required Skills</span>
                    <div className="rd-skill-tags">
                      {detailJob.required_skills.map((skill) => (
                        <span key={skill} className="rd-skill-tag rd-skill-tag--readonly">{skill}</span>
                      ))}
                    </div>
                  </div>
                )}

                <div className="rd-detail-rounds-section">
                  <span className="rd-label">Interview Pipeline</span>
                  {detailRoundsLoading ? (
                    <p className="rd-state-text">Loading rounds…</p>
                  ) : detailRounds.length === 0 ? (
                    <p className="rd-rounds-empty-text" style={{ marginTop: 8 }}>No rounds configured.</p>
                  ) : (
                    <ol className="rd-detail-rounds">
                      {detailRounds.map((r) => (
                        <li key={r.round_order} className="rd-detail-round-item">
                          <span className="rd-round-badge">{r.round_order}</span>
                          <span className="rd-round-name">{r.round_type_name}</span>
                          {r.failing_criteria !== null && (
                            <span className="rd-pass-pill">{r.failing_criteria}% pass</span>
                          )}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>

                <div className="rd-detail-rounds-section">
                  <span className="rd-label">ATS Screening Criteria</span>
                  {detailJob.ats_criteria && detailJob.ats_criteria.has_config && detailJob.ats_criteria.criteria.length > 0 ? (
                    <>
                      <ol className="rd-detail-rounds">
                        {detailJob.ats_criteria.criteria.map((c) => (
                          <li key={c.section} className="rd-detail-round-item">
                            <span className="rd-round-name">{ATS_SECTION_LABELS[c.section] ?? c.section}</span>
                            <span className="rd-pass-pill">{c.weight}%</span>
                          </li>
                        ))}
                      </ol>
                      <div className="rd-detail-meta">
                        <div className="rd-meta-item">
                          <span className="rd-label">Qualify Threshold</span>
                          <span className="rd-meta-value">{detailJob.ats_criteria.qualify_threshold}%</span>
                        </div>
                        <div className="rd-meta-item">
                          <span className="rd-label">Overqualify Threshold</span>
                          <span className="rd-meta-value">
                            {detailJob.ats_criteria.overqualify_threshold != null
                              ? `${detailJob.ats_criteria.overqualify_threshold}×`
                              : 'Not set'}
                          </span>
                        </div>
                      </div>
                      <span className={`rd-badge${detailJob.ats_criteria.auto_reject_overqualified ? ' rd-badge--salary' : ''}`}>
                        Auto-reject overqualified: {detailJob.ats_criteria.auto_reject_overqualified ? 'On' : 'Off'}
                      </span>
                    </>
                  ) : (
                    <p className="rd-rounds-empty-text" style={{ marginTop: 8 }}>Default ATS criteria (65% threshold)</p>
                  )}
                </div>

              </div>
            </div>
          </div>
        )}
      </Modal>
    </main>
  )
}

export default RecruiterDashboard
