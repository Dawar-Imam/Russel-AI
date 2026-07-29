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
import AppLayout, { shouldShowAppLayout } from './components/AppLayout'
import DebugBreadcrumb from './components/DebugBreadcrumb'

function isSignedIn() {
  return !!(sessionStorage.getItem('candidateId') || sessionStorage.getItem('recruiterId'))
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  if (!isSignedIn()) return <Navigate to="/" replace />
  return <>{children}</>
}

function CandidateRoute({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  // Unlike ProtectedRoute, a signed-out visit here (e.g. a Calendar invite's
  // interview-room link opened in a fresh/logged-out browser) sends them to sign in
  // instead of the homepage, and remembers where they were headed so Auth.tsx can
  // send them straight back after a successful candidate sign-in.
  if (!isSignedIn()) return <Navigate to="/auth" state={{ returnTo: location.pathname }} replace />
  if (sessionStorage.getItem('userType') === 'recruiter') return <Navigate to="/recruiter-dashboard" replace />
  return <>{children}</>
}

function App() {
  const location = useLocation()
  const showLayout = shouldShowAppLayout(location.pathname, isSignedIn())

  const routes = (
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
  )

  return (
    <>
      <DebugBreadcrumb />
      {showLayout ? <AppLayout>{routes}</AppLayout> : routes}
    </>
  )
}

export default App
