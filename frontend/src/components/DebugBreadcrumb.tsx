import { useState } from 'react'
import { useLocation } from 'react-router-dom'
import '../css/DebugBreadcrumb.css'

// ── Toggle this constant to show/hide the debug panel ──
const SHOW_DEBUG_BREADCRUMB = true

function DebugBreadcrumb() {
  const [open, setOpen] = useState(false)
  const location = useLocation()

  if (!SHOW_DEBUG_BREADCRUMB) return null

  const candidateId   = sessionStorage.getItem('candidateId')   ?? '—'
  const interviewMatch    = location.pathname.match(/\/interview-room\/([^/]+)/)
  const applicationMatch  = location.pathname.match(/\/application-progress\/([^/]+)/)

  const interviewId   = interviewMatch?.[1]   ?? '—'
  const applicationId = applicationMatch?.[1] ?? '—'
  const jobPostId     = sessionStorage.getItem('jobPostId') ?? '—'

  const rows: [string, string][] = [
    ['candidate_id',    candidateId],
    ['application_id',  applicationId],
    ['interview_id',    interviewId],
    ['job_post_id',     jobPostId],
  ]

  return (
    <div className="dbg-root">
      <button
        type="button"
        className={`dbg-trigger${open ? ' dbg-trigger--open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        title="Debug IDs"
      >
        {'{ }'}
      </button>

      {open && (
        <div className="dbg-panel">
          <p className="dbg-panel-title">Debug IDs</p>
          {rows.map(([key, val]) => (
            <div key={key} className="dbg-row">
              <span className="dbg-key">{key}</span>
              <span className="dbg-val" title={val}>{val}</span>
            </div>
          ))}
          <p className="dbg-hint">
            Toggle: <code>SHOW_DEBUG_BREADCRUMB</code> in<br />
            <code>src/components/DebugBreadcrumb.tsx</code>
          </p>
        </div>
      )}
    </div>
  )
}

export default DebugBreadcrumb
