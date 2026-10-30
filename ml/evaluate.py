"""模型评估：测试集准确率 / 混淆矩阵 / 严重度（如配置）/ 推理一致性。

用法：python evaluate.py [--root 评估目录]
    --root 默认 ORGANIZED_DIR/test（标准 89 张）；可传 experiments/eval_178 等合并集。
输出：experiments/eval_report.json + 混淆矩阵图 experiments/confusion_matrix.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# Windows 中文字体（混淆矩阵中文标签）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False
import numpy as np
import torch
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from torchvision import datasets, transforms

from config import (  # noqa: E402
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    IMG_SIZE,
    ORGANIZED_DIR,
    TARGET_ACCURACY,
    WORKERS,
)
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def load_test(root: Path):
    if not root.exists():
        print(f"[错误] 评估目录不存在: {root}")
        sys.exit(1)
    # 用 CachedFolder(train=False) 评估，与训练/ensemble/CV 完全同一预处理协议
    # （缓存 256×256 → resize 224×224），避免"原图直缩"与训练不一致（见 eval_protocol.py）
    from ablation import CachedFolder
    from torch.utils.data import DataLoader
    ds = CachedFolder(root, train=False)
    return ds, DataLoader(ds, batch_size=32, shuffle=False, num_workers=WORKERS)


def consistency_check(model, ds, n_images=20, repeats=5) -> float:
    """同一图重复推理，验证结果一致性（评审现场可能抽查）。"""
    import random
    import torch.nn.functional as F

    model.eval()
    random.seed(0)
    idx = random.sample(range(len(ds)), min(n_images, len(ds)))
    consistent = 0
    for i in idx:
        x, _ = ds[i]
        preds = []
        for _ in range(repeats):
            with torch.no_grad():
                preds.append(model(x.unsqueeze(0).to(DEVICE)).argmax(1).item())
        if len(set(preds)) == 1:
            consistent += 1
    return consistent / len(idx)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=None,
                        help="评估目录（默认 ORGANIZED_DIR/test）")
    args = parser.parse_args()
    root = args.root or (ORGANIZED_DIR / "test")
    print(f"[evaluate] 评估目录: {root}")
    ds, loader = load_test(root)
    model = build_model(pretrained=False).to(DEVICE)
    ckpt = CHECKPOINTS_DIR / "best_finetune.pth"
    if not ckpt.exists():
        print(f"[错误] 缺少模型权重: {ckpt}。请先训练")
        sys.exit(1)
    model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
    model.eval()

    y_true, y_pred = [], []
    with torch.no_grad():
        for x, y in loader:
            y_true += y.tolist()
            y_pred += model(x.to(DEVICE)).argmax(1).cpu().tolist()

    acc = accuracy_score(y_true, y_pred)
    # 注意：模型输出索引对应 CachedFolder 按字母序的类顺序（class_to_idx），
    # 与 config.CLASS_NAMES 顺序不同，必须用类名对齐标签。
    class_names = sorted(ds.class_to_idx, key=ds.class_to_idx.get)
    report = classification_report(
        y_true, y_pred, labels=list(range(len(class_names))),
        target_names=class_names, output_dict=True,
    )
    cons = consistency_check(model, ds)

    # 混淆矩阵图
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(class_names))))
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(9, 8))
    plt.imshow(cm, cmap="Blues")
    plt.colorbar()
    tick = list(range(len(class_names)))
    plt.xticks(tick, class_names, rotation=45, ha="right")
    plt.yticks(tick, class_names)
    for i in range(len(class_names)):
        for j in range(len(class_names)):
            plt.text(j, i, cm[i, j], ha="center", va="center",
                     color="white" if cm[i, j] > cm.max() / 2 else "black")
    plt.xlabel("预测")
    plt.ylabel("真实")
    plt.title("混淆矩阵")
    plt.tight_layout()
    plt.savefig(EXPERIMENTS_DIR / "confusion_matrix.png", dpi=150)

    result = {
        "test_accuracy": round(acc, 4),
        "target_accuracy": TARGET_ACCURACY,
        "pass": acc >= TARGET_ACCURACY,
        "consistency": round(cons, 4),
        "per_class": report,
    }
    (EXPERIMENTS_DIR / "eval_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"测试集准确率: {acc:.4f} (目标 {TARGET_ACCURACY}) "
          f"{'✅通过' if acc >= TARGET_ACCURACY else '❌未达'}")
    print(f"推理一致性: {cons:.4f}")
    print(f"报告: {EXPERIMENTS_DIR / 'eval_report.json'}")


if __name__ == "__main__":
    main()
