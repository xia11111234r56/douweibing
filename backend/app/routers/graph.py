"""动态知识图谱（双后端图引擎抽象层，兼容 ECharts 前端）。

接口契约：现有 4 端点（整图/按类查/建节点/建边）形状不变，内部切换到图引擎抽象层
（SQL+networkx 或 Neo4j，见 services.graph_backend）。新增图算法端点：
path（防治路径推荐）、reason（可解释推理链）、engine（引擎状态/降级暴露）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Disease, GraphNode, User
from ..schemas import (
    EngineInfo,
    GraphEdgeOut,
    GraphNodeOut,
    GraphPathOut,
    ReasoningChain,
)
from ..services.auth import log_operation, require_admin
from ..services.graph_backend import get_graph_backend
from ..services.graph_reason import SEVERITIES, build_path, build_reason

router = APIRouter(tags=["graph"])


class NodeCreate(BaseModel):
    label: str
    name: str
    properties: dict | None = None


class EdgeCreate(BaseModel):
    source_id: int
    target_id: int
    relation: str
    weight: float = 1.0


@router.get("/api/graph")
def get_graph(db: Session = Depends(get_db)):
    """返回整图（nodes + edges），供 ECharts graph 渲染。形状与旧实现逐字段一致。"""
    return get_graph_backend().get_graph(db)


@router.get("/api/graph/nodes/{label}", response_model=list[GraphNodeOut])
def list_nodes(label: str, db: Session = Depends(get_db)):
    return get_graph_backend().list_nodes(db, label=label)


@router.post("/api/graph/nodes", response_model=GraphNodeOut)
def create_node(
    body: NodeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    node = get_graph_backend().upsert_node(
        label=body.label, name=body.name, properties=body.properties
    )
    log_operation(db, "graph.node.create", f"新增图谱节点：{body.label}/{body.name}", admin.id)
    return node


@router.post("/api/graph/edges", response_model=GraphEdgeOut)
def create_edge(
    body: EdgeCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    for nid in (body.source_id, body.target_id):
        if db.get(GraphNode, nid) is None:
            raise HTTPException(status_code=400, detail=f"节点 {nid} 不存在")
    edge = get_graph_backend().upsert_edge(
        source_id=body.source_id,
        target_id=body.target_id,
        relation=body.relation,
        weight=body.weight,
    )
    log_operation(db, "graph.edge.create", f"新增图谱关系：{body.relation}", admin.id)
    return edge


@router.get("/api/graph/engine", response_model=EngineInfo)
def graph_engine(db: Session = Depends(get_db)):
    """图引擎状态：当前生效引擎 + 节点/边数 + Neo4j 降级错误（透明暴露给前端/评委）。"""
    return get_graph_backend().engine_info(db)


@router.get("/api/graph/path", response_model=GraphPathOut)
def graph_path(
    disease: str | None = Query(None, description="病害名（Mode B 防治路径推荐）"),
    severity: str | None = Query(None, description="轻度/中度/重度"),
    weather: str | None = Query(None, description="天气档位（高温高湿/阴雨连绵/...）"),
    from_id: int | None = Query(None, description="Mode A 最短路径起点节点 id"),
    to_id: int | None = Query(None, description="Mode A 最短路径终点节点 id"),
    max_hops: int = Query(5, ge=1, le=8),
    db: Session = Depends(get_db),
):
    """防治路径推荐：Mode A 任意两节点最短路径；Mode B 病害 → 防治药剂路径。"""
    if severity is not None and severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity 须为 {'/'.join(SEVERITIES)}")
    if from_id is not None and to_id is not None:
        return build_path(db, from_id=from_id, to_id=to_id, max_hops=max_hops)
    if not disease:
        raise HTTPException(
            status_code=400, detail="请提供 disease（防治路径推荐）或 from_id+to_id（最短路径）"
        )
    if db.query(Disease).filter(Disease.name == disease).first() is None:
        raise HTTPException(status_code=404, detail=f"病害「{disease}」不存在")
    return build_path(db, disease=disease, severity=severity, weather=weather)


@router.get("/api/graph/reason", response_model=ReasoningChain)
def graph_reason(
    disease: str = Query(..., description="病害名（含「健康」）"),
    severity: str | None = Query(None, description="轻度/中度/重度"),
    weather: str | None = Query(None, description="天气档位"),
    db: Session = Depends(get_db),
):
    """可解释推理链：寄主感染 → 症状表现 → 环境适宜 → 防治用药，每步带依据。"""
    if severity is not None and severity not in SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity 须为 {'/'.join(SEVERITIES)}")
    if db.query(Disease).filter(Disease.name == disease).first() is None:
        raise HTTPException(status_code=404, detail=f"病害「{disease}」不存在")
    return build_reason(db, disease, severity, weather)
