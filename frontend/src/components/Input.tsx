import type { InputHTMLAttributes } from 'react'
import '../css/Input.css'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {}

function Input({ className = '', ...props }: InputProps) {
  return <input className={['input', className].filter(Boolean).join(' ')} {...props} />
}

export default Input
