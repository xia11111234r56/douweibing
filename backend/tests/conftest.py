"""测试夹具：强制图引擎为 SQL，保证测试确定性与 Neo4j 是否安装/运行无关。

双后端架构下开发 .env 可能设 GRAPH_ENGINE=neo4j（本地演示真图数据库）；
config.load_dotenv 不覆盖已存在的环境变量，这里在导入 app 前硬置 GRAPH_ENGINE=sql，
测试永远走 SQL 后端（单测写方法也直接 import SQLGraphBackend），结果可复现。
"""
import os

os.environ["GRAPH_ENGINE"] = "sql"
