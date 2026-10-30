"""严重度深度模型推理（ONNX）。

- 模型文件：backend/models/severity.onnx（由 ml/export_severity_onnx.py 导出，输入 448×448）
- 输出索引 → 严重度：0=轻度 1=中度 2=重度
- 依据：用户 179 张人工标注，mobilenetv3 骨干(已在绿豆 10 类微调) + 逻辑回归，
  5 折交叉验证一致率 0.844（见 ml/experiments/severity_cv.json）。面积比类方法
  （颜色形态学 0.32、MobileSAM 面积比）在主观图级标注上无法对齐，故深度模型为主判定。
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

from ..config import MODEL_DIR

SEVERITY_LABELS = ["轻度", "中度", "重度"]
# ImageNet 归一化参数（与 ml/train_severity.py 一致）
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
SIZE = 448

_session = None


class SeverityModelNotReady(Exception):
    """严重度模型未就绪（severity.onnx 缺失时抛出）。"""


def load_severity_model():
    """加载并缓存 ONNX 会话；模型缺失时抛出 SeverityModelNotReady。"""
    global _session
    if _session is not None:
        return _session
    path = MODEL_DIR / "severity.onnx"
    if not path.exists():
        raise SeverityModelNotReady("严重度模型未就绪：backend/models/severity.onnx 缺失")
    import onnxruntime as ort

    _session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return _session


def preprocess(image_bytes: bytes) -> np.ndarray:
    """解码 → 缩放到 448×448 → RGB → ImageNet 归一化 → [1,3,448,448] float32。"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((SIZE, SIZE), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return np.ascontiguousarray(arr.transpose(2, 0, 1)[None, ...])


def predict_severity(image_bytes: bytes) -> str | None:
    """返回 轻/中/重 之一；模型缺失或推理失败返回 None（调用方回退面积比）。"""
    try:
        sess = load_severity_model()
        x = preprocess(image_bytes)
        input_name = sess.get_inputs()[0].name
        logits = sess.run(None, {input_name: x})[0][0]
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        return SEVERITY_LABELS[int(np.argmax(probs))]
    except Exception:  # noqa: BLE001
        return None
