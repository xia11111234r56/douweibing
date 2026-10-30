"""部署一致性：torch checkpoint vs 导出 ONNX 逐图对比。

双引擎各自跑同一批测试图，输出 {图名: argmax} 到 json。
    python check_onnx_parity.py torch   out_torch.json    # 用 ml/.venv
    python check_onnx_parity.py onnx    out_onnx.json     # 用 backend/.venv
比对两个 json 的差异即可（不要求同进程同时有 torch+onnxruntime）。

预处理与 backend/app/services/model_inference.py 完全一致：
    PIL resize(256,256,BILINEAR) → resize(224,224,BILINEAR) → /255 → ImageNet 归一化 → CHW。
（两段缩放与训练评估协议 ml/ablation.py CachedFolder 一致，见 ml/eval_protocol.py）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

TEST_ROOT = Path(r"d:\dc2\ml\data\organized\test")
CKPT = Path(r"d:\dc2\ml\checkpoints\best_finetune.pth")
ONNX = Path(r"d:\dc2\backend\models\classifier.onnx")

SORTED_CLASSES = ["健康", "叶腐病", "晕疫病", "枯萎病", "炭疽叶斑病",
                  "病毒病", "细菌性疫病", "细菌性萎蔫", "虫食", "轮纹叶斑病"]


def preprocess(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    img = img.resize((256, 256), Image.BILINEAR)
    img = img.resize((224, 224), Image.BILINEAR)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    return np.ascontiguousarray(arr.transpose(2, 0, 1)[None, ...])


def collect(engine: str) -> dict:
    files = sorted(p for p in TEST_ROOT.rglob("*")
                   if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"})
    preds = {}
    if engine == "torch":
        import torch
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from train_classifier import build_model
        model = build_model(pretrained=False).eval()
        model.load_state_dict(torch.load(CKPT, map_location="cpu"))
        with torch.no_grad():
            for p in files:
                x = torch.from_numpy(preprocess(p))
                preds[p.name] = int(model(x).argmax(1).item())
    else:
        import onnxruntime as ort
        sess = ort.InferenceSession(str(ONNX), providers=["CPUExecutionProvider"])
        name = sess.get_inputs()[0].name
        for p in files:
            preds[p.name] = int(sess.run(None, {name: preprocess(p)})[0][0].argmax())
    return preds


if __name__ == "__main__":
    engine, out = sys.argv[1], sys.argv[2]
    preds = collect(engine)
    Path(out).write_text(json.dumps(preds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{engine}] {len(preds)} 张 → {out}")
    if engine == "torch":
        # 顺带报告 test89 准确率（用 labels.json 顺序不可靠，直接用 SORTED 名映射）
        # 目录结构 = 类名/图名，labels 顺序 = sorted class names
        truth = {p.name: p.parent.name for p in TEST_ROOT.rglob("*") if p.is_file()}
        hit = sum(SORTED_CLASSES[v] == truth[n] for n, v in preds.items())
        print(f"[torch] test89 一致率: {hit}/{len(preds)} = {hit/len(preds):.4f}")
