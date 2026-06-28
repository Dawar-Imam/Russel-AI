# Russel-AI Code Structure

Quick reference for navigating features to files. Use this before reading code — look up the feature, go straight to the file.

---

## Directory Tree

```
Russel-AI/
├── .claude/
│   ├── agent-architecture.md      # Interview pipeline agent flow & tool I/O schemas
│   ├── code-structure.md          # This file
│   ├── database-schema.md         # Table-by-table DB schema (18 tables, DDL, FKs)
│   └── frontend-theme.md          # Design system: tokens, components, animation catalogue
│
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app init, CORS, router registration
│   │   ├── api/
│   │   │   ├── router.py          # Aggregates all endpoint routers
│   │   │   └── endpoints/
│   │   │       ├── auth.py        # /auth: signup, signin, profile, metadata
│   │   │       ├── applications.py# /applications: apply, ATS, stages, Q&A
│   │   │       ├── interviews.py  # /interviews: generate-questions, score-answers, voice-interview, status-stream
│   │   │       ├── jobs.py        # /jobs: list, detail, post (recruiter), mine
│   │   │       └── demo.py        # Demo/seed endpoints
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── application_service.py
│   │   │   ├── job_service.py
│   │   │   ├── interview_service.py
│   │   │   ├── interview_validator.py
│   │   │   ├── cv_parser_service.py
│   │   │   └── demo_service.py
│   │   ├── schemas/
│   │   │   ├── auth.py
│   │   │   ├── applications.py
│   │   │   ├── interviews.py
│   │   │   ├── jobs.py
│   │   │   └── schema.py          # Shared base schemas
│   │   ├── ai/
│   │   │   ├── app.py             # Standalone AI service entry (unused in normal run)
│   │   │   ├── ai_services/
│   │   │   │   ├── ats_service.py
│   │   │   │   ├── question_generation_service.py
│   │   │   │   ├── answer_scoring_service.py
│   │   │   │   ├── cv_relevance_service.py
│   │   │   │   └── question_bank_service.py
│   │   │   ├── interview_tools/
│   │   │   │   ├── tools.py       # LangGraph tool wrappers
│   │   │   │   ├── schemas.py     # Tool I/O schemas
│   │   │   │   ├── prompts.py     # LLM system/user prompts
│   │   │   │   └── state.py       # AgentState
│   │   │   └── voice_agent/
│   │   │       ├── agent.py       # LiveKit + Deepgram + ElevenLabs voice agent
│   │   │       ├── room_connection.py # Room creation, conduct_voice_interview, wait_for_done
│   │   │       └── test_room_connection.py
│   │   ├── core/
│   │   │   ├── config.py          # Settings: DB URL, OpenAI key, LiveKit, Deepgram, ElevenLabs
│   │   │   └── logging.py
│   │   └── database/
│   │       └── session.py         # SQLAlchemy engine + session factory
│   ├── uploads/
│   │   └── resumes/               # Uploaded CV files (UUID-named)
│   ├── tests/
│   │   ├── resumes/               # Test resume fixtures
│   │   └── generated_resumes/
│   ├── pyproject.toml             # uv project config + dependencies
│   └── .env.example
│
├── ai/                            # Standalone AI service (separate from backend/app/ai)
│   ├── app.py                     # Standalone entry point
│   ├── agents/
│   │   └── interview_agent/
│   │       ├── agent.py           # Main interview agent orchestration
│   │       ├── state.py           # AgentState definition
│   │       ├── schemas.py         # Tool I/O schemas
│   │       ├── prompts.py         # System prompts
│   │       ├── tools.py           # generate_questions_tool, score_answers_tool, validate_tool
│   │       └── voice_agent/
│   │           ├── agent.py       # Voice agent (mostly scaffold)
│   │           ├── schemas.py
│   │           ├── models.py
│   │           ├── prompt.py
│   │           └── tools.py
│   ├── ai_services/               # Mirrors backend/app/ai/ai_services (standalone use)
│   │   ├── question_generation_service.py
│   │   ├── answer_scoring_service.py
│   │   ├── cv_relevance_service.py
│   │   └── question_bank_service.py
│   ├── graph/
│   │   ├── graph.py               # LangGraph agent definition
│   │   └── state.py               # Graph-level state
│   ├── pyproject.toml
│   └── test_db.py
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # React Router setup, global route tree
│   │   ├── main.tsx               # Vite entry point
│   │   ├── pages/
│   │   │   ├── Home.tsx           # Landing page
│   │   │   ├── Auth.tsx           # Signup / Signin (role selection, CV upload)
│   │   │   ├── Jobs.tsx           # Job listing + filter
│   │   │   ├── MyApplications.tsx # Candidate applications list
│   │   │   ├── ApplicationProgress.tsx # Per-application: ATS badge, interview rounds
│   │   │   ├── InterviewRoom.tsx  # Written Q&A + Voice interview UI (WebRTC)
│   │   │   ├── InterviewStages.tsx# DEAD CODE — replaced by ApplicationProgress
│   │   │   ├── UserProfile.tsx    # Candidate + recruiter profile view/edit
│   │   │   └── RecruiterDashboard.tsx  # Recruiter: view jobs, post job
│   │   ├── components/
│   │   │   ├── JobApplyDialog.tsx # Apply-to-job modal (CV upload + submit)
│   │   │   ├── ApplicationCard.tsx# Application tile (status + navigate)
│   │   │   ├── JobCard.tsx        # Job listing tile
│   │   │   ├── UserMenu.tsx       # Auth-state dropdown (login/logout)
│   │   │   ├── BackButton.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── PageTransition.tsx # Framer Motion route wrapper (used in App.tsx)
│   │   │   ├── FilterPanel.tsx    # Job filter sidebar
│   │   │   ├── Button.tsx         # UI primitive
│   │   │   ├── Input.tsx          # UI primitive
│   │   │   ├── Select.tsx         # UI primitive
│   │   │   ├── CustomSelect.tsx   # Extended select variant
│   │   │   ├── Tag.tsx            # Skill/badge primitive
│   │   │   ├── Modal.tsx          # Modal primitive
│   │   │   └── DebugBreadcrumb.tsx
│   │   ├── api/
│   │   │   ├── auth.ts            # signup, signin, getProfile, getSignupMetadata
│   │   │   ├── jobs.ts            # getJobs, getJobDetail, postJob, getRecruiterJobs
│   │   │   ├── applications.ts    # applyToJob, runAts, getInterviewStages, getMyApplications
│   │   │   └── profile.ts         # fetchCandidateProfile, fetchRecruiterProfile, updateProfile
│   │   ├── css/
│   │   │   ├── tokens.css         # CSS custom properties (colors, spacing, radius, typography)
│   │   │   ├── index.css          # Global base styles
│   │   │   └── *.css              # One CSS file per page/component
│   │   ├── data/
│   │   │   ├── roles.ts           # Hardcoded role definitions for signup metadata
│   │   │   └── jobs.ts            # Demo job seed data
│   │   └── utils/                 # Static image assets (logo.png, bot1.png, bot2.png, backgrounds, screenshots, etc.)
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── CLAUDE.md                  # Frontend-specific design-system rules
│
├── demo-voice/                    # Isolated demo for LiveKit voice integration
│   ├── backend/                   # Standalone FastAPI app for voice demo
│   └── frontend/                  # Standalone React app for voice demo
│
├── README.md                      # Product overview, ERD, feature list
├── CLAUDE.md                      # Project-level Claude instructions
└── .vscode/
    └── launch.json                # Debug configurations
```

