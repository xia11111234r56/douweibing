"""整理原始绿豆数据 → ml/data/organized/{train,val,test}/{类}/，按「图」分层划分（无泄漏）。

策略（小类特殊处理，保证可验证又不浪费样本）：
- 每类数量 < 3   → 全部进 train（样本太少无法评估，报告中注明）
- 每类 3~5      → 留 1 张 val + 1 张 test，其余 train
- 每类 >= 6     → 按 70/15/15 分层切分

输出：organized/ 目录 + experiments/split_report.json（含每类划分明细，可追溯）。
用法：python prepare_data.py
"""
import json
import random
import shutil
from pathlib import Path

from config import CLASS_NAMES, EXPERIMENTS_DIR, ORGANIZED_DIR, RAW_DIR, RANDOM_SEED

TRAIN_RATIO, VAL_RATIO = 0.70, 0.15


def split_sizes(n: int) -> tuple[int, int, int]:
    """返回 (train, val, test)。"""
    if n < 3:
        return n, 0, 0
    if n <= 5:
        return n - 2, 1, 1
    n_test = max(1, round(n * 0.15))
    n_val = max(1, round(n * 0.15))
    n_train = n - n_val - n_test
    return n_train, n_val, n_test


def main() -> None:
    random.seed(RANDOM_SEED)
    # 仅保留 raw/ 中实际存在的类（顺序与 CLASS_NAMES 一致）
    classes = [c for c in CLASS_NAMES if (RAW_DIR / c).exists()]
    report: dict = {"seed": RANDOM_SEED, "classes": {}}

    # 清空旧划分，重建
    if ORGANIZED_DIR.exists():
        shutil.rmtree(ORGANIZED_DIR)
    for split in ("train", "val", "test"):
        (ORGANIZED_DIR / split).mkdir(parents=True, exist_ok=True)

    total = {"train": 0, "val": 0, "test": 0}
    for cls in classes:
        src_dir = RAW_DIR / cls
        imgs = sorted(src_dir.glob("*"), key=lambda p: p.name)
        n = len(imgs)
        n_train, n_val, n_test = split_sizes(n)
        random.shuffle(imgs)
        train_imgs = imgs[:n_train]
        val_imgs = imgs[n_train:n_train + n_val]
        test_imgs = imgs[n_train + n_val:]

        for split, batch in (("train", train_imgs), ("val", val_imgs), ("test", test_imgs)):
            dest = ORGANIZED_DIR / split / cls
            dest.mkdir(parents=True, exist_ok=True)
            for f in batch:
                shutil.copy2(f, dest / f.name)
            total[split] += len(batch)

        report["classes"][cls] = {"total": n, "train": len(train_imgs),
                                  "val": len(val_imgs), "test": len(test_imgs),
                                  "note": "" if n >= 6 else ("样本过少，仅训练" if n < 3 else "小类，仅各留1张验证")}

    report["total"] = total
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "split_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'类':<10} {'总量':>4} {'train':>6} {'val':>4} {'test':>5}")
    for cls in classes:
        r = report["classes"][cls]
        print(f"{cls:<10} {r['total']:>4} {r['train']:>6} {r['val']:>4} {r['test']:>5}  {r['note']}")
    print(f"{'合计':<10} {sum(report['classes'][c]['total'] for c in classes):>4} "
          f"{total['train']:>6} {total['val']:>4} {total['test']:>5}")
    print(f"划分报告: {EXPERIMENTS_DIR / 'split_report.json'}")


if __name__ == "__main__":
    main()
