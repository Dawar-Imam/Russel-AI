const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface JobRole {
  id: number
  title: string
  category: string | null
}

export interface Skill {
  id: number
  name: string
  category: string | null
  job_role_ids: number[]
}

export interface ExperienceLevel {
  id: number
  name: string
}

export interface SignupMetadata {
  job_roles: JobRole[]
  skills: Skill[]
  experience_levels: ExperienceLevel[]
}

export interface SignupResponse {
  user_id: string
  candidate_id: string
  message: string
}

export interface SigninResponse {
  user_id: string
  candidate_id: string
  message: string
}

export async function fetchSignupMetadata(): Promise<SignupMetadata> {
  const res = await fetch(`${BASE_URL}/api/auth/signup-metadata`)
  if (!res.ok) throw new Error('Failed to load signup options')
  return res.json() as Promise<SignupMetadata>
}

function toTitleCase(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

export async function createSkill(name: string, jobRoleId: number | null = null): Promise<Skill> {
  const res = await fetch(`${BASE_URL}/api/auth/skills`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: toTitleCase(name), job_role_id: jobRoleId }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<Skill>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to add skill')
  return body as Skill
}

export async function createJobRole(title: string): Promise<JobRole> {
  const res = await fetch(`${BASE_URL}/api/auth/job-roles`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: toTitleCase(title) }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<JobRole>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to add job category')
  return body as JobRole
}

export async function searchJobRoles(query: string, limit = 20): Promise<JobRole[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  const res = await fetch(`${BASE_URL}/api/auth/job-roles/search?${params.toString()}`)
  if (!res.ok) throw new Error('Failed to search job categories')
  const body = (await res.json()) as { results: JobRole[] }
  return body.results
}

export async function searchSkills(roleId: number, query: string, limit = 20): Promise<Skill[]> {
  const params = new URLSearchParams({ role_id: String(roleId), q: query, limit: String(limit) })
  const res = await fetch(`${BASE_URL}/api/auth/skills/search?${params.toString()}`)
  if (!res.ok) throw new Error('Failed to search skills')
  const body = (await res.json()) as { results: Skill[] }
  return body.results
}

export async function signupCandidate(data: {
  firstName: string
  lastName: string
  email: string
  password: string
  jobRoleId: number
  skillIds: number[]
  experienceYears: number
  cv: File | null
}): Promise<SignupResponse> {
  const form = new FormData()
  form.append('first_name', data.firstName)
  form.append('last_name', data.lastName)
  form.append('email', data.email)
  form.append('password', data.password)
  form.append('job_role_id', String(data.jobRoleId))
  form.append('skill_ids', data.skillIds.join(','))
  form.append('experience_years', String(data.experienceYears))
  if (data.cv) form.append('cv', data.cv)

  const res = await fetch(`${BASE_URL}/api/auth/signup`, { method: 'POST', body: form })
  const body = (await res.json()) as { detail?: string | { msg?: string }[] } & Partial<SignupResponse>
  if (!res.ok) {
    const detail = body.detail
    const message = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((e) => e.msg ?? '').filter(Boolean).join('; ') || 'Signup failed'
        : 'Signup failed'
    throw new Error(message)
  }
  return body as SignupResponse
}

export interface OtpActionResponse {
  message: string
}

export async function verifyOtp(userId: string, otpCode: string): Promise<OtpActionResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/verify-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId, otp_code: otpCode }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<OtpActionResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Verification failed')
  return body as OtpActionResponse
}

export async function resendOtp(userId: string): Promise<OtpActionResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/resend-otp`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: userId }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<OtpActionResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Failed to resend code')
  return body as OtpActionResponse
}

export async function signinCandidate(email: string, password: string): Promise<SigninResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<SigninResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Sign in failed')
  return body as SigninResponse
}

export interface RecruiterSignupResponse {
  user_id: string
  recruiter_id: string
  message: string
}

export interface RecruiterSigninResponse {
  user_id: string
  recruiter_id: string
  message: string
}

export async function signupRecruiter(data: {
  firstName: string
  lastName: string
  email: string
  password: string
  companyName: string
  designation: string
}): Promise<RecruiterSignupResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/recruiter/signup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      first_name: data.firstName,
      last_name: data.lastName,
      email: data.email,
      password: data.password,
      company_name: data.companyName,
      designation: data.designation,
    }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<RecruiterSignupResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Signup failed')
  return body as RecruiterSignupResponse
}

export async function fetchGoogleCalendarConnectUrl(recruiterId: string): Promise<{ authorization_url: string }> {
  const res = await fetch(`${BASE_URL}/api/google-calendar/connect?recruiter_id=${encodeURIComponent(recruiterId)}`)
  if (!res.ok) throw new Error('Failed to start Google Calendar connection')
  return res.json() as Promise<{ authorization_url: string }>
}

export async function signinRecruiter(email: string, password: string): Promise<RecruiterSigninResponse> {
  const res = await fetch(`${BASE_URL}/api/auth/recruiter/signin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = (await res.json()) as { detail?: string } & Partial<RecruiterSigninResponse>
  if (!res.ok) throw new Error(body.detail ?? 'Sign in failed')
  return body as RecruiterSigninResponse
}
