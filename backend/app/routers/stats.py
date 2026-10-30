"""统计接口：识别记录聚合（概览 Dashboard / 数据统计页 / 多模态环境交叉）。"""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Disease, Recognition, SpatialData, Treatment

router = APIRouter(tags=["stats"])

# env_metadata 合法取值（天气档位与 services/knowledge_rules.py ENV_RULES、前端 Recognize.vue 一致）
GROWTH_STAGES = ["苗期", "分枝期", "开花期", "结荚期", "成熟期"]
WEATHER_MODES = ["高温高湿", "阴雨连绵", "雨后天晴", "晴热干旱", "虫害盛发"]
PLANTING_MODES = ["露地", "大棚"]


@router.get("/api/stats/overview")
def stats_overview(db: Session = Depends(get_db)):
    """识别记录：总数、按病种/严重度分布、近 30 天趋势 + 知识库真实计数。"""
    total = db.query(Recognition).count()
    disease_count = db.query(Disease).count()
    treatment_count = db.query(Treatment).count()
    province_count = (
        db.query(func.count(func.distinct(SpatialData.region_name)))
        .filter(SpatialData.region_level == "province")
        .scalar()
        or 0
    )

    by_disease = (
        db.query(Disease.name, func.count(Recognition.id))
        .join(Recognition, Recognition.disease_id == Disease.id)
        .group_by(Disease.name)
        .all()
    )
    by_severity = (
        db.query(Recognition.severity, func.count(Recognition.id))
        .group_by(Recognition.severity)
        .all()
    )
    # 按天（MySQL DATE 截断；SQLite 用 date()）
    by_day = (
        db.query(func.date(Recognition.created_at), func.count(Recognition.id))
        .group_by(func.date(Recognition.created_at))
        .order_by(func.date(Recognition.created_at))
        .all()
    )

    return {
        "total": total,
        "disease_count": disease_count,
        "treatment_count": treatment_count,
        "province_count": province_count,
        "disease_dist": [{"name": n, "count": c} for n, c in by_disease],
        "severity_dist": [{"severity": s or "未判定", "count": c} for s, c in by_severity],
        "daily_trend": [{"date": str(d), "count": c} for d, c in by_day],
    }


def _count_dist(values: list, allowed: list[str]) -> list[dict]:
    """按合法取值顺序统计，未命中归入"其他"。"""
    counter = {v: 0 for v in allowed}
    other = 0
    for v in values:
        if v in counter:
            counter[v] += 1
        elif v:
            other += 1
    dist = [{"name": k, "count": c} for k, c in counter.items() if c]
    if other:
        dist.append({"name": "其他", "count": other})
    return dist


@router.get("/api/stats/env")
def stats_env(db: Session = Depends(get_db)):
    """多模态环境上下文聚合（消费 recognitions.env_metadata）。

    数据量（百级~千级）下用 Python 聚合，避开 MySQL/SQLite 的 JSON 函数差异。
    """
    rows = (
        db.query(Recognition.env_metadata)
        .filter(Recognition.env_metadata.isnot(None))
        .all()
    )
    meta_list = [r[0] for r in rows if isinstance(r[0], dict)]
    n = len(meta_list)

    def pick(key):
        return [m.get(key) for m in meta_list if m.get(key)]

    source_counter: dict[str, int] = {}
    for m in meta_list:
        for s in (m.get("source") or []):
            source_counter[s] = source_counter.get(s, 0) + 1

    gps = sum(1 for m in meta_list if m.get("gps_lat") is not None and m.get("gps_lon") is not None)
    clim = sum(1 for m in meta_list if m.get("clim"))

    return {
        "total": n,
        "growth_stage_dist": _count_dist(pick("growth_stage"), GROWTH_STAGES),
        "weather_dist": _count_dist(pick("weather"), WEATHER_MODES),
        "planting_dist": _count_dist(pick("planting"), PLANTING_MODES),
        "source_dist": [{"name": k, "count": v} for k, v in source_counter.items()],
        "gps_rate": round(gps / n, 4) if n else 0,
        "clim_rate": round(clim / n, 4) if n else 0,
    }


@router.get("/api/stats/cross")
def stats_cross(db: Session = Depends(get_db)):
    """交叉统计：严重度 × 天气档位、病害 × 生育期。"""
    rows = (
        db.query(Recognition.severity, Recognition.disease_id, Recognition.env_metadata)
        .filter(Recognition.env_metadata.isnot(None))
        .all()
    )

    name_map = dict(db.query(Disease.id, Disease.name).all())

    # 严重度 × 天气
    weather_levels = ["高温高湿", "阴雨连绵", "雨后天晴", "晴热干旱", "虫害盛发", "未知"]
    severity_levels = ["轻度", "中度", "重度", "未知"]
    cross_matrix: dict[str, dict[str, int]] = {
        w: {s: 0 for s in severity_levels} for w in weather_levels
    }
    for severity, _disease_id, env in rows:
        if not isinstance(env, dict):
            continue
        w = env.get("weather") or "未知"
        w = w if w in cross_matrix else "未知"
        s = severity or "未知"
        s = s if s in cross_matrix[w] else "未知"
        cross_matrix[w][s] += 1
    severity_x_weather = [
        {"weather": w, **{s: cross_matrix[w][s] for s in severity_levels}}
        for w in weather_levels
        if any(cross_matrix[w].values())
    ]

    # 病害 × 生育期
    stage_levels = ["苗期", "分枝期", "开花期", "结荚期", "成熟期", "未知"]
    disease_counter: dict[str, dict[str, int]] = {}
    for severity, disease_id, env in rows:
        if not isinstance(env, dict):
            continue
        name = name_map.get(disease_id) or "未知"
        st = env.get("growth_stage") or "未知"
        st = st if st in stage_levels else "未知"
        disease_counter.setdefault(name, {s: 0 for s in stage_levels})[st] += 1
    disease_x_stage = [
        {"disease": d, **{s: c[s] for s in stage_levels}}
        for d, c in disease_counter.items()
    ]

    return {
        "severity_x_weather": severity_x_weather,
        "disease_x_stage": disease_x_stage,
    }
