"""风险模型纯函数单测：边界值、单调性、4 档等级判定。"""

from app.services.risk_model import hum_score, risk_index, risk_level, temp_score


def test_temp_score_boundaries():
    assert temp_score(17) == 0.10
    assert temp_score(20) == 0.30
    assert temp_score(23) == 0.50
    assert temp_score(26) == 0.75
    assert temp_score(30) == 0.95
    assert temp_score(34) == 1.00
    assert temp_score(35) == 0.55


def test_temp_score_monotonic_then_drop():
    # 适温区单调不减
    assert temp_score(5) <= temp_score(18) <= temp_score(25) <= temp_score(30) <= temp_score(34)
    # 过高温回落（超出病害适温区）
    assert temp_score(36) < temp_score(30)


def test_hum_score_boundaries():
    # 区间语义：[0,150)=0.10 [150,300)=0.35 [300,450)=0.60 [450,600)=0.80 [600,∞)=0.95
    assert hum_score(149) == 0.10
    assert hum_score(150) == 0.35
    assert hum_score(299) == 0.35
    assert hum_score(300) == 0.60
    assert hum_score(449) == 0.60
    assert hum_score(450) == 0.80
    assert hum_score(599) == 0.80
    assert hum_score(600) == 0.95
    assert hum_score(700) == 0.95


def test_risk_index_high_and_low():
    # 高温高湿（6-8月）→ 高风险
    assert risk_index(28, 650) >= 75
    # 冷凉少雨 → 低风险
    assert risk_index(15, 100) < 40
    # 中等
    assert risk_index(23, 350) < 75


def test_risk_level_four_tiers():
    assert risk_level(30) == "低"
    assert risk_level(50) == "中"
    assert risk_level(65) == "较高"
    assert risk_level(80) == "高"
    # 边界
    assert risk_level(40) == "中"
    assert risk_level(60) == "较高"
    assert risk_level(75) == "高"
