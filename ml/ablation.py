"""消融实验：基线 vs +GAN增强 的分类准确率对比（论文核心实验）。

A/B 在同一测试集上评估，保证可比性。多模态融合消融（有/无环境模态）见
ablation_multimodal.py（生产 ONNX + backend knowledge_rules，基线 0.8315 → 天气
档位敏感性最高 0.8427），此处聚焦数据增强侧。

性能优化（2026-08-17）：原实现在 Windows 上每 epoch 重新解码 6000×3376 大图
（约 9 min/epoch，baseline 4.5h+）。改为一次性解码缓存为内存张量（256×256），
训练时在内存张量上做随机增强（约 15 s/epoch），A/B 全部可在 ~40 min 内完成，
结果语义与原实现一致。

用法（ml/ 目录下）：
    python ablation.py --epochs 30
产物：experiments/ablation_report.json（每变体完成后即增量落盘）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    IMG_SIZE,
    ORGANIZED_DIR,
    RANDOM_SEED,
    LR_FINETUNE,
    WEIGHT_DECAY,
)
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# 缓存到 256×256，训练时在此之上做 RandomResizedCrop(224, scale=(0.7,1.0))，
# 与原全尺寸 RandomResizedCrop 语义一致（scale 0.7-1.0 → crop 179-256 → resize 224）
CACHE_SIZE = 256


def _load_tensor(path: Path) -> torch.Tensor:
    """解码一次并缩放到 CACHE_SIZE 的 RGB 张量 [3,256,256]。"""
    img = Image.open(path).convert("RGB").resize((CACHE_SIZE, CACHE_SIZE))
    return transforms.ToTensor()(img)  # [3,256,256] 0-1


class CachedFolder(Dataset):
    """一次性解码缓存整个文件夹（ImageFolder 结构），训练时在线做随机增强。"""

    def __init__(self, root: Path, train: bool):
        self.items: list[tuple[torch.Tensor, int]] = []
        if not root.exists():
            return
        classes = sorted(d.name for d in root.iterdir() if d.is_dir())
        self.class_to_idx = {c: i for i, c in enumerate(classes)}
        for cls in classes:
            d = root / cls
            for p in sorted(
                x for x in d.iterdir()
                if x.is_file() and x.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            ):
                self.items.append((_load_tensor(p), self.class_to_idx[cls]))
        self.train = train

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i):
        x, y = self.items[i]
        if self.train:
            # 在 256×256 缓存上做与训练一致的随机增强
            crop = transforms.RandomResizedCrop(
                IMG_SIZE, scale=(0.7, 1.0), ratio=(3.0 / 4.0, 4.0 / 3.0)
            )(x)
            crop = transforms.RandomHorizontalFlip(p=0.5)(crop)
            crop = transforms.RandomVerticalFlip(p=0.5)(crop)
            crop = transforms.RandomRotation(15)(crop)
            crop = transforms.ColorJitter(0.2, 0.2, 0.2, 0.05)(crop)
        else:
            crop = transforms.Resize((IMG_SIZE, IMG_SIZE))(x)
        return transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])(crop), y


def build_augmented_train_dir() -> Path | None:
    """把 real/train + GAN augmented 合并成 ablation 训练集。"""
    aug_root = EXPERIMENTS_DIR / "augmented"
    if not aug_root.exists():
        print("[跳过+GAN] 未找到 experiments/augmented，先运行 train_gan.py")
        return None
    out = EXPERIMENTS_DIR / "ablation_train"
    if out.exists():
        shutil.rmtree(out)
    for cls in CLASS_NAMES:
        real = ORGANIZED_DIR / "train" / cls
        gen = aug_root / cls
        dst = out / cls
        if real.exists():
            shutil.copytree(real, dst)
        if gen.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for p in gen.glob("*.png"):
                shutil.copy2(p, dst / p.name)
    return out


def train_and_eval(train_root: Path, tag: str, epochs: int,
                   init_from: str = "best_public.pth", seed: int = RANDOM_SEED) -> dict:
    """训练并评估一个变体。init_from 用公开预训练权重（与主 finetune 一致，
    保证 baseline 与 +GAN 从同一初始化出发，差异仅来自训练数据）。seed 可传入
    做多种子复核（默认 RANDOM_SEED=42，向后兼容）。"""
    torch.manual_seed(seed)
    print(f"[{tag}] 缓存数据集…")
    train_ds = CachedFolder(train_root, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    test_ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    print(f"[{tag}] 训练样本 {len(train_ds)} / 验证 {len(val_ds)} / 测试 {len(test_ds)}")

    model = build_model(pretrained=True).to(DEVICE)
    init_path = CHECKPOINTS_DIR / init_from
    if init_path.exists():
        state = torch.load(init_path, map_location=DEVICE)
        model_state = model.state_dict()
        filtered = {k: v for k, v in state.items()
                    if k in model_state and v.shape == model_state[k].shape}
        model.load_state_dict(filtered, strict=False)
        print(f"[{tag}] 从 {init_from} 迁移 {len(filtered)}/{len(state)} 层")
    else:
        print(f"[{tag}] 未找到 {init_from}，退回 ImageNet 预训练")
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    criterion = nn.CrossEntropyLoss()
    # 数据已在内存，num_workers=0 免子进程开销
    tr_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    va_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    best = 0.0
    for epoch in range(epochs):
        train_one_epoch(model, tr_loader, criterion, optimizer)
        va_acc, _ = validate(model, va_loader, criterion)
        best = max(best, va_acc)
        if (epoch + 1) % 5 == 0:
            print(f"[{tag}] epoch {epoch + 1}/{epochs}  val {va_acc:.4f}")

    te_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    correct, total = 0, 0
    model.eval()
    with torch.no_grad():
        for x, y in te_loader:
            total += y.size(0)
            correct += (model(x.to(DEVICE)).argmax(1).cpu() == y).sum().item()
    test_acc = correct / total
    print(f"[{tag}] 验证准确率 {best:.4f} / 测试准确率 {test_acc:.4f}")
    return {"tag": tag, "best_val_acc": round(best, 4), "test_acc": round(test_acc, 4),
            "train_samples": len(train_ds)}


def train_one_epoch(model, loader, criterion, optimizer):
    model.train()
    for x, y in loader:
        x, y = x.to(DEVICE), y.to(DEVICE)
        optimizer.zero_grad()
        out = model(x)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
    model.eval()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=30)
    args = parser.parse_args()

    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = EXPERIMENTS_DIR / "ablation_report.json"
    results: list[dict] = []

    def persist() -> None:
        report_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    results.append(train_and_eval(ORGANIZED_DIR / "train", "baseline", args.epochs))
    persist()
    print(f"[baseline] 完成，结果已落盘 {report_path}")

    aug_train = build_augmented_train_dir()
    if aug_train is not None:
        results.append(train_and_eval(aug_train, "gan_augmented", args.epochs))
        persist()
        print(f"[gan_augmented] 完成，结果已落盘 {report_path}")

    if len(results) == 2:
        delta = results[1]["test_acc"] - results[0]["test_acc"]
        print(f"\n结论：GAN 增强使测试准确率 {'+' if delta >= 0 else ''}{delta:.4f}")
    print(f"报告: {report_path}")


if __name__ == "__main__":
    main()
