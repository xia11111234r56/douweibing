"""空间数据入库：OWID 全球绿豆产量 + WorldClim 省级 7 月气候与病害风险指数。

风险模型（规则式，可解释）：
- 高温高湿（7月均温 24~30℃ 且降水充足）利于晕疫病/炭疽叶斑病/细菌性疫病
- 风险指数 = 100 × (0.5×温度适宜度 + 0.5×湿度适宜度)
- 等级：<40 低 / 40~60 中 / 60~75 较高 / ≥75 高

产物写入 spatial_data 表，供 /api/gis/* 查询。
用法：python scripts/ingest_spatial.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pandas as pd

from app.config import SPATIAL_DIR
from app.db import SessionLocal, init_db
from app.models import SpatialData

YEARS = list(range(2019, 2025))  # OWID 最近 6 年


def ingest_owid_production(db) -> int:
    csv_path = SPATIAL_DIR / "owid_bean_production.csv"
    if not csv_path.exists():
        print("[跳过] 缺少 owid_bean_production.csv")
        return 0
    df = pd.read_csv(csv_path)
    df = df.rename(columns={"Entity": "region_name", "Code": "region_code",
                            "Year": "year", "Dry beans - Production (tonnes)": "value"})
    # 过滤聚合行（FAO 地区合计无国家代码）与无值行
    df = df[(df["year"].isin(YEARS)) & df["value"].notna()
            & df["region_code"].notna() & (df["region_name"] != "World")]
    n = 0
    for _, r in df.iterrows():
        db.add(SpatialData(
            region_code=str(r["region_code"]) if pd.notna(r["region_code"]) else None,
            region_name=r["region_name"], region_level="country",
            year=int(r["year"]), metric="production",
            value=float(r["value"]), unit="tonnes", source="OWID/FAOSTAT",
        ))
        n += 1
    print(f"OWID 绿豆产量入库 {n} 条（{len(YEARS)} 年 × 各国）")
    return n


def _load_july_climate() -> dict[tuple, tuple]:
    """返回 {(lat,lon): (tavg, prec)} 7 月网格。"""
    csv_path = SPATIAL_DIR / "worldclim_china.csv"
    if not csv_path.exists():
        return {}
    df = pd.read_csv(csv_path)
    jul = df[df["month"] == 7]
    return {(row["lat"], row["lon"]): (row["tavg"], row["prec"]) for _, row in jul.iterrows()}


def _nearest_climate(grid, lon, lat):
    best, best_d = None, 1e9
    for (glat, glon), val in grid.items():
        d = (glat - lat) ** 2 + (glon - lon) ** 2
        if d < best_d:
            best_d, best = d, val
    return best


def temp_score(t: float) -> float:
    if t < 20: return 0.2
    if t < 24: return 0.5
    if t < 28: return 0.8
    if t <= 32: return 1.0
    return 0.7  # 过高温反而不利


def hum_score(p: float) -> float:
    if p < 50: return 0.0
    if p < 100: return 0.3
    if p < 150: return 0.5
    if p < 200: return 0.7
    return 0.9


def risk_level(idx: float) -> str:
    if idx < 40: return "低"
    if idx < 60: return "中"
    if idx < 75: return "较高"
    return "高"


def ingest_province_risk(db) -> int:
    geojson = SPATIAL_DIR / "geojson" / "china.geojson"
    if not geojson.exists():
        print("[跳过] 缺少 china.geojson")
        return 0
    gj = json.loads(geojson.read_text(encoding="utf-8"))
    grid = _load_july_climate()
    if not grid:
        print("[跳过] 缺少 worldclim_china.csv")
        return 0

    n = 0
    for feat in gj["features"]:
        prop = feat["properties"]
        name = prop["name"]
        if prop.get("level") != "province":
            continue
        lon, lat = prop.get("center") or prop.get("centroid")
        if not lon:
            continue
        climate = _nearest_climate(grid, lon, lat)
        if not climate:
            continue
        tavg, prec = climate
        risk = round(100 * (0.5 * temp_score(tavg) + 0.5 * hum_score(prec)), 1)
        for metric, value in (("climate_tavg_jul", tavg), ("climate_prec_jul", prec), ("risk_index", risk)):
            db.add(SpatialData(
                region_code=str(prop["adcode"]), region_name=name,
                region_level="province", year=2023, metric=metric,
                value=value, unit=None, source="WorldClim2.1",
            ))
        n += 1
    print(f"省级 7 月气候+风险指数入库 {n} 省")
    return n


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        cnt = db.query(SpatialData).count()
        if cnt > 0:
            print(f"spatial_data 已有 {cnt} 条，跳过（如需重置删除 backend/app.db 后重跑）")
            return
        ingest_owid_production(db)
        ingest_province_risk(db)
        db.commit()
        print(f"入库完成，spatial_data 共 {db.query(SpatialData).count()} 条")
    finally:
        db.close()


if __name__ == "__main__":
    main()
