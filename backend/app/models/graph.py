"""动态知识图谱三元组表（双后端图引擎抽象层的 SQL 事实源）。

SQL 表存图节点与边的全部真值；Neo4j 后端只读只算 + 尽力镜像（见
services/graph_backend_neo4j.py），漂移由 data/sync_neo4j.py 全量重建自愈。
图节点与边支持运行时动态增改（识别热度回写 / 纠错易混淆边），是「动态知识图谱」
承诺的可落地方案。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(32), index=True)  # 病害/寄主/症状/药剂/环境/防治措施
    name: Mapped[str] = mapped_column(String(64), index=True)
    properties: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("graph_nodes.id"), index=True)
    relation: Mapped[str] = mapped_column(String(32))  # 诱发/表现为/防治于/作用于/适宜
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
