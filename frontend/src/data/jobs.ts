export interface JobPost {
  id: string
  jobPostingId: string  // DB uniqueidentifier for this job posting
  title: string
  description: string
  company: string
  requiredSkills: string[]
  minExperience: string
}

export const JOB_POSTS: JobPost[] = [
  {
    id: 'junior-backend-engineer',
    jobPostingId: 'e0000001-0000-0000-0000-000000000001',
    title: 'Junior Backend Engineer',
    description: 'Build and maintain the APIs that power our AI-driven interview platform.',
    company: 'Russel.AI',
    requiredSkills: ['Node.js', 'Express', 'SQL', 'REST APIs', 'Git'],
    minExperience: '0-1 years',
  },
]
