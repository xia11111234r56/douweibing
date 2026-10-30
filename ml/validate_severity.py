"""严重度分级人工标注验证：算法输出 vs 用户标注（轻/中/重）。

用户已按严重度人工标注一批绿豆叶图（未标病害种类）：
    D:\\dc2\\train\\0  = 轻度 mild
    D:\\dc2\\train\\2  = 中度 moderate
    D:\\dc2\\train\\4  = 重度 severe
本脚本对每张图跑颜色形态学快速路径（ml/config.py SEVERITY_THRESHOLDS，
轻≤6%、中≤25%、重>25%），与人工标注对比，输出混淆矩阵与一致率（真实指标，
不编造）。结果写 experiments/severity_validation.json，供论文/结题引用。

用法（ml/ 目录下）：python validate_severity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sklearn.metrics import confusion_matrix  # noqa: E402

from config import EXPERIMENTS_DIR  # noqa: E402
from severity_sam import severity_from_bytes  # noqa: E402

# 用户标注文件夹 → 语义等级
LABEL_DIRS = {
    "0": "轻度",  # mild
    "2": "中度",  # moderate
    "4": "重度",  # severe
}
TRAIN_ROOT = Path(__file__).resolve().parent.parent / "train"
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    if not TRAIN_ROOT.exists():
        print(f"[错误] 未找到标注数据: {TRAIN_ROOT}")
        sys.exit(1)

    y_true, y_pred, ratios = [], [], []
    n = 0
    for folder, label in LABEL_DIRS.items():
        d = TRAIN_ROOT / folder
        if not d.exists():
            print(f"[跳过] 缺失 {d}")
            continue
        files = sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT)
        for p in files:
            severity, ratio, note = severity_from_bytes(p.read_bytes(), use_sam=False)
            if severity is None:
                print(f"[失败] {p.name}: {note}")
                continue
            y_true.append(label)
            y_pred.append(severity)
            ratios.append(round(ratio, 4) if ratio is not None else None)
            n += 1
    if n == 0:
        print("[错误] 没有可评估的样本")
        sys.exit(1)

    labels = ["轻度", "中度", "重度"]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n

    # 每类召回（该人工级别中被算法正确判别的比例）
    per_class = {}
    for i, lab in enumerate(labels):
        tot = y_true.count(lab)
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        per_class[lab] = {
            "n": tot,
            "recall": round(correct / tot, 4) if tot else None,
        }

    result = {
        "n": n,
        "source": str(TRAIN_ROOT),
        "thresholds": "轻≤6% / 中≤25% / 重>25%（文献分级方案B）",
        "overall_agreement": round(acc, 4),
        "confusion_matrix_rows_true_cols_pred": {"labels": labels, "matrix": cm.tolist()},
        "per_class_recall": per_class,
        "note": "算法=颜色形态学快速路径（use_sam=False）；人工标注=用户（0轻/2中/4重）",
    }
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "severity_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"样本数: {n}")
    print("混淆矩阵（行=人工标注，列=算法输出）:")
    print("       " + "  ".join(f"{l:>4s}" for l in labels))
    for i, lab in enumerate(labels):
        print(f"{lab:>4s}  " + "  ".join(f"{v:>5d}" for v in cm[i]))
    print(f"\n总体一致率: {acc:.4f}")
    print(f"每类召回: { {k: v['recall'] for k, v in per_class.items()} }")
    print(f"报告: {EXPERIMENTS_DIR / 'severity_validation.json'}")


if __name__ == "__main__":
    main()
