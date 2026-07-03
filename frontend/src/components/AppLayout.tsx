import { useEffect, useRef, useState, type ReactNode } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import '../css/AppLayout.css'
import { toggleTheme } from '../utils/theme'
import { useTheme } from '../utils/useTheme'

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

// Routes accessible while signed out, or with no portal chrome
const NO_LAYOUT_PATHS = ['/', '/auth']
const NO_LAYOUT_PREFIXES = ['/interview-room']

export function shouldShowAppLayout(pathname: string, signedIn: boolean) {
  if (!signedIn) return false
  if (NO_LAYOUT_PATHS.includes(pathname)) return false
  if (NO_LAYOUT_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return false
  return true
}

function AppLayout({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const location = useLocation()
  const dropdownRef = useRef<HTMLDivElement>(null)

  const [isOpen, setIsOpen] = useState(false)
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)
  const [authState, setAuthState] = useState(readAuthState)
  const theme = useTheme()

  useEffect(() => {
    setAuthState(readAuthState())
  }, [location])

  useEffect(() => {
    document.body.classList.add('has-app-sidebar')
    return () => document.body.classList.remove('has-app-sidebar')
  }, [])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
        setShowLogoutConfirm(false)
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
    setShowLogoutConfirm(false)
    navigate('/')
  }

  function handleViewProfile() {
    setIsOpen(false)
    navigate('/profile')
  }

  const { email, userType } = authState
  const pathname = location.pathname

  const baseNavItems =
    userType === 'recruiter'
      ? pathname.startsWith('/job-stats') ? RECRUITER_NAV_STATS : RECRUITER_NAV_BASE
      : CANDIDATE_NAV

  const navItems = pathname.startsWith('/application-progress')
    ? [...baseNavItems, { label: 'Application Progress', to: pathname, activePrefix: '/application-progress' }]
    : baseNavItems

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar-logo" onClick={() => navigate('/')}>
          <span className="app-sidebar-logo-primary">Russel</span>
          <span className="app-sidebar-logo-accent">.AI</span>
        </div>

        <div className="app-sidebar-divider" />

        <nav className="app-sidebar-nav">
          {navItems.map(({ label, to, activePrefix }) => (
            <NavLink
              key={label}
              to={to}
              className={`app-sidebar-link${pathname.startsWith(activePrefix) ? ' app-sidebar-link--active' : ''}`}
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="app-sidebar-spacer" />
      </aside>

      <div className="app-main">
        <header className="app-topbar">
          <span className="app-topbar-signed-in">
            Signed in as {userType === 'recruiter' ? 'Recruiter' : 'Candidate'}
          </span>

          <button
            className="app-topbar-theme-toggle"
            type="button"
            aria-label="Theme toggle"
            onClick={toggleTheme}
          >
            {theme === 'light' ? (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : (
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
              </svg>
            )}
          </button>

          <div className="app-topbar-user" ref={dropdownRef}>
            <button
              className="app-topbar-avatar-btn"
              onClick={() => setIsOpen((p) => !p)}
              aria-expanded={isOpen}
              aria-label="Account menu"
            >
              <div className="app-topbar-avatar">
                {email ? email[0].toUpperCase() : 'U'}
              </div>
            </button>

            <div className={`app-topbar-dropdown${isOpen ? ' app-topbar-dropdown--open' : ''}`}>
              <div className="app-topbar-dd-profile">
                <div className="app-topbar-dd-avatar">
                  {email ? email[0].toUpperCase() : 'U'}
                </div>
                <div className="app-topbar-dd-info">
                  <span className="app-topbar-dd-role">
                    {userType === 'recruiter' ? 'Recruiter' : 'Candidate'}
                  </span>
                  <span className="app-topbar-dd-email" title={email}>
                    {email || 'User'}
                  </span>
                </div>
              </div>
              <div className="app-topbar-dd-divider" />
              <button className="app-topbar-dd-btn" onClick={handleViewProfile}>
                My Profile
              </button>
              {showLogoutConfirm ? (
                <div className="app-topbar-dd-logout-confirm">
                  <p className="app-topbar-dd-logout-confirm-text">Log out?</p>
                  <div className="app-topbar-dd-logout-confirm-actions">
                    <button className="app-topbar-dd-logout-confirm-btn app-topbar-dd-logout-confirm-btn--danger" onClick={handleLogout}>
                      Yes
                    </button>
                    <button className="app-topbar-dd-logout-confirm-btn" onClick={() => setShowLogoutConfirm(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button className="app-topbar-dd-btn app-topbar-dd-btn--logout" onClick={() => setShowLogoutConfirm(true)}>
                  Log Out
                </button>
              )}
            </div>
          </div>
        </header>

        <div className="app-content">{children}</div>
      </div>
    </div>
  )
}

export default AppLayout
