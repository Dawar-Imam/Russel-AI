import type { InputHTMLAttributes } from 'react'
import '../css/Input.css'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

function Input({ className = '', value, ...props }: InputProps) {
  return (
    <input
      className={['input', className].filter(Boolean).join(' ')}
      value={value ?? ''}
      {...props}
    />
  )
}

export default Input
