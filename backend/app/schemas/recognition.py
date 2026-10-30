from pydantic import BaseModel, Field

from .graph_reason import ReasoningChain


class EnvInput(BaseModel):
    """多模态环境模态输入（用户可选填）。

    - 自动来源：EXIF 拍摄时间 + GPS → WorldClim 月平均气候回查
    - 用户输入：生育期 / 天气档位 / 种植方式
    """

    growth_stage: str | None = Field(
        None, description="生育期：苗期/分枝期/开花期/结荚期/成熟期"
    )
    weather: str | None = Field(
        None, description="天气档位：高温高湿/阴雨连绵/雨后天晴/晴热干旱/虫害盛发"
    )
    planting: str | None = Field(None, description="种植方式：露地/大棚")
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class RecognizeRequest(BaseModel):
    image_base64: str = Field(..., description="base64 编码的叶片图")
    env: EnvInput | None = None


class Candidate(BaseModel):
    disease_id: int | None = None
    name: str
    disease_type: str | None = None
    confidence: float


class RecognizeResponse(BaseModel):
    code: int = 200
    # 识别记录 id：小程序/Web 纠错反馈依赖它（本地 record 需保存后回传）。
    # 旧版响应无此字段，前端做可选兼容（null 时隐藏反馈入口）。
    id: int | None = None
    disease_id: int | None = None
    disease_name: str | None = None
    disease_type: str | None = None
    severity: str | None = None
    severity_desc: str | None = None
    confidence: float | None = None
    candidates: list[Candidate] = []
    treatments: list[dict] = []
    env: dict = {}
    # 图谱可解释推理链（识别完直接给「推荐依据」；图引擎失败为 None，前端隐藏）
    reasoning: ReasoningChain | None = None


class RecognitionOut(BaseModel):
    """识别历史记录（recognitions 表视图，含多模态上下文）。"""

    id: int
    disease_name: str | None = None
    disease_type: str | None = None
    severity: str | None = None
    confidence: float | None = None
    candidates: list[Candidate] = []
    env_metadata: dict | None = None
    image_path: str | None = None
    user_id: int | None = None
    is_anonymous: bool = False
    # 该记录是否已收到纠错反馈（recognition_feedback 表存在任意一行即 true），
    # 供 Web 识别记录页打「已纠错」标。
    has_feedback: bool = False
    created_at: str | None = None


class RecognitionPage(BaseModel):
    items: list[RecognitionOut]
    total: int
    # 当前筛选下已纠错的记录数（页头「已纠错 X 条」）
    corrected_count: int = 0
