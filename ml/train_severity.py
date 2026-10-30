"""严重度分类器：深度特征 + 逻辑回归（替代面积比方案，5 折 CV 0.83）。

背景：面积比类方法（颜色形态学 0.32、MobileSAM 面积比反向）无法对齐用户主观
图级标注（背景/光照/多叶差异巨大）。深度特征（生产分类模型骨干 mobilenetv3_large，
已在绿豆 10 类微调，eval 模式）→ 逻辑回归可稳定分开三组（5 折 CV 0.83）。
PyTorch 全模型微调/冻结微调均退化（BN train 模式用 batch 统计扭曲特征），故采用
「冻结骨干提取特征 + sklearn LogisticRegression」，与已验证探测完全一致。

数据：D:\\dc2\\train\\{0,2,4}（0=轻 2=中 4=重，用户人工标注 179 张）
评估：分层 5 折（StratifiedKFold），报告平均准确率、每类召回（真实指标）
产物：
  checkpoints/best_severity.pth  SevModel(features + 线性头) state_dict，供 ONNX 导出
  experiments/severity_cv.json    5 折 CV 指标

用法（ml/ 目录下）：python train_severity.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torch.nn as nn  # noqa: E402
import torch.nn.functional as F  # noqa: E402
from PIL import Image  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.model_selection import StratifiedKFold  # noqa: E402
from torchvision import transforms  # noqa: E402

from config import CHECKPOINTS_DIR, EXPERIMENTS_DIR, RANDOM_SEED  # noqa: E402
from train_classifier import build_model  # noqa: E402

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
ROOT = Path(__file__).resolve().parent.parent / "train"
LABELS = [("0", "轻"), ("2", "中"), ("4", "重")]
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SIZE = 448
FEAT_DIM = 960  # mobilenetv3_large features 输出通道

tf = transforms.Compose([
    transforms.Resize((SIZE, SIZE)),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


class SevModel(nn.Module):
    """features（冻结骨干）+ 线性头（逻辑回归权重），供 ONNX 导出与后端推理。"""

    def __init__(self, features: nn.Module, weight: np.ndarray, bias: np.ndarray):
        super().__init__()
        self.features = features
        self.fc = nn.Linear(weight.shape[1], weight.shape[0])
        self.fc.weight.data = torch.tensor(weight, dtype=torch.float32)
        self.fc.bias.data = torch.tensor(bias, dtype=torch.float32)

    def forward(self, x):
        f = F.adaptive_avg_pool2d(self.features(x), 1).flatten(1)
        return self.fc(f)


def extract_features(model, pil_img) -> np.ndarray:
    x = tf(pil_img).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        f = model.features(x)
        f = F.adaptive_avg_pool2d(f, 1).flatten(1)
    return f.cpu().numpy()[0]


def main() -> None:
    if not ROOT.exists():
        print(f"[错误] 未找到标注数据: {ROOT}")
        sys.exit(1)

    # 收集并缓存解码后的 448 图
    paths, idxs, cache = [], [], []
    for fi, (folder, _) in enumerate(LABELS):
        d = ROOT / folder
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in IMG_EXT:
                paths.append(p)
                idxs.append(fi)
                cache.append(transforms.Resize((SIZE, SIZE))(Image.open(p).convert("RGB")))
    y = np.array(idxs)
    print(f"样本 {len(paths)}：{ {lab: int((y == i).sum()) for i, (_, lab) in enumerate(LABELS)} }  设备 {DEVICE}")

    # 冻结骨干（eval 模式，BN 用稳定 running stats），提取 179 张特征
    model = build_model(pretrained=True).to(DEVICE).eval()
    init = CHECKPOINTS_DIR / "best_finetune_aug.pth"
    state = torch.load(init, map_location=DEVICE)
    ms = model.state_dict()
    filtered = {k: v for k, v in state.items() if k in ms and v.shape == ms[k].shape}
    model.load_state_dict(filtered, strict=False)
    print(f"[特征提取] 骨干加载 {len(filtered)}/{len(state)} 层（eval 模式，448 输入）")
    X = np.stack([extract_features(model, img) for img in cache])
    print(f"特征矩阵 X={X.shape}")

    # 5 折交叉验证（真实指标，与探测 _feat_cv 一致）
    skf = StratifiedKFold(5, shuffle=True, random_state=RANDOM_SEED)
    fold_accs, fold_rec = [], {lab: [] for _, lab in LABELS}
    for tr, te in skf.split(X, y):
        clf = LogisticRegression(max_iter=2000)
        clf.fit(X[tr], y[tr])
        pr = clf.predict(X[te])
        fold_accs.append(float((pr == y[te]).mean()))
        for i, (_, lab) in enumerate(LABELS):
            m = y[te] == i
            fold_rec[lab].append(float((pr[m] == i).mean()) if m.any() else float("nan"))
    print(f"5折CV准确率: {np.mean(fold_accs):.4f} ± {np.std(fold_accs):.4f}")
    for lab, v in fold_rec.items():
        print(f"  {lab} 召回: {np.nanmean(v):.4f}")

    # 全量拟合最终 LR → SevModel 权重（部署用）
    clf = LogisticRegression(max_iter=2000)
    clf.fit(X, y)
    sev = SevModel(model.features.to("cpu"), clf.coef_, clf.intercept_)
    sev.eval()
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    torch.save(sev.state_dict(), CHECKPOINTS_DIR / "best_severity.pth")

    result = {
        "n": len(paths),
        "k": 5,
        "mean_acc": round(float(np.mean(fold_accs)), 4),
        "std_acc": round(float(np.std(fold_accs)), 4),
        "fold_accs": [round(a, 4) for a in fold_accs],
        "recall": {k: round(float(np.nanmean(v)), 4) for k, v in fold_rec.items()},
        "label_map": {k: v for k, v in LABELS},
        "model": "mobilenetv3_large 骨干(eval) + sklearn LogisticRegression",
        "input_size": SIZE,
        "feature_dim": FEAT_DIM,
    }
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    (EXPERIMENTS_DIR / "severity_cv.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {EXPERIMENTS_DIR / 'severity_cv.json'}")
    print(f"模型: checkpoints/best_severity.pth（SevModel，下一步 ONNX 导出）")


if __name__ == "__main__":
    main()
