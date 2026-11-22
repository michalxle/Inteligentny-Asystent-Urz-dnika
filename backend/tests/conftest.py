import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.main import app
from app.db import get_db
from app.models import User
from app.auth import hasher
from app.config import settings

@pytest.fixture
def db():
    # Uses a transaction/savepoint in the development schema. Every test rolls back.
    engine=create_engine(settings.database_url)
    connection=engine.connect();transaction=connection.begin()
    session=Session(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False)
    yield session
    session.close();transaction.rollback();connection.close();engine.dispose()

@pytest.fixture
def client(db,tmp_path,monkeypatch):
    for name in ['files','pages','exports','tmp']:(tmp_path/name).mkdir()
    monkeypatch.setattr(settings,'data_dir',tmp_path)
    def override():yield db
    app.dependency_overrides[get_db]=override
    db.add(User(username='test-operator',password_hash=hasher.hash('test-password-for-suite'),role='operator'))
    db.commit()
    with TestClient(app) as c:
        result=c.post('/api/auth/login',json={'username':'test-operator','password':'test-password-for-suite'})
        assert result.status_code==200
        c.headers['X-CSRF-Token']=result.json()['csrf']
        yield c
    app.dependency_overrides.clear()
