"""高置信分类建议入库：从 pool_annotation.csv 读置信度≥阈值（默认 0.8）的行，
按「建议标签」把图片**复制**进 organized/train/<类>/（原图留在 pending_label，不移动）。

用法（ml/ 目录下）：
    python ingest_pool.py                        # 阈值 0.8，全池入库
    python ingest_pool.py --threshold 0.7         # 自定义阈值
    python ingest_pool.py --dry-run               # 只打印将入库的分布，不实际复制
    python ingest_pool.py --pool 邢台_20260617    # 只处理指定池

文件名加池前缀（wz_/xt_…）避免跨池重名，同时保留来源可追溯。
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import EXPERIMENTS_DIR, ORGANIZED_DIR, PENDING_DIR  # noqa: E402

# 标注池名 → 入库文件名前缀（避免跨池重名）
_POOL_PREFIX = {
    "绿豆_未知": "wz_",
    "邢台_20260617": "xt_",
}
_IMAGES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=None, help="CSV 路径，默认 experiments/pool_annotation.csv")
    parser.add_argument("--threshold", type=float, default=0.8, help="置信度阈值，默认 0.8")
    parser.add_argument("--pool", default=None, help="只处理指定池，默认全部")
    parser.add_argument("--dry-run", action="store_true", help="只打印将入库的分布")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else EXPERIMENTS_DIR / "pool_annotation.csv"
    if not csv_path.exists():
        print(f"[错误] 缺少 {csv_path}，先运行 annotate_pool.py")
        sys.exit(1)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    picked = [r for r in rows if float(r["置信度"]) >= args.threshold]
    if args.pool:
        picked = [r for r in picked if r["标注池"] == args.pool]
    if not picked:
        print(f"[无] 没有置信度≥{args.threshold} 的建议。")
        sys.exit(0)

    from collections import Counter
    print(f"[计划] 共 {len(picked)} 张将入库（阈值 {args.threshold}）：")
    for cls, n in Counter(r["建议标签"] for r in picked).most_common():
        print(f"  {cls}: {n}")

    if args.dry_run:
        return

    # 先核对源文件都在，避免复制到一半失败
    missing = []
    for r in picked:
        src = PENDING_DIR / r["标注池"] / r["文件名"]
        if not src.is_file():
            missing.append(str(src))
    if missing:
        print(f"[错误] {len(missing)} 个源文件缺失，中止入库：")
        for m in missing[:10]:
            print(f"  {m}")
        sys.exit(1)

    copied = 0
    for r in picked:
        cls = r["建议标签"]
        dst_dir = ORGANIZED_DIR / "train" / cls
        dst_dir.mkdir(parents=True, exist_ok=True)
        prefix = _POOL_PREFIX.get(r["标注池"], "pool_")
        dst = dst_dir / f"{prefix}{r['文件名']}"
        if dst.exists():
            # 已存在则跳过（幂等，不覆盖已有图）
            continue
        shutil.copy2(PENDING_DIR / r["标注池"] / r["文件名"], dst)
        copied += 1

    print(f"\n[完成] 入库 {copied} 张 → {ORGANIZED_DIR / 'train'}")
    print("[提示] 重训前请删除 experiments/ablation_train 缓存，让 build_augmented_train_dir 用扩充后的 train 重建。")


if __name__ == "__main__":
    main()
