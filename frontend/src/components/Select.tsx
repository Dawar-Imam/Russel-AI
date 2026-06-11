import type { SelectHTMLAttributes } from 'react'
import '../css/Select.css'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {}

function Select({ className = '', children, ...props }: SelectProps) {
  return (
    <select className={['select', className].filter(Boolean).join(' ')} {...props}>
      {children}
    </select>
  )
}

export default Select
