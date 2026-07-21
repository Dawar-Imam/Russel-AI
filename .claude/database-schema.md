# Russel-AI Database Schema (ERD)

Source of truth: [README.md](../README.md#database-schema). This file mirrors
that ERD for quick reference by both `ai/` and `backend/` — keep it in sync
if the schema changes.

21 tables across 8 domains:

| Domain | Tables |
|---|---|
| Auth & Roles | `Roles`, `Users` |
| Profiles | `RecruiterProfiles`, `CandidateProfiles` |
| Company | `Companies` |
| Jobs | `JobRoles`, `JobPostings`, `ExperienceLevels` |
| Applications | `Applications`, `Resumes` |
| Skills | `SkillSets`, `CandidateSkills`, `JobRequiredSkills`, `RoleSkills` |
| Interviews | `InterviewRoundTypes`, `InterviewRounds`, `Interviews`, `InterviewQuestions`, `DeletedInterviewRounds` |
| Questions | `Questions` |
| Audit | `ATSEvaluationHistory` |

## Tables

### Roles
| Column | Type |
|---|---|
| id | int PK |
| name | varchar |
| description | varchar |

### ExperienceLevels
| Column | Type |
|---|---|
| id | int PK |
| name | varchar |
| min_years | int |
| max_years | int |

### JobRoles
| Column | Type |
|---|---|
| id | int PK |
| title | varchar |
| category | varchar |
| is_active | bit |

### InterviewRoundTypes
| Column | Type |
|---|---|
| id | int PK |
| name | varchar |
| description | varchar |

### SkillSets
| Column | Type |
|---|---|
| id | int PK |
| name | varchar |
| category | varchar |
| is_active | bit |

### Companies
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| name | varchar |
| domain | varchar |
| website | varchar |
| industry | varchar |
| registration_number | varchar |
| verification_status | varchar |
| created_at | datetime2 |

### Users
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| email | varchar |
| password_hash | varchar |
| first_name | varchar |
| last_name | varchar |
| phone | varchar |
| role_id | int FK -> Roles |
| is_active | bit |
| is_verified | bit |
| created_at | datetime2 |
| updated_at | datetime2 |

### CandidateProfiles
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| user_id | uniqueidentifier FK -> Users |
| bio | nvarchar |
| resume_url | varchar |
| linkedin_url | varchar |
| experience_level_id | int FK -> ExperienceLevels |
| job_role_id | int FK -> JobRoles |
| current_location | varchar |
| open_to_work | bit |
| updated_at | datetime2 |

### CandidateSkills
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| candidate_id | uniqueidentifier FK -> CandidateProfiles |
| skill_id | int FK -> SkillSets |
| proficiency_level | varchar |
| years_of_experience | int |

### RecruiterProfiles
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| user_id | uniqueidentifier FK -> Users |
| company_id | uniqueidentifier FK -> Companies |
| designation | varchar |
| company_verified | bit |
| joined_at | datetime2 |

### JobPostings
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| recruiter_id | uniqueidentifier FK -> RecruiterProfiles |
| company_id | uniqueidentifier FK -> Companies |
| job_role_id | int FK -> JobRoles |
| experience_level_id | int FK -> ExperienceLevels |
| description | nvarchar |
| location | varchar |
| job_type | varchar |
| salary_range | varchar |
| status | varchar |
| posted_at | datetime2 |
| expires_at | datetime2 |
| ats_criteria_version | int NOT NULL DEFAULT 0 — bumped by 1 every time `ats_criteria`/`qualify_threshold`/`overqualify_threshold`/`auto_reject_overqualified` changes (see `job_service.update_job`). Compared against `Applications.ats_run_version` to decide whether a candidate's ATS result is stale. |

> **Migration required**: `ALTER TABLE JobPostings ADD ats_criteria_version INT NOT NULL CONSTRAINT DF_JobPostings_ats_criteria_version DEFAULT 0;`

### JobRequiredSkills
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| job_id | uniqueidentifier FK -> JobPostings |
| skill_id | int FK -> SkillSets |
| proficiency_level | varchar |
| is_mandatory | bit |

### RoleSkills
Typical/suggested skills per job role, used at signup time (skill picker
suggestions) and by `get_or_create_skill` — distinct from
`JobRequiredSkills`, which is per specific job posting.

| Column | Type |
|---|---|
| id | int PK |
| job_role_id | int FK -> JobRoles |
| skill_id | int FK -> SkillSets |

### Resumes
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| candidate_id | uniqueidentifier FK -> CandidateProfiles |
| file_url | varchar(500) |
| file_name | varchar(255) |
| parsed_text | nvarchar(MAX) NULL — JSON text extracted by CV parser |
| uploaded_at | datetime2 |

```sql
CREATE TABLE Resumes (
    id           uniqueidentifier PRIMARY KEY DEFAULT NEWID(),
    candidate_id uniqueidentifier NOT NULL REFERENCES CandidateProfiles(id),
    file_url     varchar(500)     NOT NULL,
    file_name    varchar(255)     NOT NULL,
    parsed_text  nvarchar(MAX)    NULL,
    uploaded_at  datetime2        NOT NULL DEFAULT SYSUTCDATETIME()
);
```

### Applications
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| job_id | uniqueidentifier FK -> JobPostings |
| candidate_id | uniqueidentifier FK -> CandidateProfiles |
| status | varchar(50) — `ATS_PENDING` → `ATS_PASS` / `ATS_FAIL` → `IN_PROGRESS` → `HIRED` / `REJECTED`; also `ATS_ERROR` (LLM output failed strict schema validation — never persisted, application stays retryable) |
| cover_letter | nvarchar(MAX) NULL |
| applied_at | datetime2 |
| ats_details | nvarchar(MAX) NULL — full weighted ATS JSON result (`ATSCheckResponse`): `verdict`, `verdict_summary`, `weightage`, `skill_matching`, `experience_matching`, `projects_matching`, `certifications_matching`, `education_matching`, `achievements_matching`, `additional_skills` |
| resume_id | uniqueidentifier FK -> Resumes NULL |
| ats_evaluated_at | datetime2 NULL — UTC timestamp of the ATS LLM run that produced `ats_details` |
| ats_model_version | varchar(100) NULL — LLM model identifier (`settings.OPENAI_MODEL`) used for that run |
| ats_rerun_count | int NOT NULL DEFAULT 0 — number of times a recruiter has explicitly re-run ATS for this application |
| ats_rerun_unseen | bit NOT NULL DEFAULT 0 — set true whenever a rerun result becomes visible to the candidate; cleared once the candidate's Application Progress page has shown/acked it |
| pending_ats_rerun_details | nvarchar(MAX) NULL — a computed-but-not-yet-applied rerun ATS result, held here when a PASS→FAIL rerun landed while an `Interviews` round was `In Progress` (see `application_service.apply_pending_ats_rerun`) |
| pending_ats_rerun_evaluated_at | datetime2 NULL — companion timestamp for `pending_ats_rerun_details` |
| pending_ats_rerun_model_version | varchar(100) NULL — companion model version for `pending_ats_rerun_details` |
| pending_ats_rerun_recruiter_id | uniqueidentifier NULL — recruiter who triggered the deferred rerun, carried through to `ATSEvaluationHistory.recruiter_id` once applied |
| ats_run_version | int NOT NULL DEFAULT 0 — snapshot of `JobPostings.ats_criteria_version` taken at the *start* of the ATS run that produced the current `ats_details` (not read fresh at the end); a candidate is stale and due for re-scoring whenever `ats_run_version < JobPostings.ats_criteria_version` |

> **Migrations required**:
> ```sql
> CREATE TABLE Resumes ( ... );   -- see above
> ALTER TABLE Applications ADD resume_id uniqueidentifier NULL REFERENCES Resumes(id);
> -- Legacy: ALTER TABLE Applications ADD ats_reason nvarchar(500) NULL;
> -- Legacy: ALTER TABLE Applications ADD ats_details nvarchar(500) NULL;
> -- ats_reason was later dropped: the ats_details column was dropped, then
> -- ats_reason was sp_rename'd to ats_details (inheriting its nvarchar(500)
> -- size), then widened: ALTER TABLE Applications ALTER COLUMN ats_details NVARCHAR(MAX) NULL;
> -- ats_details is now the single column, storing the full ATSCheckResponse JSON (see above).
> -- Rows written before the weighted-scoring rewrite still hold the old shape (`reason`,
> -- `role_assessment`, etc.) — the read path treats those as ats_result=None rather than
> -- migrating them in place.
> ALTER TABLE Applications ADD ats_evaluated_at datetime2 NULL;
> ALTER TABLE Applications ADD ats_model_version varchar(100) NULL;
> -- Recruiter-triggered ATS rerun (see application_service.py / job_service.py / ats_rerun_tasks.py):
> ALTER TABLE Applications ADD ats_rerun_count int NOT NULL CONSTRAINT DF_Applications_ats_rerun_count DEFAULT 0;
> ALTER TABLE Applications ADD ats_rerun_unseen bit NOT NULL CONSTRAINT DF_Applications_ats_rerun_unseen DEFAULT 0;
> ALTER TABLE Applications ADD pending_ats_rerun_details nvarchar(MAX) NULL;
> ALTER TABLE Applications ADD pending_ats_rerun_evaluated_at datetime2 NULL;
> ALTER TABLE Applications ADD pending_ats_rerun_model_version varchar(100) NULL;
> ALTER TABLE Applications ADD pending_ats_rerun_recruiter_id uniqueidentifier NULL REFERENCES RecruiterProfiles(id);
> -- ATS staleness versioning (see JobPostings.ats_criteria_version above):
> ALTER TABLE Applications ADD ats_run_version int NOT NULL CONSTRAINT DF_Applications_ats_run_version DEFAULT 0;
>
> CREATE TABLE ATSEvaluationHistory (
>     id                 uniqueidentifier PRIMARY KEY DEFAULT NEWID(),
>     application_id     uniqueidentifier NOT NULL REFERENCES Applications(id),
>     status             varchar(50)      NOT NULL,
>     ats_details        nvarchar(MAX)    NULL,
>     ats_evaluated_at   datetime2        NULL,
>     ats_model_version  varchar(100)     NULL,
>     triggered_by       varchar(20)      NOT NULL DEFAULT 'system',  -- 'system' | 'recruiter'
>     recruiter_id       uniqueidentifier NULL REFERENCES RecruiterProfiles(id),
>     created_at         datetime2        NOT NULL DEFAULT SYSUTCDATETIME()
> );
> ```
>
> `ATSEvaluationHistory` snapshots the *previous* `ats_details`/`status` right before a
> recruiter-triggered rerun overwrites them — it's what lets the candidate-facing rerun
> notice say "previously X, now Y" and gives recruiters an audit trail instead of only
> ever seeing the latest overwrite.

### InterviewRounds
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| job_posting_id | uniqueidentifier FK -> JobPostings |
| interview_round_type_id | int FK -> InterviewRoundTypes |
| round_order | int |
| description | varchar |
| failing_criteria | int NULL — pass threshold (0–100 %) set by recruiter |
| is_active | bit |
| time_limit_minutes | int NULL — written-test time limit for this round; falls back to `settings.INTERVIEW_DURATION_MINUTES` (default 10) when NULL |
| recent_generated_sets | nvarchar(MAX) NULL — **unused by current code.** Was briefly the DB-backed store for per-round question/option-order dedup history; that moved to a Redis list (`round_question_queue:<interview_round_id>`, see `question_order_service.py`) before this column was ever populated in production. Column still exists (harmless, always NULL) but nothing reads or writes it — safe to drop in a future cleanup. |

> **Migration required**: `ALTER TABLE InterviewRounds ADD failing_criteria INT NULL;`
> **Migration required**: `ALTER TABLE InterviewRounds ADD time_limit_minutes INT NULL;`

### Interviews
| Column | Type | Notes |
|---|---|---|
| id | uniqueidentifier PK | |
| interview_round_id | uniqueidentifier FK -> InterviewRounds | |
| application_id | uniqueidentifier FK -> Applications | |
| status | varchar | `Scheduled` / `In Progress` / `Pass` / `Failed` / `Not Needed` (auto-set on later rounds when an earlier round Fails) |
| scheduled_at | datetime2 | |
| started_at | datetime2 NULL | Set once, the first time status flips to 'In Progress' (COALESCE-guarded so a later refresh never overwrites it). Used to compute a refresh-safe remaining timer (`timer_seconds = limit - elapsed`) and to stop accepting new autosaved answers once the round's time limit + grace period has passed. |
| completed_at | datetime2 | |
| feedback | nvarchar | AI-generated text feedback about the round |
| result | varchar(50) | Final numeric score (0–10) stored as text; NULL until round is scored |

> **Migration required**: `ALTER TABLE Interviews ADD started_at DATETIME2 NULL;`

### Questions
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| interview_round_type_id | int FK -> InterviewRoundTypes |
| job_role_id | int FK -> JobRoles |
| experience_level_id | int FK -> ExperienceLevels |
| question_text | nvarchar |
| is_active | bit |
| created_at | datetime2 |
| ai_generated | bit |
| question_type | varchar(20) NULL — `mcq` \| `short_answer` \| `scenario`; NULL/blank treated as `short_answer` |
| options | nvarchar(MAX) NULL — MCQ only, JSON `{"choices": ["..."], "correct_option": "..."}`; NULL for non-MCQ |

> **Migration required**:
> ```sql
> ALTER TABLE Questions ADD question_type varchar(20) NULL;
> ALTER TABLE Questions ADD options nvarchar(MAX) NULL;
> ```
> `correct_option` (inside the `options` JSON) is never returned by
> `GET`/generate-questions API responses — `app/schemas/interviews.py`'s
> `QuestionItem.correct_option` is a server-side-only field
> (`Field(exclude=True)`) used only by the scoring path, so it can't leak to
> the candidate before they submit an answer.

### InterviewQuestions
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| interview_id | uniqueidentifier FK -> Interviews |
| question_id | uniqueidentifier FK -> Questions |
| candidate_answer | nvarchar |
| score | int |
| notes | nvarchar |

### DeletedInterviewRounds
Tombstone written immediately before an `Interviews` row (and its
`InterviewQuestions`) is deleted by a PASS→FAIL ATS rerun — see
`application_service._delete_non_in_progress_interviews` and
`_delete_all_interviews`. Exists because once the `Interviews` row is gone
there is no other way to resolve a stale `interview_id` back to its
`application_id`; `interview_service.get_interview_context` checks this table
to distinguish "deleted after a fail" (→ HTTP 410) from "questions not yet
generated for this round" (→ proceeds to generate, no tombstone exists).

| Column | Type |
|---|---|
| interview_id | uniqueidentifier PK — the deleted `Interviews.id` |
| application_id | uniqueidentifier FK -> Applications |
| interview_round_id | uniqueidentifier FK -> InterviewRounds |
| deleted_at | datetime2 NOT NULL DEFAULT SYSUTCDATETIME() |
| deleted_reason | varchar(50) NOT NULL |

> **Migration required**:
> ```sql
> CREATE TABLE DeletedInterviewRounds (
>     interview_id       uniqueidentifier PRIMARY KEY,
>     application_id     uniqueidentifier NOT NULL REFERENCES Applications(id),
>     interview_round_id uniqueidentifier NOT NULL REFERENCES InterviewRounds(id),
>     deleted_at          datetime2        NOT NULL DEFAULT SYSUTCDATETIME(),
>     deleted_reason      varchar(50)      NOT NULL
> );
> ```

## Relationships

- `Roles ||--o{ Users` — has
- `Users ||--o| CandidateProfiles` — has
- `Users ||--o| RecruiterProfiles` — has
- `ExperienceLevels ||--o{ CandidateProfiles` — level
- `JobRoles ||--o{ CandidateProfiles` — role
- `CandidateProfiles ||--o{ CandidateSkills` — has
- `SkillSets ||--o{ CandidateSkills` — ref
- `Companies ||--o{ RecruiterProfiles` — employs
- `Companies ||--o{ JobPostings` — posts
- `RecruiterProfiles ||--o{ JobPostings` — creates
- `JobRoles ||--o{ JobPostings` — role
- `ExperienceLevels ||--o{ JobPostings` — level
- `JobPostings ||--o{ JobRequiredSkills` — requires
- `SkillSets ||--o{ JobRequiredSkills` — ref
- `JobRoles ||--o{ RoleSkills` — typical skills for
- `SkillSets ||--o{ RoleSkills` — ref
- `CandidateProfiles ||--o{ Resumes` — uploads
- `JobPostings ||--o{ Applications` — receives
- `CandidateProfiles ||--o{ Applications` — submits
- `Resumes ||--o{ Applications` — attached to
- `JobPostings ||--o{ InterviewRounds` — has
- `InterviewRoundTypes ||--o{ InterviewRounds` — type
- `InterviewRounds ||--o{ Interviews` — has
- `Applications ||--o{ Interviews` — schedules
- `Interviews ||--o{ InterviewQuestions` — contains
- `Questions ||--o{ InterviewQuestions` — ref
- `InterviewRoundTypes ||--o{ Questions` — type
- `JobRoles ||--o{ Questions` — role
- `ExperienceLevels ||--o{ Questions` — level
- `Applications ||--o{ ATSEvaluationHistory` — audit trail
- `Applications ||--o{ DeletedInterviewRounds` — tombstones
- `InterviewRounds ||--o{ DeletedInterviewRounds` — tombstones

## Notes for `ai/` agents

The agent suite (`ai/agents/question_generator_agent`,
`answer_scorer_agent`, `validator_agent`, `voice_agent`) maps onto the
Interview/Questions domains:

- **question_generator_agent** → produces `Questions` (and links via
  `InterviewQuestions`) for a given `InterviewRound` / `JobPosting`, scoped by
  `Questions.interview_round_type_id`, `job_role_id`, and
  `experience_level_id`, and informed by the job's required skills
  (`JobRequiredSkills`).
- **answer_scorer_agent** → fills `InterviewQuestions.candidate_answer`,
  `score`, `notes`, rolling up into `Interviews.feedback` / `result`.
- **validator_agent** → cross-checks generated questions/scores against
  `InterviewRoundTypes`, `JobRoles`, `ExperienceLevels`, and skill
  requirements.
- **voice_agent** → drives the live `Interviews` session (status transitions,
  `scheduled_at` / `completed_at`).

Keep field names, FK directions, and types consistent with this schema
when writing Pydantic models, SQLAlchemy models, or agent I/O schemas.