---

## Technology Stack

| Layer | Stack |
|---|---|
| Backend API | FastAPI (Python), SQLAlchemy ORM |
| Database | SQL Server (MSSQL via pyodbc / LocalDB) |
| LLM | OpenAI `gpt-4o-mini`, LangChain / LangGraph |
| Voice Interview | LiveKit (WebRTC), Deepgram (STT), ElevenLabs (TTS) |
| Frontend | React 18, TypeScript, Vite, React Router DOM |
| Frontend Styling | Plain CSS (design tokens — no Tailwind) |
| Package Managers | `uv` (Python), `npm` (Node.js) |

---

## Backend (`backend/app/`)

### Auth & Signup
| Feature | File | Key symbols |
|---|---|---|
| Candidate signup | `services/auth_service.py` | `signup_candidate` |
| Candidate signin | `services/auth_service.py` | `signin_candidate` |
| Recruiter signup / signin | `services/auth_service.py` | `signup_recruiter`, `signin_recruiter` |
| Candidate profile fetch | `services/auth_service.py` | `get_candidate_profile` |
| CV update on existing profile | `services/auth_service.py` | `update_candidate_cv` → calls `parse_and_store_cv` |
| Signup metadata (roles / skills / levels) | `services/auth_service.py` | `get_signup_metadata` |
| Auth HTTP endpoints | `api/endpoints/auth.py` | `POST /signup` (candidate), `POST /recruiter/signup`, `POST /signin` (candidate), `POST /recruiter/signin`, `GET /profile/candidate/{candidate_id}`, `GET /profile/recruiter/{recruiter_id}`, `GET /signup-metadata` |
| Auth Pydantic schemas | `schemas/auth.py` | `SignupResponse`, `SigninResponse`, `CandidateProfileResponse`, `RecruiterProfileResponse` |

