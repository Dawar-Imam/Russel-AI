# Russel-AI Code Structure

Quick reference for navigating features to files. Use this before reading code — look up the feature, go straight to the file.

---

## Backend (`backend/app/`)

### Auth & Signup
| Feature | File | Key symbols |
|---|---|---|
| Candidate signup | `services/auth_service.py` | `signup_candidate` |
| Candidate signin | `services/auth_service.py` | `signin_candidate` |
| Recruiter signup/signin | `services/auth_service.py` | `signup_recruiter`, `signin_recruiter` |
| Candidate profile fetch | `services/auth_service.py` | `get_candidate_profile` |
| CV update on existing profile | `services/auth_service.py` | `update_candidate_cv` → calls `parse_and_store_cv` |
| Signup metadata (roles/skills/levels) | `services/auth_service.py` | `get_signup_metadata` |
| Auth HTTP endpoints | `api/endpoints/auth.py` | `/signup`, `/signin`, `/profile` |
| Auth Pydantic schemas | `schemas/auth.py` | `SignupResponse`, `SigninResponse`, etc. |

### CV Parsing
| Feature | File | Key symbols |
|---|---|---|
| Full CV pipeline (save→parse→store) | `services/cv_parser_service.py` | `parse_and_store_cv(file_content, file_name, candidate_id) → dict` |
| LlamaParse PDF→markdown | `services/cv_parser_service.py` | `_llamaparse_to_markdown` |
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
| Interview stages fetch | `services/application_service.py` | `get_interview_stages` |
| Q&A fetch for completed round | `services/application_service.py` | `get_interview_questions(interview_id)` |
| Applications HTTP endpoints | `api/endpoints/applications.py` | `POST /apply`, `GET /ats-check`, `POST /{id}/run-ats`, `GET /{id}/interview-stages`, `GET /{id}/interviews/{interview_id}/questions` |
| Applications Pydantic schemas | `schemas/applications.py` | `ApplyResponse`, `ATSCheckResponse`, `InterviewStagesResponse`, `InterviewQuestionItem` |

### ATS LLM Service
| Feature | File | Key symbols |
|---|---|---|
| ATS eligibility LLM call | `ai/ai_services/ats_service.py` | `check_ats_eligibility(candidate_id, job_posting_id, parsed_text=None)` |
| Uses `parsed_text` when available | `ai/ai_services/ats_service.py` | passes CV markdown to LLM instead of profile/skills query |
| Falls back to DB profile+skills | `ai/ai_services/ats_service.py` | queries `CandidateProfiles`, `CandidateSkills` when `parsed_text` is None |

### Interviews

`Interviews` column semantics: `status` = `Scheduled`/`In Progress`/`Pass`/`Failed`; `result` = FLOAT numeric score (0–10); `feedback` = AI-generated text feedback.

| Feature | File | Key symbols |
|---|---|---|
| Interview context / existing questions fetch | `services/interview_service.py` | `get_interview_context`, `get_interview_questions` |
| Generate questions (LLM + store) | `services/interview_service.py` | `generate_interview_questions` |
| Score answers (LLM + store + complete) | `services/interview_service.py` | `score_interview_answers` — sets `status=Pass/Failed`, `result=float score`, `feedback=AI text` |
| Bulk save voice answers | `services/interview_service.py` | `save_voice_answers_bulk` |
| Interview HTTP endpoints | `api/endpoints/interviews.py` | `POST /{id}/generate-questions`, `POST /{id}/score-answers`, `POST /{id}/voice-interview`, `GET /{id}/status-stream` |
| Interview Pydantic schemas | `schemas/interviews.py` | `QuestionItem`, `GenerateQuestionsRequest/Response`, `AnswerItem`, `ScoreAnswersRequest/Response`, `GradedAnswer` |

### Interview AI Tools & Services
| Feature | File | Key symbols |
|---|---|---|
| LangGraph tool wrappers | `ai/interview_tools/tools.py` | `generate_questions_tool`, `score_answers_tool` |
| Tool I/O schemas | `ai/interview_tools/schemas.py` | `AnswerItem`, `GradedAnswers` |
| LLM prompts | `ai/interview_tools/prompts.py` | `GENERATE_QUESTIONS_SYSTEM_PROMPT`, `GRADE_ANSWERS_SYSTEM_PROMPT` |
| Agent graph state | `ai/interview_tools/state.py` | `AgentState` |
| Question generation LLM call | `ai/ai_services/question_generation_service.py` | generates questions via LLM |
| Answer grading LLM call | `ai/ai_services/answer_scoring_service.py` | `grade_candidate_answers` |
| CV relevance context fetch | `ai/ai_services/cv_relevance_service.py` | `fetch_candidate_cv_relevance` |
| Interview context + question bank | `ai/ai_services/question_bank_service.py` | `fetch_interview_context`, `fetch_questions_from_db` |

### Voice Agent
| Feature | File | Key symbols |
|---|---|---|
| LiveKit voice agent logic | `ai/voice_agent/agent.py` | real-time audio interview agent |
| LiveKit room creation | `ai/voice_agent/room_connection.py` | `CreateRoomResponse`, room token generation |

### Jobs
| Feature | File | Key symbols |
|---|---|---|
| Job listings / filtering | `services/job_service.py` | `get_job_postings` |
| Job detail | `services/job_service.py` | `get_job_detail` |
| Job HTTP endpoints | `api/endpoints/jobs.py` | `GET /jobs`, `GET /jobs/{id}` |
| Jobs Pydantic schemas | `schemas/jobs.py` | `JobListItem`, `JobDetailResponse` |

