const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface ATSCategoryScore {
  score_pct: number
  weight_pct: number
  weighted_score: number
}

export interface ATSWeightage {
  experience: ATSCategoryScore
  skills: ATSCategoryScore
  projects: ATSCategoryScore
  certifications: ATSCategoryScore
  education: ATSCategoryScore
  achievements: ATSCategoryScore
  weighted_average: number
  pass_threshold: number
}

export type ATSTier = 'primary' | 'secondary' | 'tertiary'
export type ATSMatchType = 'exact' | 'alternative' | 'not_found'

export interface ATSSkillMatchItem {
  requirement: string
  tier: ATSTier
  candidate_skill: string | null
  match_type: ATSMatchType
  score: number
  max_score: number
  note: string
}

export interface ATSSeniorityMatch {
  required: string
  candidate: string
  status: 'match' | 'underqualified' | 'overqualified'
  note: string
}

export interface ATSYearsMatch {
  required_years: number | null
  candidate_years: number | null
}

export interface ATSResponsibilityMatchItem {
  requirement: string
  evidence: string | null
  match_type: 'direct' | 'close' | 'not_found'
  score: number
}

export interface ATSExperienceMatching {
  seniority: ATSSeniorityMatch
  years: ATSYearsMatch
  responsibilities: ATSResponsibilityMatchItem[]
}

export interface ATSProjectMatchItem {
  project_name: string
  complexity: number
  technologies: number
  impact: number
  relevance: number
  total: number
  max: number
  note: string
}

export interface ATSCertificationMatchItem {
  certification: string
  matches_requirement: boolean
  recognition: 'industry_recognized' | 'not_recognized'
  score: number
}

export interface ATSEducationMatching {
  relevant: boolean
  score: number
  note: string
}

export interface ATSAchievementMatchItem {
  achievement: string
  relevant: boolean
  required: boolean
  score: number
}

export interface ATSCheckResponse {
  verdict: 'PASS' | 'FAIL'
  verdict_summary: string
  weightage: ATSWeightage | null
  skill_matching: ATSSkillMatchItem[]
  experience_matching: ATSExperienceMatching | null
  projects_matching: ATSProjectMatchItem[]
  certifications_matching: ATSCertificationMatchItem[]
  education_matching: ATSEducationMatching | null
  achievements_matching: ATSAchievementMatchItem[]
  additional_skills: string[]
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
