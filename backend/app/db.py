"""SQLAlchemy 引擎 / 会话 / Base 定义。"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


_engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（含新模型字段变更时的幂等处理）。

    create_all 只为不存在的表建表，不修改已存在的表；新增列走 _migrate
    轻量迁移（SQLite / MySQL 均支持 ALTER TABLE ADD COLUMN）。
    """
    from . import models  # noqa: F401  确保所有模型注册到 Base
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """已存在表补列。逐列检查，缺则 ALTER 补齐。"""
    inspector = inspect(engine)
    existing = {
        c["name"] for c in inspector.get_columns("recognition_feedback")
    }
    if "corrected_severity" not in existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE recognition_feedback "
                    "ADD COLUMN corrected_severity VARCHAR(10)"
                )
            )
