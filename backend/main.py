from __future__ import annotations

from datetime import date, timedelta
from typing import List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import bcrypt

from pydantic_models import (
    User as UserSchema,
    UserCreate,
    UserLoginRequest,
    UserProfileUpdate,
    ChangePasswordRequest,
    WordleResultCreate,
    WordleResult as WordleResultSchema,
    LeaderboardResponse,
    LeaderboardEntry,
    TodayStatus,
    DailyScore,
    HeadToHead,
    UserStats,
    AnalyticsResponse,
)
from sqlalchemy import text
from database import engine, get_db, Base
from models import User, WordleResult
from utils import compute_score, get_period_bounds


app = FastAPI(title="Wordle Tracker API")


def _migrate_add_user_profile_columns():
    """Add first_name, last_name, pet_name to users if they don't exist (SQLite)."""
    with engine.connect() as conn:
        for col in ("first_name", "last_name", "pet_name"):
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} VARCHAR(50)"))
                conn.commit()
            except Exception:
                # Column likely already exists
                pass


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    _migrate_add_user_profile_columns()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    pwd_bytes = password.encode("utf-8")[:72]  # bcrypt limit
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    pwd_bytes = plain_password.encode("utf-8")[:72]
    hash_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(func.lower(User.username) == username.lower()).first()


def _display_name(user: User) -> str:
    """Return pet_name for UI display, fallback to username for legacy users."""
    return (user.pet_name or user.username) if user else ""


def get_current_streak(db: Session, user_id: int, reference_date: date | None = None) -> int:
    """
    Current streak: consecutive days with at least one entry, going backward.
    End date = reference_date (default today) if user has entry that day, else reference_date - 1.
    """
    if reference_date is None:
        reference_date = date.today()

    rows = (
        db.query(WordleResult.date)
        .filter(WordleResult.user_id == user_id)
        .distinct()
        .all()
    )
    dates = {r.date for r in rows}
    if not dates:
        return 0

    end = reference_date if reference_date in dates else reference_date - timedelta(days=1)
    if end not in dates:
        return 0

    streak = 0
    d = end
    while d in dates:
        streak += 1
        d -= timedelta(days=1)
    return streak


