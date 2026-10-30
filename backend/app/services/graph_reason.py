"""图谱领域逻辑：防治路径推荐 + 可解释推理链。

与具体图引擎无关（SQL / Neo4j 双后端共用）。防治数据以 treatments 表为唯一事实源，
药名子串匹配映射「药剂」图节点 —— 保证不变式：推理链里的药剂必然出现在对应严重度
的方案文本中（消除「图谱防治边只覆盖中度」与 treatments 表两套数据打架的问题）。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Disease, Pesticide, Treatment
from .graph_backend import get_graph_backend

SEVERITIES = ("轻度", "中度", "重度")


def recommend_pesticides(
    db: Session, disease_id: int | None, severity: str | None
) -> list[dict]:
    """按严重度取 treatments 方案文本 → 药名子串匹配 → 图谱「药剂」节点。

    返回 [{name, usage(所在方案全文), severity, node(图节点或 None)}]。
    """
    if not disease_id or not severity:
        return []
    backend = get_graph_backend()
    rows = (
        db.query(Treatment)
        .filter(Treatment.disease_id == disease_id, Treatment.severity_level == severity)
        .all()
    )
    pesticide_names = [p.name for p in db.query(Pesticide).all()]
    pesticide_names.sort(key=len, reverse=True)  # 长名优先，避免前缀子串误匹配
    out: list[dict] = []
    seen: set[str] = set()
    for t in rows:
        content = t.content or ""
        for name in pesticide_names:
            if name and name in content and name not in seen:
                seen.add(name)
                out.append(
                    {
                        "name": name,
                        "usage": content,
                        "severity": severity,
                        "node": backend.find_node(db, label="药剂", name=name),
                    }
                )
    return out


def _edge_to(db, backend, from_id: int, to_id: int, relation: str) -> int | None:
    """找 from→to 之间指定关系的边 id（用于路径高亮）；无则 None。"""
    for e in backend.follow(db, from_id, relation=relation, direction="out", limit=200):
        if e["other_id"] == to_id:
            return e["edge_id"]
    return None


def build_reason(
    db: Session, disease_name: str, severity: str | None, weather: str | None
) -> dict:
    """组装可解释推理链：寄主感染 → 症状表现 → 环境适宜 → 防治用药，每步带依据。

    返回结构与 schemas.graph_reason.ReasoningChain 一致（字段名 source/target）。
    """
    backend = get_graph_backend()
    engine = backend.engine_name()

    if disease_name == "健康":
        return {
            "engine": engine,
            "disease": "健康",
            "severity": None,
            "weather": weather,
            "steps": [],
            "summary": "识别为健康叶片，无需防治。",
            "controls": [],
            "matched_symptoms": [],
            "note": "健康类无病害防治路径。",
        }

    disease_row = db.query(Disease).filter(Disease.name == disease_name).first()
    if disease_row is None:
        return {
            "engine": engine,
            "disease": disease_name,
            "severity": severity,
            "weather": weather,
            "steps": [],
            "summary": "",
            "controls": [],
            "matched_symptoms": [],
            "note": "知识库中未收录该病害。",
        }

    d_node = backend.find_node(db, label="病害", name=disease_name)
    steps: list[dict] = []
    notes: list[str] = []
    order = 0

    # 1. 寄主 → 感染 → 病害（反向沿「感染」边找寄主）
    if d_node is not None:
        host_edges = backend.follow(db, d_node["id"], relation="感染", direction="in", limit=1)
        if host_edges:
            order += 1
            e = host_edges[0]
            steps.append(
                {
                    "order": order,
                    "hop": "寄主→病害",
                    "relation": "感染",
                    "source": e["other_name"],
                    "target": disease_name,
                    "source_label": "寄主",
                    "target_label": "病害",
                    "weight": e["weight"],
                    "text": f"{e['other_name']}是{disease_name}的寄主作物，寄主带菌是初侵染源之一。",
                }
            )
    if not steps:
        order += 1
        steps.append(
            {
                "order": order,
                "hop": "寄主→病害",
                "relation": "感染",
                "source": "绿豆",
                "target": disease_name,
                "source_label": "寄主",
                "target_label": "病害",
                "weight": None,
                "text": "绿豆是绿豆类病害的寄主作物，寄主带菌是初侵染源之一。",
            }
        )

    # 2. 病害 → 表现为 → 症状（前 3，与图谱症状节点同源）
    symptoms = [s for s in (disease_row.symptoms or "").split("，") if len(s) > 1][:3]
    for sym in symptoms:
        order += 1
        steps.append(
            {
                "order": order,
                "hop": "病害→症状",
                "relation": "表现为",
                "source": disease_name,
                "target": sym,
                "source_label": "病害",
                "target_label": "症状",
                "weight": None,
                "text": f"典型症状：{sym}。",
            }
        )

    # 3. 病害 → 适宜 → 环境（weather 精确匹配「适宜」边）
    if weather and d_node is not None:
        matched = False
        for e in backend.follow(db, d_node["id"], relation="适宜", direction="out", limit=50):
            if e["other_name"] == weather:
                order += 1
                steps.append(
                    {
                        "order": order,
                        "hop": "病害→环境",
                        "relation": "适宜",
                        "source": disease_name,
                        "target": weather,
                        "source_label": "病害",
                        "target_label": "环境",
                        "weight": e["weight"],
                        "text": f"当前天气「{weather}」命中图谱「适宜」边，佐证该病害判定。",
                    }
                )
                matched = True
                break
        if not matched:
            notes.append(f"图谱无「{weather}」对应的适宜关系，环境段省略。")

    # 4. 病害 → 防治 → 药剂（按严重度；treatments 为唯一事实源）
    controls = recommend_pesticides(db, disease_row.id, severity) if severity else []
    for c in controls[:3]:
        order += 1
        steps.append(
            {
                "order": order,
                "hop": "病害→防治",
                "relation": "防治",
                "source": disease_name,
                "target": c["name"],
                "source_label": "病害",
                "target_label": "药剂",
                "weight": None,
                "text": f"{severity}防治：{c['usage']}",
            }
        )
    if severity and not controls:
        notes.append(f"「{severity}」未检索到明确药剂（该等级方案可能无药名）。")

    summary = (
        f"综合『寄主感染 → 症状表现 → 环境适宜 → 防治用药』图谱路径，"
        f"判定为「{disease_name}」（{severity or '未分级'}），"
        f"建议按{'、'.join(c['name'] for c in controls[:2]) or '对应'}防治用药。"
    )
    return {
        "engine": engine,
        "disease": disease_name,
        "severity": severity,
        "weather": weather,
        "steps": steps,
        "summary": summary,
        "controls": controls[:3],
        "matched_symptoms": symptoms,
        "note": "；".join(notes) or None,
    }


def build_path(
    db: Session,
    *,
    disease: str | None = None,
    severity: str | None = None,
    weather: str | None = None,
    from_id: int | None = None,
    to_id: int | None = None,
    max_hops: int = 5,
) -> dict:
    """防治路径推荐。

    Mode A（pair）：from_id → to_id 任意两节点最短路径（多跳图算法）。
    Mode B（disease）：病害节点 → 按严重度检索防治药剂（+可选环境段），组装路径与高亮。
    """
    backend = get_graph_backend()
    engine = backend.engine_name()

    # Mode A：最短路径（含边高亮）
    if from_id is not None and to_id is not None:
        node_path = backend.shortest_path(db, from_id, to_id, max_hops)
        if node_path is None:
            return {
                "engine": engine, "mode": "pair", "path": [], "steps": [],
                "highlight": {"node_ids": [], "edge_ids": []},
                "note": f"未找到节点 {from_id} → {to_id} 的最短路径（≤{max_hops} 跳）。",
            }
        names = [n["name"] for n in node_path]
        edge_ids: list[int] = []
        for i in range(len(node_path) - 1):
            eid = _edge_to(db, backend, node_path[i]["id"], node_path[i + 1]["id"], None)
            if eid:
                edge_ids.append(eid)
        steps = [
            {
                "order": i + 1,
                "relation": "→",
                "source": names[i],
                "target": names[i + 1],
                "source_label": node_path[i]["label"],
                "target_label": node_path[i + 1]["label"],
                "text": f"{names[i]} → {names[i + 1]}",
            }
            for i in range(len(node_path) - 1)
        ]
        return {
            "engine": engine, "mode": "pair", "path": node_path, "steps": steps,
            "highlight": {"node_ids": [n["id"] for n in node_path], "edge_ids": edge_ids},
            "note": f"最短路径 {len(node_path) - 1} 跳：{' → '.join(names)}。",
        }

    # Mode B：病害 → 防治路径
    d_node = backend.find_node(db, label="病害", name=disease) if disease else None
    if d_node is None:
        return {
            "engine": engine, "mode": "disease", "disease": disease,
            "severity": severity, "weather": weather, "path": [], "steps": [],
            "highlight": {"node_ids": [], "edge_ids": []},
            "note": f"图谱中不存在病害节点「{disease}」。",
        }

    path_nodes = [{"id": d_node["id"], "label": "病害", "name": disease, "type": "start"}]
    highlight_nodes = [d_node["id"]]
    highlight_edges: list[int] = []
    steps: list[dict] = []
    notes: list[str] = []

    # 药剂段（treatments 唯一事实源 → 图谱药剂节点；边仅中度种子存在，其余高亮节点）
    disease_row = db.query(Disease).filter(Disease.name == disease).first()
    controls = (
        recommend_pesticides(db, disease_row.id if disease_row else None, severity)
        if severity
        else []
    )
    for c in controls[:3]:
        if c["node"] is None:
            continue
        path_nodes.append(
            {"id": c["node"]["id"], "label": "药剂", "name": c["name"], "type": "control"}
        )
        highlight_nodes.append(c["node"]["id"])
        eid = _edge_to(db, backend, d_node["id"], c["node"]["id"], "防治")
        if eid:
            highlight_edges.append(eid)
        steps.append(
            {
                "order": len(steps) + 1,
                "relation": "防治",
                "source": disease,
                "target": c["name"],
                "source_label": "病害",
                "target_label": "药剂",
                "text": f"{severity}防治：{c['usage']}",
            }
        )
    if severity and not controls:
        notes.append(f"「{severity}」未检索到防治药剂。")

    # 环境段：weather 匹配「适宜」边
    if weather:
        matched = False
        for e in backend.follow(db, d_node["id"], relation="适宜", direction="out", limit=50):
            if e["other_name"] == weather:
                path_nodes.append(
                    {"id": e["other_id"], "label": "环境", "name": weather, "type": "env"}
                )
                highlight_nodes.append(e["other_id"])
                highlight_edges.append(e["edge_id"])
                steps.append(
                    {
                        "order": len(steps) + 1,
                        "relation": "适宜",
                        "source": disease,
                        "target": weather,
                        "source_label": "病害",
                        "target_label": "环境",
                        "text": f"当前天气「{weather}」适宜该病害发生（图谱「适宜」边）。",
                    }
                )
                matched = True
                break
        if not matched:
            notes.append(f"图谱无「{weather}」对应的适宜关系，环境段省略。")

    return {
        "engine": engine,
        "mode": "disease",
        "disease": disease,
        "severity": severity,
        "weather": weather,
        "path": path_nodes,
        "steps": steps,
        "highlight": {"node_ids": highlight_nodes, "edge_ids": highlight_edges},
        "note": "；".join(notes),
    }
