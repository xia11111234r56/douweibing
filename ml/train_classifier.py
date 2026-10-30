"""分类模型训练：两阶段迁移。

阶段1 预训练（可选）：公开数据（PlantVillage/Mendeley）—— ml/data/public/
阶段2 微调：用户绿豆数据 —— ml/data/organized/

用法（ml/ 目录下）：
    python train_classifier.py --stage public
    python train_classifier.py --stage finetune
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    GRAD_ACCUM,
    IMG_SIZE,
    LR,
    LR_FINETUNE,
    MODEL_NAME,
    ORGANIZED_DIR,
    PUBLIC_DIR,
    RANDOM_SEED,
    WEIGHT_DECAY,
    WORKERS,
)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NUM_CLASSES = len(CLASS_NAMES)


def get_transform(train: bool) -> transforms.Compose:
    base = [
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
    ]
    if train:
        # 强数据增强：应对小样本
        base.insert(0, transforms.RandomResizedCrop(IMG_SIZE, scale=(0.7, 1.0)))
        base += [
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(0.2, 0.2, 0.2, 0.05),
        ]
    base += [
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
    return transforms.Compose(base)


def build_model(pretrained: bool = True, num_classes: int | None = None) -> nn.Module:
    """轻量分类模型：mobilenetv3_large 或 efficientnet_b0（torchvision 原生）。

    num_classes 缺省用全局 NUM_CLASSES；公开预训练阶段类别数与微调不同，
    微调时通过 strict=False + 形状过滤仅迁移骨干权重。
    """
    num_classes = num_classes or NUM_CLASSES
    if MODEL_NAME == "mobilenetv3_large":
        model = models.mobilenet_v3_large(weights="IMAGENET1K_V1" if pretrained else None)
        model.classifier[3] = nn.Linear(model.classifier[3].in_features, num_classes)
    elif MODEL_NAME == "efficientnet_b0":
        model = models.efficientnet_b0(weights="IMAGENET1K_V1" if pretrained else None)
        model.classifier[1] = nn.Linear(model.classifier[1].in_features, num_classes)
    else:
        raise ValueError(f"不支持的模型: {MODEL_NAME}")
    return model


def load_dataset(root: Path, train: bool):
    if not root.exists() or not any(root.iterdir()):
        return None
    return datasets.ImageFolder(
        root=str(root),
        transform=get_transform(train),
        allow_empty=True,  # 小类（样本<3）仅在 train 训练，val/test 允许空目录
    )


def train_one_epoch(model, loader, criterion, optimizer, scaler=None):
    model.train()
    total, correct, loss_sum = 0, 0, 0.0
    optimizer.zero_grad()
    for i, (x, y) in enumerate(loader):
        x, y = x.to(DEVICE), y.to(DEVICE)
        out = model(x)
        loss = criterion(out, y) / GRAD_ACCUM
        loss.backward()
        if (i + 1) % GRAD_ACCUM == 0:
            optimizer.step()
            optimizer.zero_grad()
        loss_sum += loss.item() * GRAD_ACCUM
        total += y.size(0)
        correct += (out.argmax(1) == y).sum().item()
    return correct / total, loss_sum / max(len(loader), 1)


@torch.no_grad()
def validate(model, loader, criterion):
    model.eval()
    total, correct, loss_sum = 0, 0, 0.0
    for x, y in loader:
        x, y = x.to(DEVICE), y.to(DEVICE)
        out = model(x)
        loss = criterion(out, y)
        loss_sum += loss.item()
        total += y.size(0)
        correct += (out.argmax(1) == y).sum().item()
    return correct / total, loss_sum / max(len(loader), 1)


def run_stage(stage: str, epochs: int, lr: float, data_root: Path, tag: str,
              init_from: str | None = None):
    random.seed(RANDOM_SEED)
    torch.manual_seed(RANDOM_SEED)

    train_ds = load_dataset(data_root / "train", train=True)
    val_ds = load_dataset(data_root / "val", train=False)
    if train_ds is None or val_ds is None:
        print(f"[跳过] {stage}: 缺少 {data_root} 数据")
        return None

    # 阶段类别数：public 用数据本身的标签空间；finetune 用我们的 10 类
    num_classes = len(train_ds.classes) if stage == "public" else NUM_CLASSES
    print(f"[{stage}] 训练样本 {len(train_ds)} / 验证 {len(val_ds)}，"
          f"类别 {num_classes}，设备 {DEVICE}")
    model = build_model(pretrained=True, num_classes=num_classes).to(DEVICE)
    if init_from:
        init_path = CHECKPOINTS_DIR / init_from
        if init_path.exists():
            # 链式加载：finetune 从 public 阶段权重继续，而非重新从 ImageNet 起步。
            # strict=False + 形状过滤：public 分类头类别数不同，只迁移骨干。
            state = torch.load(init_path, map_location=DEVICE)
            model_state = model.state_dict()
            filtered = {
                k: v for k, v in state.items()
                if k in model_state and v.shape == model_state[k].shape
            }
            model.load_state_dict(filtered, strict=False)
            print(f"[{stage}] 从 {init_from} 迁移 {len(filtered)}/{len(state)} 层"
                  f"（分类头 {num_classes} 类重建）")
        else:
            print(f"[{stage}] 未找到 {init_from}，退回 ImageNet 预训练")
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=WORKERS, drop_last=False)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                            num_workers=WORKERS)

    best_acc, best_epoch = 0.0, -1
    for epoch in range(epochs):
        t0 = time.time()
        tr_acc, tr_loss = train_one_epoch(model, train_loader, criterion, optimizer)
        va_acc, va_loss = validate(model, val_loader, criterion)
        scheduler.step()
        print(f"[{stage}] epoch {epoch + 1}/{epochs}  "
              f"train {tr_acc:.4f}/{tr_loss:.4f}  val {va_acc:.4f}/{va_loss:.4f}  "
              f"{(time.time() - t0):.1f}s")
        if va_acc > best_acc:
            best_acc, best_epoch = va_acc, epoch + 1
            CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), CHECKPOINTS_DIR / f"best_{tag}.pth")

    result = {"stage": stage, "best_val_acc": best_acc, "best_epoch": best_epoch}
    print(f"[{stage}] 最优验证准确率 {best_acc:.4f} @ epoch {best_epoch}")
    return model, result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["public", "finetune"], required=True)
    parser.add_argument("--epochs", type=int, default=None)
    args = parser.parse_args()

    if args.stage == "public":
        run_stage("public", args.epochs or 20, LR,
                  PUBLIC_DIR / "organized", "public")
    else:
        _, result = run_stage(
            "finetune", args.epochs or 40, LR_FINETUNE, ORGANIZED_DIR, "finetune",
            init_from="best_public.pth",
        )
        if result:
            EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
            (EXPERIMENTS_DIR / "finetune_metrics.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("完成。下一步：python evaluate.py / python export_onnx.py")


if __name__ == "__main__":
    main()
