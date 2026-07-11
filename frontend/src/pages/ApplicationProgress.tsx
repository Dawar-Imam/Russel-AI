import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Button from '../components/Button'
import {
  runAts,
  type ATSAchievementMatchItem,
  type ATSCertificationMatchItem,
  type ATSCheckResponse,
  type ATSEducationMatching,
  type ATSExperienceMatching,
  type ATSProjectMatchItem,
  type ATSSkillMatchItem,
  type ATSTier,
  type ATSWeightage,
} from '../api/applications'
import '../css/ApplicationProgress.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

interface RoundInfo {
  interview_round_id: string
  interview_id: string | null
  title: string
  round_order: number
  status: string | null
  feedback: string | null
  result: number | null
  scheduled_at: string | null
  completed_at: string | null
  avg_score: number | null
}

interface StagesData {
  application_id: string
  rounds: RoundInfo[]
  current_round_id: string | null
  ats_status: 'pending' | 'pass' | 'fail'
  ats_result: ATSCheckResponse | null
  application_status: string | null
  job_role_title: string | null
  experience_level_name: string | null
  company: string | null
}

const ATS_CATEGORY_LABELS: Record<
  Exclude<keyof ATSWeightage, 'weighted_average' | 'pass_threshold'>,
  string
> = {
  experience: 'Professional Experience',
  skills: 'Technical & Soft Skills',
  projects: 'Projects',
  certifications: 'Certifications',
  education: 'Education',
  achievements: 'Achievements & Results',
}

function tierLabel(tier: ATSTier): string {
  return tier.charAt(0).toUpperCase() + tier.slice(1)
}

function getPctColor(pct: number): string {
  if (pct >= 70) return 'var(--color-primary)'
  if (pct >= 40) return 'var(--color-primary-dark)'
  return 'var(--color-alert)'
}

function weightageSummary(w: ATSWeightage): string {
  const keys = Object.keys(ATS_CATEGORY_LABELS) as (keyof typeof ATS_CATEGORY_LABELS)[]
  const strongest = keys.reduce((a, b) => (w[b].score_pct > w[a].score_pct ? b : a))
  const weakest = keys.reduce((a, b) => (w[b].score_pct < w[a].score_pct ? b : a))
  return `Weighted average is ${w.weighted_average.toFixed(1)}% against a pass threshold of ${w.pass_threshold}%. `
    + `Strongest category: ${ATS_CATEGORY_LABELS[strongest]} at ${w[strongest].score_pct.toFixed(0)}%. `
    + `Weakest category: ${ATS_CATEGORY_LABELS[weakest]} at ${w[weakest].score_pct.toFixed(0)}%.`
}

function skillMatchingSummary(items: ATSSkillMatchItem[]): string {
  if (items.length === 0) return 'No skill requirements were extracted from this job posting.'
  const found = items.filter(s => s.match_type !== 'not_found').length
  const primary = items.filter(s => s.tier === 'primary')
  const primaryFound = primary.filter(s => s.match_type !== 'not_found').length
  return `${found} of ${items.length} required skills were found in the candidate's Skills section. `
    + `${primaryFound} of ${primary.length} primary (must-have) skills matched. `
    + `Skills contribute 35% of the overall weighted score.`
}

function experienceSummary(exp: ATSExperienceMatching): string {
  const statusText = exp.seniority.status === 'match'
    ? 'meets'
    : exp.seniority.status === 'underqualified'
    ? 'falls short of'
    : 'exceeds'
  const respFound = exp.responsibilities.filter(r => r.match_type !== 'not_found').length
  const respLine = exp.responsibilities.length > 0
    ? `${respFound} of ${exp.responsibilities.length} responsibilities have matching evidence in the CV. `
    : 'No specific responsibilities were extracted for comparison. '
  return `Candidate seniority ${statusText} the required level (required: ${exp.seniority.required}, candidate: ${exp.seniority.candidate}). `
    + respLine
    + `Professional Experience contributes 30% of the overall weighted score.`
}

function projectsSummary(items: ATSProjectMatchItem[]): string {
  if (items.length === 0) {
    return "No relevant projects were found on the candidate's CV. Projects contribute 20% of the overall weighted score."
  }
  const avg = items.reduce((sum, p) => sum + p.total, 0) / items.length
  return `${items.length} project${items.length === 1 ? '' : 's'} evaluated against this job's responsibilities. `
    + `Average project score: ${avg.toFixed(1)} / 4. `
    + `Projects contribute 20% of the overall weighted score.`
}

