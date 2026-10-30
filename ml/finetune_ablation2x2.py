"""2×2 消融：变体 B（只加虫食）与 C（只类平衡），对照已有 A（生产）与 D（两者）。

| 变体 | 虫食+251 | 类平衡 | test89 | eval178 |
| A 生产(已有)  | ✗ | ✗ | 0.8315 | 0.8483 |
| B 只加虫食    | ✓ | ✗ | 本脚本 | 本脚本 |
| C 只类平衡    | ✗ | ✓ | 本脚本 | 本脚本 |
| D 两者(已有)  | ✓ | ✓ | 0.7978 | 0.8034 |

公平性：训练配置与生产 finetune_aug 完全一致（40 epoch、best_public 迁移、AdamW 1e-4、
CachedFolder 增强），仅在"训练数据是否含 Mendeley 虫食 251 张"与"是否用
WeightedRandomSampler+加权CE"上做开关。测试集 = organized/test 89 张 + eval_178 178 张。

用法（ml/ 目录下）：
    python finetune_ablation2x2.py --variant B
    python finetune_ablation2x2.py --variant C
产物：checkpoints/best_finetune_{B|C}.pth、experiments/{B|C}_report.json
"""
from __future__ import annotations

import argparse
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
BETA = 0.999


def effective_weights(counts: list[int], beta: float = BETA) -> list[float]:
    """Cui 2019 effective-number 类权重，归一化使均值≈1。"""
    raw = [(1.0 - beta) / (1.0 - beta ** c) for c in counts]
    mean = sum(raw) / len(raw)
    return [w / mean for w in raw]


def build_train_dir(use_caterpillar: bool) -> Path:
    """训练目录：ablation_train（生产集）± Mendeley 虫食 251 张。"""
    aug_train = EXPERIMENTS_DIR / "ablation_train"
    if not aug_train.exists():
        print("[构建] 重建 ablation_train（真实+GAN 1423 张，生产训练集）…")
        aug_train = build_augmented_train_dir()
    assert aug_train is not None, "缺少 GAN 合成图（experiments/augmented），先运行 train_gan.py"
    if not use_caterpillar:
        return aug_train
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
    print(f"[构建] 补充 Mendeley 虫食 {n} 张 → train_balanced/虫食")
    return out


def run_variant(variant: str) -> None:
    use_caterpillar = variant == "B"
    use_balance = variant == "C"
    tag = f"variant {variant}"
    torch.manual_seed(RANDOM_SEED)

    train_dir = build_train_dir(use_caterpillar)
    train_ds = CachedFolder(train_dir, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    test_ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    eval178_ds = CachedFolder(EXPERIMENTS_DIR / "eval_178", train=False)

    cls_order = sorted(train_ds.class_to_idx, key=train_ds.class_to_idx.get)
    class_counts = [0] * len(train_ds.class_to_idx)
    for _, y in train_ds.items:
        class_counts[y] += 1
    weights = effective_weights(class_counts)
    cw_map = {c: round(w, 3) for c, w in zip(cls_order, weights)}
    print(f"[{tag}] 训练 {len(train_ds)} / 验证 {len(val_ds)} / 测试 {len(test_ds)} / 178 {len(eval178_ds)}")
    print(f"[{tag}] 虫食+{use_caterpillar} 平衡+{use_balance}  样本数 {dict(zip(cls_order, class_counts))}")
    if use_balance:
        print(f"[{tag}] 类权重: {cw_map}")

    model = build_model(pretrained=True).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)
    print(f"[{tag}] 从 best_public.pth 迁移 {len(filtered)}/{len(state)} 层")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
    if use_balance:
        criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, device=DEVICE))
        sample_w = [weights[y] for _, y in train_ds.items]
        sampler = WeightedRandomSampler(sample_w, num_samples=len(train_ds), replacement=True)
        tr = DataLoader(train_ds, batch_size=BATCH_SIZE, sampler=sampler, num_workers=0)
    else:
        criterion = nn.CrossEntropyLoss()
        tr = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
    va = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    best = 0.0
    for epoch in range(EPOCHS_FINETUNE):
        train_one_epoch(model, tr, criterion, optimizer)
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), CHECKPOINTS_DIR / f"best_finetune_{variant}.pth")
        if (epoch + 1) % 5 == 0:
            print(f"[{tag}] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")

    def eval_acc(ds) -> float:
        loader = DataLoader(ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
        model.eval()
        correct, total = 0, 0
        with torch.no_grad():
            for x, y in loader:
                total += y.size(0)
                correct += (model(x.to(DEVICE)).argmax(1).cpu() == y).sum().item()
        return correct / total

    model.load_state_dict(torch.load(CHECKPOINTS_DIR / f"best_finetune_{variant}.pth", map_location=DEVICE))
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
        "variant": variant,
        "use_caterpillar": use_caterpillar, "use_balance": use_balance,
        "method": ("虫食补充(Mendeley 251)，普通 CE/shuffle" if variant == "B" else
                   "WeightedRandomSampler+加权CE(β=0.999)，无虫食补充"),
        "train_config": "与 finetune_aug 生产一致：40epoch, best_public 迁移, AdamW lr=1e-4",
        "n_train": len(train_ds), "n_val": len(val_ds), "n_test": len(test_ds), "n_178": len(eval178_ds),
        "class_counts": dict(zip(cls_order, class_counts)),
        "class_weights": cw_map if use_balance else None,
        "best_val_acc": round(best, 4),
        "test89_accuracy": round(test89, 4),
        "eval178_accuracy": round(test178, 4),
        "reference_A_production": {"test89": 0.8315, "eval178": 0.8483},
        "per_class_test89": per,
    }
    (EXPERIMENTS_DIR / f"{variant}_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / f'{variant}_report.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", choices=["B", "C"], required=True)
    args = parser.parse_args()
    run_variant(args.variant)


if __name__ == "__main__":
    main()
