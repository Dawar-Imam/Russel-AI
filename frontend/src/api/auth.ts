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
