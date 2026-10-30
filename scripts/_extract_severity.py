"""解压 PythonProject1（绿豆严重度数据）→ ml/data/severity/，保留原始结构。"""
import sys
import zipfile
from pathlib import Path

BASE = Path(r"D:\BaiduNetdiskDownload")
DST = Path(r"D:\dc2\ml\data\severity")
PREFIX = "PythonProject1/"

mode = sys.argv[1] if len(sys.argv) > 1 else "extract"

with zipfile.ZipFile(BASE / "PythonProject1.zip") as z:
    infos = [i for i in z.infolist() if i.filename.startswith(PREFIX) and i.filename != PREFIX]

    if mode == "size":
        total = sum(i.file_size for i in infos)
        files = sum(1 for i in infos if not i.is_dir())
        print(f"总条目 {len(infos)}，文件 {files} 个，解压后约 {total/1e9:.2f} GB")
        sys.exit(0)

    if mode == "extract":
        DST.mkdir(parents=True, exist_ok=True)
        done = files_done = 0
        for i in infos:
            rel = i.filename[len(PREFIX):]
            target = DST / rel
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as src, open(target, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            done += i.file_size
            files_done += 1
            if files_done % 100 == 0:
                print(f"  {files_done} 文件, {done/1e9:.2f} GB")
        print(f"✅ 完成: {files_done} 文件, {done/1e9:.2f} GB -> {DST}")
