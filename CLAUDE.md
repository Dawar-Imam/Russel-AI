# Russel-AI

AI-powered talent intelligence platform — recruiters post jobs and get
AI-screened, AI-interviewed, ranked shortlists; candidates apply, take AI
interviews, and get feedback/gap analysis. Full product overview, features,
roles, and system flow: [README.md](README.md).

## Database Schema (ERD)

Canonical ERD (Mermaid) is in [README.md](README.md#database-schema) — 17
tables across Auth/Roles, Profiles, Company, Jobs, Applications, Skills,
Interviews, and Questions domains.

For a flatter table-by-table reference (columns, FKs, relationships) and
notes on how the `ai/` agents map onto the schema, see
[.claude/database-schema.md](.claude/database-schema.md).

Both `ai/` and `backend/` operate against this single schema — when adding
models, Pydantic/SQLAlchemy schemas, agent I/O, or queries, keep table names,
column names, FK directions, and enum values consistent with it.

## Agent Architecture

[.claude/agent-architecture.md](.claude/agent-architecture.md) is the
canonical agentic flow for the interview pipeline (Interview Agent —
`generate_questions_tool`, `score_answers_tool`, `validate_tool`,
`store_results_tool` — plus the Voice Agent subagent's
`conversation_tool`/`transcript_parser_tool`), with a Mermaid diagram and
tool I/O schemas. The flow is final; the tool schemas are a working draft
that may not yet match the DB schema and will be corrected as `ai/` and
`backend/` are implemented. Read this before building or modifying anything
in `ai/` or interview-related `backend/` code.

## Repo layout

- `backend/` — FastAPI app (`uv`-managed via `pyproject.toml`). Run:
  `cd backend && uv sync && uv run uvicorn app.main:app --reload`
- `ai/` — AI agents (`question_generator_agent`, `answer_scorer_agent`,
  `validator_agent`, `voice_agent`) plus `ai_services/`, `ai_configs/`,
  entrypoint `ai/app.py`.
- `frontend/` — Vite + React + TypeScript. Has its own
  [frontend/CLAUDE.md](frontend/CLAUDE.md) with design-system rules.
  Full token reference, component patterns, animation catalogue, and
  layout rules: [.claude/frontend-theme.md](.claude/frontend-theme.md).
