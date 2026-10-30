"""全局配置：从 backend/.env 或环境变量读取，未配置时使用开发默认值。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
load_dotenv(BASE_DIR / ".env")

# 数据库连接串：开发默认 SQLite，生产用 MySQL
# 例：mysql+pymysql://root:password@localhost:3306/dc2
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'app.db'}",
)

# 模型目录（ONNX / 其他推理资产）
MODEL_DIR = Path(os.getenv("MODEL_DIR", str(BASE_DIR / "models")))

# 上传图片目录
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))

# 空间数据目录（GeoJSON / WorldClim 栅格 / FAOSTAT CSV）
SPATIAL_DIR = Path(os.getenv("SPATIAL_DIR", str(BASE_DIR.parent / "data" / "spatial")))

# 识别原图目录（生产 /opt/dc2/data/recognitions，部署包不包含）
RECOGNITION_DIR = Path(
    os.getenv("RECOGNITION_DIR", str(BASE_DIR.parent / "data" / "recognitions"))
)

# 图引擎抽象层：sql = 三元组表 + networkx（生产/服务器默认，零额外依赖）；
# neo4j = 真图数据库（本地演示/验证，用 Cypher 跑图算法）。
# Neo4j 不可达时自动回落 sql（懒连接 + 运行期降级，绝不启动即失败）。
GRAPH_ENGINE = os.getenv("GRAPH_ENGINE", "sql")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# JWT（默认密钥 ≥32 字节，生产务必用环境变量覆盖）
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-0123456789abcdef")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7

# 天气 API（可选，预留）
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

# 可训练分类白名单（纠错闭环专用，防 ONNX labels 索引漂移）。
# 必须与 ml/config.py CLASS_NAMES 保持完全一致（同序同集合）；后端种子数据
# disease.name 也复用这套名称。任何新类别必须先走 ml 全流程重训，禁止在
# 仅改此名单后重导出 ONNX（会错位）。
TRAINABLE_CLASS_NAMES = [
    "健康",
    "晕疫病",
    "炭疽叶斑病",
    "轮纹叶斑病",
    "枯萎病",
    "病毒病",
    "细菌性疫病",
    "叶腐病",
    "细菌性萎蔫",
    "虫食",
]


def ensure_dirs() -> None:
    """确保运行所需目录存在。"""
    for d in (MODEL_DIR, UPLOAD_DIR, SPATIAL_DIR, RECOGNITION_DIR):
        d.mkdir(parents=True, exist_ok=True)
