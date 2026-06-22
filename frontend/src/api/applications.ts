const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

const ATS_TIMEOUT_MS = 15_000

export interface ATSCheckResponse {
  eligible: boolean
  reason: string
}

export async function checkAtsEligibility(
  jobPostingId: string,
  candidateId: string,
): Promise<ATSCheckResponse> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), ATS_TIMEOUT_MS)

  try {
    const params = new URLSearchParams({
      job_posting_id: jobPostingId,
      candidate_id: candidateId,
    })
    const res = await fetch(`${BASE_URL}/api/applications/ats-check?${params}`, {
      signal: ctrl.signal,
    })
    if (!res.ok) throw new Error('Eligibility check failed')
    return res.json() as Promise<ATSCheckResponse>
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      // Timed out — return eligible so the soft gate never hard-blocks
      return { eligible: true, reason: 'Eligibility check timed out; proceeding.' }
    }
    throw err
  } finally {
    clearTimeout(timer)
  }
}
