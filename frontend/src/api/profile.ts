const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface CandidateProfile {
  candidate_id: string
  first_name: string
  last_name: string
  email: string
  job_role_title: string
  skills: string[]
  experience_level: string
  bio: string | null
  linkedin_url: string | null
  current_location: string | null
  open_to_work: boolean
  resume_url: string | null
  member_since: string
}

export interface RecruiterProfile {
  recruiter_id: string
  first_name: string
  last_name: string
  email: string
  company_name: string
  designation: string
  company_verified: boolean
  member_since: string
}

export async function fetchCandidateProfile(candidateId: string): Promise<CandidateProfile> {
  const res = await fetch(`${BASE_URL}/api/auth/profile/candidate/${encodeURIComponent(candidateId)}`)
  if (!res.ok) {
    const body = (await res.json()) as { detail?: string }
    throw new Error(body.detail ?? 'Failed to load profile')
  }
  return res.json() as Promise<CandidateProfile>
}

export async function fetchRecruiterProfile(recruiterId: string): Promise<RecruiterProfile> {
  const res = await fetch(`${BASE_URL}/api/auth/profile/recruiter/${encodeURIComponent(recruiterId)}`)
  if (!res.ok) {
    const body = (await res.json()) as { detail?: string }
    throw new Error(body.detail ?? 'Failed to load profile')
  }
  return res.json() as Promise<RecruiterProfile>
}
