"""下载地图底图 GeoJSON（世界 + 中国省级）到 data/spatial/geojson/。

来源（公开免费，多镜像按顺序尝试）：
- 世界：jsdelivr 上 ECharts 官方世界地图 → GitHub johan/world.geo.json（兜底）
- 中国省级：阿里云 DataV GeoAtlas（ECharts 生态常用）
用法：python scripts/download_geojson.py
"""
from __future__ import annotations

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
GEOJSON_DIR = ROOT / "data" / "spatial" / "geojson"

SOURCES = {
    # 名称 → [(URL, 说明), ...] 依次尝试，成功即停
    "world": [
        (
            "https://cdn.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json",
            "世界国家边界（ECharts 官方，jsdelivr CDN）",
        ),
        (
            "https://fastly.jsdelivr.net/npm/echarts@4.9.0/map/json/world.json",
            "世界国家边界（ECharts 官方，fastly 镜像）",
        ),
        (
            "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json",
            "世界国家边界（GitHub johan）",
        ),
    ],
    "china": [
        (
            "https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json",
            "中国省级边界（阿里云 DataV）",
        ),
    ],
}


def main() -> None:
    GEOJSON_DIR.mkdir(parents=True, exist_ok=True)
    for name, candidates in SOURCES.items():
        ok = False
        for url, desc in candidates:
            try:
                r = requests.get(url, timeout=60)
                r.raise_for_status()
                target = GEOJSON_DIR / f"{name}.geojson"
                target.write_text(r.text, encoding="utf-8")
                size_mb = target.stat().st_size / 1e6
                print(f"✅ {name}.geojson（{desc}）{size_mb:.2f}MB")
                ok = True
                break
            except Exception as e:  # noqa: BLE001
                print(f"  ⤷ 尝试失败: {url}\n    {e}")
        if not ok:
            print(f"[失败] {name}: 所有镜像均不可达")


if __name__ == "__main__":
    main()