### CV Parsing
| Feature | File | Key symbols |
|---|---|---|
| Full CV pipeline (save → parse → store) | `services/cv_parser_service.py` | `parse_and_store_cv(file_content, file_name, candidate_id) → dict` |
| LlamaParse PDF → markdown | `services/cv_parser_service.py` | `_llamaparse_to_markdown` |
| pypdf fallback parser | `services/cv_parser_service.py` | `_pypdf_to_text` |
| LLM structured extraction | `services/cv_parser_service.py` | `_llm_extract` |
| Uploaded CV files (disk) | `uploads/resumes/` | UUID-named files |

`parse_and_store_cv` returns: `{resume_id, file_url, parsed_text, bio, linkedin_url, current_location, total_experience_years, skills[{skill_id, proficiency_level, years_of_experience}]}`

### Applications & ATS
| Feature | File | Key symbols |
|---|---|---|
| Apply for job (CV optional) | `services/application_service.py` | `apply_to_job` — calls `parse_and_store_cv` if CV given, stores `resume_id` on Application |
| Auto-trigger ATS on apply | `api/endpoints/applications.py` | `apply` endpoint awaits `run_ats_for_application` after `apply_to_job` |
| Run ATS for an application | `services/application_service.py` | `run_ats_for_application` — fetches `parsed_text` from Resumes if `resume_id` exists |
| Get candidate applications list | `services/application_service.py` | `get_my_applications` |
| Interview stages fetch | `services/application_service.py` | `get_interview_stages` |
| Q&A fetch for completed round | `services/application_service.py` | `get_interview_questions(interview_id)` |
| Applications HTTP endpoints | `api/endpoints/applications.py` | `POST /apply`, `GET /my-applications`, `GET /ats-check`, `POST /{id}/run-ats`, `GET /{id}/interview-stages`, `GET /{id}/interviews/{interview_id}/questions` |
| Applications Pydantic schemas | `schemas/applications.py` | `ApplyResponse`, `ATSCheckResponse`, `InterviewStagesResponse`, `InterviewQuestionItem`, `MyApplicationItem` |

