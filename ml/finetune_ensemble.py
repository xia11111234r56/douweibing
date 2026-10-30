"""多 seed Ensemble + TTA 实验（B 配方：GAN 增强 + 真实虫食补充）。

目标：在不加任何数据的前提下，用推理侧集成稳定化提升/稳定准确率（诚实定位：降方差，
非提升真实泛化）。流程：
  1. 训 3 个 seed（42/7/1234）的 B 配方模型，best-val 保存 checkpoints/ensemble/seed{seed}.pth
  2. 在 test89（89 张）+ eval178（178 张）上评估 4 个配置：
       - 单模型（seed42）
       - 单模型 + TTA（水平翻转 softmax 平均）
       - ensemble-3（3 模型 softmax 平均）
       - ensemble-3 + TTA
  3. 顺带在 Mendeley caterpillar 251 张上验证集成不丢失真实虫食判别力（期望≈100%）

TTA 实现：CachedFolder eval 张量（BCHW 归一化）直接 torch.flip W 维即可——水平翻转
与归一化可交换，翻转后再推理求 softmax 平均。

用法（ml/ 目录下）：python finetune_ensemble.py
产物：checkpoints/ensemble/seed{seed}.pth、experiments/ensemble_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402
from torchvision import transforms  # noqa: E402
from PIL import Image  # noqa: E402

from ablation import CachedFolder, train_one_epoch  # noqa: E402
from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    EPOCHS_FINETUNE,
    EXPERIMENTS_DIR,
    IMG_SIZE,
    LR_FINETUNE,
    ORGANIZED_DIR,
    PUBLIC_DIR,
    WEIGHT_DECAY,
)
from finetune_ablation2x2 import build_train_dir  # noqa: E402
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SEEDS = [42, 7, 1234]
ENS_DIR = CHECKPOINTS_DIR / "ensemble"
MND_CATERPILLAR = PUBLIC_DIR / "organized" / "train" / "caterpillar"

IMG_T = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def train_one(seed: int) -> Path:
    torch.manual_seed(seed)
    train_dir = build_train_dir(use_caterpillar=True)
    train_ds = CachedFolder(train_dir, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    print(f"[seed {seed}] 训练 {len(train_ds)} / 验证 {len(val_ds)}")

    model = build_model(pretrained=True).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    criterion = nn.CrossEntropyLoss()
    tr = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    va = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    ENS_DIR.mkdir(parents=True, exist_ok=True)
    ckpt = ENS_DIR / f"seed{seed}.pth"
    best = 0.0
    for epoch in range(EPOCHS_FINETUNE):
        train_one_epoch(model, tr, criterion, optimizer)
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            torch.save(model.state_dict(), ckpt)
        if (epoch + 1) % 5 == 0:
            print(f"[seed {seed}] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")
    print(f"[seed {seed}] 完成 best_val {best:.4f} → {ckpt.name}")
    return ckpt


def logits_of(model, loader, tta: bool) -> tuple:
    """返回 (ys, logits)：(N,)、(N, C)，CachedFolder eval 预处理；tta 时水平翻转平均。"""
    model.eval()
    ys, outs = [], []
    with torch.no_grad():
        for x, y in loader:
            x = x.to(DEVICE)
            lg = model(x)
            if tta:
                lg = 0.5 * (lg + model(torch.flip(x, dims=[3])))
            outs.append(lg.cpu())
            ys.append(y)
    return torch.cat(ys), torch.cat(outs)


def acc(probs: torch.Tensor, ys: torch.Tensor) -> float:
    return float((probs.argmax(1) == ys).float().mean())


def load_model(ckpt: Path):
    model = build_model(pretrained=False).to(DEVICE)
    model.load_state_dict(torch.load(ckpt, map_location=DEVICE))
    return model


def cross_domain_hit(model, tta: bool = False) -> float:
    """Mendeley caterpillar 251 张 → 期望预测 虫食(idx8) 的命中率。"""
    hit, total = 0, 0
    model.eval()
    with torch.no_grad():
        for p in sorted(MND_CATERPILLAR.glob("*.jpeg")):
            x = IMG_T(Image.open(p).convert("RGB")).unsqueeze(0).to(DEVICE)
            lg = model(x)
            if tta:
                lg = 0.5 * (lg + model(torch.flip(x, dims=[3])))
            hit += (lg.argmax(1).item() == 8)
            total += 1
    return hit / total


def main() -> None:
    ckpts = [train_one(s) for s in SEEDS]
    models = [load_model(c) for c in ckpts]

    sets = {
        "test89": CachedFolder(ORGANIZED_DIR / "test", train=False),
        "eval178": CachedFolder(EXPERIMENTS_DIR / "eval_178", train=False),
    }
    data = {name: logits_of(models[0], DataLoader(ds, batch_size=BATCH_SIZE, num_workers=0), tta=False)[0]
            for name, ds in sets.items()}  # ys 各数据集取一次即可
    results = {}

    def eval_config(label: str, use_tta: bool, model_ids: list[int]) -> None:
        results[label] = {}
        for name, ds in sets.items():
            probs_sum = None
            ys = None
            for mi in model_ids:
                ys, lg = logits_of(models[mi], DataLoader(ds, batch_size=BATCH_SIZE, num_workers=0), tta=use_tta)
                p = torch.softmax(lg, dim=1)
                probs_sum = p if probs_sum is None else probs_sum + p
            results[label][name] = round(acc(probs_sum / len(model_ids), ys), 4)
        # 跨域虫食命中
        results[label]["caterpillar_hit"] = round(cross_domain_hit(models[model_ids[0]], tta=use_tta), 4)

    eval_config("single_seed42", False, [0])
    eval_config("single_tta", True, [0])
    eval_config("ensemble3", False, [0, 1, 2])
    eval_config("ensemble3_tta", True, [0, 1, 2])

    report = {
        "method": "3 seed (42/7/1234) B 配方（GAN+虫食）best-val 集成，softmax 平均；TTA=水平翻转；test89/eval178 用 CachedFolder eval 预处理",
        "per_config": results,
    }
    (EXPERIMENTS_DIR / "ensemble_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for k, v in results.items():
        print(f"\n[{k}] " + "  ".join(f"{kk} {vv}" for kk, vv in v.items()))
    print(f"报告: {EXPERIMENTS_DIR / 'ensemble_report.json'}")


if __name__ == "__main__":
    main()
