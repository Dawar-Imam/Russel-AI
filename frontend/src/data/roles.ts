export const JOB_ROLES = [
  'Frontend Developer',
  'Backend Developer',
  'Full Stack Developer',
  'Mobile Developer',
  'DevOps Engineer',
  'Data Scientist',
  'Data Analyst',
  'Machine Learning Engineer',
  'QA Engineer',
  'UI/UX Designer',
  'Product Manager',
] as const

export const ROLE_SKILLS: Record<(typeof JOB_ROLES)[number], string[]> = {
  'Frontend Developer': ['React', 'TypeScript', 'JavaScript', 'HTML', 'CSS', 'Redux', 'Next.js', 'Tailwind CSS'],
  'Backend Developer': ['Node.js', 'Express', 'Python', 'Django', 'REST APIs', 'SQL', 'MongoDB', 'PostgreSQL'],
  'Full Stack Developer': ['React', 'Node.js', 'TypeScript', 'Express', 'MongoDB', 'SQL', 'REST APIs', 'Docker'],
  'Mobile Developer': ['Swift', 'Kotlin', 'React Native', 'Flutter', 'iOS', 'Android'],
  'DevOps Engineer': ['Docker', 'Kubernetes', 'AWS', 'CI/CD', 'Terraform', 'Linux', 'Jenkins'],
  'Data Scientist': ['Python', 'Pandas', 'NumPy', 'Scikit-learn', 'TensorFlow', 'SQL', 'Data Visualization'],
  'Data Analyst': ['SQL', 'Excel', 'Power BI', 'Tableau', 'Python', 'Data Visualization'],
  'Machine Learning Engineer': ['Python', 'TensorFlow', 'PyTorch', 'Scikit-learn', 'MLOps', 'SQL'],
  'QA Engineer': ['Selenium', 'Cypress', 'Manual Testing', 'Test Automation', 'Jest', 'API Testing'],
  'UI/UX Designer': ['Figma', 'Adobe XD', 'Wireframing', 'Prototyping', 'User Research', 'Sketch'],
  'Product Manager': ['Roadmapping', 'Agile', 'Scrum', 'JIRA', 'Stakeholder Management', 'Analytics'],
}
