"""人工复核结果入库：从 review_157_table.xlsx 读「复核结论」列（人工确认标签），
把对应图片**复制**进 organized/train/<人工结论>/（原图留在 pending_label）。

用法（ml/ 目录下）：
    python ingest_review.py                      # 全量入库
    python ingest_review.py --dry-run            # 只打印分布
    python ingest_review.py --xlsx 路径          # 指定表格
    python ingest_review.py --no-writeback       # 不回写 pool_annotation.csv 的最终标签列

文件名加 rev_<编号>_ 前缀（编号 = 复核表行号），保留人工来源可追溯且防重名。
重训前需删除 experiments/ablation_train 缓存。
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import openpyxl  # noqa: E402

from config import CLASS_NAMES, EXPERIMENTS_DIR, ORGANIZED_DIR, PENDING_DIR  # noqa: E402

_IMAGES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def read_confirmed(xlsx: Path) -> list[dict]:
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) if h is not None else "" for h in rows[0]]
    cols = {h: i for i, h in enumerate(header)}
    for need in ("编号", "标注池", "文件名", "建议标签", "复核结论"):
        if need not in cols:
            print(f"[错误] 表格缺列: {need}（现有列: {header}）")
            sys.exit(1)
    out = []
    for r in rows[1:]:
        if r[cols["编号"]] is None:
            continue
        label = r[cols["复核结论"]]
        if label is None or not str(label).strip():
            continue
        out.append({
            "编号": str(r[cols["编号"]]),
            "标注池": str(r[cols["标注池"]]).strip(),
            "文件名": str(r[cols["文件名"]]).strip(),
            "建议": str(r[cols["建议标签"]]).strip(),
            "结论": str(label).strip(),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xlsx", default=str(EXPERIMENTS_DIR / "review_157_table.xlsx"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-writeback", action="store_true")
    args = parser.parse_args()

    xlsx = Path(args.xlsx)
    if not xlsx.exists():
        print(f"[错误] 缺少 {xlsx}")
        sys.exit(1)

    confirmed = read_confirmed(xlsx)
    if not confirmed:
        print("[无] 表格「复核结论」列没有确认标签。")
        sys.exit(0)

    print(f"[计划] 共 {len(confirmed)} 张人工确认：")
    for cls, n in Counter(c["结论"] for c in confirmed).most_common():
        print(f"  {cls}: {n}")

    # 校验结论类名合法
    bad = [c for c in confirmed if c["结论"] not in CLASS_NAMES]
    if bad:
        print(f"[错误] {len(bad)} 个结论不在分类体系里，中止：")
        for c in bad:
            print(f"  {c['编号']} {c['文件名']} → {c['结论']}")
        sys.exit(1)

    if args.dry_run:
        return

    # 源文件齐全检查
    missing = []
    for c in confirmed:
        src = PENDING_DIR / c["标注池"] / c["文件名"]
        if not src.is_file():
            missing.append(f"{c['编号']} {c['文件名']}")
    if missing:
        print(f"[错误] {len(missing)} 个源缺失，中止入库：")
        for m in missing[:10]:
            print(f"  {m}")
        sys.exit(1)

    copied = 0
    for c in confirmed:
        dst_dir = ORGANIZED_DIR / "train" / c["结论"]
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / f"rev_{c['编号']}_{c['文件名']}"
        if dst.exists():
            continue  # 幂等
        shutil.copy2(PENDING_DIR / c["标注池"] / c["文件名"], dst)
        copied += 1
    print(f"\n[完成] 入库 {copied} 张 → {ORGANIZED_DIR / 'train'}")
    print("[提示] 重训前删除 experiments/ablation_train，让 build_augmented_train_dir 用扩充后的 train 重建。")

    # 回写 pool_annotation.csv 的「最终标签」列，标注存档完整
    if not args.no_writeback:
        csv_path = EXPERIMENTS_DIR / "pool_annotation.csv"
        if csv_path.exists():
            key = {(c["标注池"], c["文件名"]): c["结论"] for c in confirmed}
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
            if rows and "最终标签" not in rows[0]:
                rows[0]["最终标签"] = ""  # 保证列存在（DictWriter 按第一行 key 推断）
            n_upd = 0
            for r in rows:
                lab = key.get((r.get("标注池", ""), r.get("文件名", "")))
                if lab:
                    r["最终标签"] = lab
                    n_upd += 1
            fieldnames = list(rows[0].keys())
            with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows)
            print(f"[回写] pool_annotation.csv 已更新 {n_upd} 行「最终标签」。")
        else:
            print("[提示] 未找到 pool_annotation.csv，跳过回写。")


if __name__ == "__main__":
    main()