### ATS LLM Service
| Feature | File | Key symbols |
|---|---|---|
| ATS eligibility LLM call | `ai/ai_services/ats_service.py` | `check_ats_eligibility(candidate_id, job_posting_id, parsed_text=None)` |
| Uses `parsed_text` when available | `ai/ai_services/ats_service.py` | passes CV markdown to LLM instead of profile/skills query |
| Falls back to DB profile + skills | `ai/ai_services/ats_service.py` | queries `CandidateProfiles`, `CandidateSkills` when `parsed_text` is None |

### Jobs
| Feature | File | Key symbols |
|---|---|---|
| Job listings / filtering | `services/job_service.py` | `get_job_postings` |
| Job detail | `services/job_service.py` | `get_job_detail` |
| Post a new job (recruiter) | `services/job_service.py` | `post_job` |
| Recruiter's own jobs | `services/job_service.py` | `list_recruiter_jobs` |
| Jobs HTTP endpoints | `api/endpoints/jobs.py` | `GET /`, `GET /{id}`, `POST /` (recruiter), `GET /mine?recruiter_id=`, `GET /round-types`, `GET /{job_id}/rounds` |
| Jobs Pydantic schemas | `schemas/jobs.py` | `JobListItem`, `JobDetailResponse`, `JobPostRequest`, `JobPostResponse` |

### Interviews (Written Q&A)
`Interviews` column semantics: `status` = `Scheduled`/`In Progress`/`Pass`/`Failed`; `result` = FLOAT score (0–10); `feedback` = AI-generated text.

| Feature | File | Key symbols |
|---|---|---|
| Interview context + existing questions | `services/interview_service.py` | `get_interview_context`, `get_interview_questions` |
| Generate questions (LLM + store) | `services/interview_service.py` | `generate_interview_questions` |
| Score answers (LLM + store + set Pass/Fail) | `services/interview_service.py` | `score_interview_answers` — sets `status`, `result`, `feedback` |
| Bulk-save voice answers | `services/interview_service.py` | `save_voice_answers_bulk` |
| Validate interview (Pass/Fail threshold logic) | `services/interview_validator.py` | `validate_interview` |
| Interviews HTTP endpoints | `api/endpoints/interviews.py` | `POST /{id}/generate-questions`, `POST /{id}/score-answers`, `POST /{id}/voice-interview`, `POST /{id}/report-leave`, `GET /{id}/status-stream` (SSE) |
| Interviews Pydantic schemas | `schemas/interviews.py` | `QuestionItem`, `GenerateQuestionsRequest/Response`, `AnswerItem`, `ScoreAnswersRequest/Response`, `GradedAnswer` |

### Interview AI Tools & Services
| Feature | File | Key symbols |
|---|---|---|
| LangGraph tool wrappers | `ai/interview_tools/tools.py` | `generate_questions_tool`, `score_answers_tool` |
| Tool I/O schemas | `ai/interview_tools/schemas.py` | `AnswerItem`, `GradedAnswers` |
| LLM prompts | `ai/interview_tools/prompts.py` | `GENERATE_QUESTIONS_SYSTEM_PROMPT`, `GRADE_ANSWERS_SYSTEM_PROMPT` |
| Agent graph state | `ai/interview_tools/state.py` | `AgentState` |
| Question generation LLM call | `ai/ai_services/question_generation_service.py` | `generate_questions(...)` |
| Answer grading LLM call | `ai/ai_services/answer_scoring_service.py` | `grade_candidate_answers(...)` |
| CV relevance context fetch | `ai/ai_services/cv_relevance_service.py` | `fetch_candidate_cv_relevance(...)` |
| Interview context + question bank | `ai/ai_services/question_bank_service.py` | `fetch_interview_context`, `fetch_questions_from_db` |

