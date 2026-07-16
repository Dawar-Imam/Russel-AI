const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface InterviewRoundType {
  id: number
  name: string
  description: string | null
}

export interface InterviewRoundInput {
  round_type_id: number
  round_order: number
  failing_criteria: number | null
  description?: string
}

export interface ATSCriterionInput {
  section: string
  weight: number
}

export interface JobInterviewRoundItem {
  round_order: number
  round_type_name: string
  failing_criteria: number | null
  description: string | null
}

export interface ATSCriterionSummary {
  section: string
  weight: number
}

export interface ATSCriteriaSummary {
  has_config: boolean
  criteria: ATSCriterionSummary[]
  qualify_threshold: number
  overqualify_threshold: number | null
  auto_reject_overqualified: boolean
}

export interface JobListItem {
  id: string
  description: string
  company: string
  job_role_id: number
  job_role_title: string
  experience_level_id: number
  experience_level_name: string
  location: string
  job_type: string
  salary_range: string | null
  posted_at: string
  expires_at: string | null
  required_skills: string[]
  status: string
  // Only populated on recruiter-facing listings (fetchRecruiterJobs) — null for the
  // public/candidate job list.
  ats_criteria: ATSCriteriaSummary | null
}

// ── Analytics types ───────────────────────────────────────────────────────────

export interface JobStatsRound {
  round_order: number
  round_type_name: string
  failing_criteria: number | null
  applicants_count: number
}

export interface JobStatsResponse {
  job_title: string
  description: string
  status: string
  required_skills: string[]
  rounds: JobStatsRound[]
  total_applicants: number
  passed_all_rounds: number
  hired_count: number
}

export interface RoundCandidateItem {
  candidate_id: string
  application_id: string
  interview_id: string
  name: string
  status: string
}

export interface CandidateSkillItem {
  name: string
  proficiency_level: string | null
}

export interface CandidateInfo {
  first_name: string
  last_name: string
  email: string
  bio: string | null
  current_location: string | null
  experience_level: string | null
  job_role: string | null
  skills: CandidateSkillItem[]
  phone: string | null
  linkedin_url: string | null
  experience_years_min: number | null
  experience_years_max: number | null
}

export interface InterviewProgressItem {
  round_order: number
  round_type_name: string
  status: string | null
  result: number | null
  completed_at: string | null
  interview_id: string | null
}

export interface EvaluationQuestionItem {
  question_text: string
  candidate_answer: string | null
  score: number | null
  notes: string | null
}

export interface CandidatePanelResponse {
  candidate: CandidateInfo
  progress: InterviewProgressItem[]
  evaluation: EvaluationQuestionItem[] | null
}

export interface JobFilters {
  job_role_id?: number
  experience_level_id?: number
  location?: string
  job_type?: string
  salary_range?: string
  candidate_id?: string
  offset?: number
  limit?: number
}

export interface JobPostRequest {
  recruiter_id: string
  job_role_id: number
  experience_level_id: number
  description: string
  location: string
  job_type: string
  salary_range?: string
  expires_at?: string
  skill_ids?: number[]
  interview_rounds?: InterviewRoundInput[]
  ats_criteria: ATSCriterionInput[]
  qualify_threshold?: number
  overqualify_threshold?: number
  auto_reject_overqualified?: boolean
}

export interface JobPostResponse {
  job_id: string
  message: string
}

export interface JobUpdateRequest {
  description?: string
  location?: string
  job_type?: string
  salary_range?: string | null
  expires_at?: string | null
  status?: 'active' | 'closed'
  skill_ids?: number[]
  ats_criteria?: ATSCriterionInput[]
  qualify_threshold?: number
  overqualify_threshold?: number | null
  auto_reject_overqualified?: boolean
}

export interface JobSkillOptionItem {
  id: number
  name: string
}

export interface RerunAtsResponse {
  queued: number
  skipped_pending: number
  excluded: number
  message: string
}

export interface RerunAtsStatusResponse {
  total_queued: number
  completed: number
  in_progress: boolean
}

