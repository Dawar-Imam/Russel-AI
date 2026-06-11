import { Routes, Route, useLocation } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import Home from './pages/Home'
import Auth from './pages/Auth'
import Jobs from './pages/Jobs'
import InterviewStages from './pages/InterviewStages'
import InterviewRoom from './pages/InterviewRoom'
import PageTransition from './components/PageTransition'

function App() {
  const location = useLocation()

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route
          path="/"
          element={
            <PageTransition>
              <Home />
            </PageTransition>
          }
        />
        <Route
          path="/auth"
          element={
            <PageTransition>
              <Auth />
            </PageTransition>
          }
        />
        <Route
          path="/jobs"
          element={
            <PageTransition>
              <Jobs />
            </PageTransition>
          }
        />
        <Route
          path="/interview-stages"
          element={
            <PageTransition>
              <InterviewStages />
            </PageTransition>
          }
        />
        <Route
          path="/interview-room"
          element={
            <PageTransition>
              <InterviewRoom />
            </PageTransition>
          }
        />
      </Routes>
    </AnimatePresence>
  )
}

export default App
