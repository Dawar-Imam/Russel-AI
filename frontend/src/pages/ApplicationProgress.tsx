import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import Button from '../components/Button'
import Modal from '../components/Modal'
import {
  ackAtsRerunNotice,
  runAts,
  type ATSCheckResponse,
  type ATSRelevantExperience,
  type ATSRequirementCategory,
  type ATSRequirementMatchItem,
  type ATSRerunNotice,
  type ATSSectionMatchItem,
  type ATSWeightage,
} from '../api/applications'
import '../css/ApplicationProgress.css'

const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
const WS_BASE = API_BASE.replace(/^http/, 'ws')

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
  ats_rerun_notice: ATSRerunNotice | null
}

const ATS_CATEGORY_LABELS: Record<
  Exclude<keyof ATSWeightage, 'weighted_average' | 'qualify_threshold' | 'pass_fail'>,
  string
> = {
  experience: 'Professional Experience',
  skills: 'Technical & Soft Skills',
  projects: 'Projects',
  certifications: 'Certifications',
  education: 'Education',
  achievements: 'Achievements & Results',
}

const MATCH_TYPE_LABELS: Record<ATSRequirementMatchItem['match_type'], string> = {
  exact: 'Exact Match',
  parent: 'Parent Skill',
  alternative: 'Alternative',
  exceeds: 'Exceeds',
  not_found: 'Not Found',
  not_required: 'Not Required',
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
  return `Weighted average is ${w.weighted_average.toFixed(1)}%. `
    + `Strongest category: ${ATS_CATEGORY_LABELS[strongest]} at ${w[strongest].score_pct.toFixed(0)}%. `
    + `Weakest category: ${ATS_CATEGORY_LABELS[weakest]} at ${w[weakest].score_pct.toFixed(0)}%.`
}

// x/N counts always use requirement COUNT as the denominator (not the sum of fractional 0/0.5/1
// scores) — a 0.5 (alternative) match still counts as one matched requirement out of N.
function countsLine(matched: number, total: number, noun: string): string {
  return `${matched} of ${total} ${noun} matched.`
}

function skillsSummary(items: ATSRequirementMatchItem[], weightPct: number | undefined): string {
  const skillItems = items.filter(s => s.category === 'skills' && s.match_type !== 'not_required')
  if (skillItems.length === 0) return 'No skill requirements were extracted from this job posting.'
  const matched = skillItems.filter(s => s.match_type !== 'not_found').length
  const weightLine = weightPct != null ? ` Skills contribute ${weightPct.toFixed(0)}% of the overall weighted score.` : ''
  return countsLine(matched, skillItems.length, 'requirements') + weightLine
}

function relevantExperienceSummary(exp: ATSRelevantExperience, weightPct: number | undefined): string {
  const statusText = exp.status === 'qualified'
    ? 'meets'
    : exp.status === 'underqualified'
    ? 'falls short of'
    : 'exceeds'
  const yearsLine = exp.required_years != null && exp.candidate_relevant_years != null
    ? ` (required: ${exp.required_years} yrs, relevant candidate experience: ${exp.candidate_relevant_years} yrs)`
    : ''
  const respLine = exp.responsibility_matches.length > 0
    ? ` ${countsLine(exp.responsibility_matches.filter(r => r.match_type !== 'not_found').length, exp.responsibility_matches.length, 'responsibilities')}`
    : ''
  const weightLine = weightPct != null ? ` Professional Experience contributes ${weightPct.toFixed(0)}% of the overall weighted score.` : ''
  return `Candidate's relevant experience ${statusText} the required level for ${exp.job_role_required}${yearsLine}.${respLine}${weightLine}`
}

