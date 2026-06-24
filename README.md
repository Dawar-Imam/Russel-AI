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
- Manage lookup data: roles, job roles, experience levels, skill sets, interview round types
- Platform-wide oversight
---

## Interview Status Values

The `Interviews.status` column uses the following four values:

| Status | Meaning |
|---|---|
| `Scheduled` | Date/time assigned — interview is upcoming |
| `In Progress` | Interview is currently happening |
| `Pass` | Round completed — candidate scored above the passing threshold |
| `Failed` | Round completed — candidate scored below the passing threshold, or a system/network failure occurred |

The **current round** displayed to the candidate is the interview with the lowest `round_order` (via `InterviewRounds`) whose status is `Scheduled` or `In Progress`.

### Interviews column semantics

| Column | Type | Stores |
|---|---|---|
| `status` | varchar | `Scheduled` / `In Progress` / `Pass` / `Failed` |
| `result` | float | Final numeric score (0–10) after scoring completes |
| `feedback` | nvarchar | AI-generated text feedback about the interview round |

---

## Database Schema

18 tables across the following domains:

| Domain | Tables |
|---|---|
| Auth & Roles | `Roles`, `Users` |
| Profiles | `RecruiterProfiles`, `CandidateProfiles` |
| Company | `Companies` |
| Jobs | `JobRoles`, `JobPostings`, `ExperienceLevels` |
| Applications | `Applications`, `Resumes` |
| Skills | `SkillSets`, `CandidateSkills`, `JobRequiredSkills` |
| Interviews | `InterviewRoundTypes`, `InterviewRounds`, `Interviews`, `InterviewQuestions` |
| Questions | `Questions` |

### ER Diagram

