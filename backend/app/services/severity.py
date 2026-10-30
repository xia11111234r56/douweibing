"""严重度量化：病斑面积占比 → 轻/中/重。

两条路径（复用 ml/severity_sam.py，阈值与 ml/config.py SEVERITY_THRESHOLDS 一致）：
- 快速路径（默认，实时 API）：颜色形态学（冠层内非绿色高饱和像素），无需 mobile_sam
- MobileSAM 路径：零样本分割精化病斑边界（离线校准/论文实验）
"""
from __future__ import annotations

import sys
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ml"

# 病斑面积占比 → 严重度阈值（与 ml/config.py SEVERITY_THRESHOLDS 保持一致，
# 依据刘学敏等大豆灰斑病分级标准合并为健康/轻/中/重粗粒度：轻=(0,6%]、中=(6%,25%]、重>25%）
_RATIO_THRESHOLDS = {
    "轻": 0.06,
    "中": 0.25,
}


def severity_from_ratio(ratio: float) -> str:
    if ratio < _RATIO_THRESHOLDS["轻"]:
        return "轻度"
    if ratio < _RATIO_THRESHOLDS["中"]:
        return "中度"
    return "重度"


def compute_severity(image_bytes: bytes, use_sam: bool = False):
    """返回 (severity, lesion_ratio, note)。

    主路径：深度严重度模型（mobilenetv3 骨干 + 逻辑回归，5 折交叉验证一致率
    0.844，见 ml/experiments/severity_cv.json）。面积比类方法（颜色形态学 0.32、
    MobileSAM 面积比）在用户主观图级标注上无法对齐，仅作模型缺失时的回退。
    """
    try:
        from .severity_model import predict_severity

        sev = predict_severity(image_bytes)
        if sev is not None:
            return sev, None, "深度模型（mobilenetv3骨干+LR，5折CV 0.844）"
    except Exception:  # noqa: BLE001
        pass
    # 回退：颜色形态学面积比（文献分级方案B，深度模型不可用时兜底）
    if str(ML_DIR) not in sys.path:
        sys.path.insert(0, str(ML_DIR))
    try:
        from severity_sam import severity_from_bytes

        severity, ratio, note = severity_from_bytes(image_bytes, use_sam=use_sam)
        if severity is not None:
            return severity, ratio, note + "（回退面积比，深度模型不可用）"
        return None, None, note
    except ImportError as e:
        return None, None, f"严重度依赖缺失: {e}"
    except Exception as e:  # noqa: BLE001
        return None, None, f"严重度计算失败: {e}"
