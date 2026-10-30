"""SQL 图谱 → Neo4j 全量重建（幂等可重跑，db_id 为键）。

SQL 表仍是唯一事实源；本脚本把 graph_nodes/graph_edges 整体写入 Neo4j，
用于首次接入或漂移自愈（开发库重灌种子后跑一遍即可）。
用法（backend 目录下）：
    .venv\\Scripts\\python.exe -m app.data.sync_neo4j
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from neo4j import GraphDatabase  # noqa: E402

from app.config import NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import GraphEdge, GraphNode  # noqa: E402
from app.services.graph_backend_neo4j import LABEL_MAP, RELATION_MAP  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        nodes = db.query(GraphNode).all()
        edges = db.query(GraphEdge).all()
    finally:
        db.close()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for n in nodes:
            ascii_label = LABEL_MAP.get(n.label)
            if ascii_label is None:
                print(f"跳过未知标签节点：{n.label}/{n.name}")
                continue
            props = dict(n.properties or {})
            heat = props.get("heat")
            s.run(
                f"MERGE (n:{ascii_label} {{db_id: $id}}) "
                "SET n.name = $name, n.kind = $kind, n.props_json = $props_json, n.heat = $heat",
                id=n.id, name=n.name, kind=n.label,
                props_json=json.dumps(props, ensure_ascii=False),
                heat=heat if isinstance(heat, (int, float)) else None,
            )
        for e in edges:
            ascii_rel = RELATION_MAP.get(e.relation)
            if ascii_rel is None:
                print(f"跳过未知关系边：{e.relation}")
                continue
            s.run(
                f"MATCH (a {{db_id: $src}}), (b {{db_id: $dst}}) "
                f"MERGE (a)-[r:{ascii_rel}]->(b) "
                "SET r.db_id = $id, r.relation_zh = $zh, r.weight = $weight, "
                "r.source_db = $src, r.target_db = $dst",
                src=e.source_id, dst=e.target_id, id=e.id, zh=e.relation, weight=e.weight,
            )
    with driver.session() as s:
        nc = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        ec = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    driver.close()
    print(f"Neo4j 同步完成：{nc} 节点 / {ec} 边（SQL {len(nodes)} 节点 / {len(edges)} 边）")


if __name__ == "__main__":
    main()
