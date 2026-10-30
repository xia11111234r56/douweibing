"""临时调试：检查种子数据是否正确灌入（中文路径，写入文件避免控制台乱码）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal
from app.models import Disease, Treatment, Recognition

out = Path(__file__).resolve().parent / "debug_result.txt"
lines = []

db = SessionLocal()
try:
    diseases = db.query(Disease).all()
    lines.append(f"病害数: {len(diseases)}")
    for d in diseases:
        lines.append(f"  [{d.id}] {d.name} | {d.disease_type} | treatments={len(d.treatments)}")
    t_count = db.query(Treatment).count()
    lines.append(f"防治方案总数: {t_count}")
    r_count = db.query(Recognition).count()
    lines.append(f"识别记录数: {r_count}")
finally:
    db.close()

out.write_text("\n".join(lines), encoding="utf-8")
print("已写入", out)
