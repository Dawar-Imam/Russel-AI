import { useEffect, useRef, useState } from 'react'
import '../css/InfoTooltip.css'

interface InfoTooltipProps {
  text: string
}

function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleOutside)
    return () => document.removeEventListener('mousedown', handleOutside)
  }, [open])

  return (
    <span className={`info-tooltip${open ? ' info-tooltip--open' : ''}`} ref={ref}>
      <button
        type="button"
        className="info-tooltip-icon"
        aria-label="More information"
        onClick={() => setOpen((v) => !v)}
      >
        i
      </button>
      <span className="info-tooltip-bubble" role="tooltip">{text}</span>
    </span>
  )
}

export default InfoTooltip
