const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface ATSCategoryScore {
  score_pct: number
  weight_pct: number
  weighted_score: number
  included: boolean
  matched_count: number | null
  total_count: number | null
}

export interface ATSWeightage {
  experience: ATSCategoryScore
  skills: ATSCategoryScore
  projects: ATSCategoryScore
  certifications: ATSCategoryScore
  education: ATSCategoryScore
  achievements: ATSCategoryScore
  weighted_average: number
  qualify_threshold: number
  pass_fail: 'PASS' | 'FAIL' | null
}

export type ATSMatchType = 'exact' | 'parent' | 'alternative' | 'exceeds' | 'not_found' | 'not_required'
export type ATSConfidence = 'high' | 'medium' | 'low'
export type ATSRequirementCategory = 'skills' | 'projects' | 'certifications' | 'education' | 'achievements'

export interface ATSRequirementMatchItem {
  requirement: string
  category: ATSRequirementCategory
  candidate_evidence: string | null
  match_type: ATSMatchType
  exceeds_requirement: boolean
  score: number
  max_score: number
  confidence: ATSConfidence
  reason: string
}

export interface ATSResponsibilityMatchItem {
  requirement: string
  evidence: string | null
  match_type: 'direct' | 'close' | 'not_found'
  score: number
}

export interface ATSRelevantExperience {
  job_role_required: string
  included_experience: string
  excluded_experience: string | null
  required_years: number | null
  candidate_relevant_years: number | null
  status: 'qualified' | 'underqualified' | 'overqualified'
  responsibility_matches: ATSResponsibilityMatchItem[]
}

export interface ATSSectionMatchItem {
  section: string
  jd_requires_section: boolean
  cv_has_content: boolean
  score: number
  note: string
}

export interface ATSGraceCredit {
  item: string
  points: number
  note: string
}

export interface ATSCheckResponse {
  verdict: 'QUALIFIED' | 'UNDERQUALIFIED' | 'OVERQUALIFIED'
  verdict_summary: string
  weightage: ATSWeightage | null
  requirement_matching: ATSRequirementMatchItem[]
  relevant_experience: ATSRelevantExperience | null
  section_matching: ATSSectionMatchItem[]
  grace_credits: ATSGraceCredit[]
  additional_cv_content: string[]
  is_overqualified: boolean
  final_verdict: 'PASS' | 'FAIL' | null
  override_reason: string | null
}

export interface ATSRerunNotice {
  previous_verdict: string | null
  new_verdict: string
  message: string
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

export async function ackAtsRerunNotice(applicationId: string): Promise<void> {
  await fetch(`${BASE_URL}/api/applications/${encodeURIComponent(applicationId)}/ack-ats-rerun`, {
    method: 'POST',
  })
}