function certificationsSummary(items: ATSCertificationMatchItem[]): string {
  if (items.length === 0) {
    return "No certifications were found on the candidate's CV. This dimension scores 0% (its 5% weight is not redistributed)."
  }
  const required = items.filter(c => c.matches_requirement).length
  const recognized = items.filter(c => c.recognition === 'industry_recognized').length
  return `${items.length} certification${items.length === 1 ? '' : 's'} found on the candidate's CV. `
    + `${required} explicitly required by this job; ${recognized} are industry-recognized credentials. `
    + `Certifications contribute 5% of the overall weighted score.`
}

function educationSummary(edu: ATSEducationMatching): string {
  const relevance = edu.relevant
    ? "Candidate's education is relevant to this role/domain. "
    : "Candidate's education was not judged relevant to this role/domain. "
  return relevance + (edu.note ? `${edu.note} ` : '') + 'Education contributes 5% of the overall weighted score.'
}

function achievementsSummary(items: ATSAchievementMatchItem[]): string {
  if (items.length === 0) {
    return "No achievements were found on the candidate's CV. This dimension scores 0% (its 5% weight is not redistributed)."
  }
  const full = items.filter(a => a.relevant && a.required).length
  return `${items.length} achievement${items.length === 1 ? '' : 's'} evaluated. `
    + `${full} are both relevant to the role and tied to a specific JD requirement. `
    + `Achievements contribute 5% of the overall weighted score.`
}

interface QuestionItem {
  question_id: string
  question_text: string
  candidate_answer: string | null
  score: number | null
  notes: string | null
}

function scoreVerdict(result: number | null): 'pass' | 'fail' | null {
  if (result == null) return null
  return result >= 6 ? 'pass' : 'fail'
}

function isRoundCompleted(round: RoundInfo): boolean {
  const s = (round.status ?? '').toLowerCase()
  return s === 'pass' || s === 'failed' || s === 'completed'
}

function getRoundBadgeClass(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (isRoundCompleted(round)) {
    if (s === 'pass') return 'ap-stage-badge--pass'
    if (s === 'failed' || s === 'fail') return 'ap-stage-badge--fail'
    const v = scoreVerdict(round.result)
    if (v === 'pass') return 'ap-stage-badge--pass'
    if (v === 'fail') return 'ap-stage-badge--fail'
    return 'ap-stage-badge--pass'
  }
  if (s === 'in progress') return 'ap-stage-badge--in-progress'
  if (s === 'scheduled') return 'ap-stage-badge--scheduled'
  return 'ap-stage-badge--not-started'
}

function isRoundNotNeeded(round: RoundInfo): boolean {
  return (round.status ?? '').toLowerCase() === 'not needed'
}

function getRoundLabel(round: RoundInfo): string {
  const s = (round.status ?? '').toLowerCase()
  if (s === 'pass') return 'Passed'
  if (s === 'failed' || s === 'fail') return 'Failed'
  if (s === 'completed') {
    const v = scoreVerdict(round.result)
    if (v === 'pass') return 'Passed'
    if (v === 'fail') return 'Failed'
    return 'Completed'
  }
  if (s === 'in progress') return 'In Progress'
  if (s === 'scheduled') return 'Pending'
  if (s === 'not needed') return 'Not Needed'
  return 'Not Started'
}

function getScoreColor(score: number): string {
  if (score >= 7) return 'var(--color-primary)'
  if (score >= 4) return 'var(--color-primary-dark)'
  return 'var(--color-text-primary)'
}

