"""知识图谱推理链 / 防治路径推荐 / 引擎状态 响应模型。

双后端（SQL+networkx / Neo4j）图引擎共享同一套响应契约——前端只依赖这里的字段，
无论底层引擎是三元组表还是真图数据库，响应形状逐字段一致。
"""
from pydantic import BaseModel, Field


class ReasoningStep(BaseModel):
    """可解释推理链中的一步（一跳，带方向与依据文案）。"""

    order: int
    hop: str | None = None  # "寄主→病害"
    relation: str  # 感染 / 表现为 / 适宜 / 防治
    source: str  # 起点名（用 source/target 而非 from/to，避免 Python 关键字）
    target: str
    source_label: str | None = None
    target_label: str | None = None
    weight: float | None = None
    text: str = ""  # 该步的依据文案


class ControlRec(BaseModel):
    """防治用药推荐条目（来自 treatments 表，图谱药剂节点映射）。"""

    name: str
    usage: str | None = None
    severity: str | None = None


class ReasoningChain(BaseModel):
    """可解释推理链（识别响应 /api/recognize 与 /api/graph/reason 共享）。"""

    engine: str  # sql / neo4j
    disease: str | None = None
    severity: str | None = None
    weather: str | None = None
    steps: list[ReasoningStep] = []
    summary: str = ""
    controls: list[ControlRec] = []
    matched_symptoms: list[str] = []
    note: str | None = None  # 健康类 / 无环境匹配等补充说明


class GraphPathNode(BaseModel):
    """防治路径上的一个节点。"""

    id: int
    label: str
    name: str
    type: str = "node"  # start / control / env


class GraphPathOut(BaseModel):
    """防治路径推荐结果（/api/graph/path）。"""

    engine: str
    mode: str  # disease（病害→防治路径） / pair（任意两节点最短路径）
    disease: str | None = None
    severity: str | None = None
    weather: str | None = None
    path: list[GraphPathNode] = []
    steps: list[ReasoningStep] = []
    highlight: dict = Field(default_factory=dict)  # {"node_ids":[...], "edge_ids":[...]}
    note: str = ""


class EngineInfo(BaseModel):
    """图引擎状态（/api/graph/engine）——透明暴露降级状态，演示时可给评委看。"""

    engine: str
    node_count: int
    edge_count: int
    neo4j_error: str | None = None
