"""ONNX 分类模型推理（M1 接入点）。

- 模型文件：backend/models/classifier.onnx（由 ml/export_onnx.py 导出）
- 分类标签顺序：由导出时写入的 labels.json 决定（与 ml/config.py CLASS_NAMES 一致，10 类）
- 预处理与训练一致：resize(224×224) + ImageNet 归一化
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import MODEL_DIR

# 疾病类型映射（与 backend/app/data/seed.py DISEASE_TYPES 一致）
DISEASE_TYPE_MAP = {
    "健康": "健康",
    "晕疫病": "细菌性病害",
    "炭疽叶斑病": "真菌性病害",
    "轮纹叶斑病": "真菌性病害",
    "枯萎病": "真菌性病害",
    "病毒病": "病毒性病害",
    "细菌性疫病": "细菌性病害",
    "叶腐病": "真菌性病害",
    "细菌性萎蔫": "细菌性病害",
    "虫食": "虫害",
}

# ImageNet 归一化参数（与 ml/train_classifier.py 一致）
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_session = None
_labels: dict[str, str] = {}


class ModelNotReady(Exception):
    """模型未就绪（训练导出 ONNX 之前调用识别会抛出）。"""


def _labels_path() -> Path:
    return MODEL_DIR / "labels.json"


def load_classifier():
    """加载并缓存 ONNX 会话；模型缺失时抛出 ModelNotReady。"""
    global _session
    if _session is not None:
        return _session
    path = MODEL_DIR / "classifier.onnx"
    if not path.exists():
        raise ModelNotReady(
            "模型未就绪：请先完成模型训练，用 ml/export_onnx.py 导出 "
            "classifier.onnx 到 backend/models/"
        )
    import onnxruntime as ort

    _session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    if _labels_path().exists():
        global _labels
        _labels = json.loads(_labels_path().read_text(encoding="utf-8"))
    return _session


def preprocess(image_bytes: bytes) -> np.ndarray:
    """解码 → 256×256 → 224×224（两段 BILINEAR）→ RGB → ImageNet 归一化 → [1,3,224,224] float32。

    两段缩放与训练评估协议（ml/ablation.py CachedFolder：缓存 256 再缩 224）保持一致，
    避免"原图直缩 224"造成的 1 张边界图预测翻转（见 ml/eval_protocol.py，-1.1% gap）。
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = img.resize((256, 256), Image.BILINEAR)
    img = img.resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    # HWC → CHW
    arr = arr.transpose(2, 0, 1)[None, ...]
    return np.ascontiguousarray(arr)


def predict_topk(image_bytes: bytes, k: int = 3) -> list[dict]:
    """返回前 k 个候选：{"disease_id","name","disease_type","confidence"}。"""
    sess = load_classifier()
    x = preprocess(image_bytes)
    input_name = sess.get_inputs()[0].name
    logits = sess.run(None, {input_name: x})[0][0]

    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()

    order = np.argsort(probs)[::-1][:k]
    out = []
    for idx in order:
        name = _labels.get(str(idx), "")
        dtype = DISEASE_TYPE_MAP.get(name, "未知")
        out.append({
            "disease_id": None,
            "name": name,
            "disease_type": dtype,
            "confidence": round(float(probs[idx]), 4),
        })
    return out
