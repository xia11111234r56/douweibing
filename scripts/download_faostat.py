"""下载 FAOSTAT 绿豆产量/面积数据 → data/spatial/faostat_mungbean.csv 并入库 spatial_data。

FAOSTAT 公开免费，无需注册/Key。Production 域 (QCL)：
- 产量 Production     element 5510，单位 吨
- 收获面积 Area harvested element 5312，单位 公顷

用法：python scripts/download_faostat.py [--year 2023]
首次运行会自动探测绿豆在 FAOSTAT 中的 item 代码；若未找到绿豆专属条目，
会回退到 "Beans, dry"（菜豆/干豆）并提示，便于人工核对。
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "data" / "spatial" / "faostat_mungbean.csv"

API = "https://fenixservices.fao.org/faostat/api/v1"
TIMEOUT = 60

ELEMENTS = {"production": 5510, "area": 5312}


def find_item() -> tuple[str, str] | None:
    r = requests.get(f"{API}/en/items?domain_code=QCL", timeout=TIMEOUT)
    r.raise_for_status()
    items = r.json()["data"]
    cands = [
        it for it in items
        if "mung" in it["item"].lower() or "vigna" in it["item"].lower()
    ]
    if cands:
        it = cands[0]
        return str(it["item_code"]), it["item"]
    beans = [
        it for it in items
        if "bean" in it["item"].lower() and it["item"].lower().startswith("beans")
    ]
    if beans:
        it = beans[0]
        print("[warn] 未找到绿豆专属条目，回退到:", it["item"])
        return str(it["item_code"]), it["item"]
    return None


def fetch(item_code: str, element: int) -> list[dict]:
    url = (
        f"{API}/en/data/QCL?item={item_code}&element={element}"
        "&area=%5E5000&year=%5E2024"  # %5E = ^ 前缀（FAOSTAT 语法：^5000=World）
    )
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json().get("data", [])
    out = []
    for row in rows:
        out.append({
            "area_code": row.get("area_code"),
            "area_name": row.get("area"),
            "year": int(row["year"]),
            "element": "production" if element == 5510 else "area",
            "value": float(row.get("value") or 0),
            "unit": row.get("unit"),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    found = find_item()
    if found is None:
        print("[错误] 未能探测到豆类条目，请到 https://www.fao.org/faostat 手工确认 item 代码")
        sys.exit(1)
    item_code, item_name = found
    print(f"使用 FAOSTAT item: {item_code} {item_name}")

    all_rows: list[dict] = []
    for el_name, el_code in ELEMENTS.items():
        rows = fetch(item_code, el_code)
        if args.year:
            rows = [r for r in rows if r["year"] == args.year]
        all_rows.extend(rows)
        print(f"{el_name}: {len(rows)} 条")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()) if all_rows else [])
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"✅ 保存 {len(all_rows)} 条 -> {OUT_CSV}")
    print("提示：GIS 模块再按地区/年份聚合后写入数据库 spatial_data 表")


if __name__ == "__main__":
    main()
