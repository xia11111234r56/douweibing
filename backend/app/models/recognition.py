"""识别记录（多模态输入与结果都落库，供统计/检索/论文实验使用）。"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Recognition(Base):
    __tablename__ = "recognitions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 识别结果
    disease_id: Mapped[int | None] = mapped_column(
        ForeignKey("diseases.id"), nullable=True, index=True
    )
    severity: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 轻度/中度/重度
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 全部候选疾病与置信度，格式 [{"disease_id":1,"name":"...","confidence":0.9}]
    candidates: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 多模态输入：环境上下文（EXIF 回查 + 用户输入 + 知识规则）
    env_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 例如 {"growth_stage":"结荚期","weather":"高温高湿","gps_lat":39.9,"gps_lon":116.4,
    #        "capture_month":7,"clim":{"tavg":27.0,"prec":180.0},"source":"exif+worldclim"}

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
