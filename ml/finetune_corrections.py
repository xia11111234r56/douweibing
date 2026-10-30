"""纠错数据再训练流水线：CSV → 拷贝原图 → 合并训练集 → 从生产模型续训 → 前后评估 → 导出 ONNX。

闭环：后端 /api/feedback/export 导出 CSV → 本脚本续训 → 重启后端生效。

用法（ml/ 目录下）：
    python finetune_corrections.py --csv ../feedback_export.csv --epochs 8
    python finetune_corrections.py --csv ../feedback_export.csv --epochs 8 --force  # 清空已用标记重跑

安全设计：
- 目标类只允许在 config.CLASS_NAMES 10 类内（CSV 行越界跳过计数）。
- 合并训练集类集合必须与 organized/train 完全一致（sorted 相等断言），
  保证与 export_onnx.class_order() 读 organized/train 的类序一致 → labels 不漂移。
- 导出 ONNX 前后比对 labels.json，不一致则还原旧模型中止（双保险）。
- feedback_used.json 记录已使用的 recognition_id，幂等重跑；缺失原图的行不标记，
  待图补齐后下次重试。
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (  # noqa: E402
    BACKEND_MODELS_DIR,
    CHECKPOINTS_DIR,
    CLASS_NAMES,
    EXPERIMENTS_DIR,
    LR_FINETUNE,
    ORGANIZED_DIR,
    RECOGNITION_DIR,
)
from train_classifier import run_stage  # noqa: E402

ML_ROOT = Path(__file__).resolve().parent
CORRECTIONS_DIR = ML_ROOT / "data" / "corrections"   # 纠错图归档（累积）
FEEDBACK_TRAIN_DIR = EXPERIMENTS_DIR / "feedback_train"
USED_FILE = EXPERIMENTS_DIR / "feedback_used.json"
REPORT_FILE = EXPERIMENTS_DIR / "feedback_report.json"


def load_export(csv_path: Path) -> list[dict]:
    """读导出 CSV（含 BOM），推导目标类。

    is_correct=1 → 目标类=predicted_class；is_correct=0 → 目标类=corrected_class。
    """
    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:  # utf-8-sig 兼容 BOM
        for r in csv.DictReader(f):
            is_correct = r.get("is_correct", "").strip() == "1"
            target = (
                r["predicted_class"].strip()
                if is_correct else r["corrected_class"].strip()
            )
            rows.append(
                {
                    "recognition_id": r["recognition_id"].strip(),
                    "image_path": r["image_path"].strip(),
                    "target_class": target,
                    "is_correct": is_correct,
                }
            )
    return rows


def load_used() -> set[str]:
    if USED_FILE.exists():
        return set(json.loads(USED_FILE.read_text(encoding="utf-8")))
    return set()


def save_used(used: set[str]) -> None:
    USED_FILE.write_text(
        json.dumps(sorted(used), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def dedup_latest(rows: list[dict]) -> list[dict]:
    """按 recognition_id 去重，保留最后一条（CSV 按 id 升序，最后=最新）。"""
    seen = {}
    for r in rows:
        seen[r["recognition_id"]] = r
    return list(seen.values())


def collect_corrections(rows: list[dict], used: set[str]) -> tuple[list[dict], dict]:
    """拷贝纠错原图到 corrections/{类}/{recognition_id}_{文件名}，返回成功列表与统计。"""
    copied, stats = [], {"no_target": 0, "missing_image": 0, "per_class": {}}
    for r in rows:
        cls = r["target_class"]
        if cls not in CLASS_NAMES:
            stats["no_target"] += 1
            continue
        src = RECOGNITION_DIR / r["image_path"]
        if not r["image_path"] or not src.is_file():
            stats["missing_image"] += 1
            continue
        dst_dir = CORRECTIONS_DIR / cls
        dst_dir.mkdir(parents=True, exist_ok=True)
        name = f"{r['recognition_id']}_{r['image_path']}"
        shutil.copy2(src, dst_dir / name)
        r["copied_name"] = name
        copied.append(r)
        stats["per_class"][cls] = stats["per_class"].get(cls, 0) + 1
    return copied, stats


def build_feedback_train(copied: list[dict]) -> Path:
    """重建 feedback_train：train = organized/train 全量 + corrections 合并；val = organized/val 全量。"""
    if FEEDBACK_TRAIN_DIR.exists():
        shutil.rmtree(FEEDBACK_TRAIN_DIR)
    FEEDBACK_TRAIN_DIR.mkdir(parents=True)
    shutil.copytree(ORGANIZED_DIR / "train", FEEDBACK_TRAIN_DIR / "train")
    shutil.copytree(ORGANIZED_DIR / "val", FEEDBACK_TRAIN_DIR / "val")

    # 合并纠错图（只往既有类目录里加文件，绝不新建类目录）
    train_root = FEEDBACK_TRAIN_DIR / "train"
    for r in copied:
        dst = train_root / r["target_class"] / r["copied_name"]
        shutil.copy2(CORRECTIONS_DIR / r["target_class"] / r["copied_name"], dst)

    # 守卫：训练集类集合/顺序必须与 organized/train 完全一致（labels 索引不漂移）。
    # 用 sorted 相等断言比 set 更强：既保集合又保 ImageFolder 字母序。
    assert sorted(d.name for d in train_root.iterdir() if d.is_dir()) == sorted(
        d.name for d in (ORGANIZED_DIR / "train").iterdir() if d.is_dir()
    ), "纠错数据引入了训练类集外的新类别，禁止继续（会错位 labels）"
    return FEEDBACK_TRAIN_DIR


def evaluate_ckpt(ckpt: Path) -> float:
    """在 organized/test（两段 256→224 协议）上评估分类准确率。"""
    import torch
    from torch.utils.data import DataLoader

    from ablation import CachedFolder
    from train_classifier import build_model

    device = "cuda" if torch.cuda.is_available() else "cpu"
    ds = CachedFolder(ORGANIZED_DIR / "test", train=False)
    loader = DataLoader(ds, batch_size=32, shuffle=False, num_workers=0)
    model = build_model(pretrained=False).to(device)
    model.load_state_dict(torch.load(ckpt, map_location=device))
    model.eval()
    correct = total = 0
    with torch.no_grad():
        for x, y in loader:
            pred = model(x.to(device)).argmax(1).cpu()
            correct += (pred == y).sum().item()
            total += y.size(0)
    return correct / max(total, 1)


def export_with_guard(ckpt_name: str) -> bool:
    """导出 ONNX 并在 labels 变更时还原旧模型。返回 labels 是否保持不变。"""
    from export_onnx import export_classifier

    old_labels = json.loads(
        (BACKEND_MODELS_DIR / "labels.json").read_text(encoding="utf-8")
    )
    onnx_path = BACKEND_MODELS_DIR / "classifier.onnx"
    shutil.copy2(onnx_path, onnx_path.with_suffix(".onnx.bak"))
    shutil.copy2(
        BACKEND_MODELS_DIR / "labels.json",
        BACKEND_MODELS_DIR / "labels.json.bak",
    )
    export_classifier(ckpt=ckpt_name)
    new_labels = json.loads(
        (BACKEND_MODELS_DIR / "labels.json").read_text(encoding="utf-8")
    )
    if new_labels != old_labels:
        shutil.copy2(onnx_path.with_suffix(".onnx.bak"), onnx_path)
        shutil.copy2(
            BACKEND_MODELS_DIR / "labels.json.bak",
            BACKEND_MODELS_DIR / "labels.json",
        )
        print("[中止] labels.json 与导出前不一致（索引漂移风险），已还原旧模型。")
        return False
    onnx_path.with_suffix(".onnx.bak").unlink(missing_ok=True)
    (BACKEND_MODELS_DIR / "labels.json.bak").unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True, help="后端导出的反馈 CSV")
    parser.add_argument("--epochs", type=int, default=8, help="续训轮数（小样本建议 8-15）")
    parser.add_argument("--force", action="store_true", help="清空已用标记与纠错归档，全量重跑")
    parser.add_argument(
        "--recognition-dir", type=Path, default=None,
        help="识别原图目录（默认 config.RECOGNITION_DIR）",
    )
    args = parser.parse_args()

    global RECOGNITION_DIR
    if args.recognition_dir:
        RECOGNITION_DIR = args.recognition_dir

    if not args.csv.is_file():
        print(f"[错误] 找不到 CSV: {args.csv}"); sys.exit(1)
    if not RECOGNITION_DIR.is_dir():
        print(f"[错误] 识别原图目录不存在: {RECOGNITION_DIR}"); sys.exit(1)
    if not (CHECKPOINTS_DIR / "best_finetune.pth").exists():
        print("[错误] 缺少生产模型 best_finetune.pth，先训练再纠错。"); sys.exit(1)

    if args.force:
        shutil.rmtree(CORRECTIONS_DIR, ignore_errors=True)
        save_used(set())

    rows = load_export(args.csv)
    rows = dedup_latest(rows)
    used = load_used()
    fresh = [r for r in rows if r["recognition_id"] not in used]
    print(f"CSV {len(rows)} 行去重后 {len(rows)} 条，已训练跳过 {len(rows) - len(fresh)} 条，"
          f"本次待处理 {len(fresh)} 条")

    copied, stats = collect_corrections(fresh, used)
    print(f"拷贝纠错图 {len(copied)} 张；跳过：目标类越界 {stats['no_target']}、"
          f"原图缺失 {stats['missing_image']}")
    if stats["per_class"]:
        print("按类分布:", json.dumps(stats["per_class"], ensure_ascii=False))

    if not copied:
        print("没有新的纠错样本，无需训练。"); return

    train_root = build_feedback_train(copied)

    # 从生产模型续训（不覆盖 best_finetune.pth，保留基线）
    print(f"\n=== 从 best_finetune.pth 续训（{args.epochs} epochs，lr={LR_FINETUNE}）===")
    _, result = run_stage(
        "feedback", args.epochs, LR_FINETUNE, train_root,
        tag="finetune_feedback", init_from="best_finetune.pth",
    )
    if result is None:
        print("[错误] 训练未完成"); sys.exit(1)

    # 前后评估（同协议同测试集）
    before = evaluate_ckpt(CHECKPOINTS_DIR / "best_finetune.pth")
    after = evaluate_ckpt(CHECKPOINTS_DIR / "best_finetune_feedback.pth")
    print(f"\norganized/test 评估：续训前 {before:.4f} → 续训后 {after:.4f} "
          f"（delta {after - before:+.4f}）")

    # 导出 ONNX + labels 守卫
    labels_unchanged = export_with_guard("best_finetune_feedback.pth")
    print("labels 顺序检查：", "✅ 一致" if labels_unchanged else "❌ 已还原")

    # 报告 + 幂等标记（只标记真正使用了原图的行）
    new_used = used | {r["recognition_id"] for r in copied}
    save_used(new_used)
    report = {
        "n_rows": len(rows),
        "used_this_run": len(copied),
        "skipped_no_target": stats["no_target"],
        "skipped_missing_image": stats["missing_image"],
        "per_class_used": stats["per_class"],
        "before_accuracy": round(before, 4),
        "after_accuracy": round(after, 4),
        "delta": round(after - before, 4),
        "best_val_acc": round(result["best_val_acc"], 4),
        "best_epoch": result["best_epoch"],
        "labels_unchanged": labels_unchanged,
        "total_used": len(new_used),
    }
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n报告：{REPORT_FILE}")
    print("下一步：重启后端 uvicorn 使新 ONNX 生效（model_inference 缓存 session）。")


if __name__ == "__main__":
    main()
