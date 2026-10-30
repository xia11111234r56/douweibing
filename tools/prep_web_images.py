"""Web 美化用图本地一次性预处理（不入发布包，用 backend venv 的 PIL 运行）。

产出：
1. web/public/figures/   —— docs/paper/figures 全部论文实验图（真实图表）
2. web/public/login/     —— ml/data/raw 选 6 张原图压缩 ~1600px 供登录页背景/小方块
3. web/public/favicon.png—— touxiang.png 压成 64px
4. backend/data/backfill/ —— 每类采样 N 张压缩 ~800px，随发布包部署，供服务器真实推理回填

用法：backend/.venv/Scripts/python.exe tools/prep_web_images.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "ml" / "data" / "raw"
WEB_PUBLIC = ROOT / "web" / "public"
MINIAPP_DISEASES = ROOT / "miniapp" / "images" / "diseases"

# 每类回填采样张数（少数类别仅 1-2 张原图，取尽即可）
BACKFILL_PER_CLASS = {
    "健康": 4, "晕疫病": 4, "炭疽叶斑病": 4, "轮纹叶斑病": 3, "枯萎病": 2,
    "病毒病": 4, "细菌性疫病": 2, "叶腐病": 1, "细菌性萎蔫": 3, "虫食": 1,
}

# 登录页背景/小方块取材类别（每类取排序后第 1 张）
LOGIN_CLASSES = ["健康", "炭疽叶斑病", "晕疫病", "病毒病", "细菌性萎蔫", "轮纹叶斑病"]


def _compress(src: Path, dst: Path, max_w: int, quality: int) -> None:
    im = Image.open(src)
    if im.width > max_w:
        h = round(im.height * max_w / im.width)
        im = im.resize((max_w, h), Image.LANCZOS)
    im = im.convert("RGB")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, "JPEG", quality=quality, optimize=True)
    print(f"  {dst.name}  ({dst.stat().st_size // 1024}KB, {dst.parent.name})")


def main() -> None:
    # 1. 论文图表 → web/public/figures/
    figures_dir = WEB_PUBLIC / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "docs" / "paper" / "figures").glob("fig*.png"):
        shutil.copy2(f, figures_dir / f.name)
        print(f"  copied figures/{f.name}")

    # 2. 登录页 6 张压缩图
    for i, cls in enumerate(LOGIN_CLASSES, 1):
        files = sorted((RAW / cls).glob("*"))
        if not files:
            print(f"  [warn] 空类别：{cls}")
            continue
        _compress(files[0], WEB_PUBLIC / "login" / f"leaf-{i}.jpg", 1600, 82)

    # 3. favicon 64px
    favicon = Image.open(ROOT / "touxiang.png").convert("RGB").resize((64, 64), Image.LANCZOS)
    favicon.save(WEB_PUBLIC / "favicon.png", "PNG", optimize=True)
    print("  favicon.png (64px)")

    # 4. 回填采样 → backend/data/backfill/<病名>/
    for cls, n in BACKFILL_PER_CLASS.items():
        files = sorted((RAW / cls).glob("*"))[:n]
        for j, f in enumerate(files, 1):
            _compress(f, ROOT / "backend" / "data" / "backfill" / cls / f"{j:02d}.jpg", 800, 80)

    print("完成。")


if __name__ == "__main__":
    main()
