# Russel-AI: Your AI Recruitment & Talent Intelligence Platform
Russel.AI is an AI-powered talent intelligence platform that streamlines the hiring process for recruiters and accelerates career growth for candidates. The platform automates candidate screening, interviews, evaluation, ranking, and reporting, helping recruiters focus only on the most qualified applicants. For candidates, Russel.AI provides AI mock interviews, skill gap analysis, personalized preparation guidance, and career insights to improve job readiness and hiring success.

---
 
## Overview
 
HireIQ serves two sides of the hiring process:
 
- **Recruiters** post jobs, define interview rounds, and receive a shortlisted, ranked set of candidates — with minimal manual effort.
- **Candidates** apply for jobs, go through AI-conducted interviews, and get personalised feedback on skill gaps and how to improve.
---
 
## Core Features
 
### For Recruiters
- Post job listings with required skills, experience level, and interview round definitions
- Company verification flow — recruiters must be linked to a verified company before posting
- Automated candidate screening based on skill match between candidate profile and job requirements
- AI-conducted interview rounds (configurable per job posting)
- Detailed interview reports per candidate with scores, answers, and feedback
- Final shortlist delivered — only top candidates surface to the recruiter
### For Candidates
- Sign up, build a profile with skills, experience, resume, and LinkedIn
- Browse and apply to job postings
- Attend AI-conducted interviews per application
- Receive post-interview feedback and scores
- **Mock interview mode** — practice interviews independent of any job application
- **Gap analysis** — system compares candidate skills against current market demand and highlights areas to work on
- Personalised preparation recommendations
### For Admins
- Verify companies and manage recruiter access
- Manage lookup data: roles, job titles, skill sets, question categories, interview round types
- Platform-wide oversight
---
 
## Database Schema
 
17 tables across the following domains:
 
| Domain | Tables |
|---|---|
| Auth & Roles | `ROLES`, `USERS` |
| Profiles | `RECRUITER_PROFILES`, `CANDIDATE_PROFILES` |
| Company | `COMPANIES` |
| Jobs | `JOB_TITLES`, `JOB_POSTINGS` |
| Applications | `APPLICATIONS` |
| Skills | `SKILL_SETS`, `CANDIDATE_SKILLS`, `JOB_REQUIRED_SKILLS` |
| Interviews | `INTERVIEW_ROUND_TYPES`, `INTERVIEW_ROUNDS`, `INTERVIEWS`, `INTERVIEW_QUESTIONS` |
| Questions | `QUESTION_CATEGORIES`, `QUESTIONS` |
 
### ER Diagram
 
