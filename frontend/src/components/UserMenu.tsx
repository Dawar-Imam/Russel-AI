import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import '../css/UserMenu.css'

type UserType = 'candidate' | 'recruiter' | null

function readAuthState() {
  const userType = sessionStorage.getItem('userType') as UserType
  const isSignedIn =
    userType === 'candidate'
      ? !!sessionStorage.getItem('candidateId')
      : userType === 'recruiter'
        ? !!sessionStorage.getItem('recruiterId')
        : false
  const email =
    userType === 'candidate'
      ? (sessionStorage.getItem('candidateEmail') ?? '')
      : userType === 'recruiter'
        ? (sessionStorage.getItem('recruiterEmail') ?? '')
        : ''
  return { isSignedIn, email, userType }
}

const CANDIDATE_NAV = [
  { label: 'Dashboard', to: '/my-applications', activePrefix: '/my-applications' },
  { label: 'Job Market', to: '/jobs', activePrefix: '/jobs' },
]

const RECRUITER_NAV_BASE = [
  { label: 'Dashboard', to: '/recruiter-dashboard', activePrefix: '/recruiter-dashboard' },
]

const RECRUITER_NAV_STATS = [
  ...RECRUITER_NAV_BASE,
  { label: 'Job Stats', to: '#', activePrefix: '/job-stats' },
]

function UserMenu() {
  const navigate = useNavigate()
  const location = useLocation()
  const dropdownRef = useRef<HTMLDivElement>(null)

  const [isOpen, setIsOpen] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [authState, setAuthState] = useState(readAuthState)

  useEffect(() => {
    setAuthState(readAuthState())
  }, [location])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setShowConfirm(false)
      }
    }
    if (isOpen) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  function handleLogout() {
    sessionStorage.removeItem('candidateId')
    sessionStorage.removeItem('candidateEmail')
    sessionStorage.removeItem('recruiterId')
    sessionStorage.removeItem('recruiterEmail')
    sessionStorage.removeItem('userType')
    window.dispatchEvent(new CustomEvent('auth-change'))
    setAuthState({ isSignedIn: false, email: '', userType: null })
    setIsOpen(false)
    setShowConfirm(false)
    navigate('/')
  }

  function handleViewProfile() {
    setIsOpen(false)
    navigate('/profile')
  }

  const { isSignedIn, email, userType } = authState
  const pathname = location.pathname

  if (!isSignedIn && pathname === '/jobs') return null

  return (
    <nav className="navbar">
      {/* Logo */}
      <div className="navbar-logo" onClick={() => navigate('/')}>
        <span className="navbar-logo-primary">Russel</span>
        <span className="navbar-logo-accent">.AI</span>
      </div>

      {/* Nav links */}
      {isSignedIn && (userType === 'candidate' || userType === 'recruiter') ? (
        <div className="navbar-links">
          {(userType === 'recruiter'
            ? (pathname.startsWith('/job-stats') ? RECRUITER_NAV_STATS : RECRUITER_NAV_BASE)
            : CANDIDATE_NAV
          ).map(({ label, to, activePrefix }) => (
            <NavLink
              key={label}
              to={to}
              className={`navbar-link${pathname.startsWith(activePrefix) ? ' navbar-link--active' : ''}`}
            >
              {label}
            </NavLink>
          ))}
        </div>
      ) : (
        <div className="navbar-links" />
      )}

      {/* Right side */}
      <div className="navbar-right">
        {isSignedIn ? (
          <>
          <span className="navbar-signed-in-label">
            Signed in as {userType === 'recruiter' ? 'Recruiter' : 'Candidate'}
          </span>
          <div className="navbar-user" ref={dropdownRef}>
            <button
              className="navbar-avatar-btn"
              onClick={() => setIsOpen((p) => !p)}
              aria-expanded={isOpen}
              aria-label="Account menu"
            >
              <div className="navbar-avatar">
                {email ? email[0].toUpperCase() : 'U'}
              </div>
              <span className="navbar-user-dot" />
            </button>

            <div className={`navbar-dropdown${isOpen ? ' navbar-dropdown--open' : ''}`}>
              {showConfirm ? (
                <div className="navbar-confirm">
                  <p className="navbar-confirm-text">Are you sure you want to log out?</p>
                  <button className="navbar-dd-btn navbar-dd-btn--danger" onClick={handleLogout}>
                    Yes, Log Out
                  </button>
                  <button
                    className="navbar-dd-btn navbar-dd-btn--ghost"
                    onClick={() => setShowConfirm(false)}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <>
                  <div className="navbar-dd-profile">
                    <div className="navbar-dd-avatar">
                      {email ? email[0].toUpperCase() : 'U'}
                    </div>
                    <div className="navbar-dd-info">
                      <span className="navbar-dd-role">
                        {userType === 'recruiter' ? 'Recruiter' : 'Candidate'}
                      </span>
                      <span className="navbar-dd-email" title={email}>
                        {email || 'User'}
                      </span>
                    </div>
                  </div>
                  <div className="navbar-dd-divider" />
                  <button className="navbar-dd-btn navbar-dd-btn--profile" onClick={handleViewProfile}>
                    My Profile
                  </button>
                  <div className="navbar-dd-divider" />
                  <button
                    className="navbar-dd-btn navbar-dd-btn--logout"
                    onClick={() => setShowConfirm(true)}
                  >
                    Log Out
                  </button>
                </>
              )}
            </div>
          </div>
          </>
        ) : (
          <>
            <button className="navbar-auth-btn" onClick={() => navigate('/auth')}>
              Sign In
            </button>
            <button className="navbar-auth-btn" onClick={() => navigate('/auth')}>
              Sign Up
            </button>
          </>
        )}
      </div>
    </nav>
  )
}

export default UserMenu
