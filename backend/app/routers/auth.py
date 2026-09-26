"""Day 20: sign up, log in, and "who am I?"."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, decode_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    """Add `user: User = Depends(get_current_user)` to any endpoint to make it login-only."""
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def get_optional_user(token: str | None = Depends(optional_oauth2), db: Session = Depends(get_db)) -> User | None:
    """Like get_current_user, but returns None instead of an error when not logged in.
    Used where logging in adds something (the leaderboard shows your own row)."""
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserCreate, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="That email is already registered")
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(status_code=409, detail="That username is taken")
    user = User(email=email, username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Log in with email OR username in the 'username' field."""
    name = form.username.strip()
    user = db.scalar(select(User).where((User.email == name.lower()) | (func.lower(User.username) == name.lower())))
    # Same message whether the account exists or not, so attackers can't find valid emails.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email/username or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
