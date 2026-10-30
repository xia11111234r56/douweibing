"""严重度模型导出 ONNX：best_severity.pth → best_severity.onnx，并校验一致性。

产物：checkpoints/best_severity.onnx（输入 image[1,3,448,448] 归一化 NCHW，输出 logits[1,3]）
校验：同一输入下 ONNX Runtime 与 PyTorch 输出 logits 的最大误差。

用法（ml/ 目录下）：python export_severity_onnx.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from config import CHECKPOINTS_DIR  # noqa: E402
from train_classifier import build_model  # noqa: E402
from train_severity import SevModel  # noqa: E402


def main() -> None:
    ckpt = CHECKPOINTS_DIR / "best_severity.pth"
    onnx_path = CHECKPOINTS_DIR / "best_severity.onnx"
    if not ckpt.exists():
        print(f"[错误] 缺少 {ckpt}，先运行 train_severity.py")
        sys.exit(1)

    features = build_model(pretrained=True).features
    sev = SevModel(features, np.zeros((3, 960)), np.zeros(3))
    sev.load_state_dict(torch.load(ckpt, map_location="cpu"))
    sev.eval()

    x = torch.randn(1, 3, 448, 448)
    with torch.no_grad():
        ref = sev(x).numpy()

    torch.onnx.export(
        sev, x, str(onnx_path),
        input_names=["image"], output_names=["logits"],
        opset_version=17,
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
    )
    print(f"[导出] {onnx_path} ({onnx_path.stat().st_size / 1024 / 1024:.2f} MB)")

    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    out = sess.run(None, {"image": x.numpy()})[0]
    err = float(np.max(np.abs(out - ref)))
    print(f"[校验] ONNX vs PyTorch logits 最大误差: {err:.2e}")
    assert err < 1e-4, "ONNX 输出与 PyTorch 不一致"
    print("[OK] 一致性校验通过")


if __name__ == "__main__":
    main()
