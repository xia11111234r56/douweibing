"""识别纠错反馈表：用户对识别结果反馈对/错，沉淀为再训练数据源。

闭环：识别记录(recognitions) → 反馈(recognition_feedback) → 导出 CSV
      → ml/finetune_corrections.py 续训 → 导出 ONNX → 重启后端生效。

upsert 语义：登录用户按 (recognition_id, user_id) 唯一索引覆盖更新；
匿名用户 user_id 为 NULL，SQLite/MySQL 唯一索引均视 NULL 互不相同，
因此同一识别记录可有多条匿名反馈（不互斥）。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class RecognitionFeedback(Base):
    __tablename__ = "recognition_feedback"
    __table_args__ = (UniqueConstraint("recognition_id", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recognition_id: Mapped[int] = mapped_column(
        ForeignKey("recognitions.id"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # 反馈内容：正确与否 + 正确病害（识别错误时必填）
    is_correct: Mapped[bool] = mapped_column(Boolean, default=True)
    corrected_disease_id: Mapped[int | None] = mapped_column(
        ForeignKey("diseases.id"), nullable=True, index=True
    )
    # 纠正严重度（轻/中/重）。健康 = 无病害，必须为 NULL。
    corrected_severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    recognition: Mapped["Recognition"] = relationship()  # noqa: F821
