"""导出分类模型为 ONNX（后端 CPU 推理）。

用法：python export_onnx.py [--ckpt best_finetune_feedback.pth]
默认导出生产模型 best_finetune.pth。
产物：
    backend/models/classifier.onnx   （输入 [1,3,224,224] float32，输出 [1,10]）
    backend/models/labels.json       （类别顺序，后端按此映射）
    backend/models/mobilesam_encoder.onnx + mobilesam_decoder.onnx  （M1 严重度，可选）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import torch
from torchvision import datasets

from config import (  # noqa: E402
    BACKEND_MODELS_DIR,
    CHECKPOINTS_DIR,
    IMG_SIZE,
    ORGANIZED_DIR,
)
from train_classifier import build_model  # noqa: E402


def class_order(source: Path | None = None) -> list[str]:
    """模型输出索引 → 类别名的映射顺序。

    ImageFolder 按类目录字母序生成索引，必须与训练时一致，不能直接用
    config.CLASS_NAMES（顺序不同会导致 labels.json 与模型输出错位）。

    source 缺省用 ORGANIZED_DIR/train（生产模型）；纠错再训练模型与它同序，
    因此 labels 恒以 ORGANIZED_DIR/train 为准（见 finetune_corrections.py 类集合守卫）。
    """
    root = source or (ORGANIZED_DIR / "train")
    ds = datasets.ImageFolder(str(root), allow_empty=True)
    return ds.classes


def export_classifier(
    ckpt: str = "best_finetune.pth", labels_source: Path | None = None
) -> None:
    model = build_model(pretrained=False)
    ckpt_path = CHECKPOINTS_DIR / ckpt
    if not ckpt_path.exists():
        print(f"[错误] 缺少 {ckpt_path}。请先训练。")
        sys.exit(1)
    model.load_state_dict(torch.load(ckpt_path, map_location="cpu"))
    model.eval()

    BACKEND_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
    torch.onnx.export(
        model, dummy,
        str(BACKEND_MODELS_DIR / "classifier.onnx"),
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}},
        opset_version=13,
    )
    (BACKEND_MODELS_DIR / "labels.json").write_text(
        json.dumps(
            {str(i): c for i, c in enumerate(class_order(labels_source))},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    size_mb = (BACKEND_MODELS_DIR / "classifier.onnx").stat().st_size / 1e6
    print(f"✅ classifier.onnx 导出完成（{size_mb:.1f}MB）")


def export_mobilesam() -> None:
    """可选：MobileSAM 编码器/解码器导出 ONNX（后端免 torch 依赖）。"""
    try:
        import onnx
        from mobile_sam import SamPredictor, sam_model_registry
    except ImportError as e:
        print(f"[跳过] MobileSAM 导出需要 mobile_sam: {e}")
        return
    weight = CHECKPOINTS_DIR / "mobile_sam.pt"
    if not weight.exists():
        print("[跳过] 缺少 mobile_sam.pt（下载见 MobileSAM 官方仓库 ChaoningZhang/MobileSAM）")
        return
    sam = sam_model_registry["vit_t"](checkpoint=str(weight))
    sam.eval()
    # 注：SAM 解码器含动态循环，完整 ONNX 导出较繁琐，建议后端直接跑 mobile_sam 包
    print("[提示] MobileSAM 严重度推理建议在后端直接使用 mobile_sam 包（约40MB，CPU可跑），"
          "ONNX 导出可选实现。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--ckpt", default="best_finetune.pth",
        help="要导出的权重文件名（checkpoints/ 下，默认生产模型 best_finetune.pth）",
    )
    args = parser.parse_args()
    export_classifier(ckpt=args.ckpt)
    export_mobilesam()
