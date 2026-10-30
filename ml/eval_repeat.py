"""评估端确定性量化：同一模型、同一批图、同一预处理，重复评估 N 次。

背景：best_finetune.pth（B seed42）此前三次评估 test89 = 0.8315/0.8202/0.7865，
怀疑 GPU 推理（cuDNN）本身有非确定性。本脚本对同一模型在同一数据集上
重复 forward 评估，统计每次命中数波动，并做 CPU 对照（CPU 应确定）。

用法（ml/ 下）：
    python eval_repeat.py cuda [ckpt]   # GPU 重复 5 次
    python eval_repeat.py cpu  [ckpt]   # CPU 重复 3 次
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402

from ablation import CachedFolder  # noqa: E402
from config import BATCH_SIZE, ORGANIZED_DIR  # noqa: E402
from train_classifier import build_model  # noqa: E402


def run(device: str, ckpt: Path, repeats: int) -> None:
    model = build_model(pretrained=False).to(device)
    model.load_state_dict(torch.load(ckpt, map_location=device))
    model.eval()
    ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    hits = []
    for i in range(repeats):
        correct = 0
        with torch.no_grad():
            for x, y in loader:
                x = x.to(device)
                correct += (model(x).argmax(1).cpu() == y).sum().item()
        hits.append(correct)
        print(f"[{device}] run {i + 1}: {correct}/{len(ds)} = {correct / len(ds):.4f}")
    print(f"[{device}] 命中数序列: {hits}  跨度 {max(hits) - min(hits)} 张")


if __name__ == "__main__":
    device = sys.argv[1] if len(sys.argv) > 1 else "cuda"
    ckpt = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent / "checkpoints" / "best_finetune.pth"
    repeats = {"cuda": 5, "cpu": 3}[device]
    run(device, ckpt, repeats)
