"""导出待人工复核清单：从 pool_annotation.csv 取置信度<阈值（默认 0.6）的行，
生成排序 CSV + 缩略图联系表 HTML（按建议标签分组），方便肉眼快速审核。

排序：小类（叶腐/枯萎/细菌性疫病/虫食）置顶 → 次小类（萎蔫/轮纹）→ 其余，同类内置信度升序。

用法（ml/ 目录下）：
    python export_review.py                              # 阈值 0.6
    python export_review.py --threshold 0.8 --thumb-off  # 只导 CSV，不生成缩略图
产物：
    experiments/review_<n>_list.csv         （utf-8-sig，含空白「复核结论/最终标签/备注」列）
    experiments/review_<n>_thumb/<建议标签>/*.jpg   （240px 缩略图，审完可删）
    experiments/review_<n>.html             （联系表，浏览器打开分组看图）
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torchvision.transforms as T  # noqa: E402
from PIL import Image  # noqa: E402

from config import EXPERIMENTS_DIR, PENDING_DIR  # noqa: E402

# 补小类优先：稀缺 4 类 → 次小类 → 其余
_TIER0 = {"叶腐病", "枯萎病", "细菌性疫病", "虫食"}
_TIER1 = {"细菌性萎蔫", "轮纹叶斑病"}
_POOL_PREFIX = {"绿豆_未知": "wz_", "邢台_20260617": "xt_"}

_ESC = {  # HTML 转义（类名/文件名里有中文与特殊字符）
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}


def esc(s: str) -> str:
    return "".join(_ESC.get(c, c) for c in s)


def tier(cls: str) -> int:
    if cls in _TIER0:
        return 0
    if cls in _TIER1:
        return 1
    return 2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.6, help="置信度阈值，低于此进入复核")
    parser.add_argument("--thumb-off", action="store_true", help="不生成缩略图/HTML")
    parser.add_argument("--orig", action="store_true", help="复制原图到独立文件夹（编号_建议标签_原文件名）")
    args = parser.parse_args()

    csv_path = EXPERIMENTS_DIR / "pool_annotation.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    rev = [r for r in rows if float(r["置信度"]) < args.threshold]
    rev.sort(key=lambda r: (tier(r["建议标签"]), float(r["置信度"])))
    n = len(rev)
    print(f"[复核] 共 {n} 张（阈值 {args.threshold}），排序优先级：小类→次小类→其余，同类内置信度升序")

    tag = f"review_{n}"
    fieldnames = ["编号"] + list(rev[0].keys()) + ["小类?", "复核结论", "最终标签", "备注"]
    for i, r in enumerate(rev, 1):
        r["编号"] = f"{i:03d}"
        r["小类?"] = "是" if tier(r["建议标签"]) == 0 else ""
        r["复核结论"] = ""
        r["最终标签"] = ""
        r["备注"] = ""
    out_csv = EXPERIMENTS_DIR / f"{tag}_list.csv"
    try:
        with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rev)
    except PermissionError:
        # 旧版 CSV 可能正被 Excel 占用 → 换名写入，不覆盖正在查看的旧文件
        out_csv = EXPERIMENTS_DIR / f"{tag}_table.csv"
        with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rev)
    print(f"CSV: {out_csv}")

    # 原图独立文件夹：编号_建议标签_原文件名（编号 = CSV 行号，一一对应）
    if args.orig:
        orig_root = EXPERIMENTS_DIR / f"{tag}_orig"
        orig_root.mkdir(parents=True, exist_ok=True)
        total_bytes, n_copied, missing = 0, 0, []
        for i, r in enumerate(rev, 1):
            src = PENDING_DIR / r["标注池"] / r["文件名"]
            if not src.is_file():
                missing.append(f"{i:03d} {r['文件名']}")
                continue
            dst = orig_root / f"{i:03d}_{r['建议标签']}_{src.name}"
            shutil.copy2(src, dst)
            total_bytes += src.stat().st_size
            n_copied += 1
        if missing:
            print(f"[警告] {len(missing)} 个源缺失，未复制：")
            for m in missing:
                print(f"  {m}")
        print(f"原图: {orig_root}（{n_copied} 张，约 {total_bytes / 1e6:.0f} MB，审完可删）")

    if args.thumb_off:
        return

    # 缩略图（240px）按建议标签分组 + HTML 联系表
    thumb_root = EXPERIMENTS_DIR / f"{tag}_thumb"
    html_path = EXPERIMENTS_DIR / f"{tag}.html"
    to_small = T.Resize((240, 240), antialias=True)
    parts = [f"<!doctype html><html lang=zh><meta charset=utf-8><title>复核 {n} 张</title>",
             "<style>body{font-family:system-ui,sans-serif;margin:24px;background:#f5f6f8}"
             "h2{background:#2E7D32;color:#fff;padding:8px 14px;border-radius:6px;margin:28px 0 12px}"
             ".grid{display:flex;flex-wrap:wrap;gap:10px}.card{background:#fff;border:1px solid #e3e6ea;"
             "border-radius:8px;padding:8px;width:170px;font-size:11px;color:#333}"
             ".card img{width:152px;height:152px;object-fit:cover;border-radius:4px;display:block;margin:0 auto 6px}"
             ".c{color:#c62828;font-weight:700}.n{color:#888}</style><body>"]
    per_cls: dict[str, list] = {}
    for r in rev:
        per_cls.setdefault(r["建议标签"], []).append(r)

    for cls in sorted(per_cls, key=tier):
        parts.append(f"<h2>{esc(cls)}（{len(per_cls[cls])} 张）</h2><div class=grid>")
        for r in per_cls[cls]:
            src = PENDING_DIR / r["标注池"] / r["文件名"]
            if not src.is_file():
                parts.append(f"<div class=card><span class=n>[缺源] {esc(r['文件名'])}</span></div>")
                continue
            img = Image.open(src).convert("RGB")
            thumb = to_small(img)
            tdir = thumb_root / cls
            tdir.mkdir(parents=True, exist_ok=True)
            tpath = tdir / f"{_POOL_PREFIX.get(r['标注池'], 'p_')}{Path(r['文件名']).stem}.jpg"
            thumb.save(tpath, "JPEG", quality=80)
            rel = tpath.relative_to(thumb_root.parent).as_posix()
            parts.append(
                f"<div class=card><img src='{esc(rel)}'>"
                f"<b>{esc(r['建议标签'])}</b> <span class=c>{float(r['置信度']):.2f}</span>"
                f"<br>{esc(r['文件名'])}<br><span class=n>候2 {esc(r['候选2'])} "
                f"{float(r['置信度2']):.2f} 候3 {esc(r['候选3'])} {float(r['置信度3']):.2f}</span></div>")
        parts.append("</div>")
    parts.append("</body></html>")
    html_path.write_text("".join(parts), encoding="utf-8")
    print(f"缩略图: {thumb_root}（审完可删）\nHTML: {html_path}")


if __name__ == "__main__":
    main()
