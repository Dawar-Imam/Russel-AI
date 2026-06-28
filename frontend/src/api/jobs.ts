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

export interface JobInterviewRoundItem {
  round_order: number
  round_type_name: string
  failing_criteria: number | null
  description: string | null
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
}

export interface JobFilters {
  job_role_id?: number
  experience_level_id?: number
  location?: string
  job_type?: string
  salary_range?: string
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
}

export interface JobPostResponse {
  job_id: string
  message: string
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