@app.post("/register", response_model=UserSchema)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserSchema:
    """Register a new user with username, password, first name, last name, and pet name."""
    existing = get_user_by_username(db, payload.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = hash_password(payload.password)
    new_user = User(
        username=payload.username,
        password_hash=hashed,
        first_name=payload.first_name,
        last_name=payload.last_name,
        pet_name=payload.pet_name,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/login", response_model=UserSchema)
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> UserSchema:
    """Login with username and password."""
    user = get_user_by_username(db, payload.username)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return user


@app.get("/users", response_model=List[UserSchema])
def list_users(db: Session = Depends(get_db)) -> List[UserSchema]:
    return db.query(User).all()


@app.put("/users/profile", response_model=UserSchema)
def update_profile(payload: UserProfileUpdate, db: Session = Depends(get_db)) -> UserSchema:
    """Update first name, last name, pet name, and/or username. new_username must be unique."""
    user = get_user_by_username(db, payload.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.first_name is not None:
        user.first_name = payload.first_name.strip()
    if payload.last_name is not None:
        user.last_name = payload.last_name.strip()
    if payload.pet_name is not None:
        user.pet_name = payload.pet_name.strip()

    if payload.new_username is not None:
        new_username = payload.new_username.strip()
        if new_username.lower() != user.username.lower():
            existing = get_user_by_username(db, new_username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists")
            user.username = new_username

    db.commit()
    db.refresh(user)
    return user


@app.post("/users/change-password")
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db)) -> dict:
    """Change password after verifying old password."""
    user = get_user_by_username(db, payload.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated successfully"}


@app.post("/results", response_model=WordleResultSchema)
def create_result(payload: WordleResultCreate, db: Session = Depends(get_db)) -> WordleResultSchema:
    user = get_user_by_username(db, payload.username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    score = compute_score(payload.attempts, payload.completed)

    existing = (
        db.query(WordleResult)
        .filter(WordleResult.user_id == user.id, WordleResult.date == payload.date)
        .first()
    )
    if existing:
        existing.attempts = payload.attempts
        existing.completed = payload.completed
        existing.score = score
        db.commit()
        db.refresh(existing)
        result = existing
    else:
        result = WordleResult(
            user_id=user.id,
            date=payload.date,
            attempts=payload.attempts,
            completed=payload.completed,
            score=score,
        )
        db.add(result)
        db.commit()
        db.refresh(result)

    return WordleResultSchema(
        id=result.id,
        username=user.username,
        date=result.date,
        attempts=result.attempts,
        completed=result.completed,
        score=result.score,
        pet_name=_display_name(user),
    )


@app.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    period: str = "day",
    reference_date: date | None = None,
    db: Session = Depends(get_db),
) -> LeaderboardResponse:
    """
    period: one of "day", "week", "month", "year"
    reference_date: optional, defaults to today if not provided.
    """
    period = period.lower()
    if period not in {"day", "week", "month", "year"}:
        raise HTTPException(status_code=400, detail="Invalid period")

    if reference_date is None:
        reference_date = date.today()

    start, end = get_period_bounds(reference_date, period)

    results = (
        db.query(
            User.id,
            User.username,
            User.pet_name,
            func.sum(WordleResult.score).label("total_score"),
        )
        .join(WordleResult, User.id == WordleResult.user_id)
        .filter(WordleResult.date >= start, WordleResult.date <= end)
        .group_by(User.id, User.username, User.pet_name)
        .order_by(func.sum(WordleResult.score).desc(), func.lower(User.username))
        .all()
    )

    score_by_username = {row.username: row.total_score for row in results}

    if period in ("week", "month", "year") and results:
        streaks = {row.username: get_current_streak(db, row.id, reference_date) for row in results}
        max_streak = max(streaks.values()) if streaks else 0
        if max_streak > 0:
            winners_with_max = [u for u, s in streaks.items() if s == max_streak]
            if len(winners_with_max) == 1:
                score_by_username[winners_with_max[0]] = score_by_username.get(winners_with_max[0], 0) + 1

    entries = [
        LeaderboardEntry(
            username=row.username,
            pet_name=row.pet_name or row.username,
            total_score=score_by_username.get(row.username, row.total_score),
        )
        for row in results
    ]
    entries.sort(key=lambda e: (-e.total_score, (e.pet_name or e.username).lower()))

    return LeaderboardResponse(
        period=period,
        period_start=start,
        period_end=end,
        entries=entries,
    )


@app.get("/results/today", response_model=List[TodayStatus])
def get_today_results(db: Session = Depends(get_db)) -> List[TodayStatus]:
    """Get today's entry status for all users."""
    today = date.today()
    users = db.query(User).all()

    statuses = []
    for user in users:
        result = (
            db.query(WordleResult)
            .filter(WordleResult.user_id == user.id, WordleResult.date == today)
            .first()
        )
        if result:
            statuses.append(TodayStatus(
                username=user.username,
                pet_name=_display_name(user),
                has_entry=True,
                result=WordleResultSchema(
                    id=result.id,
                    username=user.username,
                    date=result.date,
                    attempts=result.attempts,
                    completed=result.completed,
                    score=result.score,
                    pet_name=_display_name(user),
                ),
            ))
        else:
            statuses.append(TodayStatus(
                username=user.username,
                pet_name=_display_name(user),
                has_entry=False,
                result=None,
            ))

    return statuses


@app.get("/analytics", response_model=AnalyticsResponse)
def get_analytics(
    period: str = "week",
    reference_date: date | None = None,
    db: Session = Depends(get_db),
) -> AnalyticsResponse:
    """Get comprehensive analytics for the specified period."""
    period = period.lower()
    if period not in {"day", "week", "month", "year"}:
        raise HTTPException(status_code=400, detail="Invalid period")

    if reference_date is None:
        reference_date = date.today()

    start, end = get_period_bounds(reference_date, period)

    results = (
        db.query(WordleResult, User.username, User.pet_name)
        .join(User, User.id == WordleResult.user_id)
        .filter(WordleResult.date >= start, WordleResult.date <= end)
        .order_by(WordleResult.date)
        .all()
    )

    def _row_display_name(r):
        return (r.pet_name or r.username) if getattr(r, "pet_name", None) else r.username

    daily_scores = [
        DailyScore(
            date=r.WordleResult.date,
            username=r.username,
            pet_name=_row_display_name(r),
            score=r.WordleResult.score,
            attempts=r.WordleResult.attempts,
            completed=r.WordleResult.completed,
        )
        for r in results
    ]

    users = db.query(User).all()
    user_stats_list = []
    scores_by_user = {}
    streaks_by_username = {}
    streak_bonus_winner = None

    users_in_period = {r.username for r in results}
    if period in ("week", "month", "year"):
        for user in users:
            if user.username in users_in_period:
                streaks_by_username[user.username] = get_current_streak(db, user.id, reference_date)
        max_streak = max(streaks_by_username.values()) if streaks_by_username else 0
        if max_streak > 0:
            winners_with_max = [u for u, s in streaks_by_username.items() if s == max_streak]
            if len(winners_with_max) == 1:
                streak_bonus_winner = winners_with_max[0]

    for user in users:
        user_results = [r for r in results if r.username == user.username]
        if not user_results:
            continue

        total_score = sum(r.WordleResult.score for r in user_results)
        if user.username == streak_bonus_winner:
            total_score += 1
        games_played = len(user_results)
        completed_games = sum(1 for r in user_results if r.WordleResult.completed)
        total_attempts = sum(r.WordleResult.attempts for r in user_results)

        attempt_dist = {i: 0 for i in range(1, 7)}
        for r in user_results:
            if r.WordleResult.completed:
                attempt_dist[r.WordleResult.attempts] += 1

        streak_val = streaks_by_username.get(user.username) if period in ("week", "month", "year") else None

        user_stats_list.append(UserStats(
            username=user.username,
            pet_name=_display_name(user),
            total_score=total_score,
            avg_attempts=round(total_attempts / games_played, 2) if games_played else 0,
            completion_rate=round(completed_games / games_played * 100, 1) if games_played else 0,
            games_played=games_played,
            attempt_distribution=attempt_dist,
            streak=streak_val,
        ))
        scores_by_user[user.username] = total_score

    head_to_head = None
    if len(users) == 2:
        username1, username2 = users[0].username, users[1].username
        wins1, wins2, ties = 0, 0, 0

        dates_with_results = set(r.WordleResult.date for r in results)
        for d in dates_with_results:
            day_results = {r.username: r.WordleResult.score for r in results if r.WordleResult.date == d}
            if username1 in day_results and username2 in day_results:
                if day_results[username1] > day_results[username2]:
                    wins1 += 1
                elif day_results[username2] > day_results[username1]:
                    wins2 += 1
                else:
                    ties += 1

        head_to_head = HeadToHead(
            user1=_display_name(users[0]),
            user2=_display_name(users[1]),
            user1_wins=wins1,
            user2_wins=wins2,
            ties=ties,
        )

    winner = None
    if scores_by_user:
        max_score = max(scores_by_user.values())
        winner_usernames = [u for u, s in scores_by_user.items() if s == max_score]
        if len(winner_usernames) == 1:
            w = get_user_by_username(db, winner_usernames[0])
            winner = _display_name(w) if w else winner_usernames[0]

    return AnalyticsResponse(
        period=period,
        period_start=start,
        period_end=end,
        daily_scores=daily_scores,
        head_to_head=head_to_head,
        user_stats=user_stats_list,
        winner=winner,
    )


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}
