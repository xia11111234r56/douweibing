r"""知识图谱图算法测试：引擎状态 / 防治路径推荐 / 可解释推理链 / 动态回写。

运行（backend 目录下）：.venv\Scripts\python.exe -m pytest tests/test_graph_reason.py -q

前置：开发库已灌入图谱种子（graph_nodes/graph_edges 非空，test_graph 同样依赖）。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

client = TestClient(app)


# ---------- 引擎状态 ----------

def test_graph_engine():
    r = client.get("/api/graph/engine")
    assert r.status_code == 200
    body = r.json()
    assert body["engine"] == "sql"
    assert body["node_count"] > 10
    assert body["edge_count"] > 10
    assert body["neo4j_error"] is None


# ---------- 防治路径推荐 ----------

def test_graph_path_disease():
    r = client.get("/api/graph/path", params={"disease": "晕疫病", "severity": "中度"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "sql"
    assert body["mode"] == "disease"
    assert body["path"][0]["type"] == "start"
    assert body["path"][0]["name"] == "晕疫病"
    # 中度方案含 春雷·王铜 / 农用链霉素 → 应有防治药剂节点
    assert any(n["type"] == "control" for n in body["path"])
    assert any(s["relation"] == "防治" for s in body["steps"])
    assert "node_ids" in body["highlight"]


def test_graph_path_disease_with_weather():
    # 高温高湿 是 晕疫病 的「适宜」环境 → 路径应含环境段
    r = client.get(
        "/api/graph/path",
        params={"disease": "晕疫病", "severity": "重度", "weather": "高温高湿"},
    )
    assert r.status_code == 200
    body = r.json()
    assert any(n["type"] == "env" for n in body["path"])
    assert any(s["relation"] == "适宜" for s in body["steps"])


def test_graph_path_pair_shortest():
    """Mode A：寄主绿豆 → 某防治药剂 的最短路径应存在且经过病害节点。"""
    g = client.get("/api/graph").json()
    host = next(n for n in g["nodes"] if n["label"] == "寄主")
    control_edge = next(e for e in g["edges"] if e["relation"] == "防治")
    r = client.get(
        "/api/graph/path",
        params={"from_id": host["id"], "to_id": control_edge["target_id"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "pair"
    assert len(body["path"]) >= 2
    assert body["path"][0]["id"] == host["id"]
    assert body["path"][-1]["id"] == control_edge["target_id"]
    assert len(body["highlight"]["node_ids"]) >= 2


def test_graph_path_unknown_disease():
    r = client.get("/api/graph/path", params={"disease": "不存在病"})
    assert r.status_code == 404


def test_graph_path_missing_params():
    r = client.get("/api/graph/path")
    assert r.status_code == 400


def test_graph_path_invalid_severity():
    r = client.get("/api/graph/path", params={"disease": "晕疫病", "severity": "超重度"})
    assert r.status_code == 400


# ---------- 可解释推理链 ----------

def test_graph_reason_chain():
    r = client.get(
        "/api/graph/reason",
        params={"disease": "晕疫病", "severity": "中度", "weather": "高温高湿"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "sql"
    assert body["disease"] == "晕疫病"
    assert len(body["steps"]) >= 4
    relations = {s["relation"] for s in body["steps"]}
    # 5 段链：寄主感染 / 症状表现 / 环境适宜 / 防治用药
    assert {"感染", "表现为", "防治"} <= relations
    assert "适宜" in relations  # 高温高湿 命中 晕疫病 的适宜边
    assert "晕疫病" in body["summary"]
    assert body["controls"], "中度方案应检索到防治药剂"
    assert body["matched_symptoms"], "应有匹配症状"


def test_graph_reason_health():
    r = client.get("/api/graph/reason", params={"disease": "健康"})
    assert r.status_code == 200
    body = r.json()
    assert "无需防治" in body["summary"]
    assert body["controls"] == []
    assert body["note"]


def test_graph_reason_unknown():
    r = client.get("/api/graph/reason", params={"disease": "不存在病"})
    assert r.status_code == 404


# ---------- 动态回写（图引擎写方法单测） ----------

def test_bump_heat_increments():
    """识别热度回写：病害节点 properties.heat +1。"""
    from app.db import SessionLocal
    from app.models import GraphNode
    from app.services.graph_backend_sql import SQLGraphBackend

    db = SessionLocal()
    try:
        node = (
            db.query(GraphNode)
            .filter(GraphNode.label == "病害", GraphNode.name == "晕疫病")
            .first()
        )
        assert node is not None, "依赖图谱种子"
        before = (node.properties or {}).get("heat", 0)
    finally:
        db.close()

    SQLGraphBackend().bump_heat("晕疫病")

    db = SessionLocal()
    try:
        node = (
            db.query(GraphNode)
            .filter(GraphNode.label == "病害", GraphNode.name == "晕疫病")
            .first()
        )
        after = (node.properties or {}).get("heat", 0)
    finally:
        db.close()
    assert after == before + 1


def test_confusion_edge_accumulates():
    """纠错回写：同对 (预测, 正确) 重复纠错 → 易混淆边 weight 递增。"""
    from sqlalchemy import delete

    from app.db import SessionLocal
    from app.models import GraphEdge, GraphNode
    from app.services.graph_backend_sql import SQLGraphBackend

    db = SessionLocal()
    try:
        src = (
            db.query(GraphNode)
            .filter(GraphNode.label == "病害", GraphNode.name == "晕疫病")
            .first()
        )
        dst = (
            db.query(GraphNode)
            .filter(GraphNode.label == "病害", GraphNode.name == "炭疽叶斑病")
            .first()
        )
        assert src and dst, "依赖图谱种子"
        src_id, dst_id = src.id, dst.id  # 会话关闭前取出，避免 DetachedInstanceError
        # 清理历史边，保证测试可重复运行
        db.execute(
            delete(GraphEdge).where(
                GraphEdge.relation == "易混淆",
                GraphEdge.source_id == src_id,
                GraphEdge.target_id == dst_id,
            )
        )
        db.commit()
    finally:
        db.close()

    backend = SQLGraphBackend()
    backend.add_confusion_edge("晕疫病", "炭疽叶斑病")

    db = SessionLocal()
    try:
        e1 = (
            db.query(GraphEdge)
            .filter(
                GraphEdge.relation == "易混淆",
                GraphEdge.source_id == src_id,
                GraphEdge.target_id == dst_id,
            )
            .first()
        )
        w1 = e1.weight if e1 else 0
    finally:
        db.close()
    backend.add_confusion_edge("晕疫病", "炭疽叶斑病")

    db = SessionLocal()
    try:
        e2 = (
            db.query(GraphEdge)
            .filter(
                GraphEdge.relation == "易混淆",
                GraphEdge.source_id == src_id,
                GraphEdge.target_id == dst_id,
            )
            .first()
        )
        w2 = e2.weight if e2 else 0
    finally:
        db.close()
    assert w1 == 1 and w2 == 2, f"易混淆边 weight 应累计：{w1} → {w2}"
