"""识别纠错反馈接口：用户对识别结果反馈对/错 → 沉淀训练数据 → 管理员导出 CSV。

闭环：POST /api/recognitions/{id}/feedback（小程序/Web）→
      GET /api/feedback（分页查看）→
      GET /api/feedback/export（管理员导出，供 ml/finetune_corrections.py 续训）。
"""
import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from ..config import TRAINABLE_CLASS_NAMES
from ..db import get_db
from ..models import Disease, Recognition, RecognitionFeedback, User
from ..schemas.feedback import FeedbackCreate, FeedbackOut, FeedbackPage
from ..services.auth import (
    get_current_user,
    get_current_user_optional,
    log_operation,
    require_admin,
)
from ..services.graph_backend import get_graph_backend

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

# corrected_severity 追加在末尾：保证前 6 列与既有 finetune_corrections.py
# 的解析顺序兼容（无论按列名还是按位置索引读取）。
_EXPORT_HEADERS = [
    "recognition_id",
    "image_path",
    "predicted_class",
    "corrected_class",
    "is_correct",
    "created_at",
    "corrected_severity",
]


def _build_out(db: Session, fb: RecognitionFeedback) -> FeedbackOut:
    """反馈行 → 视图（关联出预测/正确病害名称）。"""
    rec = db.get(Recognition, fb.recognition_id)
    predicted = db.get(Disease, rec.disease_id) if rec and rec.disease_id else None
    corrected = (
        db.get(Disease, fb.corrected_disease_id) if fb.corrected_disease_id else None
    )
    return FeedbackOut(
        id=fb.id,
        recognition_id=fb.recognition_id,
        user_id=fb.user_id,
        is_correct=fb.is_correct,
        corrected_disease_id=fb.corrected_disease_id,
        corrected_name=corrected.name if corrected else None,
        corrected_severity=fb.corrected_severity,
        predicted_name=predicted.name if predicted else None,
        remark=fb.remark,
        created_at=str(fb.created_at),
    )


@router.post(
    "/api/recognitions/{recognition_id}/feedback", response_model=FeedbackOut
)
def submit_feedback(
    recognition_id: int,
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
):
    """提交识别纠错反馈（登录用户或匿名均可）。

    归属权限：匿名仅可反馈匿名识别记录（防枚举他人记录）；管理员可反馈任意；
    其它登录用户仅本人记录。登录用户按 (recognition_id, user_id) 覆盖更新；
    匿名每次新增。
    """
    rec = db.get(Recognition, recognition_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="识别记录不存在")

    # 归属权限（顺序：存在 → 权限 → 病害校验）
    if user is None:
        if rec.user_id is not None:
            raise HTTPException(status_code=403, detail="匿名用户仅可反馈匿名识别记录")
    elif user.role != "admin" and rec.user_id != user.id:
        raise HTTPException(status_code=403, detail="无权反馈他人的识别记录")

    # 正确病害校验：必须存在且属于可训练 10 类（防 labels 索引漂移）
    corrected_disease = None
    if body.corrected_disease_id is not None:
        corrected_disease = db.get(Disease, body.corrected_disease_id)
        if corrected_disease is None:
            raise HTTPException(status_code=404, detail="病害不存在")
        if corrected_disease.name not in TRAINABLE_CLASS_NAMES:
            raise HTTPException(
                status_code=400,
                detail=f"该病害不在可训练分类内（{'/'.join(TRAINABLE_CLASS_NAMES)}）",
            )
    # 严重度纠正：健康 = 无病害，纠正严重度无意义，强制置空（前端已隐藏该选项）
    corrected_severity = body.corrected_severity
    if corrected_disease is not None and corrected_disease.name == "健康":
        corrected_severity = None

    # upsert：登录用户覆盖自己的反馈；匿名(user_id=None)每次新增
    fb = None
    if user is not None:
        fb = (
            db.query(RecognitionFeedback)
            .filter(
                RecognitionFeedback.recognition_id == recognition_id,
                RecognitionFeedback.user_id == user.id,
            )
            .first()
        )
    if fb is None:
        fb = RecognitionFeedback(
            recognition_id=recognition_id,
            user_id=user.id if user else None,
        )
        db.add(fb)
    fb.is_correct = body.is_correct
    fb.corrected_disease_id = body.corrected_disease_id
    fb.corrected_severity = corrected_severity
    fb.remark = body.remark
    db.commit()
    db.refresh(fb)
    log_operation(
        db, "recognition.feedback", f"反馈识别#{recognition_id}",
        user.id if user else None,
    )

    # 图谱动态回写：纠错沉淀「易混淆」边（预测病害 → 正确病害，weight 累计次数）。
    # 健康非混淆对象；仅当纠错改了病害才建边；图写失败不阻断反馈主流程。
    if (
        not body.is_correct
        and body.corrected_disease_id is not None
        and rec.disease_id is not None
        and body.corrected_disease_id != rec.disease_id
    ):
        try:
            pred_disease = db.get(Disease, rec.disease_id)
            corrected_disease = db.get(Disease, body.corrected_disease_id)
            if (
                pred_disease
                and corrected_disease
                and pred_disease.name != "健康"
                and corrected_disease.name != "健康"
            ):
                get_graph_backend().add_confusion_edge(
                    pred_disease.name, corrected_disease.name
                )
        except Exception:  # noqa: BLE001
            logger.warning("图谱「易混淆」边回写失败（忽略，不影响纠错）")

    return _build_out(db, fb)


@router.get("/api/feedback", response_model=FeedbackPage)
def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """反馈列表：普通用户仅本人识别记录相关的反馈；管理员可看全部。"""
    q = db.query(RecognitionFeedback)
    if user.role != "admin":
        q = q.join(Recognition, Recognition.id == RecognitionFeedback.recognition_id)
        q = q.filter(Recognition.user_id == user.id)
    total = q.count()
    rows = (
        q.order_by(RecognitionFeedback.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_build_out(db, r) for r in rows],
        "total": total,
    }


@router.get("/api/feedback/export")
def export_feedback(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """导出全部反馈为 CSV（仅管理员）。加 BOM 供 Excel 中文兼容。

    image_path 为裸文件名（如 <uuid4 hex>.jpg），供训练端拼 RECOGNITION_DIR。
    """
    rows = db.query(RecognitionFeedback).order_by(RecognitionFeedback.id).all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_HEADERS)
    for fb in rows:
        rec = db.get(Recognition, fb.recognition_id)
        predicted = db.get(Disease, rec.disease_id) if rec and rec.disease_id else None
        corrected = (
            db.get(Disease, fb.corrected_disease_id) if fb.corrected_disease_id else None
        )
        writer.writerow(
            [
                fb.recognition_id,
                rec.image_path if rec else "",
                predicted.name if predicted else "",
                corrected.name if corrected else "",
                int(fb.is_correct),
                str(fb.created_at),
                fb.corrected_severity or "",
            ]
        )
    data = "﻿" + buf.getvalue()  # BOM
    return Response(
        content=data.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="feedback_export.csv"'
        },
    )
