"""类平衡重训 A/B 实验：虫食补充 + WeightedRandomSampler + 加权 CE，对照生产 0.8315。

背景：真实绿豆 10 类中 4 个小类样本极少（叶腐1/虫食1/枯萎2/疫病2），删小类实验
（finetune_6cls.py）已证伪（0.7865 < 0.8315，保留 10 类）。本实验不改体系，而是：
  1. 虫食补充：Mendeley 公开数据 caterpillar 251 张并入「虫食」类（真实样本 1→252）
  2. 过采样：WeightedRandomSampler（effective-number 权重, Cui 2019, β=0.999, replacement）
  3. 类平衡损失：CrossEntropyLoss(weight= 同套 effective-number 权重，归一化使均值≈1)

公平性：训练数据 = 生产 ablation_train（真实+GAN 1423 张）额外 +251 张 Mendeley 虫食；
epochs/优化器/初始化/增强与 finetune_aug.py（生产 best_finetune_aug.pth）完全一致；
测试集 = organized/test 89 张，与生产 0.8315 完全同一批图。

产物：checkpoints/best_finetune_balanced.pth、experiments/balanced_report.json
用法（ml/ 目录下，需 torch+CUDA 的 venv）：
    python finetune_balanced.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader, WeightedRandomSampler  # noqa: E402

from ablation import CachedFolder, build_augmented_train_dir, train_one_epoch  # noqa: E402
from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EPOCHS_FINETUNE,
    EXPERIMENTS_DIR,
    LR_FINETUNE,
    ORGANIZED_DIR,
    PUBLIC_DIR,
    RANDOM_SEED,
    WEIGHT_DECAY,
)
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MND_CATERPILLAR = PUBLIC_DIR / "organized" / "train" / "caterpillar"
BETA = 0.999  # Cui 2019 effective-number 阻尼


def effective_weights(counts: list[int], beta: float = BETA) -> list[float]:
    """effective-number 类权重（Cui et al. 2019, Class-Balanced Loss）：
    w_i = (1-β)/(1-β^{n_i})，再归一化使均值≈1（保持 loss 尺度与生产可比）。"""
    raw = [(1.0 - beta) / (1.0 - beta ** c) for c in counts]
    mean = sum(raw) / len(raw)
    return [w / mean for w in raw]


def build_balanced_train_dir() -> tuple[Path, int]:
    """ablation_train（生产训练集）+ Mendeley 虫食 251 张 → experiments/train_balanced。"""
    aug_train = EXPERIMENTS_DIR / "ablation_train"
    if not aug_train.exists():
        print("[构建] 重建 ablation_train（真实+GAN 1423 张，生产训练集）…")
        aug_train = build_augmented_train_dir()
    assert aug_train is not None, "缺少 GAN 合成图（experiments/augmented），先运行 train_gan.py"
    out = EXPERIMENTS_DIR / "train_balanced"
    if out.exists():
        shutil.rmtree(out)
    for cls in CLASS_NAMES:
        s = aug_train / cls
        if s.exists():
            shutil.copytree(s, out / cls)
    dst = out / "虫食"
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(MND_CATERPILLAR.glob("*.jpeg")):
        shutil.copy2(p, dst / f"mnd_{p.name}")
        n += 1
    print(f"[构建] 补充 Mendeley 虫食 {n} 张 → train_balanced/虫食（真实 1+GAN+{n}）")
    return out, n


def main() -> None:
    torch.manual_seed(RANDOM_SEED)
    train_dir, n_mnd = build_balanced_train_dir()
    train_ds = CachedFolder(train_dir, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    test_ds = CachedFolder(ORGANIZED_DIR / "test", train=False)

    class_counts = [0] * len(train_ds.class_to_idx)
    for _, y in train_ds.items:
        class_counts[y] += 1
    weights = effective_weights(class_counts)
    cls_order = sorted(train_ds.class_to_idx, key=train_ds.class_to_idx.get)
    cw_map = {cls: round(w, 3) for cls, w in zip(cls_order, weights)}
    count_map = {c: n for c, n in zip(cls_order, class_counts)}
    print(f"[bal] 训练 {len(train_ds)} / 验证 {len(val_ds)} / 测试 {len(test_ds)}，设备 {DEVICE}")
    print(f"[bal] 训练样本数: {count_map}")
    print(f"[bal] 类权重(≈1 平均): {cw_map}")

    model = build_model(pretrained=True).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)
    print(f"[bal] 从 best_public.pth 迁移 {len(filtered)}/{len(state)} 层")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, device=DEVICE))
    sample_w = [weights[y] for _, y in train_ds.items]
    sampler = WeightedRandomSampler(sample_w, num_samples=len(train_ds), replacement=True)
    tr = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler, num_workers=0)
    va = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    best = 0.0
    for epoch in range(EPOCHS_FINETUNE):
        train_one_epoch(model, tr, criterion, optimizer)
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), CHECKPOINTS_DIR / "best_finetune_balanced.pth")
        if (epoch + 1) % 5 == 0:
            print(f"[bal] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")

    # 评估：同一批 89 张测试图（与生产 0.8315 可比）
    model.load_state_dict(torch.load(CHECKPOINTS_DIR / "best_finetune_balanced.pth", map_location=DEVICE))
    model.eval()
    te = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    y_true, y_pred = [], []
    with torch.no_grad():
        for x, y in te:
            x, y = x.to(DEVICE), y.to(DEVICE)
            y_pred += model(x).argmax(1).cpu().tolist()
            y_true += y.cpu().tolist()
    test_acc = sum(a == b for a, b in zip(y_pred, y_true)) / len(y_true)
    ref = 0.8315
    delta = test_acc - ref
    print(f"\n[bal] 最优验证 {best:.4f} / 测试一致率 {test_acc:.4f}"
          f"（对照生产 {ref}，同 89 张测试图，Δ{delta:+.4f}）")

    tc, pc = Counter(y_true), Counter(y_pred)
    per = {}
    for cls, idx in sorted(test_ds.class_to_idx.items(), key=lambda kv: kv[1]):
        m = [(a, b) for a, b in zip(y_true, y_pred) if a == idx]
        rec = sum(a == b for a, b in m) / max(tc[idx], 1)
        per[cls] = {"recall": round(rec, 4), "n_test": tc[idx], "n_pred": pc[idx]}
        print(f"  {cls}: {per[cls]}")

    result = {
        "method": "类平衡重训：虫食补充(Mendeley 251) + WeightedRandomSampler(过采样,β=0.999) "
                  "+ CrossEntropyLoss(class_weight)",
        "train_config": "与 finetune_aug 生产一致：ablation_train(真实+GAN 1423) + 251 Mendeley 虫食, "
                        "40epoch, best_public 迁移, AdamW lr=1e-4",
        "n_train": len(train_ds), "n_mnd_added": n_mnd, "n_val": len(val_ds), "n_test": len(test_ds),
        "class_counts": {c: class_counts[i] for c, i in sorted(
            train_ds.class_to_idx.items(), key=lambda kv: kv[1])},
        "class_weights": cw_map,
        "best_val_acc": round(best, 4),
        "test_accuracy": round(test_acc, 4),
        "reference_10cls_production": ref,
        "delta_vs_production": round(delta, 4),
        "per_class": per,
    }
    (EXPERIMENTS_DIR / "balanced_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / 'balanced_report.json'}")


if __name__ == "__main__":
    main()
