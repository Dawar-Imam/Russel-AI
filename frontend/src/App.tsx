import { Navigate, Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Home from './pages/Home'
import Auth from './pages/Auth'
import Jobs from './pages/Jobs'
import MyApplications from './pages/MyApplications'
import RecruiterDashboard from './pages/RecruiterDashboard'
import ApplicationProgress from './pages/ApplicationProgress'
import InterviewRoom from './pages/InterviewRoom'
import UserProfile from './pages/UserProfile'
import JobPostStats from './pages/JobPostStats'
import PageTransition from './components/PageTransition'
import UserMenu from './components/UserMenu'
import DebugBreadcrumb from './components/DebugBreadcrumb'

// Routes that are accessible while signed out — no redirect, no navbar
const PUBLIC_ONLY_ROUTES = ['/', '/auth']

// Routes where the navbar should be hidden regardless of auth state
const NO_NAVBAR_PREFIXES = ['/interview-room']

function isSignedIn() {
  return !!(sessionStorage.getItem('candidateId') || sessionStorage.getItem('recruiterId'))
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isSignedIn()) return <Navigate to="/" replace />
  return <>{children}</>
}

function CandidateRoute({ children }: { children: React.ReactNode }) {
  if (!isSignedIn()) return <Navigate to="/" replace />
  if (sessionStorage.getItem('userType') === 'recruiter') return <Navigate to="/recruiter-dashboard" replace />
  return <>{children}</>
}

function App() {
  const location = useLocation()
  const hideNavbar =
    PUBLIC_ONLY_ROUTES.includes(location.pathname) ||
    NO_NAVBAR_PREFIXES.some(prefix => location.pathname.startsWith(prefix))

  return (
    <>
      {!hideNavbar && <UserMenu />}
      <DebugBreadcrumb />
      <AnimatePresence mode="wait">
        <Routes location={location} key={location.pathname}>
          {/* Public routes */}
          <Route path="/" element={<PageTransition><Home /></PageTransition>} />
          <Route path="/auth" element={<PageTransition><Auth /></PageTransition>} />
          <Route path="/jobs" element={<PageTransition><Jobs /></PageTransition>} />

          {/* Protected routes — redirect to / if signed out */}
          <Route
            path="/my-applications"
            element={<CandidateRoute><PageTransition><MyApplications /></PageTransition></CandidateRoute>}
          />
          <Route
            path="/recruiter-dashboard"
            element={<ProtectedRoute><PageTransition><RecruiterDashboard /></PageTransition></ProtectedRoute>}
          />
          <Route
            path="/application-progress/:applicationId"
            element={<CandidateRoute><PageTransition><ApplicationProgress /></PageTransition></CandidateRoute>}
          />
          <Route
            path="/interview-room/:interviewId"
            element={<CandidateRoute><PageTransition><InterviewRoom /></PageTransition></CandidateRoute>}
          />
          <Route
            path="/profile"
            element={<ProtectedRoute><PageTransition><UserProfile /></PageTransition></ProtectedRoute>}
          />
          <Route
            path="/job-stats/:jobId"
            element={<ProtectedRoute><PageTransition><JobPostStats /></PageTransition></ProtectedRoute>}
          />
        </Routes>
      </AnimatePresence>
    </>
  )
}

export default App
