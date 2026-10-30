"""公开数据整理 → ml/data/public/organized/{train,val}/{class}/

两阶段迁移的"阶段1 预训练"数据：
1. Mendeley 绿豆公开集（健康/毛虫/卷叶/MYMV，1080 张）—— 领域直接相关，必用
2. PlantVillage（38 类多作物，可选）—— 已下载则并入（类名前缀 `pv_` 防冲突）

用法：python prepare_public.py [--plantvillage]
类别标签保持公开集原生标签（pre-train 标签空间 ≠ 微调 10 类），
微调时通过 strict=False + 形状过滤只迁移骨干权重、重建分类头。
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PUBLIC_DIR, RANDOM_SEED  # noqa: E402

MENDELEY_SRC = PUBLIC_DIR / "mendeley_bean" / "raw" / "augmentation dataset(12360)" / "Mung bean(1080)"
# 公开标签 → 规范类名（保持原生语义，便于论文描述与 ImageFolder 处理）
MENDELEY_MAP = {
    "Healty leaf(288)": "healthy",
    "caterpillars(Phaseolus vulgaris)(296)": "caterpillar",
    "Leaf curl(400)": "leaf_curl",
    "Mungbean Yellow Mosaic Virus (MYMV)(96)": "mymv",
}

TRAIN_RATIO = 0.85
MAX_PER_CLASS = 600  # PlantVillage 每类上限，控制预训练规模（笔记本 GPU 友好）


def copy_split(src_root: Path, class_map: dict[str, str], out_root: Path, max_each: int | None = None):
    """把 src_root 下的子文件夹（映射到 class_map）按比例复制进 out_root/{train,val}/。"""
    for raw_name, cls in class_map.items():
        src = src_root / raw_name
        if not src.is_dir():
            print(f"[跳过] 缺 {raw_name}")
            continue
        files = sorted(p for p in src.iterdir() if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png"))
        if max_each and len(files) > max_each:
            random.seed(RANDOM_SEED)
            files = random.sample(files, max_each)
        random.seed(RANDOM_SEED)
        random.shuffle(files)
        n_train = max(int(len(files) * TRAIN_RATIO), 1)
        for i, f in enumerate(files):
            split = "train" if i < n_train else "val"
            dst = out_root / split / cls
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / f.name)
        print(f"{raw_name} → {cls}: {len(files)} 张（train {n_train} / val {len(files)-n_train}）")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plantvillage", action="store_true", help="并入 PlantVillage（需已下载）")
    args = parser.parse_args()

    out = PUBLIC_DIR / "organized"
    if out.exists():
        shutil.rmtree(out)

    if not MENDELEY_SRC.exists():
        print("[中止] 缺 Mendeley 绿豆数据，先下载解压到 ml/data/public/mendeley_bean/")
        return

    # 1) Mendeley 绿豆
    copy_split(MENDELEY_SRC, MENDELEY_MAP, out)
    # 2) PlantVillage（可选，取 color 分类；每类限 MAX_PER_CLASS 控规模）
    if args.plantvillage:
        pv_root = PUBLIC_DIR / "plantvillage_dl" / "raw" / "color"
        if pv_root.is_dir():
            pv_classes = {d.name: f"pv_{d.name}" for d in pv_root.iterdir() if d.is_dir()}
            copy_split(pv_root, pv_classes, out, max_each=MAX_PER_CLASS)
        else:
            print("[跳过] 未找到 PlantVillage color 目录")

    for split in ("train", "val"):
        n = sum(len(list(p.iterdir())) for p in (out / split).iterdir() if p.is_dir()) if (out / split).exists() else 0
        print(f"{split}: {n} 张")


if __name__ == "__main__":
    main()
