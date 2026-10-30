"""整理原始图片为 train/val/test 目录结构，并打印类别统计。

用法（ml/ 目录下）：
    python scripts/prepare_data.py
    python scripts/prepare_data.py --dry-run   # 只看映射与数量，不复制
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    CLASS_ALIASES,
    CLASS_NAMES,
    ORGANIZED_DIR,
    RANDOM_SEED,
    RAW_DIR,
    TEST_RATIO,
    TRAIN_RATIO,
    VAL_RATIO,
)

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def canonical_name(folder_name: str) -> str | None:
    return CLASS_ALIASES.get(folder_name.strip())


def collect_raw_images() -> dict[str, list[Path]]:
    """扫描 RAW_DIR，返回 {标准类名: [图片路径]}。跳过"未分类"目录。"""
    by_class: dict[str, list[Path]] = {}
    if not RAW_DIR.exists():
        print(f"[warn] 原始目录不存在: {RAW_DIR}")
        return by_class
    for folder in sorted(p for p in RAW_DIR.iterdir() if p.is_dir()):
        name = canonical_name(folder.name)
        if name is None:
            print(f"[skip] 无法识别的类别目录: {folder.name}（可在 config.CLASS_ALIASES 补充）")
            continue
        images = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
        ]
        if not images:
            print(f"[warn] 目录为空: {folder.name}")
            continue
        by_class.setdefault(name, []).extend(images)
    return by_class


def split_and_copy(by_class: dict[str, list[Path]], dry_run: bool) -> None:
    import random

    random.seed(RANDOM_SEED)
    for cls in CLASS_NAMES:
        images = by_class.get(cls, [])
        if not images:
            print(f"[warn] 类 {cls} 无图片，请补充数据（模型将无法识别该类）")
            continue
        random.shuffle(images)
        n = len(images)
        n_train = int(n * TRAIN_RATIO)
        n_val = int(n * VAL_RATIO)
        splits = {
            "train": images[:n_train],
            "val": images[n_train:n_train + n_val],
            "test": images[n_train + n_val:],
        }
        print(f"\n类 {cls}: 共 {n} 张 -> train {len(splits['train'])} / "
              f"val {len(splits['val'])} / test {len(splits['test'])}")
        for split, paths in splits.items():
            if not paths:
                continue
            dest_dir = ORGANIZED_DIR / split / cls
            dest_dir.mkdir(parents=True, exist_ok=True)
            for i, p in enumerate(paths):
                target = dest_dir / f"{i:04d}_{p.name}"
                if not dry_run:
                    shutil.copy2(p, target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计不复制")
    args = parser.parse_args()

    by_class = collect_raw_images()
    total = sum(len(v) for v in by_class.values())
    print(f"\n识别到 {len(by_class)} 个类别、共 {total} 张图片")
    for cls, paths in by_class.items():
        print(f"  {cls}: {len(paths)}")

    if not total:
        print("\n没有可用图片。请先把已分类图片放入 ml/data/raw/（每类一个文件夹）")
        sys.exit(1)

    split_and_copy(by_class, args.dry_run)
    if not args.dry_run:
        print(f"\n完成。整理结果位于 {ORGANIZED_DIR}")
        print("下一步：python train_classifier.py --stage finetune")


if __name__ == "__main__":
    main()
