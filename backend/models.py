from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=True)
    pet_name = Column(String(50), nullable=True)  # displayed in UI everywhere
    timezone = Column(String(64), nullable=True)  # e.g. "America/Los_Angeles" for "today" and default dates

    results = relationship("WordleResult", back_populates="user")


class WordleResult(Base):
    __tablename__ = "wordle_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    attempts = Column(Integer, nullable=False)
    completed = Column(Boolean, default=True)
    score = Column(Integer, nullable=False)

    user = relationship("User", back_populates="results")
