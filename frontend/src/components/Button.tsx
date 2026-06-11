import type { ButtonHTMLAttributes } from 'react'
import '../css/Button.css'

type ButtonVariant = 'primary' | 'secondary' | 'ghost'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
}

function Button({ variant = 'primary', className = '', ...props }: ButtonProps) {
  const classes = ['btn', `btn-${variant}`, className].filter(Boolean).join(' ')
  return <button className={classes} {...props} />
}

export default Button
