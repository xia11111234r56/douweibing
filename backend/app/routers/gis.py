"""GIS / 遥感模块：全球干豆产量分布、省级病害风险区划。

数据来自 OWID/FAOSTAT（干豆口径）与 WorldClim 2.1（见 data/spatial/ 与数据库 spatial_data 表）。
风险等级口径唯一真源：app/services/risk_model.py。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import SPATIAL_DIR
from ..db import get_db
from ..models import SpatialData
from ..services.risk_model import WINDOW_DESC, risk_level

router = APIRouter(tags=["gis"])


@router.get("/api/gis/mungbean")
def mungbean_data(
    level: str = Query("country", description="country / province"),
    year: int | None = Query(None, description="指定年份，缺省返回最近一年"),
    db: Session = Depends(get_db),
):
    """按国家/省返回干豆产量（tonnes）。格式适配 ECharts map（name, value）。

    附加 years（production 全部年份降序）供前端年份选择器；unit 为产量单位。
    """
    q = db.query(SpatialData).filter(SpatialData.region_level == level)
    if year is not None:
        q = q.filter(SpatialData.year == year)
    else:
        # 只按 production 指标取最新年份——避免被省级风险行（year=2023）污染年份
        latest = db.query(func.max(SpatialData.year)).filter(
            SpatialData.region_level == level,
            SpatialData.metric == "production",
        ).scalar()
        if latest is not None:
            q = q.filter(SpatialData.year == latest)
    rows = q.all()
    years = [
        y for (y,) in db.query(SpatialData.year)
        .filter(SpatialData.region_level == level, SpatialData.metric == "production")
        .distinct().order_by(SpatialData.year.desc()).all()
    ]
    result: dict = {"level": level, "year": None, "unit": "tonnes", "years": years, "series": {}}
    if rows:
        result["year"] = rows[0].year
        for r in rows:
            result["series"].setdefault(r.metric, []).append(
                {"name": r.region_name, "value": r.value}
            )
    return result


@router.get("/api/gis/geojson/{name}")
def geojson(name: str):
    """读取地图底图 GeoJSON。file: data/spatial/geojson/{name}.geojson"""
    path = SPATIAL_DIR / "geojson" / f"{name}.geojson"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"缺少底图 {name}.geojson")
    import json
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/gis/risk")
def risk_map(db: Session = Depends(get_db)):
    """病害风险区划：基于 WorldClim 2.1 JJA（6-8 月）温湿度 + 规则模型（ingest_spatial.py 预计算入库）。

    返回省级风险指数与 4 档等级（risk_model.py 唯一真源），适配 ECharts 中国地图 choropleth。
    年份取库内最大年份，不硬编码。
    """
    latest = (
        db.query(func.max(SpatialData.year))
        .filter(SpatialData.region_level == "province", SpatialData.metric == "risk_index")
        .scalar()
    )
    year = latest if latest is not None else 2023
    rows = (
        db.query(SpatialData)
        .filter(SpatialData.region_level == "province", SpatialData.year == year)
        .all()
    )
    series: dict[str, list] = {}
    for r in rows:
        series.setdefault(r.metric, []).append({"name": r.region_name, "value": r.value})
    # 风险等级：与入库同一模型（risk_level），不再用 value/25 hack
    risk_rows = [
        {"name": r.region_name, "value": r.value, "level": risk_level(r.value)}
        for r in rows if r.metric == "risk_index"
    ]
    return {
        "model": "climate-rule-v2",
        "year": year,
        "desc": f"{WINDOW_DESC}均温与累计降水 → 高温高湿适宜度 → 病害风险指数（WorldClim 2.1，规则模型，0-100）",
        "series": series,
        "risk": risk_rows,
    }
