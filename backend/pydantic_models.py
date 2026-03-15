from datetime import date
from typing import Optional, List

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)


class User(UserBase):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    pet_name: Optional[str] = None

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    """Schema for user registration."""
    password: str = Field(..., min_length=4, max_length=100)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    pet_name: str = Field(..., min_length=1, max_length=50)


class UserLoginRequest(UserBase):
    """Schema for user login with password."""
    password: str = Field(..., min_length=1)


class UserProfileUpdate(BaseModel):
    """Schema for updating user profile. username identifies the user."""
    username: str = Field(..., min_length=1, max_length=50)  # current username
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    pet_name: Optional[str] = Field(None, min_length=1, max_length=50)
    new_username: Optional[str] = Field(None, min_length=1, max_length=50)


class ChangePasswordRequest(BaseModel):
    """Schema for changing password."""
    username: str = Field(..., min_length=1)
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=4, max_length=100)


class WordleResultBase(BaseModel):
    username: str  # for API identity when creating
    date: date
    attempts: int = Field(..., ge=1, le=6)
    completed: bool = True


class WordleResultCreate(WordleResultBase):
    pass


class WordleResult(WordleResultBase):
    id: int
    score: int
    pet_name: Optional[str] = None  # for display in UI

    class Config:
        from_attributes = True


class LeaderboardEntry(BaseModel):
    username: str
    pet_name: Optional[str] = None  # display in UI
    total_score: int


class LeaderboardResponse(BaseModel):
    period: str
    period_start: date
    period_end: date
    entries: List[LeaderboardEntry]


class TodayStatus(BaseModel):
    username: str
    pet_name: Optional[str] = None  # display in UI
    has_entry: bool
    result: Optional["WordleResult"] = None


class DailyScore(BaseModel):
    date: date
    username: str
    pet_name: Optional[str] = None  # display in UI
    score: int
    attempts: int
    completed: bool


class HeadToHead(BaseModel):
    user1: str  # pet_name for display
    user2: str
    user1_wins: int
    user2_wins: int
    ties: int


class UserStats(BaseModel):
    username: str
    pet_name: Optional[str] = None  # display in UI
    total_score: int
    avg_attempts: float
    completion_rate: float
    games_played: int
    attempt_distribution: dict  # {1: count, 2: count, ...}
    streak: Optional[int] = None  # set only for week/month/year periods


class AnalyticsResponse(BaseModel):
    period: str
    period_start: date
    period_end: date
    daily_scores: List[DailyScore]
    head_to_head: Optional[HeadToHead] = None
    user_stats: List[UserStats]
    winner: Optional[str] = None  # pet_name of period winner, None if tie

