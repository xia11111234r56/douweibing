"""模型辅助标注：对待标注池（pending_label）逐图推理，输出 Top-3 建议 + 严重度。

用途：绿豆_未知/邢台等未分类图片先用分类器给出建议标签，人工审核后入库，
补充小类（叶腐病/枯萎病/细菌性疫病/虫食）样本。

用法（ml/ 目录下）：
    python annotate_pool.py                    # 处理整个 pending_label
    python annotate_pool.py --pool 邢台_20260617
产物：experiments/pool_annotation.csv（utf-8-sig，Excel 可直接打开）
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import datasets, transforms

from config import (  # noqa: E402
    CHECKPOINTS_DIR,
    EXPERIMENTS_DIR,
    IMG_SIZE,
    ORGANIZED_DIR,
    PENDING_DIR,
)
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
TOP_K = 3

# 预测输出索引 → 类名（与训练一致：ImageFolder 按字母序）
_CLASSES_CACHE: list[str] | None = None


def class_order() -> list[str]:
    global _CLASSES_CACHE
    if _CLASSES_CACHE is None:
        ds = datasets.ImageFolder(str(ORGANIZED_DIR / "train"), allow_empty=True)
        _CLASSES_CACHE = ds.classes
    return _CLASSES_CACHE


def predict_proba(model, x: torch.Tensor) -> torch.Tensor:
    with torch.no_grad():
        return F.softmax(model(x.to(DEVICE)), dim=1).cpu()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default=None,
                        help="只处理指定子目录（如 邢台_20260617），默认全部")
    args = parser.parse_args()

    ckpt = CHECKPOINTS_DIR / "best_finetune.pth"
    if not ckpt.exists():
        print(f"[错误] 缺少 {ckpt}。请先训练分类器。")
        sys.exit(1)

    classes = class_order()
    model = build_model(pretrained=False, num_classes=len(classes)).to(DEVICE)
    model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
    model.eval()

    # 与统一预处理协议一致：两段 256→224（训练/评估/生产 ONNX 同款，见 ablation.py CachedFolder）
    transform = transforms.Compose([
        transforms.Resize((256, 256)),
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    pools = [args.pool] if args.pool else [p.name for p in PENDING_DIR.iterdir() if p.is_dir()]
    rows: list[dict] = []

    for pool in sorted(pools):
        pool_dir = PENDING_DIR / pool
        if not pool_dir.is_dir():
            print(f"[跳过] 不存在: {pool_dir}")
            continue
        images = sorted(
            p for p in pool_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        )
        print(f"[{pool}] 待标注 {len(images)} 张")
        for i, path in enumerate(images, 1):
            img = Image.open(path).convert("RGB")
            x = transform(img).unsqueeze(0)
            prob = predict_proba(model, x)[0]
            top_idx = prob.argsort(descending=True)[:TOP_K].tolist()
            top_names = [classes[k] for k in top_idx]
            top_probs = [round(float(prob[k]), 4) for k in top_idx]
            rows.append({
                "标注池": pool,
                "文件名": path.name,
                "建议标签": top_names[0],
                "置信度": top_probs[0],
                "候选2": top_names[1], "置信度2": top_probs[1],
                "候选3": top_names[2], "置信度3": top_probs[2],
                "待人工复核": "是" if top_probs[0] < 0.6 else "",
            })
            if i % 50 == 0 or i == len(images):
                print(f"  已处理 {i}/{len(images)}")

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    out = EXPERIMENTS_DIR / "pool_annotation.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n完成，共 {len(rows)} 张，结果: {out}")


if __name__ == "__main__":
    main()
