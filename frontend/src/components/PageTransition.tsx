import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import '../css/PageTransition.css'

interface PageTransitionProps {
  children: ReactNode
}

const variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
}

function PageTransition({ children }: PageTransitionProps) {
  return (
    <motion.div
      className="page-transition"
      variants={variants}
      initial="initial"
      animate="animate"
      exit="exit"
      transition={{ duration: 0.35, ease: 'easeInOut' }}
    >
      {children}
    </motion.div>
  )
}

export default PageTransition
