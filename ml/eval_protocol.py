"""评估协议对比：同一模型、同一批图，CachedFolder(256→224 两级) vs 原图直缩 224(一级)。

背景：best_finetune.pth 用 CachedFolder eval 读出 0.8315，evaluate.py（ImageFolder
原图直缩）读出 0.8202，check_onnx_parity（backend PIL 原图直缩）也 0.8202。怀疑
是预处理协议差异而非 GPU 非确定。本脚本在单进程内用两种协议逐图预测，输出各自
准确率 + 逐图不一致数。

用法（ml/ 下）：python eval_protocol.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402
from torchvision import datasets, transforms  # noqa: E402

from ablation import CachedFolder  # noqa: E402
from config import BATCH_SIZE, IMG_SIZE, ORGANIZED_DIR, WORKERS  # noqa: E402
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
CKPT = Path(__file__).resolve().parent / "checkpoints" / "best_finetune.pth"


def main() -> None:
    model = build_model(pretrained=False).to(DEVICE)
    model.load_state_dict(torch.load(CKPT, map_location=DEVICE))
    model.eval()

    root = ORGANIZED_DIR / "test"
    # 协议 A：CachedFolder（缓存 256 → eval resize 224，与训练一致）
    ds_a = CachedFolder(root, train=False)
    pred_a = []
    with torch.no_grad():
        for x, _ in DataLoader(ds_a, batch_size=BATCH_SIZE, num_workers=0):
            pred_a += model(x.to(DEVICE)).argmax(1).cpu().tolist()

    # 协议 B：ImageFolder 原图直缩 224（evaluate.py / backend 一致）
    tr_b = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    ds_b = datasets.ImageFolder(str(root), transform=tr_b, allow_empty=True)
    pred_b = []
    with torch.no_grad():
        for x, _ in DataLoader(ds_b, batch_size=32, shuffle=False, num_workers=WORKERS):
            pred_b += model(x.to(DEVICE)).argmax(1).cpu().tolist()

    y = [y for _, y in ds_a.items]
    acc_a = sum(pa == t for pa, t in zip(pred_a, y)) / len(y)
    acc_b = sum(pb == t for pb, t in zip(pred_b, y)) / len(y)
    diff = sum(pa != pb for pa, pb in zip(pred_a, pred_b))
    print(f"协议A CachedFolder(256→224): {acc_a:.4f}")
    print(f"协议B 原图直缩224:          {acc_b:.4f}")
    print(f"逐图预测不一致: {diff}/{len(y)} 张")


if __name__ == "__main__":
    main()
