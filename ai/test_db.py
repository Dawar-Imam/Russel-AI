from sqlalchemy import select

from agents.interview_agent.models import CandidateProfiles
from app.database.session import SessionLocal

CANDIDATE_ID = "b0000001-0000-0000-0000-000000000001"

with SessionLocal() as session:
    candidate = session.execute(
        select(CandidateProfiles).where(CandidateProfiles.id == CANDIDATE_ID)
    ).scalar_one()

print(candidate.id)
print(candidate.bio)
print(candidate.resume_url)
