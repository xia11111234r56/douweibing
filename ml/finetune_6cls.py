"""6 类 A/B 实验：去掉样本≤2 的 4 类后重训，验证能否提高测试一致率。

被移出类：枯萎病(2)/细菌性疫病(2)/叶腐病(1)/虫食(1) —— 它们在测试集本就无样本
（support=0），保留 6 类：健康/晕疫病/炭疽叶斑病/轮纹叶斑病/病毒病/细菌性萎蔫。

公平性：训练配置与 finetune_aug.py（生产 best_finetune_aug.pth）完全一致——
ablation_train（真实+GAN）数据、40 epoch、best_public.pth 迁移骨干、CachedFolder
在线增强；测试集 = organized/test 中 6 类，与 10 类基线 0.8315 所用的 89 张完全相同
（被删 4 类在测试集 support=0，故 89 张全部来自这 6 类）。

产物：checkpoints/best_finetune_6cls.pth、experiments/ablation_6cls.json
用法（ml/ 目录下，需 torch+CUDA 的 venv）：
    python finetune_6cls.py
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
from torch.utils.data import DataLoader  # noqa: E402

from ablation import CachedFolder, build_augmented_train_dir, train_one_epoch  # noqa: E402
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
KEEP = ["健康", "晕疫病", "炭疽叶斑病", "轮纹叶斑病", "病毒病", "细菌性萎蔫"]
DROPPED = ["枯萎病", "细菌性疫病", "叶腐病", "虫食"]


def build_6cls_dirs() -> tuple[Path, Path, Path]:
    aug_train = EXPERIMENTS_DIR / "ablation_train"
    if not aug_train.exists():
        print("[构建] 生成 ablation_train（真实+GAN，10 类）…")
        aug_train = build_augmented_train_dir()
    assert aug_train is not None, "缺少 GAN 合成图（experiments/augmented），先运行 train_gan.py"
    out = {
        "train": EXPERIMENTS_DIR / "ablation_train_6cls",
        "val": EXPERIMENTS_DIR / "val_6cls",
        "test": EXPERIMENTS_DIR / "test_6cls",
    }
    src_root = {
        "train": aug_train,
        "val": ORGANIZED_DIR / "val",
        "test": ORGANIZED_DIR / "test",
    }
    for key, dst in out.items():
        if dst.exists():
            shutil.rmtree(dst)
        for cls in KEEP:
            s = src_root[key] / cls
            if s.exists():
                shutil.copytree(s, dst / cls)
    return out["train"], out["val"], out["test"]


def main() -> None:
    torch.manual_seed(RANDOM_SEED)
    train_dir, val_dir, test_dir = build_6cls_dirs()
    train_ds = CachedFolder(train_dir, train=True)
    val_ds = CachedFolder(val_dir, train=False)
    test_ds = CachedFolder(test_dir, train=False)
    n, nv, nt = len(train_ds), len(val_ds), len(test_ds)
    print(f"[6cls] 训练 {n} / 验证 {nv} / 测试 {nt}，设备 {DEVICE}")
    print(f"[6cls] 测试集 {nt} 张（与 10 类基线同一批图，对照 0.8315）")

    model = build_model(pretrained=True, num_classes=6).to(DEVICE)
    init = CHECKPOINTS_DIR / "best_public.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)
    print(f"[6cls] 从 best_public.pth 迁移 {len(filtered)}/{len(state)} 层")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
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
            torch.save(model.state_dict(), CHECKPOINTS_DIR / "best_finetune_6cls.pth")
        if (epoch + 1) % 5 == 0:
            print(f"[6cls] epoch {epoch + 1}/{EPOCHS_FINETUNE}  val {va_acc:.4f}  best {best:.4f}")

    # 评估：同一批 89 张测试图（与 10 类基线可比）
    model.load_state_dict(torch.load(CHECKPOINTS_DIR / "best_finetune_6cls.pth", map_location=DEVICE))
    model.eval()
    te = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)
    y_true, y_pred = [], []
    with torch.no_grad():
        for x, y in te:
            x, y = x.to(DEVICE), y.to(DEVICE)
            y_pred += model(x).argmax(1).cpu().tolist()
            y_true += y.cpu().tolist()
    test_acc = sum(a == b for a, b in zip(y_pred, y_true)) / len(y_true)
    print(f"\n[6cls] 最优验证 {best:.4f} / 测试一致率 {test_acc:.4f}"
          f"（对照 10 类生产 0.8315，同 89 张测试图）")

    tc, pc = Counter(y_true), Counter(y_pred)
    per = {}
    for cls, idx in sorted(test_ds.class_to_idx.items(), key=lambda kv: kv[1]):
        m = [(a, b) for a, b in zip(y_true, y_pred) if a == idx]
        rec = sum(a == b for a, b in m) / max(tc[idx], 1)
        per[cls] = {"recall": round(rec, 4), "n_test": tc[idx], "n_pred": pc[idx]}
        print(f"  {cls}: {per[cls]}")

    result = {
        "dropped": DROPPED, "kept": KEEP,
        "n_train": n, "n_val": nv, "n_test": nt,
        "best_val_acc": round(best, 4),
        "test_accuracy": round(test_acc, 4),
        "reference_10cls_production": 0.8315,
        "per_class": per,
        "config": "与 finetune_aug 一致：ablation_train(真实+GAN) 40epoch best_public 迁移；"
                  "测试集与 10 类基线完全同一批 89 张",
    }
    (EXPERIMENTS_DIR / "ablation_6cls.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / 'ablation_6cls.json'}")


if __name__ == "__main__":
    main()