function sectionMatchingSummary(
  label: string,
  item: ATSSectionMatchItem | undefined,
  weightPct: number | undefined,
  counts: [number, number] | undefined,
): string {
  const countsPart = counts ? ` ${countsLine(counts[0], counts[1], 'sub-requirements')}` : ''
  const weightLine = weightPct != null ? ` ${label} contributes ${weightPct.toFixed(0)}% of the overall weighted score.` : ''
  if (!item) return `No ${label.toLowerCase()} content was found on the candidate's CV.${countsPart}${weightLine}`
  return `${item.note}${countsPart}${weightLine}`
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
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const [rerunNotice, setRerunNotice] = useState<ATSRerunNotice | null>(null)

  function fetchStages() {
    if (!applicationId) return
    fetch(`${API_BASE}/api/applications/${applicationId}/interview-stages`)
      .then(res => {
        if (!res.ok) throw new Error(`Server error ${res.status}`)
        return res.json() as Promise<StagesData>
      })
      .then(setData)
      .catch(err => setError(err instanceof Error ? err.message : 'Failed to load stages'))
      .finally(() => setLoading(false))
  }

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
    fetchStages()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicationId])

  // Recruiter re-ran ATS since the candidate last saw a result — show it once, then ack
  // so it doesn't reappear on a later visit/refresh.
  useEffect(() => {
    if (data?.ats_rerun_notice) setRerunNotice(data.ats_rerun_notice)
  }, [data])

  function closeRerunNotice() {
    setRerunNotice(null)
    if (applicationId) ackAtsRerunNotice(applicationId).catch(() => {})
  }

  // Live updates: reconnecting WebSocket that re-fetches stages when the backend
  // announces ATS completion, instead of waiting on a page refresh/poll.
  useEffect(() => {
    if (!applicationId) return
    let cancelled = false

    function connect() {
      if (cancelled) return
      const ws = new WebSocket(`${WS_BASE}/ws/applications/${applicationId}`)
      wsRef.current = ws

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
      }

      ws.onmessage = event => {
        try {
          const payload = JSON.parse(event.data)
          if (payload?.event === 'ats_completed') fetchStages()
        } catch {
          // Ignore malformed payloads — the REST fetch above remains the source of truth.
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onclose = () => {
        if (cancelled) return
        const attempt = reconnectAttemptsRef.current
        reconnectAttemptsRef.current = attempt + 1
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        reconnectTimerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
                ats_status: result.verdict === 'QUALIFIED' ? 'pass' : 'fail',
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

    // Counts for a requirement_matching category, or undefined if the JD had no itemized
    // sub-requirements tagged under it (falls back to just the section_matching holistic score).
    function categoryCounts(category: ATSRequirementCategory): [number, number] | undefined {
      const items = result!.requirement_matching.filter(r => r.category === category && r.match_type !== 'not_required')
      if (items.length === 0) return undefined
      return [items.filter(r => r.match_type !== 'not_found').length, items.length]
    }

    return (
      <div className="ap-ats-breakdown">

        {/* 1. Verdict badge — reuses the existing pass/fail styling; final_verdict is the true
            PASS/FAIL (Axis 1, with Axis 2 override applied if configured). Overqualification is
            shown as a separate informational flag next to it — reusing the same badge style
            (Part A: informational unless auto_reject_overqualified forced the override above). */}
        <span className={`ap-ats-verdict-badge ap-ats-verdict-badge--${result.final_verdict === 'PASS' ? 'pass' : 'fail'}`}>
          ATS {result.final_verdict === 'PASS' ? 'Passed' : 'Failed'}
        </span>
        {result.is_overqualified && (
          <span
            className={`ap-ats-verdict-badge ap-ats-verdict-badge--${result.override_reason === 'overqualified' ? 'fail' : 'pass'}`}
            title={result.override_reason === 'overqualified'
              ? 'This candidate was auto-rejected for exceeding the overqualification threshold.'
              : 'This candidate exceeds the overqualification threshold — informational only, did not affect the verdict.'}
          >
            Overqualified
          </span>
        )}

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
            {(Object.keys(ATS_CATEGORY_LABELS) as (keyof typeof ATS_CATEGORY_LABELS)[])
              // Part C.1: only show sections the recruiter's ats_criteria actually selected
              // (or all of them for legacy jobs, where `included` defaults true).
              .filter(key => result.weightage![key].included)
              .map(key => {
                const cat = result.weightage![key]
                return (
                  <div key={key} className="ap-ats-score-row">
                    <div className="ap-ats-score-row-header">
                      <span className="ap-ats-score-row-name">{ATS_CATEGORY_LABELS[key]}</span>
                      {cat.total_count != null && (
                        <span className="ap-ats-score-row-weight">{cat.matched_count}/{cat.total_count} matched</span>
                      )}
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
            <span className="ap-ats-score-overall-max">/ 100</span>
            {result.grace_credits.length > 0 && (
              <p className="ap-ats-score-row-reasoning">
                Grace credits (reviewer context, not blended into the score above): {result.grace_credits.map(g => `${g.item} (+${g.points})`).join(', ')}
              </p>
            )}
          </div>
        )}

        {/* 4. Skills — requirement_matching rows tagged category="skills" only (Part B.3); other
            categories' rows are rendered within their own section below (6-9). */}
        {(result.weightage == null || result.weightage.skills.included) && (() => {
          const skillItems = result.requirement_matching.filter(r => r.category === 'skills')
          if (skillItems.length === 0) return null
          return renderAtsSection(
            'requirements',
            ATS_CATEGORY_LABELS.skills,
            skillsSummary(result.requirement_matching, result.weightage?.skills.weight_pct),
            <>
              <div className="ap-ats-skill-grid">
                <div className="ap-ats-skill-grid-row ap-ats-skill-grid-row--header">
                  <span>Confidence</span>
                  <span>Requirement</span>
                  <span>Status</span>
                  <span>Reason</span>
                  <span>Score</span>
                </div>
                {skillItems.map((r, i) => (
                  <div key={i} className="ap-ats-skill-grid-row">
                    <span className={`ap-ats-confidence-badge ap-ats-confidence-badge--${r.confidence}`}>{r.confidence}</span>
                    <span className="ap-ats-skill-req">{r.requirement}{r.exceeds_requirement ? ' (exceeds)' : ''}</span>
                    <span className={`ap-ats-match-badge ap-ats-match-badge--${r.match_type === 'not_found' || r.match_type === 'not_required' ? 'not_found' : 'exact'}`}>
                      {MATCH_TYPE_LABELS[r.match_type]}
                    </span>
                    <span className="ap-ats-skill-note">{r.reason}</span>
                    <span className="ap-ats-skill-score">{r.score}/{r.max_score}</span>
                  </div>
                ))}
              </div>
              {result.additional_cv_content.length > 0 && (
                <div className="ap-ats-additional-skills">
                  <span className="ap-ats-item-label">Other CV Content Not Tied to a Requirement</span>
                  <div className="ap-ats-tag-list">
                    {result.additional_cv_content.map(item => (
                      <span key={item} className="ap-ats-tag">{item}</span>
                    ))}
                  </div>
                </div>
              )}
            </>,
            sectionScoreChip(result.weightage?.skills.score_pct)
          )
        })()}

        {/* 5. Relevant experience */}
        {result.relevant_experience && (result.weightage == null || result.weightage.experience.included) && renderAtsSection(
          'experience',
          'Relevant Experience',
          relevantExperienceSummary(result.relevant_experience, result.weightage?.experience.weight_pct),
          <>
            <div className="ap-ats-seniority-row">
              <div className="ap-ats-meta-pair">
                <span className="ap-ats-meta-pair-label">Role</span>
                <span className="ap-ats-meta-pair-value">{result.relevant_experience.job_role_required}</span>
              </div>
              <span
                className={`ap-ats-seniority-badge ap-ats-seniority-badge--${result.relevant_experience.status === 'qualified' ? 'match' : result.relevant_experience.status}`}
              >
                {result.relevant_experience.status === 'qualified'
                  ? 'Qualified'
                  : result.relevant_experience.status === 'underqualified'
                  ? 'Underqualified'
                  : 'Overqualified'}
              </span>
            </div>
            {(result.relevant_experience.required_years != null || result.relevant_experience.candidate_relevant_years != null) && (
              <p className="ap-ats-item-value">
                Years — required: {result.relevant_experience.required_years ?? 'n/a'}, relevant candidate experience:{' '}
                {result.relevant_experience.candidate_relevant_years ?? 'n/a'}
              </p>
            )}
            <p className="ap-ats-item-value">{result.relevant_experience.included_experience}</p>
            {result.relevant_experience.excluded_experience && (
              <p className="ap-ats-item-value">Excluded: {result.relevant_experience.excluded_experience}</p>
            )}
            {result.relevant_experience.responsibility_matches.length > 0 && (
              <div className="ap-ats-skill-grid">
                <div className="ap-ats-skill-grid-row ap-ats-skill-grid-row--header">
                  <span />
                  <span>Responsibility</span>
                  <span>Status</span>
                  <span>Evidence</span>
                  <span>Score</span>
                </div>
                {result.relevant_experience.responsibility_matches.map((r, i) => (
                  <div key={i} className="ap-ats-skill-grid-row">
                    <span />
                    <span className="ap-ats-skill-req">{r.requirement}</span>
                    <span className={`ap-ats-match-badge ap-ats-match-badge--${r.match_type === 'not_found' ? 'not_found' : 'exact'}`}>
                      {r.match_type === 'direct' ? 'Direct' : r.match_type === 'close' ? 'Close' : 'Not Found'}
                    </span>
                    <span className="ap-ats-skill-note">{r.evidence ?? 'No matching evidence found in the CV.'}</span>
                    <span className="ap-ats-skill-score">{r.score}/1</span>
                  </div>
                ))}
              </div>
            )}
          </>,
          sectionScoreChip(result.weightage?.experience.score_pct)
        )}

        {/* 6-9. Projects / Certifications / Education / Achievements — one aggregate score+note
            each from section_matching, plus itemized requirement_matching rows tagged with that
            category when the JD had explicit sub-requirements in it (Part B.3/C.2). */}
        {(['projects', 'certifications', 'education', 'achievements'] as const)
          .filter(section => result.weightage == null || result.weightage[section].included)
          .map(section => {
            const item = result.section_matching.find(s => s.section === section)
            const itemizedRows = result.requirement_matching.filter(r => r.category === section)
            return (
              <Fragment key={section}>
                {renderAtsSection(
                  section,
                  ATS_CATEGORY_LABELS[section],
                  sectionMatchingSummary(ATS_CATEGORY_LABELS[section], item, result.weightage?.[section].weight_pct, categoryCounts(section)),
                  <>
                    {item ? (
                      <div className="ap-ats-skill-row-top">
                        <span className={`ap-ats-match-badge ap-ats-match-badge--${item.cv_has_content ? 'exact' : 'not_found'}`}>
                          {item.cv_has_content ? 'Content Found' : 'Not Found'}
                        </span>
                        <span className="ap-ats-skill-score">{item.score.toFixed(0)}%</span>
                      </div>
                    ) : (
                      <p className="ap-ats-item-value">No {ATS_CATEGORY_LABELS[section].toLowerCase()} content was found or required for this role.</p>
                    )}
                    {itemizedRows.length > 0 && (
                      <div className="ap-ats-skill-grid">
                        <div className="ap-ats-skill-grid-row ap-ats-skill-grid-row--header">
                          <span>Confidence</span>
                          <span>Requirement</span>
                          <span>Status</span>
                          <span>Reason</span>
                          <span>Score</span>
                        </div>
                        {itemizedRows.map((r, i) => (
                          <div key={i} className="ap-ats-skill-grid-row">
                            <span className={`ap-ats-confidence-badge ap-ats-confidence-badge--${r.confidence}`}>{r.confidence}</span>
                            <span className="ap-ats-skill-req">{r.requirement}</span>
                            <span className={`ap-ats-match-badge ap-ats-match-badge--${r.match_type === 'not_found' || r.match_type === 'not_required' ? 'not_found' : 'exact'}`}>
                              {MATCH_TYPE_LABELS[r.match_type]}
                            </span>
                            <span className="ap-ats-skill-note">{r.reason}</span>
                            <span className="ap-ats-skill-score">{r.score}/{r.max_score}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>,
                  sectionScoreChip(result.weightage?.[section].score_pct)
                )}
              </Fragment>
            )
          })}

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
      <Modal isOpen={rerunNotice !== null} onClose={closeRerunNotice}>
        {rerunNotice && (
          <div className="ap-rerun-notice">
            <p className="ap-detail-msg-title">ATS Screening Updated</p>
            <p className="ap-detail-msg-body">{rerunNotice.message}</p>
            <Button variant="primary" onClick={closeRerunNotice}>Got it</Button>
          </div>
        )}
      </Modal>
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
