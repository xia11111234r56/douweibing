"""生成论文配图（fig1..fig7），全部数据来自真实实验产物，不伪造。

- fig1 数据集类别分布      <- ml/data/raw 各目录真实文件计数（601 张）
- fig2 测试集每类指标      <- ml/experiments/eval_report.json per_class
- fig3 真实 vs ACGAN 生成  <- ml/data/raw + ml/experiments/augmented（GAN 训练时生成样本）
- fig4 GAN A/B 消融       <- ml/experiments/ablation_report.json
- fig5 5 折 CV            <- ml/experiments/cv_report.json
- fig6 2×2 消融           <- eval_report_178/B_report/C_report/balanced_report.json
- fig7 识别流程图           <- 方法章节流程图（示意，无数字）

用法：python make_figs.py  -> 输出 docs/paper/figures/figN_*.png（dpi 200）
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ML = Path(__file__).resolve().parent
EXP = ML / "experiments"
OUT = ML.parent / "docs" / "paper" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# 中文字体
avail = {f.name for f in font_manager.fontManager.ttflist}
_cjk = next((f for f in ("Microsoft YaHei", "SimHei", "SimSun", "KaiTi") if f in avail), None)
if _cjk:
    plt.rcParams["font.sans-serif"] = [_cjk]
plt.rcParams["axes.unicode_minus"] = False

RAW = ML / "data" / "raw"
SORTED_CLASSES = ["健康", "叶腐病", "晕疫病", "枯萎病", "炭疽叶斑病", "病毒病", "细菌性疫病", "细菌性萎蔫", "虫食", "轮纹叶斑病"]


def rd(name: str) -> dict | list:
    p = EXP / name
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return ast.literal_eval(p.read_text(encoding="utf-8"))


# ---------- fig1 数据集类别分布 ----------
def fig1():
    counts = {cls: len(list((RAW / cls).glob("*"))) for cls in SORTED_CLASSES}
    assert sum(counts.values()) == 601, counts
    items = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    names, vals = zip(*items)
    fig, ax = plt.subplots(figsize=(9, 4.6))
    bars = ax.bar(range(len(names)), vals, color="#4C72B0")
    for i, v in enumerate(vals):
        ax.text(i, v + 4, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("样本数")
    ax.set_ylim(0, max(vals) * 1.12)
    ax.set_title("绿豆病害数据集类别分布（共 601 张，10 类）", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_dataset_dist.png", dpi=200)
    plt.close(fig)


# ---------- fig2 测试集每类指标 ----------
def fig2():
    r = rd("eval_report.json")
    classes = ["健康", "晕疫病", "炭疽叶斑病", "病毒病", "细菌性萎蔫", "轮纹叶斑病"]
    data = [(c, r["per_class"][c]) for c in classes]
    names = [c for c, _ in data]
    p = [d["precision"] for _, d in data]
    rec = [d["recall"] for _, d in data]
    f1 = [d["f1-score"] for _, d in data]
    x = range(len(names))
    fig, ax = plt.subplots(figsize=(9, 4.6))
    w = 0.26
    ax.bar([i - w for i in x], p, w, label="精确率", color="#4C72B0")
    ax.bar(x, rec, w, label="召回率", color="#DD8452")
    ax.bar([i + w for i in x], f1, w, label="F1", color="#55A868")
    for i in x:
        ax.text(i - w, p[i] + 0.02, f"{p[i]:.2f}", ha="center", fontsize=8)
        ax.text(i, rec[i] + 0.02, f"{rec[i]:.2f}", ha="center", fontsize=8)
        ax.text(i + w, f1[i] + 0.02, f"{f1[i]:.2f}", ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, rotation=25, ha="right", fontsize=9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("指标值")
    ax.legend(fontsize=9)
    ax.set_title("生产模型在 89 张测试集上的各类别指标（支持数>0 的 6 类）", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_per_class.png", dpi=200)
    plt.close(fig)


# ---------- fig4 生成质量指标对比（真实数据，不展示雪花噪点图） ----------
def fig3():
    q = rd("gan_quality.json")["overall"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.8))
    # 面板 1：类内像素标准差（多样性）
    ax = axes[0]
    vals = [q["mean_gen_pixel_std"], q["mean_real_pixel_std"]]
    bars = ax.bar(["生成图", "真实图"], vals, width=0.5, color=["#4C72B0", "#55A868"])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.005, f"{v:.3f}", ha="center", fontsize=9)
    ax.set_ylim(0, 0.28)
    ax.set_title("类内像素标准差\n（多样性）", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # 面板 2：分类一致性 vs 随机基线
    ax = axes[1]
    vals = [q["class_agree_rate"], 0.1]
    bars = ax.bar(["生成图", "随机基线（10 类）"], vals, width=0.5, color=["#4C72B0", "#C44E52"])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.008, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_ylim(0, 0.2)
    ax.set_title("分类一致性\n（生成图判为所属类比例）", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    # 面板 3：分类平均置信度
    ax = axes[2]
    ax.bar(["生成图"], [q["mean_conf"]], width=0.5, color=["#4C72B0"])
    ax.text(0, q["mean_conf"] + 0.015, f"{q['mean_conf']:.2f}", ha="center", fontsize=9)
    ax.set_ylim(0, 0.6)
    ax.set_title("分类平均置信度\n（远低于正确分类所需）", fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.suptitle("ACGAN 生成质量评估（每类抽样 50 张、共 500 张生成图）", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(OUT / "fig4_gan_quality.png", dpi=200)
    plt.close(fig)


# ---------- fig4 GAN A/B 消融 ----------
def fig4():
    r = rd("ablation_report.json")
    by = {d["tag"]: d for d in r}
    names = ["无增强基线", "GAN 增强"]
    vals = [by["baseline"]["test_acc"], by["gan_augmented"]["test_acc"]]
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    bars = ax.bar(names, vals, width=0.5, color=["#8C8C8C", "#4C72B0"])
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.01, f"{v:.4f}", ha="center", fontsize=10)
    ax.set_ylim(0, 0.95)
    ax.set_ylabel("测试准确率")
    ax.set_title("GAN 增强 A/B 消融（30 epoch，同一初始化）\n测试准确率 0.7865→0.8202（+0.0337）", fontsize=11)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_gan_ablation.png", dpi=200)
    plt.close(fig)


# ---------- fig5 5 折 CV ----------
def fig5():
    r = rd("cv_report.json")
    folds = [f["test_acc"] for f in r["folds"]]
    pooled = r["pooled_accuracy"]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    bars = ax.bar([f"折{i}" for i in range(1, 6)], folds, color="#4C72B0")
    for b, v in zip(bars, folds):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.006, f"{v:.4f}", ha="center", fontsize=9)
    ax.axhline(pooled, ls="--", color="#C44E52", lw=1.5)
    ax.text(4.3, pooled + 0.006, f"pooled {pooled:.4f}", color="#C44E52", fontsize=10, ha="right")
    ax.set_ylim(0.75, 0.95)
    ax.set_ylabel("测试一致率")
    ax.set_title("全量 601 张 5 折交叉验证（真实图，不含 GAN，保守估计）", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_cv_5fold.png", dpi=200)
    plt.close(fig)


# ---------- fig6 2×2 消融 ----------
def fig6():
    a89 = rd("eval_report.json")["test_accuracy"]
    a178 = rd("eval_report_178.json")["test_accuracy"]
    b = rd("B_report.json")
    c = rd("C_report.json")
    d = rd("balanced_report.json")
    names = ["A 生产", "B 只加虫食", "C 只类平衡", "D 虫食+平衡"]
    t89 = [a89, b["test89_accuracy"], c["test89_accuracy"], d["test_accuracy"]]
    t178 = [a178, b["eval178_accuracy"], c["eval178_accuracy"], d["test_accuracy_178"]]
    x = range(len(names))
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    w = 0.34
    ax.bar([i - w / 2 for i in x], t89, w, label="test89（固定 89 张）", color="#4C72B0")
    ax.bar([i + w / 2 for i in x], t178, w, label="eval178（扩大评估集）", color="#DD8452")
    for i in x:
        ax.text(i - w / 2, t89[i] + 0.005, f"{t89[i]:.4f}", ha="center", fontsize=8)
        ax.text(i + w / 2, t178[i] + 0.005, f"{t178[i]:.4f}", ha="center", fontsize=8)
    ax.set_xticks(list(x))
    ax.set_xticklabels(names, fontsize=10)
    ax.set_ylim(0.72, 0.92)
    ax.set_ylabel("一致率")
    ax.legend(fontsize=9)
    ax.set_title("虫食补充 × 类平衡 2×2 消融（真实指标）", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_2x2_ablation.png", dpi=200)
    plt.close(fig)


# ---------- fig7 识别流程图 ----------
def fig7():
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    def box(x, y, w, h, text, fc="#E8F0FB", ec="#2F5B93"):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.008",
                                    fc=fc, ec=ec, lw=1.4))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=10)

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color="#2F5B93", lw=1.3))

    # 输入
    box(0.02, 0.40, 0.13, 0.22, "输入\n叶片图像\nEXIF 时间/GPS\n用户环境档位")
    # 三模态
    box(0.28, 0.62, 0.15, 0.22, "图像模态\nONNX MobileNetV3\n→ Top-K 候选")
    box(0.50, 0.62, 0.15, 0.22, "环境模态\nWorldClim 气候回查\n→ 环境上下文")
    box(0.72, 0.62, 0.15, 0.22, "知识规则模态\n病害—环境先验\n→ 置信度修正")
    # 严重度
    box(0.28, 0.18, 0.15, 0.20, "严重度模型\n深度特征+逻辑回归\n→ 轻/中/重")
    # 融合输出
    box(0.72, 0.30, 0.24, 0.24, "多模态融合\n置信度后验修正 + 严重度合成\n\n输出：病害类别 / 严重度 / 置信度 / 防治方案")

    arrow(0.15, 0.51, 0.28, 0.71)  # 输入 -> 图像
    arrow(0.15, 0.51, 0.50, 0.71)  # 输入 -> 环境
    arrow(0.15, 0.51, 0.72, 0.71)  # 输入 -> 知识规则
    arrow(0.355, 0.62, 0.355, 0.38)  # 图像 -> 严重度
    arrow(0.355, 0.18, 0.80, 0.30)   # 严重度 -> 融合
    arrow(0.355, 0.73, 0.72, 0.70)   # 图像 -> 融合
    arrow(0.575, 0.73, 0.72, 0.66)   # 环境 -> 融合
    arrow(0.795, 0.73, 0.82, 0.54)   # 知识规则 -> 融合
    ax.set_title("图像—环境—知识规则三模态融合识别流程", fontsize=13, pad=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig7_pipeline.png", dpi=200)
    plt.close(fig)


def main() -> None:
    fig1()
    fig2()
    fig3()
    fig4()
    fig5()
    fig6()
    fig7()
    for p in sorted(OUT.glob("fig*.png")):
        print(f"  {p.name}  {p.stat().st_size//1024} KB")


if __name__ == "__main__":
    main()
