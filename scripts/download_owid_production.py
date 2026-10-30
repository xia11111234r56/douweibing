"""OWID 全球豆类产量兜底数据 → data/spatial/owid_bean_production.csv。

背景：FAOSTAT API（fenixservices.fao.org）在部分网络被 Cloudflare 拦截（HTTP 521/403）。
Our World in Data 的 "Bean production"（干豆大类，含绿豆 Vigna radiata）数据源自 FAO（FAOSTAT
Production QCL），可正常访问，作为 GIS 全球产量分布图的兜底数据源，出处如实标注。

OWID CSV 需浏览器 User-Agent 才能绕过其机器人拦截。

用法：python scripts/download_owid_production.py
"""
from __future__ import annotations

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT_CSV = ROOT / "data" / "spatial" / "owid_bean_production.csv"

URL = "https://ourworldindata.org/grapher/bean-production.csv"
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}


def main() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(URL, headers=UA, timeout=120)
    r.raise_for_status()
    OUT_CSV.write_bytes(r.content)
    lines = r.text.splitlines()
    print(f"✅ 保存 {OUT_CSV}（{len(lines)} 行）")
    print("表头:", lines[0])
    print("示例行:", lines[1] if len(lines) > 1 else "(空)")
    # 统计最新年份
    years = sorted({l.split(",")[2] for l in lines[1:] if len(l.split(",")) > 2})
    print("年份范围:", years[0] if years else "-", "→", years[-1] if years else "-")


if __name__ == "__main__":
    main()
