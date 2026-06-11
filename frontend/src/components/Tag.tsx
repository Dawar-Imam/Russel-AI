import type { ReactNode } from 'react'
import '../css/Tag.css'

type TagVariant = 'default' | 'active' | 'info'

interface TagProps {
  children: ReactNode
  variant?: TagVariant
  onClick?: () => void
  onRemove?: () => void
  className?: string
}

function Tag({ children, variant = 'default', onClick, onRemove, className = '' }: TagProps) {
  const classes = ['tag', `tag-${variant}`, onClick ? 'tag-clickable' : '', className]
    .filter(Boolean)
    .join(' ')

  return (
    <span className={classes} onClick={onClick}>
      {children}
      {onRemove && (
        <button
          type="button"
          className="tag-remove"
          aria-label="Remove"
          onClick={(event) => {
            event.stopPropagation()
            onRemove()
          }}
        >
          &times;
        </button>
      )}
    </span>
  )
}

export default Tag
