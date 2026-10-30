"""生产配置多种子复现实验：估计 0.8315 是否偶然（波动区间）。

生产配方 = finetune_aug.py 完全一致：训练集 ablation_train（真实+GAN 1423 张）、
40 epoch、AdamW lr=1e-4 wd=1e-4、best_public.pth 迁移骨干、普通 CrossEntropyLoss、
best-val 状态评估测试集（organized/test 89 张）。仅改变 torch.manual_seed 种子。

对每个种子：记录 best_val 与 test_acc。报告 mean±std / min-max，含重跑 seed 42
（复现 0.8315 则管线确定性好；否则偏差即 CUDA 非确定性下限）。

产物：experiments/seed_sweep.json
用法（ml/ 目录下，需 torch+CUDA 的 venv）：
    python finetune_seedsweep.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from torch.utils.data import DataLoader  # noqa: E402

from ablation import CachedFolder, build_augmented_train_dir, train_one_epoch  # noqa: E402
from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    EPOCHS_FINETUNE,
    EXPERIMENTS_DIR,
    LR_FINETUNE,
    ORGANIZED_DIR,
    WEIGHT_DECAY,
)
from train_classifier import build_model, validate  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
SEEDS = [42, 1, 7, 1234]  # 42 = 生产种子（验证可复现性）；1/7/1234 = 波动抽样


def eval_test(model, test_ds) -> float:
    te = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    correct, total = 0, 0
    model.eval()
    with torch.no_grad():
        for x, y in te:
            total += y.size(0)
            correct += (model(x.to(DEVICE)).argmax(1).cpu() == y).sum().item()
    return correct / total


def run_seed(seed: int, train_ds, val_ds, test_ds) -> dict:
    torch.manual_seed(seed)
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

    best = 0.0
    best_state = None
    for epoch in range(EPOCHS_FINETUNE):
        train_one_epoch(model, tr, criterion, optimizer)
        va_acc, _ = validate(model, va, criterion)
        if va_acc > best:
            best = va_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        if (epoch + 1) % 10 == 0:
            print(f"[seed {seed}] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")

    model.load_state_dict(best_state)
    test_acc = eval_test(model, test_ds)
    print(f"[seed {seed}] 最优验证 {best:.4f} / 测试一致率 {test_acc:.4f}（生产 seed42 参照 0.8315）")
    return {"seed": seed, "best_val_acc": round(best, 4), "test_accuracy": round(test_acc, 4)}


def main() -> None:
    aug_train = EXPERIMENTS_DIR / "ablation_train"
    if not aug_train.exists():
        print("[构建] 重建 ablation_train（真实+GAN 1423 张，生产训练集）…")
        aug_train = build_augmented_train_dir()
    assert aug_train is not None, "缺少 GAN 合成图（experiments/augmented），先运行 train_gan.py"

    # 缓存一次，各 seed 复用（CachedFolder 张量缓存与 RNG 无关；增强在 __getitem__ 用全局 RNG）
    print(f"[缓存] 训练/验证/测试集…（设备 {DEVICE}）")
    train_ds = CachedFolder(aug_train, train=True)
    val_ds = CachedFolder(ORGANIZED_DIR / "val", train=False)
    test_ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    print(f"[seedsweep] 训练 {len(train_ds)} / 验证 {len(val_ds)} / 测试 {len(test_ds)}，种子 {SEEDS}")

    results = [run_seed(s, train_ds, val_ds, test_ds) for s in SEEDS]
    tests = [r["test_accuracy"] for r in results]
    vals = [r["best_val_acc"] for r in results]
    summary = {
        "method": "生产配置多种子复现：ablation_train(真实+GAN) 40epoch best_public 迁移 普通CE，"
                  "仅换 torch.manual_seed；best-val 状态评估同一批 89 张测试图",
        "seeds": SEEDS,
        "per_seed": results,
        "test_mean": round(sum(tests) / len(tests), 4),
        "test_std": round((sum((t - sum(tests) / len(tests)) ** 2 for t in tests)
                           / (len(tests) - 1)) ** 0.5, 4),
        "test_min": min(tests), "test_max": max(tests),
        "test_all": tests,
        "val_mean": round(sum(vals) / len(vals), 4),
        "val_all": vals,
        "reference_single_run_seed42_production": 0.8315,
    }
    (EXPERIMENTS_DIR / "seed_sweep.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[seedsweep] 测试一致率 {summary['test_all']}")
    print(f"[seedsweep] 均值 {summary['test_mean']:.4f} ± {summary['test_std']:.4f} "
          f"(min {summary['test_min']:.4f} / max {summary['test_max']:.4f})")
    print(f"报告: {EXPERIMENTS_DIR / 'seed_sweep.json'}")


if __name__ == "__main__":
    main()
