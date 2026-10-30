"""识别记录回填：用真实叶片图跑生产推理管线，为统计图表填充真实数据。

在服务器 /opt/dc2/backend 运行：
    .venv/bin/python -m scripts.backfill_recognitions

读取 backend/data/backfill/<病名>/*.jpg（本地已采样压缩，随发布包部署），每张配一组
轮转的环境上下文（生育期/天气/种植/经纬度），走 services/recognize.recognize 完整管线
（分类→严重度→环境模态→知识规则→防治方案→落库），结果均为真实模型推理、不伪造标签。

跑完可删除 data/backfill 目录释放磁盘（约 1.5MB）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.db import SessionLocal
from app.models import User
from app.schemas.recognition import EnvInput
from app.services.recognize import recognize

BACKFILL_DIR = Path(__file__).resolve().parent.parent / "data" / "backfill"

# 与 stats.py / seed / 前端一致的档位
GROWTH_STAGES = ["苗期", "分枝期", "开花期", "结荚期", "成熟期"]
WEATHERS = ["高温高湿", "阴雨连绵", "雨后天晴", "晴热干旱", "虫害盛发"]
PLANTINGS = ["露地", "大棚"]
# 绿豆主产区真实经纬度（河北邢台 / 安徽阜阳 / 河南开封），触发 WorldClim 气候回查
LOCATIONS = [(36.85, 114.50), (33.00, 116.00), (34.80, 114.00)]


def main() -> None:
    if not BACKFILL_DIR.is_dir():
        print(f"[warn] 未找到回填图片目录：{BACKFILL_DIR}（发布包需包含 backend/data/backfill/）")
        sys.exit(1)

    images = sorted(BACKFILL_DIR.rglob("*.jpg"))
    print(f"共 {len(images)} 张回填图（{BACKFILL_DIR}）")

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        admin_id = admin.id if admin else None
        print(f"识别记录绑定用户：admin (id={admin_id})")

        dist: dict[str, int] = {}
        ok = 0
        for i, img in enumerate(images):
            # 轮转环境上下文，尽量覆盖 5 天气 × 5 生育期 × 2 种植 × 3 经纬度
            env_input = EnvInput(
                growth_stage=GROWTH_STAGES[i % len(GROWTH_STAGES)],
                weather=WEATHERS[i % len(WEATHERS)],
                planting=PLANTINGS[i % len(PLANTINGS)],
                lat=LOCATIONS[i % len(LOCATIONS)][0],
                lon=LOCATIONS[i % len(LOCATIONS)][1],
            )
            try:
                resp = recognize(img.read_bytes(), env_input, db, user_id=admin_id)
            except Exception as exc:  # noqa: BLE001 单个失败不影响整体
                print(f"  [{img.parent.name}/{img.name}] 推理失败: {exc}")
                continue
            ok += 1
            dist[resp.disease_name or "未知"] = dist.get(resp.disease_name or "未知", 0) + 1
            print(
                f"  [{img.parent.name}] → {resp.disease_name} | "
                f"{resp.severity} | {resp.confidence:.3f} | "
                f"{env_input.weather}/{env_input.growth_stage}/{env_input.planting}"
            )

        print(f"\n成功 {ok}/{len(images)} 条。真实推理分布统计：")
        for name, count in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"  {name}: {count}")
    finally:
        db.close()

    print("完成。")


if __name__ == "__main__":
    main()