```mermaid
erDiagram
 
  ROLES {
    int id PK
    varchar name
    varchar description
  }
 
  USERS {
    uuid id PK
    varchar email
    varchar password_hash
    varchar first_name
    varchar last_name
    varchar phone
    int role_id FK
    boolean is_active
    boolean is_verified
    timestamp created_at
    timestamp updated_at
  }
 
  COMPANIES {
    uuid id PK
    varchar name
    varchar domain
    varchar website
    varchar industry
    varchar registration_number
    enum verification_status
    timestamp created_at
  }
 
  RECRUITER_PROFILES {
    uuid id PK
    uuid user_id FK
    uuid company_id FK
    varchar designation
    boolean company_verified
    timestamp joined_at
  }
 
  CANDIDATE_PROFILES {
    uuid id PK
    uuid user_id FK
    text bio
    varchar resume_url
    varchar linkedin_url
    int years_of_experience
    varchar current_location
    boolean open_to_work
    timestamp updated_at
  }
 
  JOB_TITLES {
    int id PK
    varchar title
    varchar category
    boolean is_active
  }
 
  JOB_POSTINGS {
    uuid id PK
    uuid recruiter_id FK
    uuid company_id FK
    int job_title_id FK
    varchar designation
    text description
    varchar location
    enum job_type
    varchar salary_range
    enum status
    timestamp posted_at
    timestamp expires_at
  }
 
  APPLICATIONS {
    uuid id PK
    uuid job_id FK
    uuid candidate_id FK
    enum status
    text cover_letter
    timestamp applied_at
  }
 
  SKILL_SETS {
    int id PK
    varchar name
    varchar category
    boolean is_active
  }
 
  CANDIDATE_SKILLS {
    uuid id PK
    uuid candidate_id FK
    int skill_id FK
    enum proficiency_level
    int years_of_experience
  }
 
  JOB_REQUIRED_SKILLS {
    uuid id PK
    uuid job_id FK
    int skill_id FK
    enum proficiency_level
    boolean is_mandatory
  }
 
  INTERVIEW_ROUND_TYPES {
    int id PK
    varchar name
    varchar description
  }
 
  INTERVIEW_ROUNDS {
    uuid id PK
    uuid job_posting_id FK
    int interview_round_type_id FK
    int round_order
    varchar description
    boolean is_active
  }
 
  INTERVIEWS {
    uuid id PK
    uuid interview_round_id FK
    uuid application_id FK
    enum status
    timestamp scheduled_at
    timestamp completed_at
    text feedback
    enum result
  }
 
  QUESTION_CATEGORIES {
    int id PK
    varchar name
    varchar description
  }
 
  QUESTIONS {
    uuid id PK
    int category_id FK
    text question_text
    enum difficulty_level
    boolean is_active
    timestamp created_at
  }
 
  INTERVIEW_QUESTIONS {
    uuid id PK
    uuid interview_id FK
    uuid question_id FK
    text candidate_answer
    int score
    text notes
  }
 
  ROLES ||--o{ USERS : "assigned to"
  USERS ||--o| RECRUITER_PROFILES : "has"
  USERS ||--o| CANDIDATE_PROFILES : "has"
  COMPANIES ||--o{ RECRUITER_PROFILES : "employs"
  COMPANIES ||--o{ JOB_POSTINGS : "posts"
  RECRUITER_PROFILES ||--o{ JOB_POSTINGS : "creates"
  JOB_TITLES ||--o{ JOB_POSTINGS : "categorizes"
  JOB_POSTINGS ||--o{ APPLICATIONS : "receives"
  CANDIDATE_PROFILES ||--o{ APPLICATIONS : "submits"
  SKILL_SETS ||--o{ CANDIDATE_SKILLS : "tagged on"
  SKILL_SETS ||--o{ JOB_REQUIRED_SKILLS : "required in"
  CANDIDATE_PROFILES ||--o{ CANDIDATE_SKILLS : "has"
  JOB_POSTINGS ||--o{ JOB_REQUIRED_SKILLS : "requires"
  JOB_POSTINGS ||--o{ INTERVIEW_ROUNDS : "defines"
  INTERVIEW_ROUND_TYPES ||--o{ INTERVIEW_ROUNDS : "typed as"
  INTERVIEW_ROUNDS ||--o{ INTERVIEWS : "schedules"
  APPLICATIONS ||--o{ INTERVIEWS : "goes through"
  QUESTION_CATEGORIES ||--o{ QUESTIONS : "categorizes"
  QUESTIONS ||--o{ INTERVIEW_QUESTIONS : "asked in"
  INTERVIEWS ||--o{ INTERVIEW_QUESTIONS : "contains"
```
 
---
 
## User Roles
 
| Role | Description |
|---|---|
| `candidate` | Signs up to find jobs, attend interviews, and prepare |
| `recruiter` | Posts jobs, defines interview rounds, reviews shortlisted candidates |
| `admin` | Verifies companies, manages platform data |
 
---
 
## System Flow
 
```
Recruiter posts job → Candidates apply → AI screens by skill match
→ AI conducts interview rounds → Scores & feedback generated
→ Recruiter receives shortlisted candidates with reports
```
 
```
Candidate signs up → Builds profile → Applies to jobs
→ Attends AI interviews → Gets feedback & gap analysis
→ Practices via mock interviews → Improves and re-applies
```
 
---
 
## System Design
 
- Full flow diagram: [draw.io](https://app.diagrams.net/#G1CyvYuqgtQgt8ghGicG6CHgu0zTUcIK5C#%7B%22pageId%22%3A%22FgCxdf08D7E8nqMTdc42%22%7D)
 


