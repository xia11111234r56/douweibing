"""通用 checkpoint 评估：任意 checkpoint × 任意评估目录（可多个），输出一致率。

用于消融表：同一模型在 89 张测试集与 178 张合并集（val+test）上的对比，
避免为每个变体重复写评估代码。

用法（ml/ 目录下）：
    python eval_checkpoint.py <checkpoint> [<评估目录> ...]
示例：
    python eval_checkpoint.py checkpoints/best_finetune_balanced.pth \
        data/organized/test experiments/eval_178
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402

from ablation import CachedFolder  # noqa: E402
from config import BATCH_SIZE  # noqa: E402
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ckpt", type=Path, help="checkpoint 文件")
    parser.add_argument("roots", type=Path, nargs="+", help="评估目录（可多个）")
    args = parser.parse_args()

    model = build_model(pretrained=False).to(DEVICE)
    model.load_state_dict(torch.load(args.ckpt, map_location=DEVICE))
    model.eval()

    for root in args.roots:
        ds = CachedFolder(root, train=False)
        loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
        correct, total = 0, 0
        with torch.no_grad():
            for x, y in loader:
                total += y.size(0)
                correct += (model(x.to(DEVICE)).argmax(1).cpu() == y).sum().item()
        acc = correct / total
        print(f"{root.name}\t{acc:.4f}\t({correct}/{total})")


if __name__ == "__main__":
    main()
