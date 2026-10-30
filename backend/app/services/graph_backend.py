"""图引擎抽象层：统一接口 + 工厂 + 降级语义。

双后端架构（让项目名「动态知识图谱」名副其实）：
- sql 后端：三元组表（graph_nodes / graph_edges）为唯一事实源，读时灌入内存
  networkx 有向图跑图算法（最短路径 / 邻居 / 路径推荐），写操作 SQLAlchemy 持久化
  ——生产 / 服务器默认，零额外依赖，稳定可交付。
- neo4j 后端：真图数据库，跑原生 Cypher 图算法；写操作先落 SQL 再尽力镜像，
  SQL 仍是唯一事实源，漂移可由 data/sync_neo4j.py 全量重建自愈。

降级语义：懒连接 + 运行期回落，绝不启动即失败。Neo4j 缺失 / 查询失败 → 告警日志 +
该请求回落 SQL 并照常 200；当前生效引擎经 GET /api/graph/engine 透明暴露（演示时
可直接给评委看降级设计）。

接口约定：图内节点用 graph_nodes.id（≠ 业务表 diseases.id）；跨表引用一律按
「label + name」定位（如 find_node(label="病害", name="晕疫病")），避免 id 空间混淆。
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol

from sqlalchemy.orm import Session

from ..config import GRAPH_ENGINE

logger = logging.getLogger(__name__)

_backend: "GraphBackend | None" = None
_backend_lock = threading.Lock()


class GraphBackend(Protocol):
    """图引擎统一接口（SQL / Neo4j 双实现）。"""

    def engine_name(self) -> str: ...

    def engine_info(self, db: Session) -> dict: ...

    # ---- 读 ----
    def get_graph(self, db: Session) -> dict: ...
    def list_nodes(self, db: Session, label: str | None = None) -> list[dict]: ...
    def find_node(
        self, db: Session, *, label: str, name: str
    ) -> dict | None: ...
    def find_node_by_id(self, db: Session, node_id: int) -> dict | None: ...
    def follow(
        self,
        db: Session,
        node_id: int,
        *,
        relation: str | None = None,
        direction: str = "out",
        limit: int = 10,
    ) -> list[dict]: ...
    def shortest_path(
        self, db: Session, from_id: int, to_id: int, max_hops: int = 5
    ) -> list[dict] | None: ...
    def subgraph(self, db: Session, node_ids: list[int]) -> dict: ...

    # ---- 写（自开会话隔离提交，SQL 为事实源；Neo4j 尽力镜像，失败不致命）----
    def upsert_node(
        self, *, label: str, name: str, properties: dict | None = None
    ) -> dict: ...
    def upsert_edge(
        self, *, source_id: int, target_id: int, relation: str, weight: float = 1.0
    ) -> dict: ...
    def bump_heat(self, disease_name: str, delta: int = 1) -> int | None: ...
    def add_confusion_edge(
        self, pred_disease_name: str, corrected_disease_name: str
    ) -> int | None: ...


def get_graph_backend() -> GraphBackend:
    """按 GRAPH_ENGINE 懒加载单例。Neo4j 连接失败 → 回落 SQL（绝不启动即失败）。

    neo4j 分支在首次调用时才 import（阶段二引入 graph_backend_neo4j 前不会报错），
    任何初始化异常都降级为 SQL 并告警。
    """
    global _backend
    with _backend_lock:
        if _backend is not None:
            return _backend
        if GRAPH_ENGINE == "neo4j":
            try:
                from .graph_backend_neo4j import Neo4jGraphBackend

                candidate = Neo4jGraphBackend()
                if candidate.probe():
                    _backend = candidate
                    logger.info("图引擎：Neo4j（%s）", candidate.uri)
                else:
                    logger.warning("Neo4j 不可达，回落 SQL 图引擎")
                    from .graph_backend_sql import SQLGraphBackend

                    _backend = SQLGraphBackend()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Neo4j 初始化失败（%s），回落 SQL 图引擎", exc)
                from .graph_backend_sql import SQLGraphBackend

                _backend = SQLGraphBackend()
        else:
            from .graph_backend_sql import SQLGraphBackend

            _backend = SQLGraphBackend()
        return _backend
