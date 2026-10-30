"""空间数据入库（可幂等重跑）：OWID 全球干豆产量 + WorldClim 2.1 省级 JJA 气候与病害风险
+ 中国省级绿豆主产区产量（中国农村统计年鉴 2022）。

风险模型来自 app/services/risk_model.py（唯一真源，供本脚本与 routers/gis.py 共用）：
- 高温高湿适宜度指数 0-100 = 100 × (0.5 × JJA均温适宜度 + 0.5 × JJA累计降水适宜度)
- JJA = 6-8 月（绿豆开花结荚关键期）；等级 <40 低 / <60 中 / <75 较高 / ≥75 高

省级绿豆产量（绿豆专属口径，非干豆）：
- 数据源《中国农村统计年鉴》7-18 各地区分品种粮食作物产量（绿豆），2022 年为年鉴口径可查的
  最新完整分省数据；仅收录有独立绿豆统计的全国产量前十主产省，其余省份如实不列。
- 单位换算：万吨 → 吨（×10000）。

幂等：单事务 delete-then-insert（国家 production 2019-2024 + 省级 year=2023 风险 3 指标
+ 省级 year=2022 绿豆产量，并顺带清理旧 7 月口径 jul 指标）。重跑安全，数据或模型升级后直接重跑即可。

产物写入 spatial_data 表，供 /api/gis/* 查询。
用法（本机/服务器一致，无 pandas 依赖）：cd backend && .venv/bin/python -m scripts.ingest_spatial
"""
import csv
import json
import re

from app.config import SPATIAL_DIR
from app.db import SessionLocal, init_db
from app.models import SpatialData
from app.services.risk_model import risk_index

YEARS = list(range(2019, 2025))  # OWID 最近 6 年
ISO_RE = re.compile(r"^[A-Z]{3}$")  # ISO 3166-1 alpha-3：仅真国家，排除 OWID_ 聚合行
PROV_METRICS = ("climate_tavg_jja", "climate_prec_jja", "risk_index")  # String(16) 兼容
OLD_JUL_METRICS = ("climate_tavg_jul", "climate_prec_jul")  # 已废弃口径，入库时清理

# 中国绿豆主产区产量（2022，中国农村统计年鉴口径，单位：吨）。
# adcode → 产量吨（6.95 万吨 = 69500 t 等）。仅年鉴有独立绿豆统计的前十主产省。
PROVINCE_MUNGBEAN_2022_T = {
    150000: 69500,  # 内蒙古自治区
    220000: 65400,  # 吉林省
    340000: 46200,  # 安徽省
    510000: 26400,  # 四川省
    410000: 25700,  # 河南省
    430000: 23200,  # 湖南省
    500000: 23100,  # 重庆市
    450000: 21100,  # 广西壮族自治区
    140000: 13400,  # 山西省
    130000: 12900,  # 河北省
}


def _purge(db) -> None:
    """删除将被重灌的旧数据（国家产量 + 省级风险/产量 + 废弃 jul 指标）。"""
    n_old_jul = db.query(SpatialData).filter(
        SpatialData.region_level == "province",
        SpatialData.year == 2023,
        SpatialData.metric.in_(OLD_JUL_METRICS),
    ).delete(synchronize_session=False)
    db.query(SpatialData).filter(
        SpatialData.region_level == "country",
        SpatialData.metric == "production",
        SpatialData.year.in_(YEARS),
    ).delete(synchronize_session=False)
    n_prov = db.query(SpatialData).filter(
        SpatialData.region_level == "province",
        SpatialData.year == 2023,
        SpatialData.metric.in_(PROV_METRICS),
    ).delete(synchronize_session=False)
    n_prov_prod = db.query(SpatialData).filter(
        SpatialData.region_level == "province",
        SpatialData.year == 2022,
        SpatialData.metric == "production",
    ).delete(synchronize_session=False)
    print(f"[清理] 旧 jul {n_old_jul}、省级风险 {n_prov}、省级产量 {n_prov_prod}、国家产量已清空")


def _ingest_owid_production(db) -> int:
    """OWID/FAOSTAT 干豆产量（Dry beans 口径，含绿豆等大宗豆类，如实标注）。"""
    csv_path = SPATIAL_DIR / "owid_bean_production.csv"
    if not csv_path.exists():
        print("[跳过] 缺少 owid_bean_production.csv")
        return 0
    metric_col = "Dry beans - Production (tonnes)"
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            code = (r.get("Code") or "").strip()
            name = (r.get("Entity") or "").strip()
            if name == "World" or not ISO_RE.fullmatch(code):
                continue
            try:
                year = int(r.get("Year"))
                value = float(r.get(metric_col))
            except (TypeError, ValueError):
                continue
            if year not in YEARS:
                continue
            rows.append(SpatialData(
                region_code=code, region_name=name, region_level="country",
                year=year, metric="production", value=value,
                unit="tonnes", source="OWID/FAOSTAT",
            ))
    db.add_all(rows)
    n_country = len({r.region_name for r in rows})
    print(f"OWID 干豆产量入库 {len(rows)} 条（{len(YEARS)} 年 × {n_country} 国）")
    return len(rows)