### Voice Agent (Interview)
| Feature | File | Key symbols |
|---|---|---|
| LiveKit voice agent logic | `ai/voice_agent/agent.py` | system prompt, question-asking loop, follow-up, cheating detection |
| LiveKit room creation + token | `ai/voice_agent/room_connection.py` | `conduct_voice_interview`, `CreateRoomResponse` |
| STT (Deepgram) | `ai/voice_agent/agent.py` | DeepgramSTT plugin |
| TTS (ElevenLabs) | `ai/voice_agent/agent.py` | ElevenLabsTTS plugin |
| Done signal / poll | `api/endpoints/interviews.py` | `GET /{id}/status-stream` (SSE) |

### Infrastructure
| Feature | File |
|---|---|
| DB connection (`pyodbc` SQL Server LocalDB) | `app/database/session.py` |
| LLM config (`get_llm()` → LangChain ChatOpenAI) | `app/core/config.py` |
| FastAPI app entry + router registration | `app/main.py` |
| API router aggregation | `app/api/router.py` |
| Environment variables | `backend/.env` / `backend/.env.example` |
| Dependencies | `backend/pyproject.toml` |

---

## Standalone AI Service (`ai/`)

This is a separate Python package mirroring the interview logic for standalone use or testing outside the main backend. Run via `ai/app.py`. The backend `backend/app/ai/` is what runs in production — both share the same logical structure.

| Feature | File | Notes |
|---|---|---|
| Entry point | `ai/app.py` | Standalone FastAPI/script runner |
| Interview agent orchestration | `ai/agents/interview_agent/agent.py` | generate → score → validate flow |
| Agent state | `ai/agents/interview_agent/state.py` | `AgentState` |
| Tool functions | `ai/agents/interview_agent/tools.py` | `generate_questions_tool`, `score_answers_tool`, `validate_tool` |
| Tool schemas | `ai/agents/interview_agent/schemas.py` | |
| Data models | `ai/agents/interview_agent/models.py` | |
| Prompts | `ai/agents/interview_agent/prompts.py` | |
| Voice agent scaffold | `ai/agents/interview_agent/voice_agent/` | Agent body mostly empty; tools/schemas/models in place (`agent.py`, `tools.py`, `schemas.py`, `models.py`, `prompt.py`) |
| LangGraph definition | `ai/graph/graph.py` | |
| Shared AI services | `ai/ai_services/` | Mirrors `backend/app/ai/ai_services/` |

---

## Frontend (`frontend/src/`)

### Pages
| Page | File | Route |
|---|---|---|
| Landing | `pages/Home.tsx` + `css/Home.css` | `/` |
| Sign up / Sign in | `pages/Auth.tsx` + `css/Auth.css` | `/auth` |
| Jobs listing | `pages/Jobs.tsx` + `css/Jobs.css` | `/jobs` |
| My applications | `pages/MyApplications.tsx` + `css/MyApplications.css` | `/my-applications` |
| Application progress (ATS + interview rounds) | `pages/ApplicationProgress.tsx` + `css/ApplicationProgress.css` | `/application-progress/:applicationId` |
| Interview room (written Q&A + voice) | `pages/InterviewRoom.tsx` + `css/InterviewRoom.css` | `/interview-room/:interviewId` |
| User profile (candidate + recruiter) | `pages/UserProfile.tsx` + `css/UserProfile.css` | `/profile` |
| Recruiter dashboard (jobs list + post job) | `pages/RecruiterDashboard.tsx` + `css/RecruiterDashboard.css` | `/recruiter-dashboard` |

> `pages/InterviewStages.tsx` — **dead code**, replaced by `ApplicationProgress`. Safe to delete.

