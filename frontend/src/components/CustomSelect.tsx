import { useEffect, useRef, useState } from 'react'
import '../css/CustomSelect.css'

interface Option {
  value: string
  label: string
}

interface CustomSelectProps {
  id?: string
  value: string
  options: Option[]
  placeholder: string
  onChange: (value: string) => void
}

function CustomSelect({ id, value, options, placeholder, onChange }: CustomSelectProps) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onOutsideClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) document.addEventListener('mousedown', onOutsideClick)
    return () => document.removeEventListener('mousedown', onOutsideClick)
  }, [open])

  const selectedLabel = options.find((o) => o.value === value)?.label

  return (
    <div className="cs-root" ref={rootRef}>
      <button
        id={id}
        type="button"
        className={`cs-trigger${open ? ' cs-trigger--open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={selectedLabel ? '' : 'cs-placeholder'}>
          {selectedLabel ?? placeholder}
        </span>
        <svg
          className={`cs-chevron${open ? ' cs-chevron--open' : ''}`}
          width="12"
          height="7"
          viewBox="0 0 12 7"
          fill="none"
        >
          <path
            d="M1 1l5 5 5-5"
            stroke="#9a9a9a"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>

      {open && (
        <ul className="cs-list" role="listbox">
          {options.map((opt) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              className={`cs-option${opt.value === value ? ' cs-option--selected' : ''}`}
              onMouseDown={() => {
                onChange(opt.value)
                setOpen(false)
              }}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default CustomSelect
