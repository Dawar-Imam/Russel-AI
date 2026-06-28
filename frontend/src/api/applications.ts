const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface ATSCheckResponse {
  eligible: boolean
  reason: string
}

export interface MyApplicationItem {
  application_id: string
  job_id: string
  status: string
  applied_at: string
  description: string
  location: string | null
  job_type: string
  salary_range: string | null
  job_role_id: number
  job_role_title: string
  experience_level_id: number
  experience_level_name: string
  company: string
  latest_interview_round_title: string | null
}

export async function runAts(applicationId: string): Promise<ATSCheckResponse> {
  const res = await fetch(`${BASE_URL}/api/applications/${applicationId}/run-ats`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('ATS check failed')
  return res.json() as Promise<ATSCheckResponse>
}

export async function fetchMyApplications(candidateId: string): Promise<MyApplicationItem[]> {
  const res = await fetch(
    `${BASE_URL}/api/applications/my-applications?candidate_id=${encodeURIComponent(candidateId)}`,
  )
  if (!res.ok) throw new Error('Failed to load your applications')
  return res.json() as Promise<MyApplicationItem[]>
}
