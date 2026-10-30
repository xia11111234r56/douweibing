"""图片识别接口 + 识别记录查询。"""
import base64
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import RECOGNITION_DIR
from ..db import get_db
from ..models import Disease, Recognition, RecognitionFeedback, User
from ..schemas import (
    Candidate,
    RecognizeRequest,
    RecognizeResponse,
    RecognitionPage,
)
from ..services.auth import get_current_user, get_current_user_optional
from ..services.model_inference import ModelNotReady
from ..services.recognize import recognize

router = APIRouter(tags=["recognize"])


@router.post("/api/recognize", response_model=RecognizeResponse)
def recognize_endpoint(
    body: RecognizeRequest,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """图片识别。可选鉴权：登录用户记录归属本人，小程序匿名调用不受影响。"""
    try:
        image_bytes = base64.b64decode(body.image_base64)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="图片 base64 解码失败")
    try:
        return recognize(image_bytes, body.env, db, user_id=user.id if user else None)
    except ModelNotReady as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/api/recognitions", response_model=RecognitionPage)
def list_recognitions(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    disease_id: int | None = Query(None, description="按病害过滤"),
    severity: str | None = Query(None, description="轻度/中度/重度"),
    start_date: str | None = Query(None, description="起始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    has_feedback: bool | None = Query(
        None, description="按纠错状态筛选：true=已纠错，false=未纠错"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """识别历史：普通用户只看自己的记录，管理员可看全部（含小程序/匿名）。"""
    q = db.query(Recognition)
    if user.role != "admin":
        q = q.filter(Recognition.user_id == user.id)
    if disease_id:
        q = q.filter(Recognition.disease_id == disease_id)
    if severity:
        q = q.filter(Recognition.severity == severity)
    if start_date:
        q = q.filter(Recognition.created_at >= start_date)
    if end_date:
        q = q.filter(Recognition.created_at < f"{end_date} 23:59:59")

    # 全库已纠错记录 id 集合（筛选、统计、逐行标记共用一次查询）
    corrected_ids: set[int] = {
        fid for (fid,) in db.query(RecognitionFeedback.recognition_id).distinct()
    }

    if has_feedback is True:
        if corrected_ids:
            q = q.filter(Recognition.id.in_(corrected_ids))
        else:
            q = q.filter(Recognition.id == -1)  # 无已纠错记录 → 恒空
    elif has_feedback is False:
        if corrected_ids:
            q = q.filter(~Recognition.id.in_(corrected_ids))

    total = q.count()
    # 当前筛选下已纠错记录数（页头「已纠错 X 条」）
    if has_feedback is None:
        corrected_count = (
            q.filter(Recognition.id.in_(corrected_ids)).count() if corrected_ids else 0
        )
    else:
        corrected_count = total if has_feedback else 0

    rows = (
        q.order_by(Recognition.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for r in rows:
        d = db.get(Disease, r.disease_id) if r.disease_id else None
        items.append(
            {
                "id": r.id,
                "disease_name": d.name if d else None,
                "disease_type": d.disease_type if d else None,
                "severity": r.severity,
                "confidence": r.confidence,
                "candidates": [Candidate(**c) for c in (r.candidates or [])],
                "env_metadata": r.env_metadata,
                "image_path": r.image_path,
                "user_id": r.user_id,
                "is_anonymous": r.user_id is None,
                "has_feedback": r.id in corrected_ids,
                "created_at": str(r.created_at),
            }
        )
    return {"items": items, "total": total, "corrected_count": corrected_count}


@router.get("/api/recognitions/image/{filename}")
def recognition_image(filename: str):
    """识别原图（公开接口）。文件名是 uuid4().hex 生成的 32 位十六进制 + .jpg，
    不可枚举、正则校验防目录穿越；供 <img>/el-image 标签直接加载。
    旧版 /api/recognitions/{rec_id}/image 需要鉴权头，img 标签不带 Authorization 会 401，故弃用。"""
    if not re.fullmatch(r"[0-9a-f]{32}\.jpg", filename):
        raise HTTPException(status_code=404, detail="非法文件名")
    path = RECOGNITION_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="原图文件缺失")
    return FileResponse(path, media_type="image/jpeg")
