# Russel-AI Code Structure

Quick reference for navigating features to files. Use this before reading code — look up the feature, go straight to the file.

---

## Directory Tree

```
Russel-AI/
├── .claude/
│   ├── agent-architecture.md      # Interview pipeline agent flow & tool I/O schemas
│   ├── code-structure.md          # This file
│   ├── database-schema.md         # Table-by-table DB schema, DDL, FKs
│   └── frontend-theme.md          # Design system: tokens, components, animation catalogue
│
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI app init, CORS, router registration
│   │   ├── api/
│   │   │   ├── router.py          # Aggregates all endpoint routers
│   │   │   └── endpoints/
│   │   │       ├── auth.py        # /auth: signup, signin, profile, metadata
│   │   │       ├── applications.py# /applications: apply, ATS, stages, Q&A, my-applications
│   │   │       ├── interviews.py  # /interviews: generate-questions, score-answers, voice-interview, report-leave, status-stream
│   │   │       ├── jobs.py        # /jobs: list, post, mine, round-types, rounds, stats, round candidates, candidate panel, interview-qa
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
│   │   │   ├── jobs.py            # Job posting, multi-round config, job-stats analytics schemas
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
│   │   │       ├── agent.py       # LiveKit + STT/TTS voice agent (question loop, follow-ups, cheating detection)
│   │   │       ├── room_connection.py # Room creation, conduct_voice_interview, status-stream signaling
│   │   │       ├── whisper_stt.py # OpenRouter Whisper STT adapter — secondary/fallback engine
│   │   │       └── test_room_connection.py
│   │   ├── core/
│   │   │   ├── config.py          # Settings: DB URL, OpenAI key, LiveKit, Deepgram, ElevenLabs, OpenRouter/Whisper
│   │   │   └── logging.py
│   │   └── database/
│   │       └── session.py         # pyodbc connection (SQL Server / LocalDB)
│   ├── uploads/
│   │   └── resumes/               # Uploaded CV files (UUID-named)
│   ├── tests/                     # pytest suite — run: cd backend && uv run pytest
│   │   ├── test_recruiter_dashboard.py   # Job posting, multi-round config, recruiter job listing
│   │   ├── test_ats_flow.py              # ATS eligibility + Applications.status transitions
│   │   ├── test_cv_and_apply.py          # CV parsing + apply_to_job flow
│   │   ├── test_round_cascade.py         # Not Needed / HIRED cascade logic on round completion
│   │   ├── test_test_mode_question_cache.py # test_mode in-memory question cache (no DB writes)
│   │   ├── test_test_mode_isolation.py   # test_mode never pollutes real DB rows
│   │   ├── test_save_voice_answers_bulk.py
│   │   ├── test_question_generator_flow.py
│   │   ├── test_agent_behavior.py
│   │   ├── test_voice_pipeline.py
│   │   ├── test_elevenlabs_pipeline.py
│   │   ├── test_stt_engine_selection.py  # Deepgram vs Whisper fallback selection
│   │   ├── test_whisper_stt.py
│   │   ├── resumes/ / generated_resumes/ # Test resume fixtures + generator script
│   │   └── generate_resumes.py
│   ├── pyproject.toml             # uv project config + dependencies
│   └── .env.example
│
├── ai/                            # Standalone AI service (separate from backend/app/ai)
│   ├── app.py                     # Standalone entry point
│   ├── agents/interview_agent/    # Mirrors backend/app/ai logic for standalone use/testing
│   ├── ai_services/                # Mirrors backend/app/ai/ai_services
│   ├── graph/                     # LangGraph agent definition
│   ├── pyproject.toml
│   └── test_db.py
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # React Router setup, global route tree
│   │   ├── main.tsx                # Vite entry point
│   │   ├── pages/
│   │   │   ├── Home.tsx                  # Landing page
│   │   │   ├── Auth.tsx                  # Signup / Signin (candidate + recruiter, CV upload)
│   │   │   ├── Jobs.tsx                  # Candidate job listing + filters + apply dialog
│   │   │   ├── MyApplications.tsx        # Candidate applications list
│   │   │   ├── ApplicationProgress.tsx   # Per-application: ATS badge, interview round timeline, Q&A
│   │   │   ├── InterviewRoom.tsx         # Written Q&A + Voice interview UI (WebRTC)
│   │   │   ├── RecruiterDashboard.tsx    # Recruiter: job list, post job w/ multi-round config
│   │   │   ├── JobPostStats.tsx          # Recruiter: per-job analytics — rounds, candidates, candidate detail panel
│   │   │   ├── UserProfile.tsx           # Candidate + recruiter profile view/edit
│   │   │   └── InterviewStages.tsx       # DEAD CODE — replaced by ApplicationProgress
│   │   ├── components/
│   │   │   ├── JobApplyDialog.tsx # Apply-to-job modal (CV upload + submit)
│   │   │   ├── ApplicationCard.tsx# Application tile — status label/variant incl. HIRED/REJECTED
│   │   │   ├── JobCard.tsx        # Job listing tile
│   │   │   ├── UserMenu.tsx       # Auth-state dropdown (login/logout), role-aware nav
│   │   │   ├── DebugBreadcrumb.tsx# Floating "{ }" panel — recruiter_id+job_post_id or candidate_id+application_id+interview_id+job_post_id, switches by sessionStorage userType
│   │   │   ├── BackButton.tsx
│   │   │   ├── Header.tsx
│   │   │   ├── PageTransition.tsx # Framer Motion route wrapper (used in App.tsx)
│   │   │   ├── FilterPanel.tsx    # Job filter sidebar
│   │   │   ├── Button.tsx         # UI primitive
│   │   │   ├── Input.tsx          # UI primitive
│   │   │   ├── Select.tsx         # UI primitive
│   │   │   ├── CustomSelect.tsx   # Extended select variant
│   │   │   ├── Tag.tsx            # Skill/badge primitive
│   │   │   └── Modal.tsx          # Modal primitive
│   │   ├── api/
│   │   │   ├── auth.ts            # signup, signin, getProfile, getSignupMetadata
│   │   │   ├── jobs.ts            # getJobs, postJob, getRecruiterJobs, fetchInterviewRoundTypes, fetchJobRounds, fetchJobStats, fetchRoundCandidates, fetchCandidatePanel, fetchInterviewQA
│   │   │   ├── applications.ts    # applyToJob, runAts, getInterviewStages, getMyApplications
│   │   │   └── profile.ts         # fetchCandidateProfile, fetchRecruiterProfile, updateProfile
│   │   ├── css/
│   │   │   ├── tokens.css         # CSS custom properties (colors, spacing, radius, typography)
│   │   │   ├── index.css          # Global base styles
│   │   │   └── *.css              # One CSS file per page/component (incl. JobPostStats.css)
│   │   ├── data/                  # Hardcoded signup metadata / demo seed data
│   │   └── utils/                 # Static image assets
│   ├── tests/
│   │   └── application-progress.spec.ts  # Playwright e2e spec
│   ├── playwright.config.ts
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
| Backend API | FastAPI (Python), `pyodbc` (raw SQL — no ORM) |
| Database | SQL Server (MSSQL via pyodbc / LocalDB) |
| LLM | OpenAI `gpt-4o-mini`, LangChain / LangGraph |
| Voice Interview | LiveKit (WebRTC), Deepgram nova-3 (primary STT), OpenRouter Whisper (fallback STT), ElevenLabs (TTS) |
| Frontend | React 18, TypeScript, Vite, React Router DOM |
| Frontend Styling | Plain CSS (design tokens — no Tailwind) |
| Testing | pytest (backend, `backend/tests/`), Playwright (frontend e2e, `frontend/tests/`) |
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
| Auth HTTP endpoints | `api/endpoints/auth.py` | `POST /signup`, `POST /recruiter/signup`, `POST /signin`, `POST /recruiter/signin`, `GET /profile/candidate/{id}`, `GET /profile/recruiter/{id}`, `GET /signup-metadata` |

### CV Parsing
| Feature | File | Key symbols |
|---|---|---|
| Full CV pipeline (save → parse → store) | `services/cv_parser_service.py` | `parse_and_store_cv(file_content, file_name, candidate_id) → dict` |
| LlamaParse PDF → markdown | `services/cv_parser_service.py` | `_llamaparse_to_markdown` |
| pypdf fallback parser | `services/cv_parser_service.py` | `_pypdf_to_text` |
| LLM structured extraction | `services/cv_parser_service.py` | `_llm_extract` |
| Uploaded CV files (disk) | `uploads/resumes/` | UUID-named files |

`parse_and_store_cv` returns: `{resume_id, file_url, parsed_text, bio, linkedin_url, current_location, total_experience_years, skills[{skill_id, proficiency_level, years_of_experience}]}`

### Applications, ATS & Hiring State Machine
`Applications.status` flow: `ATS_PENDING` → `ATS_PASS` / `ATS_FAIL` → (interviews proceed) → `HIRED` (auto-set when last active round is Passed) / `REJECTED` (never auto-set currently — see Known Gaps).

| Feature | File | Key symbols |
|---|---|---|
| Apply for job (CV optional) | `services/application_service.py` | `apply_to_job` — creates one `Interviews` row per active round upfront, calls `parse_and_store_cv` if CV given |
| Job expiry check on apply | `services/application_service.py` | `apply_to_job` — `CAST(expires_at AS DATE) >= CAST(GETDATE() AS DATE)`, matches `/jobs` listing semantics (job stays applyable through its whole expiry day) |
| Auto-trigger ATS on apply | `api/endpoints/applications.py` | `apply` endpoint awaits `run_ats_for_application` after `apply_to_job` |
| Run ATS for an application | `services/application_service.py` | `run_ats_for_application` — fetches `parsed_text` from Resumes if `resume_id` exists |
| Candidate-facing status derivation | `services/application_service.py` | `_derive_status(app_status, latest_interview_status, has_failed_round)` — checks `HIRED`/`REJECTED`/`ATS_FAIL`/`ATS_PENDING` first, then falls back to interview-round-derived status (`INTERVIEW_PASS`/`INTERVIEW_FAILED`/`IN_PROGRESS`) |
| Get candidate applications list | `services/application_service.py` | `get_my_applications` |
| Interview stages fetch (per-application round timeline) | `services/application_service.py` | `get_interview_stages` — `current_round_id` = first round in `ACTIVE_STATUSES` (`Scheduled`/`In Progress`); naturally skips `Not Needed` rounds |
| Q&A fetch for completed round | `services/application_service.py` | `get_interview_questions(interview_id)` |
| Applications HTTP endpoints | `api/endpoints/applications.py` | `POST /apply`, `GET /ats-check`, `GET /my-applications`, `POST /{id}/run-ats`, `GET /{id}/interview-stages`, `GET /{id}/interviews/{interview_id}/questions` |

### ATS LLM Service
| Feature | File | Key symbols |
|---|---|---|
| ATS eligibility LLM call | `ai/ai_services/ats_service.py` | `check_ats_eligibility(candidate_id, job_posting_id, parsed_text=None)` |
| Uses `parsed_text` when available | `ai/ai_services/ats_service.py` | passes CV markdown to LLM instead of profile/skills query |
| Falls back to DB profile + skills | `ai/ai_services/ats_service.py` | queries `CandidateProfiles`, `CandidateSkills` when `parsed_text` is None |

### Jobs (Listing, Posting, Multi-Round Config)
| Feature | File | Key symbols |
|---|---|---|
| Candidate job listing (active + non-expired only) | `services/job_service.py` | `list_jobs` — filters `status='active'` and `CAST(expires_at AS DATE) >= CAST(GETDATE() AS DATE)` |
| Recruiter's own jobs (all statuses) | `services/job_service.py` | `list_recruiter_jobs` |
| Post a new job with multi-round interview config | `services/job_service.py` | `post_job` — inserts `JobPostings`, `JobRequiredSkills`, and one `InterviewRounds` row per configured round (`round_order`, `failing_criteria`, `round_type_id`) |
| Interview round types catalogue | `services/job_service.py` | `list_interview_round_types` |
| Rounds configured for a job | `services/job_service.py` | `get_job_rounds` |
| Jobs HTTP endpoints | `api/endpoints/jobs.py` | `GET ""` (list, filtered), `POST ""` (recruiter post), `GET /mine?recruiter_id=`, `GET /round-types`, `GET /{job_id}/rounds` |
| Jobs Pydantic schemas | `schemas/jobs.py` | `JobListItem`, `JobPostRequest`, `JobPostResponse`, `InterviewRoundInput`, `JobInterviewRoundItem`, `InterviewRoundTypeItem` |

### Recruiter Job Analytics (`/job-stats` page backend)
| Feature | File | Key symbols |
|---|---|---|
| Job-level stats (rounds, applicant counts, hired count) | `services/job_service.py` | `get_job_stats` — `hired_count` = `COUNT(*) FROM Applications WHERE status='HIRED'` |
| Candidates in a given round (with their per-round interview status) | `services/job_service.py` | `get_round_candidates(job_id, round_order)` — reads `Interviews.status` directly, so `Not Needed` candidates show correctly once a prior round fails |
| Candidate detail panel (profile + full round progress + Q&A) | `services/job_service.py` | `get_candidate_panel(application_id, interview_id)` |
| Q&A for one interview (recruiter view) | `services/job_service.py` | `get_interview_qa(interview_id)` |
| Job-stats HTTP endpoints | `api/endpoints/jobs.py` | `GET /{job_id}/stats`, `GET /{job_id}/rounds/{round_order}/candidates`, `GET /{job_id}/candidate-panel/{application_id}?interview_id=`, `GET /interview-qa/{interview_id}` |
| Job-stats Pydantic schemas | `schemas/jobs.py` | `JobStatsResponse`, `JobStatsRound`, `RoundCandidateItem`, `CandidatePanelResponse`, `CandidateInfo`, `CandidateSkillItem`, `InterviewProgressItem`, `EvaluationQuestionItem` |

> `get_candidate_panel` does **not** currently surface `Applications.status` (e.g. `HIRED`) — candidate rows/panel badges show raw `Interviews.status` (`Pass`/`Failed`/`Not Needed`/etc.) only. The aggregate "Total Selected" count on the page is the only place `HIRED` is reflected. See Known Gaps.

### Interviews (Written Q&A + Round Completion Cascades)
`Interviews.status` = `Scheduled` / `In Progress` / `Pass` / `Failed` / `Not Needed`; `result` = FLOAT score (0–10); `feedback` = AI-generated text.

| Feature | File | Key symbols |
|---|---|---|
| Interview context + existing questions | `services/interview_service.py` | `get_interview_context`, `get_interview_questions` |
| Generate questions (LLM + store) | `services/interview_service.py` | `generate_interview_questions` — blocks restart if status already `Pass`/`Failed`/`Not Needed` |
| Score answers (LLM + store + set Pass/Fail) | `services/interview_service.py` | `score_interview_answers` → `_save_scores_and_complete` sets `status`/`result`/`feedback`, then cascades (see below) |
| **Cascade: Failed → later rounds `Not Needed`** | `services/interview_service.py` | `_mark_subsequent_rounds_not_needed` — on `Failed`, flips later still-`Scheduled` rounds (same application, higher `round_order`, active) to `Not Needed` so the candidate doesn't appear to progress |
| **Cascade: Pass on last round → `HIRED`** | `services/interview_service.py` | `_maybe_mark_hired` — on `Pass`, if no later *active* round exists for that job, sets `Applications.status = 'HIRED'` |
| Cheating termination | `services/interview_service.py` | `mark_interview_terminated` — runs through validator, also triggers the `Not Needed` cascade on `Failed` |
| Leave-mid-interview auto-fail | `services/interview_service.py` | `mark_interview_failed_on_leave` — same cascade behavior |
| Bulk-save voice answers | `services/interview_service.py` | `save_voice_answers_bulk` |
| test_mode in-memory question cache | `services/interview_service.py` | `_test_mode_questions` dict, `merge_test_mode_answers`, `clear_test_mode_cache` — test interviews never write `Questions`/`InterviewQuestions` rows |
| Validate interview (Pass/Fail threshold logic) | `services/interview_validator.py` | `validate_interview` |
| Interviews HTTP endpoints | `api/endpoints/interviews.py` | `POST /{id}/generate-questions`, `POST /{id}/score-answers`, `POST /{id}/voice-interview`, `POST /{id}/report-leave`, `GET /{id}/status-stream` (SSE) |

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
| STT engine selection | `ai/voice_agent/agent.py` | `_build_stt_engine` — Deepgram nova-3 if `DEEPGRAM_API_KEY` set (primary), else `OpenRouterWhisperSTT` wrapped in `StreamAdapter` with Silero VAD (fallback) |
| Whisper STT adapter (OpenRouter) | `ai/voice_agent/whisper_stt.py` | `OpenRouterWhisperSTT` — batch `_recognize_impl`, VAD-buffered utterances |
| LiveKit room creation + token | `ai/voice_agent/room_connection.py` | `conduct_voice_interview`, `CreateRoomResponse` |
| TTS (ElevenLabs) | `ai/voice_agent/agent.py` | ElevenLabsTTS plugin |
| Done signal / poll | `api/endpoints/interviews.py` | `GET /{id}/status-stream` (SSE), `signal_interview_done`/`wait_for_interview_done` in `room_connection.py` |

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

This is a separate Python package mirroring the interview logic for standalone use or testing outside the main backend. Run via `ai/app.py`. The backend `backend/app/ai/` is what runs in production — both share the same logical structure but `ai/` has not received the cascade/test_mode/Whisper updates made to `backend/app/ai/`.

| Feature | File | Notes |
|---|---|---|
| Entry point | `ai/app.py` | Standalone FastAPI/script runner |
| Interview agent orchestration | `ai/agents/interview_agent/agent.py` | generate → score → validate flow |
| Tool functions | `ai/agents/interview_agent/tools.py` | `generate_questions_tool`, `score_answers_tool`, `validate_tool` |
| Voice agent scaffold | `ai/agents/interview_agent/voice_agent/` | Agent body mostly empty; tools/schemas/models in place |
| LangGraph definition | `ai/graph/graph.py` | |
| Shared AI services | `ai/ai_services/` | Mirrors `backend/app/ai/ai_services/` |

---

## Frontend (`frontend/src/`)

### Pages
| Page | File | Route |
|---|---|---|
| Landing | `pages/Home.tsx` + `css/Home.css` | `/` |
| Sign up / Sign in | `pages/Auth.tsx` + `css/Auth.css` | `/auth` |
| Jobs listing (candidate) | `pages/Jobs.tsx` + `css/Jobs.css` | `/jobs` |
| My applications | `pages/MyApplications.tsx` + `css/MyApplications.css` | `/my-applications` |
| Application progress (ATS + interview round timeline) | `pages/ApplicationProgress.tsx` + `css/ApplicationProgress.css` | `/application-progress/:applicationId` |
| Interview room (written Q&A + voice) | `pages/InterviewRoom.tsx` + `css/InterviewRoom.css` | `/interview-room/:interviewId` |
| Recruiter dashboard (job list + post job, multi-round config) | `pages/RecruiterDashboard.tsx` + `css/RecruiterDashboard.css` | `/recruiter-dashboard` |
| Job post stats (recruiter analytics per job) | `pages/JobPostStats.tsx` + `css/JobPostStats.css` | `/job-stats/:jobId` |
| User profile (candidate + recruiter) | `pages/UserProfile.tsx` + `css/UserProfile.css` | `/profile` |

> `pages/InterviewStages.tsx` — **dead code**, replaced by `ApplicationProgress`. Safe to delete.

### Job Post Stats page (`JobPostStats.tsx`)
Recruiter-only analytics view for a single job posting.
- **Left pane**: job info card (role, status, round count, applicant/selected totals, scrollable description, required skills) — fixed height with margin so it never fills the full viewport.
- **Right pane**: collapsible list of interview rounds; expanding a round lazy-loads its candidates (`fetchRoundCandidates`) with a status badge per candidate (`Pass`/`Failed`/`Scheduled`/`In Progress`/`Not Needed`).
- **Candidate dialog**: clicking a candidate opens a panel (`fetchCandidatePanel`) showing round-by-round progress cards (click a completed round to load its Q&A via `fetchInterviewQA`) plus full candidate info/skills.
- Status badge styling helpers: `ivStatusClass`, `isCompleted` (`pass`/`failed` only — `Not Needed` is not clickable for Q&A).

### Application Progress page (`ApplicationProgress.tsx`)
Candidate-facing per-application view: ATS bubble → per-round bubbles with status badges (`Pending`/`In Progress`/`Passed`/`Failed`/`Not Needed`/`Not Started`), Q&A detail panel for completed rounds, test-mode toggle (`localStorage.russell_test_mode`) to jump between rounds during manual QA.

### Components
| Component | File | Used in |
|---|---|---|
| Job apply dialog (CV upload + submit) | `components/JobApplyDialog.tsx` | Jobs page |
| Application card (status label/variant incl. Hired/Rejected) | `components/ApplicationCard.tsx` | MyApplications page |
| Job card (listing tile) | `components/JobCard.tsx` | Jobs page |
| User menu (auth state, logout, role-aware nav) | `components/UserMenu.tsx` | Global — App.tsx |
| Debug IDs panel | `components/DebugBreadcrumb.tsx` | Global — App.tsx. Shows `recruiter_id` + `job_post_id` on recruiter pages, `candidate_id` + `application_id` + `interview_id` + `job_post_id` on candidate pages (switches on `sessionStorage.userType`) |
| Back button | `components/BackButton.tsx` | Multiple pages |
| Page header | `components/Header.tsx` | Multiple pages |
| Page transition (Framer Motion) | `components/PageTransition.tsx` | App.tsx wraps every route |
| Filter panel (job filters sidebar) | `components/FilterPanel.tsx` | Jobs page |
| Button / Input / Select / CustomSelect / Tag / Modal | `components/*.tsx` | UI primitives |

### API Client (`frontend/src/api/`)
| Feature | File | Key functions |
|---|---|---|
| Auth | `api/auth.ts` | `signup`, `signupRecruiter`, `signin`, `signinRecruiter`, `getProfile`, `getSignupMetadata` |
| Jobs | `api/jobs.ts` | `getJobs`, `postJob`, `getRecruiterJobs`, `fetchInterviewRoundTypes`, `fetchJobRounds`, `fetchJobStats`, `fetchRoundCandidates`, `fetchCandidatePanel`, `fetchInterviewQA` |
| Applications | `api/applications.ts` | `applyToJob`, `runAts`, `getInterviewStages`, `getMyApplications` |
| Profile | `api/profile.ts` | `fetchCandidateProfile`, `fetchRecruiterProfile`, `updateProfile` |

### Design System
| Resource | File |
|---|---|
| CSS tokens (colors, spacing, radius) | `css/tokens.css` |
| Full design spec | `.claude/frontend-theme.md` |
| Quick component rules | `frontend/CLAUDE.md` |

### Testing
| Layer | File(s) | Run |
|---|---|---|
| Backend unit/integration tests | `backend/tests/*.py` | `cd backend && uv run pytest` |
| Frontend e2e (Playwright) | `frontend/tests/application-progress.spec.ts`, `frontend/playwright.config.ts` | `cd frontend && npx playwright test` |

---

## Schema & Agent References

| Resource | File |
|---|---|
| Full DB schema (DDL, FKs) | `.claude/database-schema.md` |
| Interview agent pipeline + tool I/O schemas | `.claude/agent-architecture.md` |
| Product overview + ERD | `README.md` |

---

## Key Data Flows

**Candidate signup with CV:**
`POST /auth/signup` → `signup_candidate` → `parse_and_store_cv` → INSERT Resumes → INSERT Users + CandidateProfiles + CandidateSkills

**Recruiter posts a job with multi-round config:**
`POST /jobs` → `post_job` → INSERT JobPostings + JobRequiredSkills + one `InterviewRounds` row per configured round (`round_order`, `round_type_id`, `failing_criteria`) → return `JobPostResponse`

**Apply for job:**
`POST /applications/apply` → `apply_to_job` → (CV given) `parse_and_store_cv` → INSERT Applications (`status='ATS_PENDING'`) → INSERT one `Interviews` row per active round (`status='Scheduled'`) → auto `run_ats_for_application` → `check_ats_eligibility` → UPDATE `Applications.status` to `ATS_PASS`/`ATS_FAIL`

**Written interview (full round):**
`POST /interviews/{id}/generate-questions` → LLM → store Questions + InterviewQuestions → candidate answers in `InterviewRoom.tsx` → `POST /interviews/{id}/score-answers` → LLM grades → `interview_validator.py` determines Pass/Fail → `_save_scores_and_complete` sets `status`/`result`/`feedback` → **cascade**: `Failed` flips later rounds to `Not Needed`; `Pass` on the last active round flips `Applications.status` to `HIRED`.

**Voice interview (full round):** same scoring/cascade tail as above, fed by:
`POST /interviews/{id}/voice-interview` → `room_connection.py` creates LiveKit room → `InterviewRoom.tsx` connects via `livekit-client` (WebRTC) → `voice_agent/agent.py` joins server-side (Deepgram or Whisper STT + OpenAI LLM + ElevenLabs TTS), asks stored questions, detects cheating, generates follow-ups → transcript → `save_voice_answers_bulk` → `score-answers` as above → frontend polls `GET /{id}/status-stream` (SSE).

**Recruiter views job analytics:**
`/job-stats/:jobId` → `fetchJobStats` (`GET /jobs/{job_id}/stats`) for the summary card + round list → expand a round → `fetchRoundCandidates` (`GET /jobs/{job_id}/rounds/{round_order}/candidates`, reads live `Interviews.status` per candidate) → click a candidate → `fetchCandidatePanel` (`GET /jobs/{job_id}/candidate-panel/{application_id}?interview_id=`) → click a completed round card → `fetchInterviewQA` (`GET /jobs/interview-qa/{interview_id}`).

---

## Known Gaps / Follow-ups

- `Applications.status` is never auto-set to `REJECTED` on interview failure (intentionally — see `_derive_status`, which derives `INTERVIEW_FAILED` dynamically from interview round status instead, to avoid corrupting the `ats_status` field which also reads `_ATS_FAILED_STATUSES`).
- `HIRED` is only set going forward by `_maybe_mark_hired` on a fresh `Pass` scoring event — applications that already passed every round *before* this cascade was added are not retroactively updated.
- `get_candidate_panel` / `get_round_candidates` (recruiter `/job-stats` page) surface `Interviews.status`, not `Applications.status` — a hired candidate's last round still just shows `Pass`, not a `Hired` badge.
- `pages/InterviewStages.tsx` is dead code.
- `ai/` (standalone service) has not received the `Not Needed`/`HIRED` cascade, test_mode cache, or Whisper STT updates made to `backend/app/ai/` — the two trees have drifted.
