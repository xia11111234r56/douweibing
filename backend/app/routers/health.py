from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import MODEL_DIR
from ..db import get_db

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health(db: Session = Depends(get_db)):
    """健康检查：数据库连通性 + 模型就绪状态。"""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "database": "ok" if db_ok else "error",
        "model_ready": (MODEL_DIR / "classifier.onnx").exists(),
        "version": "0.1.0",
    }
