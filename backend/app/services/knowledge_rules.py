"""知识模态：环境-病害规则先验，对候选疾病置信度做后验修正。

规则来源于植保知识与知识图谱中的"病害—环境"关联：
- 高温高湿 / 阴雨连绵 → 促进真菌性、细菌性病害（叶斑病/锈病/炭疽病/细菌性疫病）
- 高温干燥 / 昼夜温差 → 白粉病高发
- 高温干旱、蚜虫多 → 病毒病传播重
"""
from __future__ import annotations

WEATHER_RULES: dict[str, list[tuple[str, float]]] = {
    # weather 档位 → [(疾病名关键词, 置信度修正量), ...]
    "高温高湿": [
        ("叶斑病", 0.04), ("锈病", 0.04), ("炭疽病", 0.04),
        ("细菌性疫病", 0.04), ("白粉病", -0.02),
    ],
    "阴雨连绵": [
        ("锈病", 0.04), ("叶斑病", 0.03), ("炭疽病", 0.02),
    ],
    "雨后天晴": [
        ("叶斑病", 0.03), ("炭疽病", 0.03),
    ],
    "晴热干旱": [
        ("白粉病", 0.04), ("病毒病", 0.03), ("虫食", 0.02),
    ],
    "虫害盛发": [
        ("虫食", 0.05), ("病毒病", 0.03),
    ],
}

# 温湿度区间规则（当 clim.tavg 可用时）
def _temperature_rule(tavg: float) -> list[tuple[str, float]]:
    rules: list[tuple[str, float]] = []
    if tavg >= 25:
        # 高温利于真菌/细菌病害
        rules.append(("叶斑病", 0.02))
        rules.append(("炭疽病", 0.02))
        rules.append(("细菌性疫病", 0.02))
    if tavg < 15:
        rules.append(("锈病", 0.02))
    return rules


def adjust_candidates(
    candidates: list[dict],
    env: dict | None,
) -> list[dict]:
    """按环境上下文对 candidates 做置信度修正（in-place 语义，返回新列表）。

    candidates: [{"disease_id":..,"name":..,"disease_type":..,"confidence":0.9}]
    """
    if not env:
        return candidates
    weather = env.get("weather")
    clim = env.get("clim") or {}

    rules: list[tuple[str, float]] = []
    if weather:
        rules += WEATHER_RULES.get(weather, [])
    if clim.get("tavg") is not None:
        rules += _temperature_rule(float(clim["tavg"]))

    for cand in candidates:
        delta = 0.0
        for keyword, adj in rules:
            if keyword in cand["name"]:
                delta += adj
        cand["confidence"] = min(1.0, max(0.0, cand["confidence"] + delta))

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    return candidates
