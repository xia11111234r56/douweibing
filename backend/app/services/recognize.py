"""识别编排：图像分类 → 严重度 → 环境模态 → 知识规则 → 防治方案 → 图谱推理链 → 落库。"""
from __future__ import annotations

import io
import logging
import uuid

from PIL import Image
from sqlalchemy.orm import Session

from ..config import RECOGNITION_DIR
from ..models import Disease, Recognition
from ..schemas.recognition import Candidate, RecognizeResponse
from . import graph_reason, knowledge_rules, model_inference, severity as severity_svc
from .env import build_env_context
from .graph_backend import get_graph_backend

logger = logging.getLogger(__name__)

SEVERITY_DESC = {
    "轻度": "叶片病斑少、面积小，对产量影响有限，及时防控即可。",
    "中度": "病斑明显增多，叶片功能受损，建议立即按方案用药并加强管理。",
    "重度": "病害大面积发生，需加大防治力度，必要时拔除病株防止扩散。",
}


def _save_image(image_bytes: bytes) -> str | None:
    """保存识别原图（缩放 ≤1280、JPEG q85），返回文件名；失败返回 None 不阻塞识别。"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img = img.convert("RGB")
        img.thumbnail((1280, 1280))
        RECOGNITION_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.jpg"
        img.save(RECOGNITION_DIR / name, "JPEG", quality=85)
        return name
    except Exception:  # noqa: BLE001
        return None


def recognize(
    image_bytes: bytes, env_input, db: Session, user_id: int | None = None
) -> RecognizeResponse:
    """执行完整识别流程。模型未就绪时抛出 ModelNotReady（由路由转 503）。

    user_id：可选鉴权绑定——Web 登录用户识别归属本人，小程序匿名调用为 None。
    """
    # 1. 图像分类（top-5 候选）
    candidates: list[dict] = model_inference.predict_topk(image_bytes, k=5)

    # 2. 严重度分级（深度模型 mobilenetv3+LR；面积比法仅作模型缺失时兜底）
    severity, lesion_ratio, sev_note = severity_svc.compute_severity(image_bytes)

    # 3. 环境模态（EXIF + WorldClim 回查 + 用户输入）
    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception:
        img = None
    env = build_env_context(img, env_input)

    # 4. 知识规则后验修正
    candidates = knowledge_rules.adjust_candidates(candidates, env)

    # 5. top1 结果 + 防治方案
    top = candidates[0]
    disease = db.query(Disease).filter(Disease.name == top["name"]).first()
    top["disease_id"] = disease.id if disease else None

    treatments: list[dict] = []
    if disease and severity:
        for t in disease.treatments:
            if t.severity_level == severity:
                treatments.append(
                    {
                        "method_type": t.method_type,
                        "content": t.content,
                        "severity_level": t.severity_level,
                    }
                )

    # 6. 图谱可解释推理链（识别完直接给「推荐依据」；图失败返回 None，绝不拖垮识别）
    reasoning = None
    try:
        reasoning = graph_reason.build_reason(db, top["name"], severity, env.get("weather"))
    except Exception:  # noqa: BLE001
        logger.exception("图谱推理链构建失败，已跳过（识别不受影响）")

    # 7. 落库（识别记录，含多模态上下文与归属用户；原图存盘供详情回显）
    record = Recognition(
        image_path=_save_image(image_bytes),
        user_id=user_id,
        disease_id=disease.id if disease else None,
        severity=severity,
        confidence=top["confidence"],
        candidates=candidates,
        env_metadata=env,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    # 8. 图谱动态回写：识别热度 +1（「动态知识图谱」随使用生长；失败不致命）
    try:
        get_graph_backend().bump_heat(top["name"])
    except Exception:  # noqa: BLE001
        logger.warning("图谱热度回写失败（忽略）")

    return RecognizeResponse(
        id=record.id,
        disease_id=record.disease_id,
        disease_name=top["name"],
        disease_type=top["disease_type"],
        severity=severity,
        severity_desc=SEVERITY_DESC.get(severity) if severity else sev_note,
        confidence=top["confidence"],
        candidates=[Candidate(**c) for c in candidates],
        treatments=treatments,
        env=env,
        reasoning=reasoning,
    )
