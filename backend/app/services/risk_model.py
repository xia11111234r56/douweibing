"""病害风险规则模型（唯一真源）：ingest_spatial.py 与 routers/gis.py 共用。

风险 = 高温高湿适宜度指数（0-100，规则式模型，非实证预测）。
时间窗：6-8 月（绿豆开花结荚关键期）。
- 指数 = 100 × (0.5 × 温度适宜度 + 0.5 × 湿度适宜度)
- 等级：<40 低 / 40-60 中 / 60-75 较高 / ≥75 高
"""

WINDOW_DESC = "6-8月（绿豆开花结荚关键期）"
RISK_LEVELS = ("低", "中", "较高", "高")


def temp_score(t: float) -> float:
    """温度适宜度：JJA 均温（℃）。过低不利；过高（>34℃）超出病害适温区反而不利。"""
    if t < 18:
        return 0.10
    if t < 21:
        return 0.30
    if t < 24:
        return 0.50
    if t < 27:
        return 0.75
    if t < 31:
        return 0.95
    if t <= 34:
        return 1.00
    return 0.55


def hum_score(p: float) -> float:
    """湿度适宜度：JJA 累计降水（mm）。降水越多越湿润，对叶部真菌/细菌病害越有利。"""
    if p < 150:
        return 0.10
    if p < 300:
        return 0.35
    if p < 450:
        return 0.60
    if p < 600:
        return 0.80
    return 0.95


def risk_index(tavg: float, prec: float) -> float:
    """综合风险指数 0-100（保留 1 位小数）。"""
    return round(100 * (0.5 * temp_score(tavg) + 0.5 * hum_score(prec)), 1)


def risk_level(idx: float) -> str:
    """风险指数 → 等级（4 档）。"""
    if idx < 40:
        return "低"
    if idx < 60:
        return "中"
    if idx < 75:
        return "较高"
    return "高"
