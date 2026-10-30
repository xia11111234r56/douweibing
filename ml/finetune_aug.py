"""GAN 增强生产模型微调：在 真实+GAN 合成（1423 张）上训练分类器。

消融实验（ablation.py）显示 GAN 增强使测试准确率 0.7865→0.8202，本脚本把该
结论落地为可部署模型：训练完成后将 best_finetune_aug.pth 覆盖 best_finetune.pth，
再 evaluate.py（真实测试集指标）与 export_onnx.py（导出 ONNX）即可。

用法（ml/ 目录下）：
    python finetune_aug.py
产物：checkpoints/best_finetune_aug.pth
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from ablation import CachedFolder, build_augmented_train_dir  # noqa: E402
from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    EPOCHS_FINETUNE,
    EXPERIMENTS_DIR,
    LR_FINETUNE,
    ORGANIZED_DIR,
    RANDOM_SEED,
    WEIGHT_DECAY,
)
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def main() -> None:
    aug_dir = EXPERIMENTS_DIR / "ablation_train"
    if not aug_dir.exists():
        print("[构建] 生成 ablation_train（真实 + GAN 合成）…")
        aug_dir = build_augmented_train_dir()
    if aug_dir is None:
        print("[错误] 缺少 GAN 合成图（experiments/augmented），先运行 train_gan.py")
        sys.exit(1)

    torch.manual_seed(RANDOM_SEED)
    print("[缓存] 训练/验证集…")
    train_ds = CachedFolder(aug_dir, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    print(f"[finetune_aug] 训练 {len(train_ds)} / 验证 {len(val_ds)}，设备 {DEVICE}")

    model = build_model(pretrained=True).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    if init.exists():
        state = torch.load(init, map_location=DEVICE)
        ms = model.state_dict()
        filtered = {k: v for k, v in state.items()
                    if k in ms and v.shape == ms[k].shape}
        model.load_state_dict(filtered, strict=False)
        print(f"[finetune_aug] 从 {init} 迁移 {len(filtered)}/{len(state)} 层")
    else:
        print(f"[finetune_aug] 未找到 {init}，退回 ImageNet 预训练")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    criterion = nn.CrossEntropyLoss()
    tr = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    va = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    best = 0.0
    for epoch in range(EPOCHS_FINETUNE):
        model.train()
        for x, y in tr:
            x, y = x.to(DEVICE), y.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            torch.save(model.state_dict(), CHECKPOINTS_DIR / "best_finetune_aug.pth")
        if (epoch + 1) % 5 == 0:
            print(f"[finetune_aug] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")

    print(f"[finetune_aug] 最优验证准确率 {best:.4f} → checkpoints/best_finetune_aug.pth")
    print("下一步：备份基线后覆盖 best_finetune.pth，再 evaluate.py + export_onnx.py")


if __name__ == "__main__":
    main()
