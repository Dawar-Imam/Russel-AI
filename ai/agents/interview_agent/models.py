from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.mssql import DATETIME2, NVARCHAR, UNIQUEIDENTIFIER
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base

# Models below cover the subset of the schema (see .claude/database-schema.md)
# needed by the question_generator and answer_scorer tools. Lookup/profile
# tables not used by these tools (Users, Companies, RecruiterProfiles, ...)
# are intentionally not mapped here.


class ExperienceLevels(Base):
    __tablename__ = "ExperienceLevels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    min_years: Mapped[int] = mapped_column(Integer)
    max_years: Mapped[int] = mapped_column(Integer)


class JobRoles(Base):
    __tablename__ = "JobRoles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean)


class InterviewRoundTypes(Base):
    __tablename__ = "InterviewRoundTypes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(255))


class SkillSets(Base):
    __tablename__ = "SkillSets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean)


class Questions(Base):
    __tablename__ = "Questions"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    interview_round_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("InterviewRoundTypes.id")
    )
    job_role_id: Mapped[int] = mapped_column(Integer, ForeignKey("JobRoles.id"))
    experience_level_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ExperienceLevels.id")
    )
    question_text: Mapped[str] = mapped_column(NVARCHAR)
    is_active: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[object] = mapped_column(DATETIME2)


class CandidateProfiles(Base):
    __tablename__ = "CandidateProfiles"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    user_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER)  # -> Users.id
    bio: Mapped[str] = mapped_column(NVARCHAR)
    resume_url: Mapped[str] = mapped_column(String(255))
    linkedin_url: Mapped[str] = mapped_column(String(255))
    experience_level_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ExperienceLevels.id")
    )
    job_role_id: Mapped[int] = mapped_column(Integer, ForeignKey("JobRoles.id"))
    current_location: Mapped[str] = mapped_column(String(100))
    open_to_work: Mapped[bool] = mapped_column(Boolean)
    updated_at: Mapped[object] = mapped_column(DATETIME2)


class CandidateSkills(Base):
    __tablename__ = "CandidateSkills"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    candidate_id: Mapped[str] = mapped_column(
        UNIQUEIDENTIFIER, ForeignKey("CandidateProfiles.id")
    )
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("SkillSets.id"))
    proficiency_level: Mapped[str] = mapped_column(String(50))
    years_of_experience: Mapped[int] = mapped_column(Integer)


class JobPostings(Base):
    __tablename__ = "JobPostings"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    recruiter_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER)  # -> RecruiterProfiles.id
    company_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER)  # -> Companies.id
    job_role_id: Mapped[int] = mapped_column(Integer, ForeignKey("JobRoles.id"))
    designation: Mapped[str] = mapped_column(String(150))
    description: Mapped[str] = mapped_column(NVARCHAR)
    location: Mapped[str] = mapped_column(String(100))
    job_type: Mapped[str] = mapped_column(String(50))
    salary_range: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50))
    posted_at: Mapped[object] = mapped_column(DATETIME2)
    expires_at: Mapped[object] = mapped_column(DATETIME2)


class JobRequiredSkills(Base):
    __tablename__ = "JobRequiredSkills"

    id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, primary_key=True)
    job_id: Mapped[str] = mapped_column(UNIQUEIDENTIFIER, ForeignKey("JobPostings.id"))
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("SkillSets.id"))
    proficiency_level: Mapped[str] = mapped_column(String(50))
    is_mandatory: Mapped[bool] = mapped_column(Boolean)