function ApplicationProgress() {
  const { applicationId } = useParams<{ applicationId: string }>()
  const navigate = useNavigate()

  const [testMode, setTestMode] = useState(() => localStorage.getItem('russell_test_mode') === '1')
  const [data, setData] = useState<StagesData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [atsError, setAtsError] = useState(false)
  const [selectedRoundId, setSelectedRoundId] = useState<string | null>(null)
  const [roundQuestions, setRoundQuestions] = useState<Record<string, QuestionItem[]>>({})
  const [loadingQuestions, setLoadingQuestions] = useState<Record<string, boolean>>({})
  const [openAtsSections, setOpenAtsSections] = useState<Record<string, boolean>>({})
  const atsTriggered = useRef(false)
  const fetchedRounds = useRef<Set<string>>(new Set())

  function toggleAtsSection(id: string) {
    setOpenAtsSections(prev => ({ ...prev, [id]: !prev[id] }))
  }

  function renderAtsSection(id: string, title: string, summary: string, detail: ReactNode, headerExtra?: ReactNode) {
    const open = !!openAtsSections[id]
    return (
      <div className="ap-ats-item ap-ats-section">
        <div className="ap-ats-section-header">
          <span className="ap-ats-item-label">{title}</span>
          <button
            type="button"
            className={`ap-ats-info-btn${open ? ' ap-ats-info-btn--active' : ''}`}
            onClick={() => toggleAtsSection(id)}
            aria-expanded={open}
            title={open ? `Hide ${title} details` : `Show ${title} details`}
          >
            i
          </button>
        </div>
        {headerExtra}
        <p className="ap-ats-section-summary">{summary}</p>
        {open && <div className="ap-ats-section-detail">{detail}</div>}
      </div>
    )
  }

  function toggleTestMode() {
    setTestMode(prev => {
      const next = !prev
      localStorage.setItem('russell_test_mode', next ? '1' : '0')
      return next
    })
  }

  function fetchRoundQuestions(round: RoundInfo) {
    if (!round.interview_id || fetchedRounds.current.has(round.interview_round_id)) return
    fetchedRounds.current.add(round.interview_round_id)
    setLoadingQuestions(prev => ({ ...prev, [round.interview_round_id]: true }))
    fetch(`${API_BASE}/api/applications/${applicationId}/interviews/${round.interview_id}/questions`)
      .then(res => res.ok ? res.json() as Promise<QuestionItem[]> : Promise.resolve([]))
      .then(items => setRoundQuestions(prev => ({ ...prev, [round.interview_round_id]: items })))
      .catch(() => setRoundQuestions(prev => ({ ...prev, [round.interview_round_id]: [] })))
      .finally(() => setLoadingQuestions(prev => ({ ...prev, [round.interview_round_id]: false })))
  }

  const currentRound = data?.rounds.find(r => r.interview_round_id === data.current_round_id)
  const allRoundsCompleted =
    data != null && data.ats_status === 'pass' &&
    (!data.current_round_id || currentRound?.status === 'Completed')

  const failedRound = data?.rounds.find(r => (r.status ?? '').toLowerCase() === 'failed')
  const isTerminal = data != null && data.ats_status === 'pass' &&
    (failedRound != null || (allRoundsCompleted && data.rounds.length > 0))
  const latestRound = isTerminal
    ? (failedRound ?? [...(data?.rounds ?? [])].reverse().find(r => r.status != null) ?? null)
    : null

  function getOutcomeInfo(): { title: string } {
    const appStatus = data?.application_status
    if (appStatus === 'HIRED') return { title: 'Congratulations! You have been hired.' }
    if (appStatus === 'REJECTED') return { title: 'Your application was not successful.' }
    if (failedRound) return { title: `You did not pass the ${failedRound.title} round.` }
    if (allRoundsCompleted && data && data.rounds.length > 0)
      return { title: 'You have completed all interview rounds.' }
    return { title: 'Interview process complete.' }
  }

  useEffect(() => {
    if (!applicationId) return
    fetch(`${API_BASE}/api/applications/${applicationId}/interview-stages`)
      .then(res => {
        if (!res.ok) throw new Error(`Server error ${res.status}`)
        return res.json() as Promise<StagesData>
      })
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load stages'))
      .finally(() => setLoading(false))
  }, [applicationId])

  // Set default selected breadcrumb once data loads
  useEffect(() => {
    if (!data || selectedRoundId !== null) return
    if (data.ats_status !== 'pass') {
      setSelectedRoundId('ats')
    } else if (data.current_round_id) {
      setSelectedRoundId(data.current_round_id)
    } else {
      const last = data.rounds[data.rounds.length - 1]
      setSelectedRoundId(last?.interview_round_id ?? 'ats')
    }
  }, [data, selectedRoundId])

  useEffect(() => {
    if (!applicationId || !data || data.ats_status !== 'pending' || atsTriggered.current) return
    atsTriggered.current = true
    runAts(applicationId)
      .then(result => {
        setData(prev =>
          prev
            ? {
                ...prev,
                ats_status: result.verdict === 'PASS' ? 'pass' : 'fail',
                ats_result: result,
              }
            : prev
        )
      })
      .catch(() => setAtsError(true))
  }, [applicationId, data])

  // Fetch questions when a completed round is selected
  useEffect(() => {
    if (!data || !selectedRoundId || selectedRoundId === 'ats') return
    const round = data.rounds.find(r => r.interview_round_id === selectedRoundId)
    if (round && isRoundCompleted(round)) fetchRoundQuestions(round)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRoundId, data])

  // True when the panel is showing a completed round's Q&A (× button should appear)
  const qaRound = (selectedRoundId && selectedRoundId !== 'ats')
    ? data?.rounds.find(r => r.interview_round_id === selectedRoundId && isRoundCompleted(r)) ?? null
    : null
  const isQAView = qaRound !== null

  function closeQA() { setSelectedRoundId(null) }

  function renderQABlock(round: RoundInfo) {
    const verdictKey = scoreVerdict(round.result) ?? 'pending'
    const questions = roundQuestions[round.interview_round_id] ?? []
    const questionsLoading = loadingQuestions[round.interview_round_id] ?? false
    return (
      <div className="ap-detail-qa">
        <div className="ap-detail-meta">
          <div className="ap-detail-meta-item">
            <span className="ap-detail-meta-label">Verdict</span>
            <span className={`ap-detail-meta-value ap-detail-meta-value--${verdictKey}`}>
              {verdictKey === 'pass' ? 'Passed' : verdictKey === 'fail' ? 'Failed' : 'Completed'}
            </span>
          </div>
          {round.avg_score != null && (
            <div className="ap-detail-meta-item">
              <span className="ap-detail-meta-label">Avg. Score</span>
              <span className="ap-detail-meta-value">{round.avg_score.toFixed(1)} / 10</span>
            </div>
          )}
        </div>
        {round.feedback && <p className="ap-detail-feedback">{round.feedback}</p>}
        {questionsLoading ? (
          <p className="ap-qa-loading">Loading questions…</p>
        ) : questions.length > 0 ? (
          <div className="ap-qa-section">
            <p className="ap-qa-section-label">Interview Q&amp;A</p>
            <div className="ap-qa-list">
              {questions.map((q, qi) => (
                <div key={q.question_id} className="ap-qa-item">
                  <div className="ap-qa-header">
                    <span className="ap-qa-num">Q{qi + 1}</span>
                    {q.score != null && (
                      <span className="ap-qa-score" style={{ color: getScoreColor(q.score) }}>
                        {q.score}/10
                      </span>
                    )}
                  </div>
                  <p className="ap-qa-question">{q.question_text}</p>
                  {q.candidate_answer ? (
                    <p className="ap-qa-answer">{q.candidate_answer}</p>
                  ) : (
                    <p className="ap-qa-answer ap-qa-answer--empty">No answer recorded</p>
                  )}
                  {q.notes && <p className="ap-qa-notes">{q.notes}</p>}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    )
  }

  function renderAtsResult() {
    const result = data?.ats_result
    if (!result) return null

    function sectionScoreChip(pct: number | undefined): ReactNode {
      if (pct == null) return undefined
      return (
        <div className="ap-ats-section-score">
          <span className="ap-ats-section-score-value" style={{ color: getPctColor(pct) }}>{pct.toFixed(0)}%</span>
        </div>
      )
    }

    return (
      <div className="ap-ats-breakdown">

        {/* 1. Pass/Fail badge */}
        <span className={`ap-ats-verdict-badge ap-ats-verdict-badge--${result.verdict.toLowerCase()}`}>
          ATS {result.verdict === 'PASS' ? 'Passed' : 'Failed'}
        </span>

        {/* 2. Verdict summary */}
        {result.verdict_summary && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Summary</span>
            <p className="ap-ats-item-value">{result.verdict_summary}</p>
          </div>
        )}

        {data.job_role_title && (
          <div className="ap-ats-item">
            <span className="ap-ats-item-label">Job Role</span>
            <span className="ap-ats-item-value">
              {data.experience_level_name ? `${data.experience_level_name} ` : ''}
              {data.job_role_title}
            </span>
          </div>
        )}

        {/* 3. Weightage calculated */}
        {result.weightage && renderAtsSection(
          'weightage',
          'Weightage Calculated',
          weightageSummary(result.weightage),
          <div className="ap-ats-score-list">
            {(Object.keys(ATS_CATEGORY_LABELS) as (keyof typeof ATS_CATEGORY_LABELS)[]).map(key => {
              const cat = result.weightage![key]
              return (
                <div key={key} className="ap-ats-score-row">
                  <div className="ap-ats-score-row-header">
                    <span className="ap-ats-score-row-name">{ATS_CATEGORY_LABELS[key]}</span>
                    <span className="ap-ats-score-row-weight">{cat.weight_pct.toFixed(0)}% weight</span>
                    <span className="ap-ats-score-row-value" style={{ color: getPctColor(cat.score_pct) }}>
                      {cat.score_pct.toFixed(0)}%
                    </span>
                  </div>
                  <div className="ap-ats-score-bar">
                    <div
                      className="ap-ats-score-bar-fill"
                      style={{ width: `${cat.score_pct}%`, backgroundColor: getPctColor(cat.score_pct) }}
                    />
                  </div>
                  <p className="ap-ats-score-row-reasoning">
                    Weighted contribution: {cat.weighted_score.toFixed(1)} pts
                  </p>
                </div>
              )
            })}
          </div>,
          <div className="ap-ats-score-overall">
            <span className="ap-ats-score-overall-value" style={{ color: getPctColor(result.weightage.weighted_average) }}>
              {result.weightage.weighted_average.toFixed(1)}
            </span>
            <span className="ap-ats-score-overall-max">/ 100 · pass threshold {result.weightage.pass_threshold}</span>
          </div>
        )}

        {/* 4. Skill matching */}
        {result.skill_matching.length > 0 && renderAtsSection(
          'skills',
          'Skill Matching',
          skillMatchingSummary(result.skill_matching),
          <>
            <div className="ap-ats-skill-grid">
              <div className="ap-ats-skill-grid-row ap-ats-skill-grid-row--header">
                <span>Importance</span>
                <span>Skill</span>
                <span>Status</span>
                <span>Description</span>
                <span>Score</span>
              </div>
              {result.skill_matching.map((s, i) => (
                <div key={i} className="ap-ats-skill-grid-row">
                  <span className={`ap-ats-tier-badge ap-ats-tier-badge--${s.tier}`}>{tierLabel(s.tier)}</span>
                  <span className="ap-ats-skill-req">{s.requirement}</span>
                  <span className={`ap-ats-match-badge ap-ats-match-badge--${s.match_type === 'not_found' ? 'not_found' : 'exact'}`}>
                    {s.match_type === 'not_found' ? 'Not Found' : 'Found'}
                  </span>
                  <span className="ap-ats-skill-note">{s.note}</span>
                  <span className="ap-ats-skill-score">{s.score}/{s.max_score}</span>
                </div>
              ))}
            </div>
            {result.additional_skills.length > 0 && (
              <div className="ap-ats-additional-skills">
                <span className="ap-ats-item-label">Other Skills Candidate Has</span>
                <div className="ap-ats-tag-list">
                  {result.additional_skills.map(skill => (
                    <span key={skill} className="ap-ats-tag">{skill}</span>
                  ))}
                </div>
              </div>
            )}
          </>,
          sectionScoreChip(result.weightage?.skills.score_pct)
        )}

        {/* 5. Experience matching */}
        {result.experience_matching && renderAtsSection(
          'experience',
          'Experience Matching',
          experienceSummary(result.experience_matching),
          <>
            <div className="ap-ats-seniority-row">
              <div className="ap-ats-meta-pair">
                <span className="ap-ats-meta-pair-label">Required</span>
                <span className="ap-ats-meta-pair-value">{result.experience_matching.seniority.required}</span>
              </div>
              <div className="ap-ats-meta-pair">
                <span className="ap-ats-meta-pair-label">Candidate</span>
                <span className="ap-ats-meta-pair-value">{result.experience_matching.seniority.candidate}</span>
              </div>
              <span
                className={`ap-ats-seniority-badge ap-ats-seniority-badge--${result.experience_matching.seniority.status}`}
              >
                {result.experience_matching.seniority.status === 'match'
                  ? 'Match'
                  : result.experience_matching.seniority.status === 'underqualified'
                  ? 'Underqualified'
                  : 'Overqualified'}
              </span>
            </div>
            {(result.experience_matching.years.required_years != null || result.experience_matching.years.candidate_years != null) && (
              <p className="ap-ats-item-value">
                Years — required: {result.experience_matching.years.required_years ?? 'n/a'}, candidate:{' '}
                {result.experience_matching.years.candidate_years ?? 'n/a'}
              </p>
            )}
            {result.experience_matching.seniority.note && (
              <p className="ap-ats-item-value">{result.experience_matching.seniority.note}</p>
            )}
            {result.experience_matching.responsibilities.length > 0 && (
              <div className="ap-ats-skill-table">
                {result.experience_matching.responsibilities.map((r, i) => (
                  <div key={i} className="ap-ats-skill-row">
                    <div className="ap-ats-skill-row-top">
                      <span className="ap-ats-skill-req">{r.requirement}</span>
                      <span className="ap-ats-skill-score">{r.score}/1</span>
                    </div>
                    <p className="ap-ats-skill-note">{r.evidence ?? 'No matching evidence found in the CV.'}</p>
                  </div>
                ))}
              </div>
            )}
          </>,
          sectionScoreChip(result.weightage?.experience.score_pct)
        )}

        {/* 6. Projects matching */}
        {result.projects_matching.length > 0 && renderAtsSection(
          'projects',
          'Projects Matching',
          projectsSummary(result.projects_matching),
          <div className="ap-ats-project-list">
            {result.projects_matching.map((p, i) => (
              <div key={i} className="ap-ats-project-card">
                <div className="ap-ats-skill-row-top">
                  <span className="ap-ats-skill-req">{p.project_name}</span>
                  <span className="ap-ats-skill-score">{p.total.toFixed(1)}/{p.max}</span>
                </div>
                <div className="ap-ats-project-subscores">
                  <span>Complexity {p.complexity}</span>
                  <span>Technologies {p.technologies}</span>
                  <span>Impact {p.impact}</span>
                  <span>Relevance {p.relevance}</span>
                </div>
                {p.note && <p className="ap-ats-skill-note">{p.note}</p>}
              </div>
            ))}
          </div>,
          sectionScoreChip(result.weightage?.projects.score_pct)
        )}

        {/* 7. Certifications */}
        {renderAtsSection(
          'certifications',
          'Certifications',
          certificationsSummary(result.certifications_matching),
          result.certifications_matching.length > 0 ? (
            <div className="ap-ats-skill-table">
              {result.certifications_matching.map((c, i) => (
                <div key={i} className="ap-ats-skill-row">
                  <div className="ap-ats-skill-row-top">
                    <span className="ap-ats-skill-req">{c.certification}</span>
                    <span className="ap-ats-skill-score">{c.score}/1</span>
                  </div>
                  <div className="ap-ats-skill-row-bottom">
                    <span className={`ap-ats-match-badge ap-ats-match-badge--${c.matches_requirement ? 'exact' : 'not_found'}`}>
                      {c.matches_requirement ? 'Job Requirement' : 'Not Job Requirement'}
                    </span>
                    <span className={`ap-ats-match-badge ap-ats-match-badge--${c.recognition === 'industry_recognized' ? 'exact' : 'not_found'}`}>
                      {c.recognition === 'industry_recognized' ? 'Industry Recognized' : 'Not Recognized'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="ap-ats-item-value">No certifications found on the candidate's CV.</p>
          ),
          sectionScoreChip(result.weightage?.certifications.score_pct)
        )}

        {/* 8. Education */}
        {result.education_matching && renderAtsSection(
          'education',
          'Education',
          educationSummary(result.education_matching),
          <>
            <div className="ap-ats-skill-row-top">
              <span className={`ap-ats-match-badge ap-ats-match-badge--${result.education_matching.relevant ? 'exact' : 'not_found'}`}>
                {result.education_matching.relevant ? 'Relevant' : 'Not Relevant'}
              </span>
              <span className="ap-ats-skill-score">{result.education_matching.score}/1</span>
            </div>
            {result.education_matching.note && <p className="ap-ats-item-value">{result.education_matching.note}</p>}
          </>,
          sectionScoreChip(result.weightage?.education.score_pct)
        )}

        {/* 9. Achievements */}
        {result.achievements_matching.length > 0 && renderAtsSection(
          'achievements',
          'Achievements',
          achievementsSummary(result.achievements_matching),
          <div className="ap-ats-skill-table">
            {result.achievements_matching.map((a, i) => (
              <div key={i} className="ap-ats-skill-row">
                <div className="ap-ats-skill-row-top">
                  <span className="ap-ats-skill-req">{a.achievement}</span>
                  <span className="ap-ats-skill-score">{a.score}/1</span>
                </div>
                <div className="ap-ats-skill-row-bottom">
                  {a.relevant && <span className="ap-ats-tag ap-ats-tag--matched">Relevant</span>}
                  {a.required && <span className="ap-ats-tag ap-ats-tag--matched">Tied to requirement</span>}
                </div>
              </div>
            ))}
          </div>,
          sectionScoreChip(result.weightage?.achievements.score_pct)
        )}

      </div>
    )
  }

  function renderDetailContent() {
    if (!data) return null

    // ATS failed / error
    if (data.ats_status === 'fail' || atsError) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening Failed</p>
          {renderAtsResult()}
        </div>
      )
    }

    // ATS pending
    if (data.ats_status === 'pending') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening in progress…</p>
          <p className="ap-detail-msg-body">Please check back shortly.</p>
        </div>
      )
    }

    // Nothing selected (after closing Q&A)
    if (!selectedRoundId) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">Select a round</p>
          <p className="ap-detail-msg-body">Click an interview round on the left to view its Q&amp;A and status.</p>
        </div>
      )
    }

    // ATS breadcrumb selected
    if (selectedRoundId === 'ats') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">ATS Screening Passed</p>
          {renderAtsResult()}
        </div>
      )
    }

    // Round breadcrumb selected
    const round = data.rounds.find(r => r.interview_round_id === selectedRoundId)
    if (!round) return null

    const s = (round.status ?? '').toLowerCase()

    if (s === 'in progress') {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title} interview in progress</p>
        </div>
      )
    }

    if (isRoundNotNeeded(round)) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title}</p>
          <p className="ap-detail-msg-body">Not needed — a prior round was not passed.</p>
        </div>
      )
    }

    if (!isRoundCompleted(round)) {
      return (
        <div className="ap-detail-msg">
          <p className="ap-detail-msg-title">{round.title}</p>
          <p className="ap-detail-msg-body">This round hasn't started yet.</p>
        </div>
      )
    }

    // Completed — Q&A
    return renderQABlock(round)
  }

  return (
    <main className="app-progress-page">
      <div className="app-progress-body">

        {/* Heading row */}
        <div className="app-progress-heading-row">
          <h1 className="app-progress-heading">Application Progress</h1>
          <div className="app-progress-heading-actions">
            <button
              className={`test-mode-toggle${testMode ? ' test-mode-toggle--on' : ''}`}
              onClick={toggleTestMode}
              title="Toggle test mode to jump to any interview round"
            >
              <span className="test-mode-toggle-track">
                <span className="test-mode-toggle-thumb" />
              </span>
              <span className="test-mode-toggle-label">Test Mode</span>
            </button>
            {data && !isTerminal && !allRoundsCompleted && data.ats_status !== 'fail' && !atsError && (
              <Button
                variant="primary"
                className="app-progress-cta"
                onClick={() => {
                  if (currentRound?.interview_id) {
                    navigate(`/interview-room/${currentRound.interview_id}`)
                  }
                }}
                disabled={!data.current_round_id || data.ats_status === 'pending'}
              >
                {data.ats_status === 'pending' ? 'ATS Screening…' : 'Go To Interview Room'}
              </Button>
            )}
          </div>
        </div>

        {loading && <p className="stages-status-text">Loading…</p>}
        {error && <p className="stages-status-text stages-error">{error}</p>}

        {data && (
          <>
            {/* Horizontal bubble timeline */}
            <div className="app-progress-timeline">
              <div className="stage-bubble-wrapper">
                <div className={`stage-bubble${data.ats_status === 'pending' ? ' stage-bubble--ats-pending' : ''}`}>
                  {data.ats_status === 'pending' && 'ATS\nChecking…'}
                  {data.ats_status === 'pass' && 'ATS\nPass'}
                  {data.ats_status === 'fail' && 'ATS\nFailed'}
                </div>
                {data.ats_status === 'pending' && (
                  <span className="stage-current-label">ATS Checking…</span>
                )}
                {data.ats_status === 'fail' && (
                  <span className="stage-current-label stage-current-label--static">ATS Failed</span>
                )}
              </div>
              {data.rounds.map(round => (
                <div key={round.interview_round_id} className="stage-bubble-wrapper">
                  <div className="stage-bubble">{round.title}</div>
                  {!isTerminal && data.ats_status === 'pass' && round.interview_round_id === data.current_round_id && (
                    <span className="stage-current-label">Current Round</span>
                  )}
                </div>
              ))}
            </div>

            {/* Left / right pane row */}
            <div className="ap-content-row">

              {/* Left pane: job card + breadcrumbs */}
              <div className="ap-left-pane">

                {/* Job card */}
                {(data.job_role_title || data.company) && (
                  <div className="ap-job-card">
                    {data.job_role_title && (
                      <span className="ap-job-role">{data.job_role_title}</span>
                    )}
                    {data.experience_level_name && (
                      <span className="ap-job-level">{data.experience_level_name}</span>
                    )}
                    {data.company && (
                      <span className="ap-job-company">{data.company}</span>
                    )}
                    <span className="ap-job-rounds">
                      {data.rounds.length} Round{data.rounds.length !== 1 ? 's' : ''}
                    </span>
                  </div>
                )}

                {/* Outcome banner — shown once the interview process is terminal */}
                {isTerminal && (
                  <div className="ap-outcome-block">
                    <p className="ap-outcome-block-title">{getOutcomeInfo().title}</p>
                    {latestRound?.status && (
                      <span className={`ap-stage-badge ${getRoundBadgeClass(latestRound)}`}>
                        {latestRound.title}: {getRoundLabel(latestRound)}
                      </span>
                    )}
                    {latestRound?.feedback && (
                      <p className="ap-outcome-block-feedback">{latestRound.feedback}</p>
                    )}
                  </div>
                )}

                {/* Breadcrumbs */}
                <div className="ap-breadcrumbs">
                  <span className="ap-breadcrumbs-label">Interview Rounds</span>
                  <button
                    className={`ap-crumb${selectedRoundId === 'ats' ? ' ap-crumb--active' : ''}`}
                    onClick={() => setSelectedRoundId('ats')}
                  >
                    ATS Screening
                  </button>
                  {data.rounds.map(round => (
                    <button
                      key={round.interview_round_id}
                      className={`ap-crumb${selectedRoundId === round.interview_round_id ? ' ap-crumb--active' : ''}`}
                      onClick={() => setSelectedRoundId(round.interview_round_id)}
                    >
                      {round.title}
                    </button>
                  ))}
                </div>

              </div>

              {/* Right pane: blurred detail panel */}
              <div className="ap-right-pane">
                <div className="ap-detail-panel">
                  {isQAView && (
                    <div className="ap-panel-close-row">
                      <button className="ap-panel-close-btn" onClick={closeQA} title="Close Q&A">×</button>
                    </div>
                  )}
                  <div className="ap-panel-body">
                    {renderDetailContent()}
                  </div>
                </div>
              </div>

              {/* Rightmost: test-mode jump panel — only when test mode on */}
              {testMode && (
                <div className="ap-test-panel">
                  <span className="ap-test-panel-label">Jump to round</span>
                  <div className="ap-test-panel-list">
                    {data.rounds.map(round =>
                      round.interview_id && (
                        <button
                          key={round.interview_round_id}
                          className="ap-test-panel-btn"
                          onClick={() => navigate(`/interview-room/${round.interview_id}`)}
                        >
                          {round.title}
                        </button>
                      )
                    )}
                  </div>
                </div>
              )}

            </div>

          </>
        )}

      </div>
    </main>
  )
}

export default ApplicationProgress
