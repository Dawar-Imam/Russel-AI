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
  fetchAtsRerunStatus,
  fetchInterviewRoundTypes,
  fetchJobRounds,
  fetchJobSkills,
  fetchRecruiterJobs,
  postJob,
  rerunAts,
  updateJob,
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
  time_limit_minutes: string
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

function atsCriteriaFromJob(job: JobListItem): ATSCriterionState[] {
  if (!job.ats_criteria || !job.ats_criteria.has_config) return defaultAtsCriteria()
  const bySection = new Map(job.ats_criteria.criteria.map((c) => [c.section, c.weight]))
  return ATS_SECTION_DEFS.map((d) => ({
    section: d.section,
    label: d.label,
    enabled: bySection.has(d.section),
    weight: String(bySection.get(d.section) ?? d.defaultWeight),
  }))
}

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

  // ATS rerun (recruiter-triggered) — keyed by job id so the badge survives dialog close/reopen
  const [rerunStatusByJob, setRerunStatusByJob] = useState<Record<string, { total: number; completed: number; inProgress: boolean }>>({})
  const [rerunStarting, setRerunStarting] = useState(false)
  const [rerunError, setRerunError] = useState<string | null>(null)
  // Snapshot from the most recent "Rerun ATS" click — how many candidates for that job
  // have an interview In Progress right now and were skipped entirely (not queued, not
  // even LLM-checked) because of it. Point-in-time like skipped_pending/excluded, not
  // re-polled — it reflects what happened at dispatch, not live state.
  const [rerunInProgressCountByJob, setRerunInProgressCountByJob] = useState<Record<string, number>>({})
  // Same snapshot semantics as rerunInProgressCountByJob above, but for candidates
  // skipped because they were already scored against this job's current ATS criteria —
  // lets the UI explain a 0-queued rerun instead of it looking like nothing happened.
  const [rerunNotStaleCountByJob, setRerunNotStaleCountByJob] = useState<Record<string, number>>({})
  const rerunPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function pollRerunStatus(jobId: string) {
    if (rerunPollRef.current) clearInterval(rerunPollRef.current)
    rerunPollRef.current = setInterval(() => {
      fetchAtsRerunStatus(jobId)
        .then(status => {
          setRerunStatusByJob(prev => ({
            ...prev,
            [jobId]: { total: status.total_queued, completed: status.completed, inProgress: status.in_progress },
          }))
          if (!status.in_progress && rerunPollRef.current) {
            clearInterval(rerunPollRef.current)
            rerunPollRef.current = null
          }
        })
        .catch(() => {
          if (rerunPollRef.current) {
            clearInterval(rerunPollRef.current)
            rerunPollRef.current = null
          }
        })
    }, 3000)
  }

  useEffect(() => {
    return () => {
      if (rerunPollRef.current) clearInterval(rerunPollRef.current)
    }
  }, [])

  function handleRerunAts(jobId: string) {
    setRerunError(null)
    setRerunStarting(true)
    rerunAts(jobId, recruiterId)
      .then(result => {
        setRerunStatusByJob(prev => ({
          ...prev,
          [jobId]: { total: result.queued, completed: 0, inProgress: result.queued > 0 },
        }))
        setRerunInProgressCountByJob(prev => ({ ...prev, [jobId]: result.in_progress_count }))
        setRerunNotStaleCountByJob(prev => ({ ...prev, [jobId]: result.not_stale_count }))
        if (result.queued > 0) pollRerunStatus(jobId)
      })
      .catch(err => setRerunError(err instanceof Error ? err.message : 'Failed to start ATS rerun'))
      .finally(() => setRerunStarting(false))
  }

  // Inline job-edit (within the same detail dialog card) — separate draft state from
  // detailJob so Cancel can discard without touching the displayed job, and Save only
  // commits once the PUT succeeds.
  const [editMode, setEditMode] = useState(false)
  const [editDescription, setEditDescription] = useState('')
  const [editLocation, setEditLocation] = useState('')
  const [editJobType, setEditJobType] = useState('')
  const [editSalaryMin, setEditSalaryMin] = useState('')
  const [editSalaryMax, setEditSalaryMax] = useState('')
  const [editSalaryError, setEditSalaryError] = useState<string | null>(null)
  const [editExpiresAt, setEditExpiresAt] = useState('')
  const [editExpiresAtError, setEditExpiresAtError] = useState<string | null>(null)
  const [editStatus, setEditStatus] = useState<'active' | 'closed'>('active')
  const [editSkills, setEditSkills] = useState<TaxonomyOption[]>([])
  const [editSkillsLoading, setEditSkillsLoading] = useState(false)
  const [editSkillsLoadFailed, setEditSkillsLoadFailed] = useState(false)
  const [editAtsCriteria, setEditAtsCriteria] = useState<ATSCriterionState[]>(defaultAtsCriteria())
  const [editQualifyThreshold, setEditQualifyThreshold] = useState('65')
  const [editQualifyThresholdError, setEditQualifyThresholdError] = useState<string | null>(null)
  const [editOverqualifyThreshold, setEditOverqualifyThreshold] = useState('')
  const [editAutoRejectOverqualified, setEditAutoRejectOverqualified] = useState(false)
  const [editSaving, setEditSaving] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)
  const [editAttempted, setEditAttempted] = useState(false)

  function handleOpenEdit() {
    if (!detailJob) return
    setEditDescription(detailJob.description)
    setEditLocation(detailJob.location)
    setEditJobType(detailJob.job_type)
    const bounds = parseSalaryBounds(detailJob.salary_range)
    setEditSalaryMin(bounds ? String(bounds[0]) : '')
    setEditSalaryMax(bounds ? String(bounds[1]) : '')
    setEditSalaryError(null)
    setEditExpiresAt(detailJob.expires_at ? detailJob.expires_at.split('T')[0] : '')
    setEditExpiresAtError(null)
    setEditStatus(detailJob.status === 'closed' ? 'closed' : 'active')
    setEditAtsCriteria(atsCriteriaFromJob(detailJob))
    setEditQualifyThreshold(String(detailJob.ats_criteria?.qualify_threshold ?? 65))
    setEditQualifyThresholdError(null)
    setEditOverqualifyThreshold(
      detailJob.ats_criteria?.overqualify_threshold != null ? String(detailJob.ats_criteria.overqualify_threshold) : '',
    )
    setEditAutoRejectOverqualified(detailJob.ats_criteria?.auto_reject_overqualified ?? false)
    setEditError(null)
    setEditAttempted(false)
    setEditSkills([])
    setEditSkillsLoadFailed(false)
    setEditSkillsLoading(true)
    fetchJobSkills(detailJob.id)
      .then((skills) => setEditSkills(skills.map((s) => ({ value: s.id, label: s.name }))))
      .catch(() => setEditSkillsLoadFailed(true))
      .finally(() => setEditSkillsLoading(false))
    setEditMode(true)
  }

  function handleCancelEdit() {
    setEditMode(false)
    setEditError(null)
  }

  function handleToggleEditAtsSection(section: string) {
    setEditAtsCriteria((prev) => prev.map((c) => (c.section === section ? { ...c, enabled: !c.enabled } : c)))
  }

  function handleEditAtsWeightChange(section: string, value: string) {
    setEditAtsCriteria((prev) => prev.map((c) => (c.section === section ? { ...c, weight: value } : c)))
  }

  function handleEditSalaryMinChange(value: string) {
    setEditSalaryMin(value)
    setEditSalaryError(value !== '' && editSalaryMax !== '' && Number(value) > Number(editSalaryMax) ? 'Min must not exceed max' : null)
  }

  function handleEditSalaryMaxChange(value: string) {
    setEditSalaryMax(value)
    setEditSalaryError(editSalaryMin !== '' && value !== '' && Number(editSalaryMin) > Number(value) ? 'Min must not exceed max' : null)
  }

  function handleEditExpiresAtChange(value: string) {
    setEditExpiresAt(value)
    setEditExpiresAtError(value && value < todayIso() ? 'Expiry date must be today or in the future.' : null)
  }

  function handleEditQualifyThresholdBlur() {
    setEditQualifyThresholdError(validateQualifyThreshold(editQualifyThreshold))
  }

  async function loadEditSkillOptions(query: string): Promise<TaxonomyOption[]> {
    if (!detailJob) return []
    const skills = await searchSkills(detailJob.job_role_id, query)
    return skills.map((s) => ({ value: s.id, label: s.name }))
  }

  async function createEditSkillOption(name: string): Promise<TaxonomyOption> {
    const skill = await createSkill(name, detailJob ? detailJob.job_role_id : null)
    return { value: skill.id, label: skill.name }
  }

  async function handleSaveEdit() {
    if (!detailJob) return
    setEditAttempted(true)
    const qualifyErr = validateQualifyThreshold(editQualifyThreshold)
    setEditQualifyThresholdError(qualifyErr)
    if (
      !editDescription.trim() ||
      !editLocation.trim() ||
      !editJobType ||
      !editSalaryMin.trim() ||
      !editSalaryMax.trim() ||
      editSalaryError ||
      editExpiresAtError ||
      qualifyErr ||
      !editAtsValid
    ) return

    setEditSaving(true)
    setEditError(null)
    try {
      await updateJob(detailJob.id, recruiterId, {
        description: editDescription,
        location: editLocation,
        job_type: editJobType,
        salary_range: formatSalaryRange(editSalaryMin, editSalaryMax) ?? undefined,
        expires_at: editExpiresAt || undefined,
        status: editStatus,
        // Omitted (not sent) if the skill-id lookup failed, so a failed fetch can never
        // silently wipe the job's existing required skills on save.
        skill_ids: editSkillsLoadFailed ? undefined : editSkills.map((s) => s.value),
        ats_criteria: editAtsEnabledCriteria.map((c) => ({ section: c.section, weight: Number(c.weight) || 0 })),
        qualify_threshold: Math.min(100, Math.max(0, Number(editQualifyThreshold))),
        overqualify_threshold: editOverqualifyThreshold !== '' ? Math.max(0, Number(editOverqualifyThreshold)) : undefined,
        auto_reject_overqualified: editOverqualifyThreshold !== '' ? editAutoRejectOverqualified : false,
      })
      const updatedJobs = await fetchRecruiterJobs(recruiterId)
      setJobs(updatedJobs)
      const updatedDetail = updatedJobs.find((j) => j.id === detailJob.id)
      if (updatedDetail) setDetailJob(updatedDetail)
      setEditMode(false)
    } catch (err) {
      setEditError(err instanceof Error ? err.message : 'Failed to update job')
    } finally {
      setEditSaving(false)
    }
  }

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
    setSelectedRounds((prev) => [
      ...prev,
      { uid: crypto.randomUUID(), round_type_id: rt.id, name: rt.name, failing_criteria: '50', time_limit_minutes: '' },
    ])
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

  // Blank = let the backend default it (45 min for non-oral rounds; oral rounds keep
  // their existing global default) — so this only clamps to a positive integer, no cap.
  function handleDurationChange(uid: string, value: string) {
    const num = Number(value)
    const clamped = value === '' ? '' : String(Math.max(1, Math.trunc(num) || 1))
    setSelectedRounds((prev) => prev.map((r) => (r.uid === uid ? { ...r, time_limit_minutes: clamped } : r)))
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
          time_limit_minutes: r.time_limit_minutes !== '' ? Math.max(1, Number(r.time_limit_minutes)) : null,
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

  function handleCloseDetail() {
    setDetailJob(null); setDetailRounds([]); setEditMode(false); setEditError(null)
  }

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

  const editAtsEnabledCriteria = editAtsCriteria.filter((c) => c.enabled)
  const editAtsTotalWeight = editAtsEnabledCriteria.reduce((sum, c) => sum + (Number(c.weight) || 0), 0)
  const editAtsValid = editAtsEnabledCriteria.length > 0 && editAtsTotalWeight === 100

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
                        <div className="rd-round-threshold" title="Candidate time limit — defaults to 45 min if left blank">
                          <input
                            className="rd-threshold-input"
                            type="number" min="1"
                            placeholder="45"
                            value={round.time_limit_minutes}
                            onChange={(e) => handleDurationChange(round.uid, e.target.value)}
                            onKeyDown={blockNonNumericKey}
                          />
                          <span className="rd-threshold-suffix">min</span>
                        </div>
                        <button type="button" className="rd-round-remove" onClick={() => handleRemoveRound(round.uid)} aria-label="Remove">✕</button>
                      </li>
                    ))}
                  </ol>
                )}

                <p className="rd-threshold-hint">% = minimum score to pass this round · min = candidate time limit (blank = 45 min default)</p>
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
                {!editMode && (
                  <>
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
                    <button
                      type="button"
                      className="rd-stats-btn-inline"
                      disabled={rerunStarting}
                      onClick={() => handleRerunAts(detailJob.id)}
                      title="Re-run ATS screening for every eligible applicant against this job's current requirements"
                    >
                      {rerunStatusByJob[detailJob.id]?.inProgress
                        ? `Rerunning ATS… (${rerunStatusByJob[detailJob.id].completed}/${rerunStatusByJob[detailJob.id].total})`
                        : 'Rerun ATS'}
                    </button>
                    <button type="button" className="rd-stats-btn-inline" onClick={handleOpenEdit} title="Edit job details">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4 }}>
                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4Z" />
                      </svg>
                      Edit
                    </button>
                  </>
                )}
                <button type="button" className="rd-close-btn" onClick={handleCloseDetail} aria-label="Close">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>
            </div>
            {!editMode && rerunError && <p className="rd-field-error">{rerunError}</p>}
            {!editMode && !rerunStatusByJob[detailJob.id]?.inProgress && rerunStatusByJob[detailJob.id]?.total > 0 && (
              <p className="rd-rounds-empty-text">ATS rerun complete for {rerunStatusByJob[detailJob.id].total} candidate(s).</p>
            )}
            {!editMode && (rerunInProgressCountByJob[detailJob.id] ?? 0) > 0 && (
              <p className="rd-rounds-empty-text">
                {rerunInProgressCountByJob[detailJob.id]} candidate{rerunInProgressCountByJob[detailJob.id] === 1 ? '' : 's'} {rerunInProgressCountByJob[detailJob.id] === 1 ? 'has' : 'have'} an interview in progress — ATS screening will run once their interview finishes.
              </p>
            )}
            {!editMode && (rerunNotStaleCountByJob[detailJob.id] ?? 0) > 0 && (
              <p className="rd-rounds-empty-text">
                {rerunNotStaleCountByJob[detailJob.id]} candidate{rerunNotStaleCountByJob[detailJob.id] === 1 ? '' : 's'} already screened against the current criteria — please update the job description/ATS criteria to re-screen {rerunNotStaleCountByJob[detailJob.id] === 1 ? 'them' : 'these candidates'}.
              </p>
            )}

            {/* Two-column body */}
            <div className="rd-detail-cols">
              {/* Left — description */}
              <div className="rd-detail-left">
                {editMode ? (
                  <>
                    <div className="rd-field-group">
                      <div className="rd-field">
                        <label className="rd-label">Job Type<span className="required-star"> *</span></label>
                        <Select value={editJobType} onChange={(e: ChangeEvent<HTMLSelectElement>) => setEditJobType(e.target.value)}>
                          <option value="" disabled>Select type</option>
                          {JOB_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                        </Select>
                        {editAttempted && !editJobType && <span className="rd-field-error">Job type is required.</span>}
                      </div>
                      <div className="rd-field">
                        <label className="rd-label">Status</label>
                        <Select value={editStatus} onChange={(e: ChangeEvent<HTMLSelectElement>) => setEditStatus(e.target.value as 'active' | 'closed')}>
                          <option value="active">Active</option>
                          <option value="closed">Closed</option>
                        </Select>
                      </div>
                    </div>
                    <div className="rd-field">
                      <label className="rd-label">Salary Range<span className="required-star"> *</span></label>
                      <div className="rd-salary-row">
                        <div className="rd-salary-field">
                          <span className="rd-salary-prefix">$</span>
                          <input className="rd-input rd-salary-input" type="number" min="0" max="10000000" step="1000" placeholder="Min" value={editSalaryMin} onChange={(e) => handleEditSalaryMinChange(e.target.value)} onKeyDown={blockNonNumericKey} />
                        </div>
                        <span className="rd-salary-sep">—</span>
                        <div className="rd-salary-field">
                          <span className="rd-salary-prefix">$</span>
                          <input className="rd-input rd-salary-input" type="number" min="0" max="10000000" step="1000" placeholder="Max" value={editSalaryMax} onChange={(e) => handleEditSalaryMaxChange(e.target.value)} onKeyDown={blockNonNumericKey} />
                        </div>
                      </div>
                      {editSalaryError && <span className="rd-field-error">{editSalaryError}</span>}
                      {editAttempted && !editSalaryError && (!editSalaryMin.trim() || !editSalaryMax.trim()) && (
                        <span className="rd-field-error">Salary range is required.</span>
                      )}
                    </div>
                    <div className="rd-field">
                      <label className="rd-label">Description<span className="required-star"> *</span></label>
                      <textarea
                        className="rd-textarea"
                        value={editDescription}
                        onChange={(e) => setEditDescription(e.target.value)}
                        rows={7}
                      />
                      {editAttempted && !editDescription.trim() && <span className="rd-field-error">Description is required.</span>}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="rd-detail-tags">
                      <span className="rd-badge">{detailJob.job_type}</span>
                      {detailJob.salary_range && <span className="rd-badge rd-badge--salary">{detailJob.salary_range}</span>}
                      <span className={`rd-status-badge rd-status-badge--${detailJob.status}`}>{detailJob.status}</span>
                    </div>
                    <p className="rd-detail-description">{detailJob.description}</p>
                  </>
                )}
              </div>

              {/* Divider */}
              <div className="rd-form-divider" />

              {/* Right — meta + rounds */}
              <div className="rd-detail-right">
                {editMode ? (
                  <>
                    <div className="rd-field">
                      <label className="rd-label">Location<span className="required-star"> *</span></label>
                      <input className="rd-input" type="text" value={editLocation} onChange={(e) => setEditLocation(e.target.value)} />
                      {editAttempted && !editLocation.trim() && <span className="rd-field-error">Location is required.</span>}
                    </div>
                    <div className="rd-field">
                      <label className="rd-label">Expires On <span className="rd-optional">(optional)</span></label>
                      <input className="rd-input" type="date" value={editExpiresAt} min={todayIso()} onChange={(e) => handleEditExpiresAtChange(e.target.value)} />
                      {editExpiresAtError && <span className="rd-field-error">{editExpiresAtError}</span>}
                    </div>
                  </>
                ) : (
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
                )}

                <div className="rd-detail-skills-section">
                  <span className="rd-label">Required Skills</span>
                  {editMode ? (
                    editSkillsLoading ? (
                      <p className="rd-state-text">Loading skills…</p>
                    ) : editSkillsLoadFailed ? (
                      <p className="rd-field-error">Couldn't load skills for editing — existing skills will be left unchanged on save.</p>
                    ) : (
                      <>
                        <TaxonomySelect
                          isMulti
                          loadOptions={loadEditSkillOptions}
                          onCreateOption={createEditSkillOption}
                          value={editSkills}
                          onChange={setEditSkills}
                          placeholder="Search or type to add skills…"
                          controlShouldRenderValue={false}
                        />
                        {editSkills.length > 0 && (
                          <div className="rd-skill-tags">
                            {editSkills.map((opt) => (
                              <span key={opt.value} className="rd-skill-tag">
                                {opt.label}
                                <button
                                  type="button"
                                  className="rd-skill-tag-remove"
                                  onClick={() => setEditSkills((prev) => prev.filter((s) => s.value !== opt.value))}
                                  aria-label={`Remove ${opt.label}`}
                                >✕</button>
                              </span>
                            ))}
                          </div>
                        )}
                      </>
                    )
                  ) : detailJob.required_skills.length > 0 ? (
                    <div className="rd-skill-tags">
                      {detailJob.required_skills.map((skill) => (
                        <span key={skill} className="rd-skill-tag rd-skill-tag--readonly">{skill}</span>
                      ))}
                    </div>
                  ) : (
                    <p className="rd-rounds-empty-text" style={{ marginTop: 8 }}>No skills specified.</p>
                  )}
                </div>

                <div className="rd-detail-rounds-section">
                  <span className="rd-label">
                    Interview Pipeline
                    {editMode && <InfoTooltip text="Rounds and their order can't be changed after a job is posted — only new fields above and the ATS criteria below." />}
                  </span>
                  {detailRoundsLoading ? (
                    <p className="rd-state-text">Loading rounds…</p>
                  ) : detailRounds.length === 0 ? (
                    <p className="rd-rounds-empty-text" style={{ marginTop: 8 }}>No rounds configured.</p>
                  ) : (
                    <ol className={`rd-detail-rounds${editMode ? ' rd-detail-rounds--locked' : ''}`}>
                      {detailRounds.map((r) => {
                        const isOralRound = r.round_type_name.toLowerCase().includes('oral')
                          || r.round_type_name.toLowerCase().includes('voice')
                        // Written rounds with no explicit duration fall back to the backend's
                        // 45-min default; oral rounds keep their own existing default, which
                        // this UI doesn't hardcode.
                        const displayMinutes = r.time_limit_minutes ?? (isOralRound ? null : 45)
                        return (
                          <li key={r.round_order} className="rd-detail-round-item">
                            <span className="rd-round-badge">{r.round_order}</span>
                            <span className="rd-round-name">{r.round_type_name}</span>
                            {r.failing_criteria !== null && (
                              <span className="rd-pass-pill">{r.failing_criteria}% pass</span>
                            )}
                            {displayMinutes !== null && (
                              <span className="rd-pass-pill">{displayMinutes} min</span>
                            )}
                          </li>
                        )
                      })}
                    </ol>
                  )}
                </div>

                <div className="rd-detail-rounds-section">
                  <span className="rd-label">ATS Screening Criteria</span>
                  {editMode ? (
                    <>
                      <div className="rd-rounds-header">
                        <span className="rd-rounds-count">{editAtsTotalWeight}% total</span>
                      </div>
                      <ol className="rd-rounds-list">
                        {editAtsCriteria.map((c) => (
                          <li key={c.section} className="rd-round-item">
                            <input type="checkbox" checked={c.enabled} onChange={() => handleToggleEditAtsSection(c.section)} />
                            <span className="rd-round-name">{c.label}</span>
                            {c.enabled && (
                              <div className="rd-round-threshold">
                                <input
                                  className="rd-threshold-input"
                                  type="number" min="0" max="100"
                                  value={c.weight}
                                  onChange={(e) => handleEditAtsWeightChange(c.section, e.target.value)}
                                  onKeyDown={blockNonNumericKey}
                                />
                                <span className="rd-threshold-suffix">%</span>
                              </div>
                            )}
                          </li>
                        ))}
                      </ol>
                      {editAttempted && editAtsEnabledCriteria.length === 0 && (
                        <span className="rd-field-error">Select at least one ATS section</span>
                      )}
                      {editAttempted && editAtsEnabledCriteria.length > 0 && editAtsTotalWeight !== 100 && (
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
                              value={editQualifyThreshold}
                              onChange={(e) => setEditQualifyThreshold(e.target.value)}
                              onBlur={handleEditQualifyThresholdBlur}
                              onKeyDown={blockNonNumericKey}
                            />
                            <span className="rd-threshold-suffix">%</span>
                          </div>
                        </li>
                        {editQualifyThresholdError && (
                          <li className="rd-round-item">
                            <span className="rd-field-error">{editQualifyThresholdError}</span>
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
                              value={editOverqualifyThreshold}
                              onChange={(e) => setEditOverqualifyThreshold(e.target.value)}
                              onKeyDown={blockNonNumericKey}
                            />
                            <span className="rd-threshold-suffix">×</span>
                          </div>
                        </li>
                        {editOverqualifyThreshold !== '' && (
                          <li className="rd-round-item">
                            <input type="checkbox" checked={editAutoRejectOverqualified} onChange={() => setEditAutoRejectOverqualified((v) => !v)} />
                            <span className="rd-round-name">Auto-reject overqualified candidates</span>
                          </li>
                        )}
                      </ol>
                    </>
                  ) : detailJob.ats_criteria && detailJob.ats_criteria.has_config && detailJob.ats_criteria.criteria.length > 0 ? (
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

            {editMode && (
              <div className="rd-form-actions">
                {editError && <p className="rd-field-error rd-post-error">{editError}</p>}
                <Button type="button" variant="secondary" onClick={handleCancelEdit} disabled={editSaving}>Cancel</Button>
                <Button type="button" variant="primary" onClick={handleSaveEdit} disabled={editSaving || !!editSalaryError || !!editExpiresAtError || !!editQualifyThresholdError}>
                  {editSaving ? 'Saving…' : 'Save Changes'}
                </Button>
              </div>
            )}
          </div>
        )}
      </Modal>
    </main>
  )
}

export default RecruiterDashboard
