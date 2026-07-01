# Russel-AI Database Schema (ERD)

Source of truth: [README.md](../README.md#database-schema). This file mirrors
that ERD for quick reference by both `ai/` and `backend/` — keep it in sync
if the schema changes.

18 tables across 8 domains:

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

### JobRequiredSkills
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| job_id | uniqueidentifier FK -> JobPostings |
| skill_id | int FK -> SkillSets |
| proficiency_level | varchar |
| is_mandatory | bit |

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
| resume_id | uniqueidentifier FK -> Resumes NULL |
| status | varchar — `ATS_PENDING` → `ATS_PASS` / `ATS_FAIL` → `IN_PROGRESS` → `HIRED` / `REJECTED` |
| ats_reason | nvarchar(500) NULL — LLM-produced explanation stored after ATS runs |
| cover_letter | nvarchar |
| applied_at | datetime2 |

> **Migrations required**:
> ```sql
> CREATE TABLE Resumes ( ... );   -- see above
> ALTER TABLE Applications ADD resume_id uniqueidentifier NULL REFERENCES Resumes(id);
> -- Legacy: ALTER TABLE Applications ADD ats_reason nvarchar(500) NULL;
> ```

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

> **Migration required**: `ALTER TABLE InterviewRounds ADD failing_criteria INT NULL;`

### Interviews
| Column | Type | Notes |
|---|---|---|
| id | uniqueidentifier PK | |
| interview_round_id | uniqueidentifier FK -> InterviewRounds | |
| application_id | uniqueidentifier FK -> Applications | |
| status | varchar | `Scheduled` / `In Progress` / `Pass` / `Failed` / `Not Needed` (auto-set on later rounds when an earlier round Fails) |
| scheduled_at | datetime2 | |
| completed_at | datetime2 | |
| feedback | nvarchar | AI-generated text feedback about the round |
| result | float | Final numeric score (0–10); NULL until round is scored |

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

### InterviewQuestions
| Column | Type |
|---|---|
| id | uniqueidentifier PK |
| interview_id | uniqueidentifier FK -> Interviews |
| question_id | uniqueidentifier FK -> Questions |
| candidate_answer | nvarchar |
| score | int |
| notes | nvarchar |

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
