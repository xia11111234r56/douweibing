"""5 折交叉验证：601 张真实图全量评估（统计上最稳的"真实准确率"估计）。

背景：固定 89 张测试集太小（每张≈1.1% 一致率），且小类（叶腐/枯萎/疫病/虫食）support=0。
5 折 CV 把 601 张真实图按类分层分 5 折，每折轮流做测试，每张图恰好被评估一次：
  - 覆盖全部 10 类（含小类）
  - 输出 mean±std / min-max 与合并按类 recall
  - 训练配置与生产一致（mobilenetv3_large、40 epoch、AdamW lr=1e-4、best_public 迁移、
    普通 CrossEntropyLoss、CachedFolder 在线增强）
  - 用真实图训练（不含 GAN：GAN 图由全量真实图生成，跨折会泄漏），作为保守估计；
    生产 GAN 模型在固定 89/178 张上的数另报（0.8315 / 0.8483）。

协议：StratifiedKFold(5, shuffle, random_state=42)；每折训练 40 epoch 后评估末轮模型
在测试折上的一致率（CV 无独立 val，不按 best-val 选择，与 ablation 末轮评估一致）。

产物：experiments/cv_report.json
用法（ml/ 目录下，需 torch+CUDA 的 venv）：
    python finetune_cv.py
"""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from torch.utils.data import DataLoader, Subset  # noqa: E402

from ablation import CachedFolder, train_one_epoch  # noqa: E402
from config import (  # noqa: E402
    BATCH_SIZE,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EPOCHS_FINETUNE,
    EXPERIMENTS_DIR,
    LR_FINETUNE,
    ORGANIZED_DIR,
    RANDOM_SEED,
    WEIGHT_DECAY,
)
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
N_SPLITS = 5


def build_cv_all_dir() -> Path:
    out = EXPERIMENTS_DIR / "cv_all"
    if out.exists():
        shutil.rmtree(out)
    for split in ("train", "val", "test"):
        for cls in CLASS_NAMES:
            s = ORGANIZED_DIR / split / cls
            if not s.exists():
                continue
            dst = out / cls
            dst.mkdir(parents=True, exist_ok=True)
            for p in s.iterdir():
                if p.is_file():
                    shutil.copy2(p, dst / p.name)
    return out


def main() -> None:
    torch.manual_seed(RANDOM_SEED)
    cv_root = build_cv_all_dir()
    # 双缓存：训练折用增强模式，测试折用 Resize 模式（代码与生产共用）
    print(f"[cv] 缓存 {len(list(cv_root.iterdir()))} 类 …（设备 {DEVICE}）")
    ds_train = CachedFolder(cv_root, train=True)
    ds_eval = CachedFolder(cv_root, train=False)
    print(f"[cv] 全量真实图 {len(ds_train)} 张（organize train+val+test）")

    y_all = [y for _, y in ds_train.items]
    skf = StratifiedKFold(n_splits=N_SPLITS, shuffle=True, random_state=RANDOM_SEED)
    folds, y_true_all, y_pred_all = [], [], []
    for fold, (tr_idx, te_idx) in enumerate(skf.split(list(range(len(y_all))), y_all), 1):
        print(f"\n[fold {fold}/{N_SPLITS}] 训练 {len(tr_idx)} / 测试 {len(te_idx)}")
        tr = DataLoader(Subset(ds_train, tr_idx), batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
        te = DataLoader(Subset(ds_eval, te_idx), batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

        model = build_model(pretrained=True).to(DEVICE)
        init = CHECKPOINTS_DIR / "best_public.pth"
        state = torch.load(init, map_location=DEVICE)
        ms = model.state_dict()
        filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
        model.load_state_dict(filtered, strict=False)
        optimizer = torch.optim.AdamW(model.parameters(), lr=LR_FINETUNE, weight_decay=WEIGHT_DECAY)
        criterion = nn.CrossEntropyLoss()

        for epoch in range(EPOCHS_FINETUNE):
            train_one_epoch(model, tr, criterion, optimizer)
            if (epoch + 1) % 10 == 0:
                print(f"[fold {fold}] epoch {epoch + 1}/{EPOCHS_FINETUNE}")

        model.eval()
        correct = 0
        with torch.no_grad():
            for x, y in te:
                x, y = x.to(DEVICE), y.to(DEVICE)
                pred = model(x).argmax(1).cpu().tolist()
                y = y.cpu().tolist()
                correct += sum(a == b for a, b in zip(pred, y))
                y_pred_all += pred
                y_true_all += y
        acc = correct / len(te_idx)
        folds.append({"fold": fold, "n_test": len(te_idx), "test_acc": round(acc, 4)})
        print(f"[fold {fold}] 测试一致率 {acc:.4f}（累计 {len(y_true_all)} 张）")

    accs = [f["test_acc"] for f in folds]
    pooled = sum(a == b for a, b in zip(y_pred_all, y_true_all)) / len(y_true_all)
    mean, std = float(np.mean(accs)), float(np.std(accs, ddof=1))
    print(f"\n[cv] 各折: {accs}")
    print(f"[cv] 均值 {mean:.4f} ± {std:.4f}（min {min(accs):.4f} / max {max(accs):.4f}）")
    print(f"[cv] 合并(pooled)一致率 {pooled:.4f}（{len(y_true_all)} 张全评估）")

    tc, pc = Counter(y_true_all), Counter(y_pred_all)
    per = {}
    cls_order = sorted(ds_train.class_to_idx, key=ds_train.class_to_idx.get)
    for cls, idx in zip(cls_order, range(len(cls_order))):
        m = [(a, b) for a, b in zip(y_true_all, y_pred_all) if a == idx]
        rec = sum(a == b for a, b in m) / max(tc[idx], 1)
        per[cls] = {"recall": round(rec, 4), "n_test": tc[idx], "n_pred": pc[idx]}
        print(f"  {cls}: {per[cls]}")

    result = {
        "method": "5 折 StratifiedKFold，601 张真实图（train+val+test 全量），每张图恰被评估一次；"
                  "真实图训练（不含 GAN，避免跨折泄漏），40epoch，best_public 迁移，末轮模型评估测试折",
        "n_splits": N_SPLITS, "n_total": len(y_true_all),
        "folds": folds,
        "mean": round(mean, 4), "std": round(std, 4),
        "min": min(accs), "max": max(accs),
        "pooled_accuracy": round(pooled, 4),
        "per_class": per,
        "note": "保守估计（真实-only）；生产 GAN 模型固定集：test89=0.8315, val+test178=0.8483",
    }
    (EXPERIMENTS_DIR / "cv_report.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / 'cv_report.json'}")


if __name__ == "__main__":
    main()