def _load_jja_climate() -> dict[tuple, tuple]:
    """返回 {(lat,lon): (tavg_jja, prec_jja)}。JJA = 6-8 月均温均值 + 累计降水。"""
    csv_path = SPATIAL_DIR / "worldclim_china.csv"
    if not csv_path.exists():
        return {}
    agg: dict[tuple, list] = {}
    with open(csv_path, encoding="utf-8-sig") as f:  # 表头带 BOM，必须用 utf-8-sig
        for r in csv.DictReader(f):
            try:
                month = int(r["month"])
                lat = float(r["lat"])
                lon = float(r["lon"])
                t = float(r["tavg"])
                p = float(r["prec"])
            except (KeyError, ValueError):
                continue
            if month not in (6, 7, 8):
                continue
            key = (lat, lon)
            a = agg.get(key)
            if a is None:
                agg[key] = [t, p, 1]
            else:
                a[0] += t
                a[1] += p
                a[2] += 1
    return {key: (t / n, p) for key, (t, p, n) in agg.items()}


def _nearest_climate(grid, lon, lat):
    best, best_d = None, 1e9
    for (glat, glon), val in grid.items():
        d = (glat - lat) ** 2 + (glon - lon) ** 2
        if d < best_d:
            best_d, best = d, val
    return best


def _ingest_province_risk(db) -> int:
    """34 省（china.geojson 省会/中心点）JJA 均温、累计降水与风险指数，year=2023。"""
    geojson = SPATIAL_DIR / "geojson" / "china.geojson"
    if not geojson.exists():
        print("[跳过] 缺少 china.geojson")
        return 0
    grid = _load_jja_climate()
    if not grid:
        print("[跳过] 缺少 worldclim_china.csv")
        return 0
    gj = json.loads(geojson.read_text(encoding="utf-8"))
    rows = []
    for feat in gj["features"]:
        prop = feat["properties"]
        if prop.get("level") != "province":
            continue
        lon, lat = prop.get("center") or prop.get("centroid")
        if not lon:
            continue
        climate = _nearest_climate(grid, lon, lat)
        if not climate:
            continue
        tavg_jja, prec_jja = climate
        for metric, value in (
            ("climate_tavg_jja", round(tavg_jja, 1)),
            ("climate_prec_jja", round(prec_jja, 0)),
            ("risk_index", risk_index(tavg_jja, prec_jja)),
        ):
            rows.append(SpatialData(
                region_code=str(prop["adcode"]),
                region_name=prop["name"],
                region_level="province",
                year=2023,
                metric=metric,
                value=value,
                unit=None,
                source="WorldClim2.1",
            ))
    db.add_all(rows)
    print(f"省级 JJA 气候+风险指数入库 {len(rows) // 3} 省 × 3 指标")
    return len(rows)


def _ingest_province_production(db) -> int:
    """中国绿豆主产区产量（2022，年鉴口径）。region_name 取 china.geojson 要素名保证地图匹配。"""
    geojson = SPATIAL_DIR / "geojson" / "china.geojson"
    if not geojson.exists():
        print("[跳过] 缺少 china.geojson")
        return 0
    gj = json.loads(geojson.read_text(encoding="utf-8"))
    rows = []
    for feat in gj["features"]:
        prop = feat["properties"]
        adcode = prop.get("adcode")
        tonnes = PROVINCE_MUNGBEAN_2022_T.get(adcode)
        if tonnes is None:
            continue
        rows.append(SpatialData(
            region_code=str(adcode),
            region_name=prop["name"],
            region_level="province",
            year=2022,
            metric="production",
            value=float(tonnes),
            unit="tonnes",
            source="中国农村统计年鉴(2022)",
        ))
    db.add_all(rows)
    print(f"省级绿豆主产区产量入库 {len(rows)} 省（2022，年鉴口径）")
    return len(rows)


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        _purge(db)
        n1 = _ingest_owid_production(db)
        n2 = _ingest_province_risk(db)
        n3 = _ingest_province_production(db)
        db.commit()
        total = db.query(SpatialData).count()
        print(f"入库完成：OWID {n1} + 省级风险 {n2} + 省级产量 {n3} 条，spatial_data 共 {total} 条")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