```mermaid
erDiagram
  Roles {
    int id PK
    varchar name
    varchar description
  }

  ExperienceLevels {
    int id PK
    varchar name
    int min_years
    int max_years
  }

  JobRoles {
    int id PK
    varchar title
    varchar category
    bit is_active
  }

  InterviewRoundTypes {
    int id PK
    varchar name
    varchar description
  }

  SkillSets {
    int id PK
    varchar name
    varchar category
    bit is_active
  }

  Companies {
    uniqueidentifier id PK
    varchar name
    varchar domain
    varchar website
    varchar industry
    varchar registration_number
    varchar verification_status
    datetime2 created_at
  }

  Users {
    uniqueidentifier id PK
    varchar email
    varchar password_hash
    varchar first_name
    varchar last_name
    varchar phone
    int role_id FK
    bit is_active
    bit is_verified
    datetime2 created_at
    datetime2 updated_at
  }

  CandidateProfiles {
    uniqueidentifier id PK
    uniqueidentifier user_id FK
    nvarchar bio
    varchar resume_url
    varchar linkedin_url
    int experience_level_id FK
    int job_role_id FK
    varchar current_location
    bit open_to_work
    datetime2 updated_at
  }

  CandidateSkills {
    uniqueidentifier id PK
    uniqueidentifier candidate_id FK
    int skill_id FK
    varchar proficiency_level
    int years_of_experience
  }

  RecruiterProfiles {
    uniqueidentifier id PK
    uniqueidentifier user_id FK
    uniqueidentifier company_id FK
    varchar designation
    bit company_verified
    datetime2 joined_at
  }

  JobPostings {
    uniqueidentifier id PK
    uniqueidentifier recruiter_id FK
    uniqueidentifier company_id FK
    int job_role_id FK
    int experience_level_id FK
    nvarchar description
    varchar location
    varchar job_type
    varchar salary_range
    varchar status
    datetime2 posted_at
    datetime2 expires_at
  }

  JobRequiredSkills {
    uniqueidentifier id PK
    uniqueidentifier job_id FK
    int skill_id FK
    varchar proficiency_level
    bit is_mandatory
  }

  Resumes {
    uniqueidentifier id PK
    uniqueidentifier candidate_id FK
    varchar file_url
    varchar file_name
    nvarchar parsed_text
    datetime2 uploaded_at
  }

  Applications {
    uniqueidentifier id PK
    uniqueidentifier job_id FK
    uniqueidentifier candidate_id FK
    uniqueidentifier resume_id FK
    varchar status
    nvarchar ats_reason
    nvarchar cover_letter
    datetime2 applied_at
  }

  InterviewRounds {
    uniqueidentifier id PK
    uniqueidentifier job_posting_id FK
    int interview_round_type_id FK
    int round_order
    varchar description
    bit is_active
  }

  Interviews {
    uniqueidentifier id PK
    uniqueidentifier interview_round_id FK
    uniqueidentifier application_id FK
    varchar status
    datetime2 scheduled_at
    datetime2 completed_at
    nvarchar feedback
    float result
  }

  Questions {
    uniqueidentifier id PK
    int interview_round_type_id FK
    int job_role_id FK
    int experience_level_id FK
    nvarchar question_text
    bit is_active
    datetime2 created_at
    bit ai_generated
  }

  InterviewQuestions {
    uniqueidentifier id PK
    uniqueidentifier interview_id FK
    uniqueidentifier question_id FK
    nvarchar candidate_answer
    int score
    nvarchar notes
  }

  Roles ||--o{ Users : "has"
  Users ||--o| CandidateProfiles : "has"
  Users ||--o| RecruiterProfiles : "has"
  ExperienceLevels ||--o{ CandidateProfiles : "level"
  JobRoles ||--o{ CandidateProfiles : "role"
  CandidateProfiles ||--o{ CandidateSkills : "has"
  SkillSets ||--o{ CandidateSkills : "ref"
  Companies ||--o{ RecruiterProfiles : "employs"
  Companies ||--o{ JobPostings : "posts"
  RecruiterProfiles ||--o{ JobPostings : "creates"
  JobRoles ||--o{ JobPostings : "role"
  ExperienceLevels ||--o{ JobPostings : "level"
  JobPostings ||--o{ JobRequiredSkills : "requires"
  SkillSets ||--o{ JobRequiredSkills : "ref"
  CandidateProfiles ||--o{ Resumes : "uploads"
  JobPostings ||--o{ Applications : "receives"
  CandidateProfiles ||--o{ Applications : "submits"
  Resumes ||--o{ Applications : "attached to"
  JobPostings ||--o{ InterviewRounds : "has"
  InterviewRoundTypes ||--o{ InterviewRounds : "type"
  InterviewRounds ||--o{ Interviews : "has"
  Applications ||--o{ Interviews : "schedules"
  Interviews ||--o{ InterviewQuestions : "contains"
  Questions ||--o{ InterviewQuestions : "ref"
  InterviewRoundTypes ||--o{ Questions : "type"
  JobRoles ||--o{ Questions : "role"
  ExperienceLevels ||--o{ Questions : "level"
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

---

## Project Setup

### Backend (FastAPI, `uv`-managed via `pyproject.toml`)

- `app/main.py` – FastAPI app with CORS, `/health` endpoint, mounts API router
- `app/core/config.py` – pydantic-settings based config (reads `.env`)
- `app/core/logging.py` – logging setup
- `app/api/router.py` + `app/api/endpoints/demo.py` – demo endpoint at `/demo/`
- `app/schemas/schema.py` – `DemoMessage` pydantic model
- `app/services/demo_service.py` – demo service returning the message
- `app/database/__init__.py` – placeholder for DB setup
- `.env.example` for config

Run:
```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload
```

### Frontend (Vite + React + TypeScript)

- `src/components/Header.tsx`, `src/pages/Home.tsx` – sample component/page
- `src/App.tsx` – react-router routes, `src/main.tsx` – entry with `BrowserRouter`
- `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`

Run:
```bash
cd frontend && npm install && npm run dev
```

### AI Agents (LangGraph, `uv`-managed via `pyproject.toml`)

- `agents/interview_agent/` – Interview Agent
  - `schemas.py` – Pydantic I/O schemas for `generate_questions_tool` / `score_answers_tool`
  - `prompts.py` – system/user prompts for question generation, CV-relevance extraction, and answer grading
  - `tools.py` – `generate_questions_tool`, `score_answers_tool` graph node functions
  - `models.py` – SQLAlchemy models for the schema subset these tools use (`Questions`, `JobRoles`, `ExperienceLevels`, `InterviewRoundTypes`, `SkillSets`, `CandidateProfiles`, `CandidateSkills`, `JobPostings`, `JobRequiredSkills`)
- `agents/voice_agent/` – scaffold only (`agent.py`, `models.py`, `prompt.py`, `schemas.py`, `tools.py`)
- `ai_services/` – service layer used by the interview agent tools
  - `question_bank_service.py` – `fetch_questions_from_db`, `fetch_interview_context`
  - `cv_relevance_service.py` – `fetch_candidate_cv_relevance` (+ resume-PDF variant `fetch_candidate_cv_relevance_2`)
  - `question_generation_service.py` – `generate_questions`
  - `answer_scoring_service.py` – `grade_candidate_answers`
- `graph/` – `state.py` (`AgentState` TypedDict) and `graph.py` (`interview_graph` LangGraph `StateGraph`)
- `ai_configs/` – `config.py` (pydantic-settings + `get_llm()` ChatOpenAI factory), `db.py` (SQLAlchemy engine/session against SQL Server LocalDB `RusselAI`)
- `app.py` – CLI entrypoint that runs `generate_questions_tool` then `score_answers_tool`
- `.env.example` for config (`DATABASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL`)

See [.claude/agent-architecture.md](.claude/agent-architecture.md) for the
full agentic flow and tool I/O contracts.

Run:
```bash
cd ai && uv sync && uv run python app.py
```
