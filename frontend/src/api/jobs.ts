const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface JobListItem {
  id: string
  designation: string
  description: string
  company: string
  job_role_id: number
  job_role_title: string
  location: string
  job_type: string
  salary_range: string | null
  posted_at: string
  expires_at: string | null
  required_skills: string[]
}

export interface JobFilters {
  job_role_id?: number
  location?: string
  job_type?: string
  salary_range?: string
  offset?: number
  limit?: number
}

export interface JobPostRequest {
  recruiter_id: string
  job_role_id: number
  designation: string
  description: string
  location: string
  job_type: string
  salary_range?: string
  expires_at?: string
}

export interface JobPostResponse {
  job_id: string
  message: string
}

export async function fetchJobs(
  filters: JobFilters = {},
  signal?: AbortSignal,
): Promise<JobListItem[]> {
  const params = new URLSearchParams()
  if (filters.job_role_id != null) params.set('job_role_id', String(filters.job_role_id))
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
