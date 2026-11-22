import secrets, hashlib
from datetime import timedelta
from fastapi import Depends, Request, HTTPException
from sqlalchemy.orm import Session as DBSession
from argon2 import PasswordHasher
from .db import get_db
from .models import Session, User, now

hasher=PasswordHasher()

def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()

def current_user(request:Request,db:DBSession=Depends(get_db)):
    raw=request.cookies.get('umb_session','');s=db.get(Session,token_hash(raw)) if raw else None
    if not s or s.expires<now():raise HTTPException(401,'Zaloguj się do aplikacji')
    if request.method not in ['GET','HEAD','OPTIONS']:
        if not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),s.csrf):raise HTTPException(403,'Niepoprawny token sesji. Odśwież stronę.')
    user=db.get(User,s.user_id)
    if not user:raise HTTPException(401,'Konto nie istnieje')
    request.state.auth_session=s
    return user

def require_admin(user=Depends(current_user)):
    if user.role!='admin':raise HTTPException(403,'Wymagane konto administratora')
    return user