### Components
| Component | File | Used in |
|---|---|---|
| Job apply dialog (CV upload + submit) | `components/JobApplyDialog.tsx` | Jobs page |
| Application card (status + navigate) | `components/ApplicationCard.tsx` | MyApplications page |
| Job card (listing tile) | `components/JobCard.tsx` | Jobs page |
| User menu (auth state, logout) | `components/UserMenu.tsx` | Global — App.tsx |
| Back button | `components/BackButton.tsx` | Multiple pages |
| Page header | `components/Header.tsx` | Multiple pages |
| Page transition (Framer Motion) | `components/PageTransition.tsx` | App.tsx wraps every route |
| Filter panel (job filters sidebar) | `components/FilterPanel.tsx` | Jobs page |
| Button | `components/Button.tsx` | UI primitive |
| Input | `components/Input.tsx` | UI primitive |
| Select / CustomSelect | `components/Select.tsx`, `components/CustomSelect.tsx` | UI primitives |
| Tag | `components/Tag.tsx` | UI primitive (skills, badges) |
| Modal | `components/Modal.tsx` | UI primitive |

### API Client (`frontend/src/api/`)
| Feature | File | Key functions |
|---|---|---|
| Auth | `api/auth.ts` | `signup` (candidate), `signupRecruiter`, `signin` (candidate), `signinRecruiter`, `getProfile`, `getSignupMetadata` |
| Jobs | `api/jobs.ts` | `getJobs`, `getJobDetail`, `postJob`, `getRecruiterJobs`, `fetchInterviewRoundTypes`, `fetchJobRounds` |
| Applications | `api/applications.ts` | `applyToJob`, `runAts`, `getInterviewStages`, `getMyApplications` |
| Profile | `api/profile.ts` | `fetchCandidateProfile`, `fetchRecruiterProfile`, `updateProfile` |

### Design System
| Resource | File |
|---|---|
| CSS tokens (colors, spacing, radius) | `css/tokens.css` |
| Full design spec | `.claude/frontend-theme.md` |
| Quick component rules | `frontend/CLAUDE.md` |

---

## Schema & Agent References

| Resource | File |
|---|---|
| Full DB schema (18 tables, DDL, FKs) | `.claude/database-schema.md` |
| Interview agent pipeline + tool I/O schemas | `.claude/agent-architecture.md` |
| Product overview + ERD | `README.md` |

---

## Key Data Flows

**Candidate signup with CV:**
`POST /auth/signup` → `signup_candidate` → `parse_and_store_cv` → INSERT Resumes → INSERT Users + CandidateProfiles + CandidateSkills

**Apply for job with CV:**
`POST /applications/apply` → `apply_to_job` → `parse_and_store_cv` → INSERT Resumes → INSERT Applications (with `resume_id`) → auto `run_ats_for_application` → `check_ats_eligibility(parsed_text=...)` → UPDATE Applications.status

**Apply for job without CV:**
`POST /applications/apply` → `apply_to_job` → INSERT Applications (resume_id NULL) → auto `run_ats_for_application` → `check_ats_eligibility` queries `CandidateProfiles` + `CandidateSkills` → UPDATE Applications.status

**Recruiter posts a job:**
`POST /jobs` → `post_job` → INSERT JobPostings + JobRequiredSkills → return `JobPostResponse`

**Written interview (full round):**
`POST /interviews/{id}/generate-questions` → `generate_interview_questions` → LLM → store Questions + InterviewQuestions
→ candidate answers in `InterviewRoom.tsx`
→ `POST /interviews/{id}/score-answers` → `score_interview_answers` → LLM grades → UPDATE InterviewQuestions.score + set `status`/`result`/`feedback` on Interview
→ `interview_validator.py` determines Pass/Fail threshold

**Voice interview (full round):**
`POST /interviews/{id}/voice-interview`
→ `room_connection.py` creates LiveKit room, returns room token
→ `InterviewRoom.tsx` connects via `livekit-client` SDK (WebRTC)
→ `voice_agent/agent.py` joins room (server-side), uses Deepgram STT + OpenAI LLM + ElevenLabs TTS
→ agent asks stored questions, listens, checks for cheating, generates follow-ups
→ transcript collected → `save_voice_answers_bulk`
→ `POST /interviews/{id}/score-answers` → LLM scores → Pass/Fail stored
→ frontend polls `GET /{id}/status-stream` (SSE) and renders results