### Infrastructure
| Feature | File |
|---|---|
| DB connection (`pyodbc` SQL Server LocalDB) | `app/database/session.py` |
| LLM config (`get_llm()` → LangChain ChatOpenAI) | `app/core/config.py` |
| FastAPI app entry, router registration | `app/main.py` |
| API router aggregation | `app/api/router.py` |
| Environment variables | `backend/.env` / `backend/.env.example` |
| Dependencies | `backend/pyproject.toml` |

---

## Frontend (`frontend/src/`)

### Pages
| Page | File | Route |
|---|---|---|
| Home / landing | `pages/Home.tsx` + `css/Home.css` | `/` |
| Sign up / Sign in | `pages/Auth.tsx` + `css/Auth.css` | `/auth` |
| Jobs listing | `pages/Jobs.tsx` + `css/Jobs.css` | `/jobs` |
| My applications | `pages/MyApplications.tsx` + `css/MyApplications.css` | `/my-applications` |
| Application progress (interview stages) | `pages/ApplicationProgress.tsx` + `css/ApplicationProgress.css` | `/application-progress/:applicationId` |
| Interview room (written Q&A) | `pages/InterviewRoom.tsx` + `css/InterviewRoom.css` | `/interview-room/:interviewId` |
| User profile (candidate + recruiter views) | `pages/UserProfile.tsx` + `css/UserProfile.css` | `/profile` |
| Recruiter dashboard | `pages/RecruiterDashboard.tsx` + `css/RecruiterDashboard.css` | `/recruiter-dashboard` |

> `pages/InterviewStages.tsx` + `css/InterviewStages.css` — **dead code**, replaced by `ApplicationProgress`. Safe to delete.

### Components
| Component | File | Used in |
|---|---|---|
| Job apply dialog (CV upload, submit) | `components/JobApplyDialog.tsx` + `css/JobApplyDialog.css` | Jobs page |
| Application card (status + navigate) | `components/ApplicationCard.tsx` + `css/ApplicationCard.css` | MyApplications page |
| Job card (listing tile) | `components/JobCard.tsx` + `css/JobCard.css` | Jobs page |
| User menu (auth state, logout) | `components/UserMenu.tsx` + `css/UserMenu.css` | Global (App.tsx) |
| Back button | `components/BackButton.tsx` + `css/BackButton.css` | Various pages |
| Page header | `components/Header.tsx` + `css/Header.css` | Various pages |
| Page transition (Framer Motion) | `components/PageTransition.tsx` | App.tsx wraps every route |
| Button | `components/Button.tsx` + `css/Button.css` | UI primitive |
| Input | `components/Input.tsx` + `css/Input.css` | UI primitive |
| Select | `components/Select.tsx` + `css/Select.css` | UI primitive |
| Tag | `components/Tag.tsx` + `css/Tag.css` | UI primitive |
| Modal | `components/Modal.tsx` + `css/Modal.css` | UI primitive |

### API Client
| Feature | File | Key functions |
|---|---|---|
| Applications API calls | `api/applications.ts` | `applyToJob`, `runAts`, `getInterviewStages` |
| Auth API calls | `api/auth.ts` | `signup`, `signin`, `getProfile` |
| Jobs API calls | `api/jobs.ts` | `getJobs`, `getJobDetail` |
| Profile API calls | `api/profile.ts` | `fetchCandidateProfile`, `fetchRecruiterProfile` |

### Design System
| Resource | File |
|---|---|
| CSS tokens (colors, spacing, radius) | `css/tokens.css` |
| Full design spec | `.claude/frontend-theme.md` |
| Quick rules | `frontend/CLAUDE.md` |

---

## Schema & Agent References

| Resource | File |
|---|---|
| Full DB schema (all 18 tables, DDL, FKs) | `.claude/database-schema.md` |
| Interview agent pipeline + tool I/O schemas | `.claude/agent-architecture.md` |
| Project overview & ERD | `README.md` |

---

## Key Data Flows

**Signup with CV:**
`POST /auth/signup` → `signup_candidate` → `parse_and_store_cv` → INSERT Resumes → INSERT Users + CandidateProfiles + CandidateSkills

**Apply for job with CV:**
`POST /applications/apply` → `apply_to_job` → `parse_and_store_cv` → INSERT Resumes → INSERT Applications (with `resume_id`) → auto `run_ats_for_application` → `check_ats_eligibility(parsed_text=...)` → UPDATE Applications status

**Apply for job without CV:**
`POST /applications/apply` → `apply_to_job` → INSERT Applications (resume_id NULL) → auto `run_ats_for_application` → `check_ats_eligibility` queries `CandidateProfiles` + `CandidateSkills` → UPDATE Applications status

**Written interview:**
`POST /interviews/{id}/generate-questions` → `generate_interview_questions` → LLM → store Questions + InterviewQuestions → candidate answers in `/interview-room/:id` → `POST /interviews/{id}/score-answers` → `score_interview_answers` → LLM grades → UPDATE InterviewQuestions.score + complete interview

**Voice interview:**
`POST /interviews/{id}/voice-interview` → LiveKit room created → `ai/voice_agent/agent.py` joins room → real-time audio Q&A → `save_voice_answers_bulk` → `POST /interviews/{id}/score-answers`
