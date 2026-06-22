import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import '../css/UserMenu.css'

function UserMenu() {
  const navigate = useNavigate()
  const location = useLocation()
  const menuRef = useRef<HTMLDivElement>(null)

  const [isOpen, setIsOpen] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [authState, setAuthState] = useState(() => ({
    isSignedIn: !!sessionStorage.getItem('candidateId'),
    email: sessionStorage.getItem('candidateEmail') ?? '',
  }))

  // Sync with sessionStorage whenever navigation occurs (e.g., after sign-in)
  useEffect(() => {
    setAuthState({
      isSignedIn: !!sessionStorage.getItem('candidateId'),
      email: sessionStorage.getItem('candidateEmail') ?? '',
    })
  }, [location])

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setShowConfirm(false)
      }
    }
    if (isOpen) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  function handleToggle() {
    setIsOpen((prev) => !prev)
    if (isOpen) setShowConfirm(false)
  }

  function handleLogout() {
    sessionStorage.removeItem('candidateId')
    sessionStorage.removeItem('candidateEmail')
    setAuthState({ isSignedIn: false, email: '' })
    setIsOpen(false)
    setShowConfirm(false)

    const isProtectedRoute =
      location.pathname.startsWith('/interview-stages') ||
      location.pathname.startsWith('/interview-room')
    if (isProtectedRoute) {
      navigate('/jobs')
    }
  }

  const { isSignedIn, email } = authState

  return (
    <div className="user-menu" ref={menuRef}>
      <button
        className={`user-menu-trigger${isSignedIn ? ' user-menu-trigger--active' : ''}`}
        onClick={handleToggle}
        aria-label={isSignedIn ? 'Account menu' : 'Sign in'}
        aria-expanded={isOpen}
      >
        <svg
          className="user-menu-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="8" r="4" />
          <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
        </svg>
        <span className={`user-menu-dot${isSignedIn ? ' user-menu-dot--online' : ''}`} />
      </button>

      <div className={`user-menu-dropdown${isOpen ? ' user-menu-dropdown--open' : ''}`}>
        {isSignedIn ? (
          showConfirm ? (
            <div className="user-menu-confirm">
              <p className="user-menu-confirm-text">Are you sure you want to log out?</p>
              <button className="user-menu-btn user-menu-btn--danger" onClick={handleLogout}>
                Yes, Log Out
              </button>
              <button
                className="user-menu-btn user-menu-btn--ghost"
                onClick={() => setShowConfirm(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <>
              <div className="user-menu-profile">
                <div className="user-menu-avatar">
                  {email ? email[0].toUpperCase() : 'U'}
                </div>
                <div className="user-menu-info">
                  <span className="user-menu-status">Signed in as</span>
                  <span className="user-menu-email" title={email}>
                    {email || 'Candidate'}
                  </span>
                </div>
              </div>
              <div className="user-menu-divider" />
              <button
                className="user-menu-btn user-menu-btn--logout"
                onClick={() => setShowConfirm(true)}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                  <polyline points="16 17 21 12 16 7" />
                  <line x1="21" y1="12" x2="9" y2="12" />
                </svg>
                Log Out
              </button>
            </>
          )
        ) : (
          <button
            className="user-menu-btn user-menu-btn--signin"
            onClick={() => {
              setIsOpen(false)
              navigate('/auth')
            }}
          >
            Sign In
          </button>
        )}
      </div>
    </div>
  )
}

export default UserMenu
