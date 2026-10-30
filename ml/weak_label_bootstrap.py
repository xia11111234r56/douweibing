"""弱标签自举消融：3-seed 投票采纳的池子样本并入训练集，与真实基线对比。

采纳条件（experiments/pool_vote_accept.csv 建议采纳=是）：
- 3 模型投票一致 + 平均置信 >= 0.9 + 大类白名单（eval_178 实测准确率 ~92%）

本脚本执行：
1. 泄漏检查：采纳图 md5 与 organized val/test 比对，有重叠立即中止
2. 构建 experiments/weak_label/{类}/wl_{原名}（按预测类归档）
3. 构建 experiments/ablation_train_weaklabel/ = real/train + weak_label

用法（ml/ 目录下）：
    python weak_label_bootstrap.py             # 只做 1-3 步（构建）
    python weak_label_bootstrap.py --ablate    # 构建 + 多 seed 配对消融
产物：
    experiments/weak_label_ablation_report.json
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ablation import train_and_eval  # noqa: E402
from config import CLASS_NAMES, EXPERIMENTS_DIR, ORGANIZED_DIR, PENDING_DIR  # noqa: E402

ACCEPT_CSV = EXPERIMENTS_DIR / "pool_vote_accept.csv"
WEAK_DIR = EXPERIMENTS_DIR / "weak_label"
MERGE_DIR = EXPERIMENTS_DIR / "ablation_train_weaklabel"
REPORT = EXPERIMENTS_DIR / "weak_label_ablation_report.json"
EPOCHS = 30


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_accepts() -> list[dict]:
    """读采纳清单，返回 [{pool, fname, label}]。"""
    if not ACCEPT_CSV.exists():
        print(f"[错误] 缺少 {ACCEPT_CSV}，先跑池子投票脚本")
        sys.exit(1)
    rows = []
    with ACCEPT_CSV.open(encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["建议采纳"] == "是":
                rows.append({"pool": r["标注池"], "fname": r["文件名"], "label": r["预测类"]})
    print(f"[采纳清单] {len(rows)} 张")
    return rows


def check_leak(accepts: list[dict]) -> list[dict]:
    """md5 比对采纳图与 val/test，返回通过（无泄漏）的采纳项。"""
    evals = []
    for sub in ["val", "test"]:
        root = ORGANIZED_DIR / sub
        for cls in sorted(p.name for p in root.iterdir() if p.is_dir()):
            evals.extend(p for p in (root / cls).iterdir() if p.is_file())
    print(f"[泄漏检查] 评估集 {len(evals)} 张，计算采纳图 md5…")
    eval_md5 = {md5(p) for p in evals}
    ok = []
    for item in accepts:
        src = PENDING_DIR / item["pool"] / item["fname"]
        if not src.exists():
            print(f"  [警告] 缺图 {src}，跳过")
            continue
        h = md5(src)
        if h in eval_md5:
            print(f"  [泄漏!] {item['pool']}/{item['fname']} 与评估集内容相同，中止")
            sys.exit(1)
        ok.append(item)
    print(f"[泄漏检查] 无重叠，{len(ok)} 张通过")
    return ok


def build(accepts: list[dict]) -> Path:
    """构建 weak_label 与合并训练集。"""
    if WEAK_DIR.exists():
        shutil.rmtree(WEAK_DIR)
    n = 0
    for item in accepts:
        src = PENDING_DIR / item["pool"] / item["fname"]
        dst_dir = WEAK_DIR / item["label"]
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst_dir / f"wl_{item['fname']}")
        n += 1
    print(f"[weak_label] {n} 张已按预测类归档 -> {WEAK_DIR}")

    if MERGE_DIR.exists():
        shutil.rmtree(MERGE_DIR)
    for cls in CLASS_NAMES:
        real = ORGANIZED_DIR / "train" / cls
        weak = WEAK_DIR / cls
        dst = MERGE_DIR / cls
        if real.exists():
            shutil.copytree(real, dst)
        if weak.exists():
            dst.mkdir(parents=True, exist_ok=True)
            for p in weak.iterdir():
                shutil.copy2(p, dst / p.name)
    real_n = sum(1 for cls in CLASS_NAMES for _ in (ORGANIZED_DIR / "train" / cls).iterdir())
    weak_n = sum(1 for _ in WEAK_DIR.rglob("*.jpg"))
    print(f"[合并] real/train {real_n} + weak_label {weak_n} -> {MERGE_DIR}")
    return MERGE_DIR


def ablate(train_root: Path, seeds: list[int]) -> dict:
    """多 seed 配对消融：每 seed 重跑 baseline 与 +弱标签（同环境对比）。"""
    rows = []
    for seed in seeds:
        base = train_and_eval(ORGANIZED_DIR / "train", f"baseline_wl_s{seed}", EPOCHS, seed=seed)
        var = train_and_eval(train_root, f"weaklabel_s{seed}", EPOCHS, seed=seed)
        delta = var["test_acc"] - base["test_acc"]
        rows.append({"seed": seed, "baseline_test": base["test_acc"],
                     "weaklabel_test": var["test_acc"], "delta": round(delta, 4)})
        print(f"[seed {seed}] baseline {base['test_acc']:.4f} / +弱标签 {var['test_acc']:.4f}  delta {delta:+.4f}")
    deltas = [r["delta"] for r in rows]
    m = sum(deltas) / len(deltas)
    sd = (sum((d - m) ** 2 for d in deltas) / (len(deltas) - 1)) ** 0.5
    return {"seeds": rows, "mean_delta": round(m, 4), "std_delta": round(sd, 4)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ablate", action="store_true", help="构建后跑多 seed 配对消融")
    parser.add_argument("--seeds", default="42,1000,7777")
    args = parser.parse_args()

    accepts = collect_accepts()
    accepts = check_leak(accepts)
    train_root = build(accepts)

    if args.ablate:
        seeds = [int(s.strip()) for s in args.seeds.split(",") if s.strip()]
        report = ablate(train_root, seeds)
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"\n报告: {REPORT}")
