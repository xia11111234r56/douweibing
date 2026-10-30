"""严重度量化：MobileSAM 零样本病斑分割 → 病斑面积占比 → 轻/中/重。

方法：
1. 用颜色阈值在 HSV 空间粗提取"病斑候选"（褐色/黄色等病色区域）→ 连通域作 SAM 框提示
2. MobileSAM 按框提示分割出精确病斑掩码
3. 病斑面积 / 叶片面积 = 病斑占比 → 按阈值映射严重度

此实现是起点，阈值与 SAM 提示策略在论文实验中标定。
用法（ml/ 目录下）：python severity_sam.py <图片路径>
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from PIL import Image

from config import CHECKPOINTS_DIR, SEVERITY_THRESHOLDS  # noqa: E402

# 病色区域 HSV 阈值（2026-08-17 田间照片校准）：
# 田间背景多为绿色（Hue 35-90），病斑为坏死褐/黄化，需与健康绿区分开。
DISEASE_HSV = {
    # 坏死褐色病斑（深褐，Hue 低）
    "brown": ((5, 60, 40), (25, 255, 255)),
    # 黄色晕圈/黄化（Hue 25-40，高饱和区别于黄绿叶片）
    "yellow": ((25, 100, 80), (40, 255, 255)),
}


def _load_predictor():
    from mobile_sam import SamPredictor, sam_model_registry

    weight = CHECKPOINTS_DIR / "mobile_sam.pt"
    if not weight.exists():
        raise FileNotFoundError(
            f"缺少 {weight}。下载 mobile_sam.pt 放入 ml/checkpoints/"
        )
    sam = sam_model_registry["vit_t"](checkpoint=str(weight))
    return SamPredictor(sam)


def severity_from_bytes(image_bytes: bytes, use_sam: bool = False) -> tuple[str | None, float | None, str]:
    """后端调用入口：返回 (severity, lesion_ratio, note)。

    use_sam=False 走快速颜色形态学（实时 API 默认，~10ms）；
    use_sam=True 走 MobileSAM 零样本分割精化（离线校准/论文实验）。
    """
    try:
        predictor = _load_predictor() if use_sam else None
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        ratio = compute_lesion_ratio(predictor, image, use_sam=use_sam)
        severity = ratio_to_severity(ratio)
        method = "mobile_sam" if use_sam else "color-morphology"
        return severity, ratio, method
    except FileNotFoundError as e:
        return None, None, str(e)
    except ImportError as e:
        return None, None, f"缺少 mobile_sam 包: {e}"


def ratio_to_severity(ratio: float) -> str:
    if ratio < SEVERITY_THRESHOLDS["轻"]:
        return "轻度"
    if ratio < SEVERITY_THRESHOLDS["中"]:
        return "中度"
    return "重度"


def _leaf_mask(hsv: np.ndarray) -> np.ndarray:
    """绿色叶片区域作为叶片掩码（近似）。"""
    import cv2

    lower = np.array([30, 40, 40])
    upper = np.array([90, 255, 255])
    return cv2.inRange(hsv, lower, upper)


def _lesion_mask(hsv: np.ndarray, leaf: np.ndarray) -> np.ndarray:
    """病斑掩码：非绿色 + 高饱和 + 落在绿色冠层（扩张绿区）内的异色像素。

    田间照片上病斑为叶片上的坏死褐/黄化区域——本身非绿，但位于绿色冠层内。
    """
    import cv2

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    canopy = cv2.dilate(leaf, kernel)
    non_green = 255 - leaf
    high_sat = cv2.inRange(hsv, np.array([0, 60, 40]), np.array([180, 255, 255]))
    lesion = cv2.bitwise_and(cv2.bitwise_and(non_green, high_sat), canopy)
    # 开运算去噪点
    return cv2.morphologyEx(lesion, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))


def _lesion_boxes(combo: np.ndarray, h: int, w: int) -> list[list[int]]:
    """由病色掩码 + 连通域得到 SAM 框提示 [x1,y1,x2,y2]。"""
    import cv2

    num, labels, stats, _ = cv2.connectedComponentsWithStats(combo, connectivity=8)
    boxes = []
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < w * h * 0.0008:  # 过滤噪点（比之前更宽松，病斑可能较小）
            continue
        boxes.append([x, y, x + bw, y + bh])
    return boxes


def compute_lesion_ratio(predictor, image: Image.Image, max_box: int = 20,
                         use_sam: bool = True) -> float:
    """病斑面积 / 叶片面积（田间照片）。

    归一化原则：
    - 叶片 = HSV 绿色冠层（田间背景多同为绿色，取绿色近似冠层）
    - 病斑 = 冠层内非绿色高饱和像素（坏死褐/黄化），排除背景与健康绿
    - use_sam=True 时用 MobileSAM 零样本精化病斑边界；False 为纯颜色形态学（快，
      实时后端默认走此路径，SAM 变体用于离线校准/论文实验）

    2026-08-17 在 5 类×6 张样本上实测：健康 0.01~0.06，病 0.02~0.29。
    轻/中/重阈值依据 config.SEVERITY_THRESHOLDS（刘学敏等大豆灰斑病分级标准
    合并方案B：轻=(0,6%]、中=(6%,25%]、重>25%）。
    """
    import cv2

    rgb = np.array(image)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, w = rgb.shape[:2]

    leaf = _leaf_mask(hsv)
    leaf_pixels = max(int((leaf > 0).sum()), 1)
    lesion_mask = _lesion_mask(hsv, leaf)

    if not use_sam:
        return min(int((lesion_mask > 0).sum()) / leaf_pixels, 1.0)

    # MobileSAM 精化病斑：连通域框提示，分割结果与叶片掩码求交
    boxes = _lesion_boxes(lesion_mask, h, w)[:max_box]
    if not boxes:
        return min(int((lesion_mask > 0).sum()) / leaf_pixels, 1.0)
    predictor.set_image(rgb)
    lesion_pixels = 0
    for box in boxes:
        m, _, _ = predictor.predict(box=np.array([box]), multimask_output=False)
        m = m[0] & (leaf > 0)
        lesion_pixels += int(m.sum())
    lesion_pixels = min(lesion_pixels, leaf_pixels)
    return min(lesion_pixels / leaf_pixels, 1.0)


if __name__ == "__main__":
    path = sys.argv[1]
    predictor = _load_predictor()
    img = Image.open(path).convert("RGB")
    ratio = compute_lesion_ratio(predictor, img)
    print(f"病斑占比: {ratio:.3f}  严重度: {ratio_to_severity(ratio)}")
