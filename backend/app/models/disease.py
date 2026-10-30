"""病害知识域：寄主 / 病害 / 症状 / 防治方案 / 药剂 / 环境规则。"""
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Column,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class Host(Base):
    """寄主作物，如绿豆 Vigna radiata。"""

    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)  # 绿豆
    scientific_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Disease(Base):
    __tablename__ = "diseases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # 绿豆叶斑病
    name_en: Mapped[str | None] = mapped_column(String(64), nullable=True)
    host_id: Mapped[int] = mapped_column(ForeignKey("hosts.id"))
    disease_type: Mapped[str] = mapped_column(String(16))  # 真菌性/细菌性/病毒性/生理性/健康
    pathogen: Mapped[str | None] = mapped_column(Text, nullable=True)  # 病原
    symptoms: Mapped[str | None] = mapped_column(Text, nullable=True)  # 症状描述
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)  # 发病环境
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    host: Mapped[Host] = relationship()
    treatments: Mapped[list["Treatment"]] = relationship(back_populates="disease")


class Symptom(Base):
    """症状节点（知识图谱多跳：病害 表现为 症状）。"""

    __tablename__ = "symptoms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)  # 褐色斑点 / 白色粉状霉层...
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


# 病害-症状 多对多
disease_symptom = Table(
    "disease_symptoms",
    Base.metadata,
    Column("disease_id", ForeignKey("diseases.id"), primary_key=True),
    Column("symptom_id", ForeignKey("symptoms.id"), primary_key=True),
)


class Treatment(Base):
    """防治方案：病害 × 严重度 × 防治方法。"""

    __tablename__ = "treatments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), index=True)
    severity_level: Mapped[str] = mapped_column(String(8))  # 轻度/中度/重度
    method_type: Mapped[str] = mapped_column(String(16))  # 化学/农业/生物/注意事项
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    disease: Mapped[Disease] = relationship(back_populates="treatments")


class Pesticide(Base):
    """药剂。"""

    __tablename__ = "pesticides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    active_ingredient: Mapped[str | None] = mapped_column(String(64), nullable=True)
    usage: Mapped[str | None] = mapped_column(Text, nullable=True)  # 使用方法/浓度


# 药剂-病害 多对多
pesticide_disease = Table(
    "pesticide_diseases",
    Base.metadata,
    Column("pesticide_id", ForeignKey("pesticides.id"), primary_key=True),
    Column("disease_id", ForeignKey("diseases.id"), primary_key=True),
)


class DiseaseEnvRule(Base):
    """多模态环境规则：环境条件下对某病害置信度的后验修正。"""

    __tablename__ = "disease_env_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    disease_id: Mapped[int] = mapped_column(ForeignKey("diseases.id"), index=True)
    condition: Mapped[str] = mapped_column(String(32))  # 高温高湿 / 阴雨连绵 ...
    adjustment: Mapped[float] = mapped_column(Float, default=0.0)  # 置信度修正量
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
