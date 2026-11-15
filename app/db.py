import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 中台内部数据库到位后，设置环境变量 MI_DATABASE_URL 即可切换，代码不变。
DATABASE_URL = os.environ.get(
    "MI_DATABASE_URL", "sqlite:///" + os.path.join(DATA_DIR, "app.db").replace("\\", "/")
)

IS_SQLITE = DATABASE_URL.startswith("sqlite")
if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    side_engine = engine
else:
    # Each server process: up to 60 connections for requests (20 kept open + 40 on demand).
    # The default (5 + 10) ran dry when ~15 people saved in the same instant.
    engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=40, pool_timeout=30, pool_pre_ping=True, pool_recycle=1800)
    # A separate small pool for work done right after a save (live-update notice). It must not
    # borrow from the request pool: a save still holds its own connection at that moment, and
    # needing a second one from the same pool can deadlock when the pool is full.
    side_engine = create_engine(DATABASE_URL, pool_size=4, max_overflow=30, pool_timeout=30, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
