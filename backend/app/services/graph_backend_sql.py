"""SQL 图引擎：三元组表（graph_nodes / graph_edges）为唯一事实源。

读：简单读取直接 SQLAlchemy 查表（保持 API 形状逐字段不变）；图算法（最短路径 /
邻居 / 路径推荐）把两表灌入内存 networkx.DiGraph 再跑（图谱 ≤120 节点，重建开销
可忽略）。写：自开 SessionLocal 隔离提交，异常不污染调用方主流程。
"""
from __future__ import annotations

import logging

import networkx as nx

from ..db import SessionLocal
from ..models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)


def _node_dict(n: GraphNode) -> dict:
    return {"id": n.id, "label": n.label, "name": n.name, "properties": n.properties}


def _edge_dict(e: GraphEdge) -> dict:
    return {
        "id": e.id,
        "source_id": e.source_id,
        "target_id": e.target_id,
        "relation": e.relation,
        "weight": e.weight,
    }


class SQLGraphBackend:
    """SQL + networkx 实现。所有读方法接收请求级 db；写方法自开会话。"""

    def engine_name(self) -> str:
        return "sql"

    # ---- 读 ----

    def engine_info(self, db) -> dict:
        node_count = db.query(GraphNode).count()
        edge_count = db.query(GraphEdge).count()
        return {
            "engine": "sql",
            "node_count": node_count,
            "edge_count": edge_count,
            "neo4j_error": None,
        }

    def get_graph(self, db) -> dict:
        nodes = db.query(GraphNode).all()
        edges = db.query(GraphEdge).all()
        return {
            "nodes": [_node_dict(n) for n in nodes],
            "edges": [_edge_dict(e) for e in edges],
        }

    def list_nodes(self, db, label: str | None = None) -> list[dict]:
        q = db.query(GraphNode)
        if label:
            q = q.filter(GraphNode.label == label)
        return [_node_dict(n) for n in q.all()]

    def find_node(self, db, *, label: str, name: str) -> dict | None:
        n = (
            db.query(GraphNode)
            .filter(GraphNode.label == label, GraphNode.name == name)
            .first()
        )
        return _node_dict(n) if n else None

    def find_node_by_id(self, db, node_id: int) -> dict | None:
        n = db.get(GraphNode, node_id)
        return _node_dict(n) if n else None

    def _load(self, db) -> nx.DiGraph:
        """两表 → 内存有向图（节点 key=graph_nodes.id，边带 relation/weight/id）。"""
        G = nx.DiGraph()
        for n in db.query(GraphNode).all():
            G.add_node(n.id, label=n.label, name=n.name, properties=n.properties or {})
        for e in db.query(GraphEdge).all():
            G.add_edge(e.source_id, e.target_id, relation=e.relation, weight=e.weight, id=e.id)
        return G

    def follow(
        self,
        db,
        node_id: int,
        *,
        relation: str | None = None,
        direction: str = "out",
        limit: int = 10,
    ) -> list[dict]:
        """沿出/入边找关联节点，按权重降序取前 limit。"""
        G = self._load(db)
        if node_id not in G:
            return []
        out: list[dict] = []
        for u, v, data in (G.out_edges(node_id, data=True) if direction == "out" else G.in_edges(node_id, data=True)):
            if relation is not None and data["relation"] != relation:
                continue
            other = v if direction == "out" else u
            out.append(
                {
                    "other_id": other,
                    "other_name": G.nodes[other]["name"],
                    "other_label": G.nodes[other]["label"],
                    "relation": data["relation"],
                    "weight": data["weight"],
                    "edge_id": data["id"],
                }
            )
        out.sort(key=lambda e: e["weight"], reverse=True)
        return out[:limit]

    def shortest_path(self, db, from_id: int, to_id: int, max_hops: int = 5) -> list[dict] | None:
        G = self._load(db)
        if from_id not in G or to_id not in G:
            return None
        # 无权最短路径（按跳数），与 Neo4j 后端的 Cypher shortestPath 语义一致，
        # 保证双引擎 /api/graph/path(Mode A) 响应逐字段相同。
        try:
            node_path = nx.shortest_path(G, from_id, to_id)
        except nx.NetworkXNoPath:
            return None
        if len(node_path) - 1 > max_hops:
            return None
        return [
            {"id": nid, "label": G.nodes[nid]["label"], "name": G.nodes[nid]["name"]}
            for nid in node_path
        ]

    def subgraph(self, db, node_ids: list[int]) -> dict:
        G = self._load(db).subgraph(node_ids)
        return {
            "nodes": [
                {"id": nid, "label": G.nodes[nid]["label"], "name": G.nodes[nid]["name"],
                 "properties": G.nodes[nid]["properties"] or None}
                for nid in G.nodes
            ],
            "edges": [
                {"id": d["id"], "source_id": u, "target_id": v, "relation": d["relation"],
                 "weight": d["weight"]}
                for u, v, d in G.edges(data=True)
            ],
        }

    # ---- 写（自开会话隔离提交；失败抛异常由调用方 try/except 兜住）----

    def upsert_node(self, *, label: str, name: str, properties: dict | None = None) -> dict:
        """按 (label, name) 幂等 upsert（已存在则更新 properties），返回节点。"""
        db = SessionLocal()
        try:
            n = (
                db.query(GraphNode)
                .filter(GraphNode.label == label, GraphNode.name == name)
                .first()
            )
            if n is None:
                n = GraphNode(label=label, name=name, properties=properties)
                db.add(n)
            elif properties is not None:
                n.properties = properties
            db.commit()
            db.refresh(n)
            return _node_dict(n)
        finally:
            db.close()

    def upsert_edge(
        self, *, source_id: int, target_id: int, relation: str, weight: float = 1.0
    ) -> dict:
        """按 (source, target, relation) 幂等 upsert（已存在则更新权重）。"""
        db = SessionLocal()
        try:
            e = (
                db.query(GraphEdge)
                .filter(
                    GraphEdge.source_id == source_id,
                    GraphEdge.target_id == target_id,
                    GraphEdge.relation == relation,
                )
                .first()
            )
            if e is None:
                e = GraphEdge(source_id=source_id, target_id=target_id, relation=relation, weight=weight)
                db.add(e)
            else:
                e.weight = weight
            db.commit()
            db.refresh(e)
            return _edge_dict(e)
        finally:
            db.close()

    def bump_heat(self, disease_name: str, delta: int = 1) -> int | None:
        """识别热度回写：病害节点 properties.heat += delta；无节点返回 None。"""
        db = SessionLocal()
        try:
            n = (
                db.query(GraphNode)
                .filter(GraphNode.label == "病害", GraphNode.name == disease_name)
                .first()
            )
            if n is None:
                return None
            props = dict(n.properties or {})
            props["heat"] = props.get("heat", 0) + delta
            n.properties = props
            db.commit()
            return n.id
        finally:
            db.close()

    def add_confusion_edge(
        self, pred_disease_name: str, corrected_disease_name: str
    ) -> int | None:
        """纠错回写：原预测病害 → 正确病害 建/更新「易混淆」边（weight 累计次数）。

        以病害「名称」定位图节点（graph_nodes.id ≠ diseases.id，按名跨表对齐）。
        """
        db = SessionLocal()
        try:
            pred = (
                db.query(GraphNode)
                .filter(GraphNode.label == "病害", GraphNode.name == pred_disease_name)
                .first()
            )
            correct = (
                db.query(GraphNode)
                .filter(GraphNode.label == "病害", GraphNode.name == corrected_disease_name)
                .first()
            )
            if pred is None or correct is None:
                return None
            e = (
                db.query(GraphEdge)
                .filter(
                    GraphEdge.source_id == pred.id,
                    GraphEdge.target_id == correct.id,
                    GraphEdge.relation == "易混淆",
                )
                .first()
            )
            if e is None:
                e = GraphEdge(
                    source_id=pred.id, target_id=correct.id, relation="易混淆", weight=1.0
                )
                db.add(e)
            else:
                e.weight = (e.weight or 1.0) + 1
            db.commit()
            db.refresh(e)
            return e.id
        finally:
            db.close()