export async function fetchInterviewRoundTypes(): Promise<InterviewRoundType[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/round-types`)
  if (!res.ok) throw new Error('Failed to load interview round types')
  return res.json() as Promise<InterviewRoundType[]>
}

export async function fetchJobRounds(jobId: string): Promise<JobInterviewRoundItem[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/rounds`)
  if (!res.ok) throw new Error('Failed to load interview rounds')
  return res.json() as Promise<JobInterviewRoundItem[]>
}

export async function fetchJobs(
  filters: JobFilters = {},
  signal?: AbortSignal,
): Promise<JobListItem[]> {
  const params = new URLSearchParams()
  if (filters.job_role_id != null) params.set('job_role_id', String(filters.job_role_id))
  if (filters.experience_level_id != null) params.set('experience_level_id', String(filters.experience_level_id))
  if (filters.location) params.set('location', filters.location)
  if (filters.job_type) params.set('job_type', filters.job_type)
  if (filters.salary_range) params.set('salary_range', filters.salary_range)
  if (filters.candidate_id) params.set('candidate_id', filters.candidate_id)
  if (filters.offset != null) params.set('offset', String(filters.offset))
  if (filters.limit != null) params.set('limit', String(filters.limit))
  const query = params.toString()
  const res = await fetch(`${BASE_URL}/api/jobs${query ? `?${query}` : ''}`, { signal })
  if (!res.ok) throw new Error('Failed to load jobs')
  return res.json() as Promise<JobListItem[]>
}

export async function fetchRecruiterJobs(recruiterId: string): Promise<JobListItem[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/mine?recruiter_id=${encodeURIComponent(recruiterId)}`)
  if (!res.ok) throw new Error('Failed to load your job postings')
  return res.json() as Promise<JobListItem[]>
}

export async function fetchInterviewQA(interviewId: string): Promise<EvaluationQuestionItem[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/interview-qa/${encodeURIComponent(interviewId)}`)
  if (!res.ok) throw new Error('Failed to load interview Q&A')
  return res.json() as Promise<EvaluationQuestionItem[]>
}

export async function fetchJobStats(jobId: string): Promise<JobStatsResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/stats`)
  if (!res.ok) throw new Error('Failed to load job stats')
  return res.json() as Promise<JobStatsResponse>
}

export async function fetchRoundCandidates(jobId: string, roundOrder: number): Promise<RoundCandidateItem[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/rounds/${roundOrder}/candidates`)
  if (!res.ok) throw new Error('Failed to load round candidates')
  return res.json() as Promise<RoundCandidateItem[]>
}

export async function fetchCandidatePanel(
  jobId: string,
  applicationId: string,
  interviewId: string,
): Promise<CandidatePanelResponse> {
  const res = await fetch(
    `${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/candidate-panel/${encodeURIComponent(applicationId)}?interview_id=${encodeURIComponent(interviewId)}`,
  )
  if (!res.ok) throw new Error('Failed to load candidate details')
  return res.json() as Promise<CandidatePanelResponse>
}

export async function postJob(data: JobPostRequest): Promise<JobPostResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const body = (await res.json()) as { detail?: string } & Partial<JobPostResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to post job')
  return body as JobPostResponse
}

export async function fetchJobSkills(jobId: string): Promise<JobSkillOptionItem[]> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/skills`)
  if (!res.ok) throw new Error('Failed to load job skills')
  return res.json() as Promise<JobSkillOptionItem[]>
}

export async function updateJob(jobId: string, recruiterId: string, data: JobUpdateRequest): Promise<JobPostResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}?recruiter_id=${encodeURIComponent(recruiterId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  const body = (await res.json()) as { detail?: string } & Partial<JobPostResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to update job')
  return body as JobPostResponse
}

export async function rerunAts(jobId: string, recruiterId: string): Promise<RerunAtsResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/rerun-ats?recruiter_id=${encodeURIComponent(recruiterId)}`, {
    method: 'POST',
  })
  const body = (await res.json()) as { detail?: string } & Partial<RerunAtsResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to start ATS rerun')
  return body as RerunAtsResponse
}

export async function fetchAtsRerunStatus(jobId: string): Promise<RerunAtsStatusResponse> {
  const res = await fetch(`${BASE_URL}/api/jobs/${encodeURIComponent(jobId)}/rerun-ats/status`)
  if (!res.ok) throw new Error('Failed to load ATS rerun status')
  return res.json() as Promise<RerunAtsStatusResponse>
}
