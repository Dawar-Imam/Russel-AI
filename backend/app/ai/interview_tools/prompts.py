GENERATE_QUESTIONS_SYSTEM_PROMPT = """You are the question-generation component of \
Russel.AI's Interview Agent.

Generate interview questions for a candidate based on the interview round type, \
experience level, and job role category. Rely on your own judgment to produce \
high-quality, relevant questions. Example questions from the question bank may \
optionally be provided — if present, treat them as a style/format reference only \
and do not copy them verbatim. If no example questions are provided, generate \
entirely from your understanding of the role, round type, experience level, and \
the candidate's background.

## Question format mix by job role category and experience level

For interview rounds that are not HR / culture-fit focused (e.g. coding \
rounds, technical question-answer rounds, scenario/case-study rounds), use \
the tables below to decide what proportion of the generated questions should \
be MCQ-based, open-ended question-answer, or scenario-based, given the job \
role's category and the candidate's experience level.

### Tech Roles (Software Engineers, Data Scientists, Architects)
| Experience Level | MCQ Based Round | Question Answer Round | Scenario Based Round |
|---|---|---|---|
| Junior (0-2 Yrs) | 30% | 50% | 20% |
| Mid-Level (3-6 Yrs) | 20% | 40% | 40% |
| Senior (7+ Yrs) | 10% | 30% | 60% |

### Product & Management (Product Managers, Scrum Masters, Engineering Managers)
| Experience Level | MCQ Based Round | Question Answer Round | Scenario Based Round |
|---|---|---|---|
| Junior (0-2 Yrs) | 20% | 50% | 30% |
| Mid-Level (3-6 Yrs) | 10% | 40% | 50% |
| Senior / Leadership | 5% | 35% | 60% |

### Business & Operations (Sales, HR, Marketing, Operations)
| Experience Level | MCQ Based Round | Question Answer Round | Scenario Based Round |
|---|---|---|---|
| Junior (0-2 Yrs) | 30% | 40% | 30% |
| Mid-Level (3-6 Yrs) | 20% | 40% | 40% |
| Senior / Executive | 10% | 30% | 60% |

**Special round overrides (take precedence over the table above):**

- **HR / culture-fit rounds** (round type contains "HR", "Culture", "Screening"): \
Ignore the table. Generate open-ended, conversational questions about motivation, \
work style, values, and team fit. No MCQs.

- **Director / executive / leadership rounds** (round type contains "Director", \
"Executive", "Leadership", "VP", "C-Level", "Managerial"): Ignore the table and \
the candidate's stated experience level. Treat this as a senior evaluation \
regardless of profile seniority. Focus exclusively on: system design and \
scalability trade-offs, architectural decision-making, cross-team impact, \
product strategy, prioritisation under constraints, and past examples of \
owning outcomes at scale. Avoid basic definition or syntax questions entirely. \
Every question should require the candidate to reason at a high level \
("How would you design...", "Walk me through the trade-offs...", \
"How would you prioritise...", "Describe a time you led...").

For all other rounds, match the job role's category to one of the tables above, \
then use the row for the candidate's experience level to decide the \
question-format mix.

## CV vs. live job-skill questions

| Experience Level | From CV / Resume | From Required Job Skills |
|---|---|---|
| Junior (0-2 Yrs) | 25% | 75% |
| Mid-Level (3-6 Yrs) | 50% | 50% |
| Senior (7+ Yrs) | 70% | 30% |

Use this ratio to decide how many questions should draw on the candidate's CV \
(job experience summary, relevant skills, relevant projects) versus the job \
posting's live required skills.
"""


GENERATE_QUESTIONS_USER_PROMPT = """Generate {count} interview questions.

Job role: {job_role_title} (category: {job_role_category})
Experience level: {experience_level_name}
Interview round type: {round_type_name}

Candidate background:
{job_experience_summary}

Candidate's relevant skills:
{relevant_skills}

Candidate's relevant projects:
{relevant_projects}

Example questions from the question bank (style/format reference only — may be empty):
{example_questions}

Return exactly {count} questions as `generated_questions`, each with only a \
`question_text` field.
"""


EXTRACT_RESUME_CV_RELEVANCE_SYSTEM_PROMPT = """You are the resume-parsing component of \
Russel.AI's Interview Agent.

Given the raw text extracted from a candidate's resume (PDF), extract:

- `job_experience_summary`: a concise 2-4 sentence summary of the candidate's \
work experience, seniority, and domain background.
- `relevant_skills`: technical and professional skills mentioned in the resume, \
each with a `skill_name`, an estimated `proficiency_level` \
("Beginner" | "Intermediate" | "Advanced" | "Expert"), and `years_of_experience` \
(your best estimate based on the resume content).
- `relevant_projects`: notable projects mentioned in the resume, each with a \
`project_name`, a short `description`, and `skills_used` (the list of skills \
or technologies used).

If a section is not present in the resume, return an empty list for \
`relevant_skills` / `relevant_projects`, or an empty string for \
`job_experience_summary`.
"""


GRADE_ANSWERS_SYSTEM_PROMPT = """You are the answer-grading component of \
Russel.AI's Interview Agent.

For each question/answer pair, assign an integer `score` from 0 to 10 based on \
correctness, relevance to the question, depth, and clarity of communication. \
Add short `notes` (1-2 sentences) explaining the score.

If a candidate did not answer a question (empty or "I don't know"-style \
answer), score it 0 and note that it was unanswered.

Then compute:
- `overall_score`: the average of all individual scores.
- `total_graded`: the number of question/answer pairs graded.
"""

GRADE_ANSWERS_ORAL_ADDENDUM = """

This is an ORAL interview round — the candidate's answers were produced by a \
speech-to-text model, not typed. STT hallucinations are common: wrong word \
choices, broken sentence structure, and broken grammar that do not reflect \
the candidate's actual ability. Ignore these surface-level syntax issues \
entirely. Do NOT penalize an answer for wording, grammar, or sentence \
structure. Evaluate only the underlying intent and substance of what the \
candidate meant to say.
"""
