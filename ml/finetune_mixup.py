"""mixup 消融：在 B 生产配方上叠加 mixup 批内混合，对比 test89/eval178 与生产 0.8315/0.8483。

与 finetune_ablation2x2 --variant B 完全同配方（真实+GAN+虫食 251、40 epoch、
best_public 迁移、AdamW 1e-4、CachedFolder 增强），唯一差异：训练循环内做 mixup。

用法（ml/ 目录下）：
    python finetune_mixup.py --alpha 0.2        # mixup α=0.2（推荐默认）
    python finetune_mixup.py --alpha 0.0        # α=0 = 纯 B 基线（对照）
    python finetune_mixup.py --alpha 0.4 --epochs 40 --seed 42
产物：checkpoints/best_finetune_mixup.pth、experiments/mixup_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.distributions import Beta  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402

from ablation import CachedFolder  # noqa: E402
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
from finetune_ablation2x2 import build_train_dir  # noqa: E402
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def mixup_batch(x: torch.Tensor, y: torch.Tensor, alpha: float):
    """批内 mixup：λ~Beta(α,α)，x 与随机置换的批混合，返回 (x_mix, y_a, y_b, lam)。
    alpha<=0 时不做 mixup，lam=1.0 退化为原 batch。"""
    if alpha <= 0:
        return x, y, y, torch.tensor(1.0, device=x.device)
    lam = Beta(alpha, alpha).sample().to(x.device)
    perm = torch.randperm(x.size(0), device=x.device)
    x_mix = lam * x + (1 - lam) * x[perm]
    return x_mix, y, y[perm], lam


def train_one_epoch_mixup(model, loader, criterion, optimizer, alpha: float) -> None:
    model.train()
    for x, y in loader:
        x, y = x.to(DEVICE), y.to(DEVICE)
        x, y_a, y_b, lam = mixup_batch(x, y, alpha)
        optimizer.zero_grad()
        out = model(x)
        loss = lam * criterion(out, y_a) + (1 - lam) * criterion(out, y_b)
        loss.backward()
        optimizer.step()
    model.eval()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alpha", type=float, default=0.2, help="mixup Beta 参数，0=不做")
    parser.add_argument("--epochs", type=int, default=EPOCHS_FINETUNE)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    tag = f"mixup α={args.alpha}"

    train_dir = build_train_dir(use_caterpillar=True)
    train_ds = CachedFolder(train_dir, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    test_ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    eval178_ds = CachedFolder(EXPERIMENTS_DIR / "eval_178", train=False)

    print(f"[{tag}] 训练 {len(train_ds)} / 验证 {len(val_ds)} / 测试 {len(test_ds)} / 178 {len(eval178_ds)}")

    model = build_model(pretrained=True).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)
    print(f"[{tag}] 从 best_public.pth 迁移 {len(filtered)}/{len(state)} 层")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    criterion = nn.CrossEntropyLoss()
    tr = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    va = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    best = 0.0
    for epoch in range(args.epochs):
        train_one_epoch_mixup(model, tr, criterion, optimizer, args.alpha)
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), CHECKPOINTS_DIR / "best_finetune_mixup.pth")
        if (epoch + 1) % 5 == 0:
            print(f"[{tag}] epoch {epoch + 1}/{args.epochs}  val {va_acc:.4f}  best {best:.4f}")

    def eval_acc(ds) -> float:
        loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for x, y in loader:
                total += y.size(0)
                correct += (model(x.to(DEVICE)).argmax(1).cpu() == y).sum().item()
        return correct / total

    model.load_state_dict(torch.load(CHECKPOINTS_DIR / "best_finetune_mixup.pth", map_location=DEVICE))
    test89 = eval_acc(test_ds)
    test178 = eval_acc(eval178_ds)
    print(f"\n[{tag}] 最优验证 {best:.4f} / test89 {test89:.4f} / eval178 {test178:.4f}")

    y_true, y_pred = [], []
    loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    model.eval()
    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            y_pred += model(x).argmax(1).cpu().tolist()
            y_true += y.cpu().tolist()
    tc, pc = Counter(y_true), Counter(y_pred)
    per = {}
    for cls, idx in sorted(test_ds.class_to_idx.items(), key=lambda kv: kv[1]):
        m = [(a, b) for a, b in zip(y_true, y_pred) if a == idx]
        rec = sum(a == b for a, b in m) / max(tc[idx], 1)
        per[cls] = {"recall": round(rec, 4), "n_test": tc[idx], "n_pred": pc[idx]}

    result = {
        "variant": "mixup", "alpha": args.alpha, "epochs": args.epochs, "seed": args.seed,
        "train_config": "与生产 B 一致：真实+GAN+虫食251, 40epoch, best_public 迁移, AdamW lr=1e-4, +mixup",
        "n_train": len(train_ds), "n_val": len(val_ds), "n_test": len(test_ds), "n_178": len(eval178_ds),
        "best_val_acc": round(best, 4),
        "test89_accuracy": round(test89, 4),
        "eval178_accuracy": round(test178, 4),
        "reference_B_production": {"test89": 0.8315, "eval178": 0.8483},
        "per_class_test89": per,
    }
    (EXPERIMENTS_DIR / "mixup_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / 'mixup_report.json'}")


if __name__ == "__main__":
    main()
