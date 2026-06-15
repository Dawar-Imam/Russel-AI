from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from ai_configs.config import settings

Base = declarative_base()

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
