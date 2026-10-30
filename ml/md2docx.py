"""把论文 markdown 初稿转成 Word (.docx)，供《智慧农业（中英文）》投稿提交。

仅处理投稿版用到的 markdown 子集：标题（#/##/###）、引用块（>）、表格（|..|）、
有序/无序列表、加粗/斜体/行内代码、分隔线（--- 跳过）。Unicode 上标 ¹²³ 转 Word
上标；中文字体宋体、标题黑体、西文 Times New Roman。

用法：python md2docx.py <input.md> <output.docx>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

INLINE = re.compile(r"(\*\*.*?\*\*|\*.*?\*|`[^`]*`)")


def set_font(run, size=12, bold=False, italic=False, superscript=False, cn="宋体", en="Times New Roman"):
    run.font.name = en
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = RGBColor(0, 0, 0)
    if superscript:
        run.font.superscript = True
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = rPr.makeelement(qn("w:rFonts"), {})
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), en)
    rFonts.set(qn("w:hAnsi"), en)
    rFonts.set(qn("w:eastAsia"), cn)


def add_runs(p, text, size=12, bold=False, italic=False, cn="宋体"):
    """把 **b**、*i*、`code` 解析进段落；Unicode 上标 ¹²³ 转 Word superscript。"""
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) >= 4:
            add_runs(p, part[2:-2], size=size, bold=True, italic=italic, cn=cn)
        elif part.startswith("`") and part.endswith("`") and len(part) >= 2:
            r = p.add_run(part[1:-1])
            set_font(r, size=size, bold=bold, italic=italic, cn=cn)
        elif part.startswith("*") and part.endswith("*") and len(part) >= 2:
            add_runs(p, part[1:-1], size=size, bold=bold, italic=True, cn=cn)
        else:
            for seg in re.split("([\u00b9\u00b2\u00b3])", part):
                if not seg:
                    continue
                if seg in "\u00b9\u00b2\u00b3":
                    r = p.add_run(seg.translate(str.maketrans("\u00b9\u00b2\u00b3", "123")))
                    set_font(r, size=size, bold=bold, italic=italic, superscript=True, cn=cn)
                else:
                    r = p.add_run(seg)
                    set_font(r, size=size, bold=bold, italic=italic, cn=cn)


def build(md_text: str, base_dir: Path) -> Document:
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
    normal.paragraph_format.line_spacing = 1.5

    lines = md_text.splitlines()
    i, n = 0, len(lines)
    while i < n:
        stripped = lines[i].strip()

        if not stripped or stripped == "---":
            i += 1
            continue

        # 表格块：当前行以 | 开头，且下一行是 |---| 分隔行
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:\-|]+\|\s*$", lines[i + 1]):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            j = i + 2
            rows = []
            while j < n and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            table = doc.add_table(rows=1 + len(rows), cols=len(header))
            table.style = "Table Grid"
            for k, h in enumerate(header):
                cell = table.rows[0].cells[k]
                cell.text = ""
                add_runs(cell.paragraphs[0], h, size=10.5, bold=True)
            for r_idx, row in enumerate(rows):
                for k, val in enumerate(row):
                    cell = table.rows[r_idx + 1].cells[k]
                    cell.text = ""
                    add_runs(cell.paragraphs[0], val, size=10.5)
            i = j
            continue

        # 引用块：合并连续 > 行
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip()[1:].strip())
                i += 1
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(24)
            add_runs(p, " ".join(buf), size=12)
            continue

        # 图片行（markdown 插图）
        m = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", stripped)
        if m:
            img_path = base_dir / m.group(1)
            if img_path.exists():
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.add_run().add_picture(str(img_path), width=Inches(5.5))
            else:
                print(f"WARN 图片不存在: {img_path}")
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                alt = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped).group(1).strip()
                add_runs(p, f"【此处待插入图片：{alt}】", size=12, bold=True)
            i += 1
            continue

        # 图注行（以「图N 」开头，居中加粗）
        if re.match(r"^图\s*\d+", stripped):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_runs(p, stripped, size=10.5, bold=True)
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            h = doc.add_heading("", level=level)
            if level == 1:
                h.alignment = WD_ALIGN_PARAGRAPH.CENTER
                add_runs(h, m.group(2).strip(), size=16, bold=True, cn="黑体")
            else:
                add_runs(h, m.group(2).strip(), size=14 if level == 2 else 12, bold=True, cn="黑体")
            i += 1
            continue

        # 无序列表
        m = re.match(r"^\s*[-•]\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, m.group(1), size=12)
            i += 1
            continue

        # 有序列表
        m = re.match(r"^(\d+)\.\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Number")
            add_runs(p, m.group(2), size=12)
            i += 1
            continue

        # 参考文献条目（[1] ...）用小五号
        size = 10.5 if re.match(r"^\[\d+\]", stripped) else 12
        p = doc.add_paragraph()
        add_runs(p, stripped, size=size)
        i += 1

    return doc


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    build(src.read_text(encoding="utf-8"), src.parent).save(str(dst))
    print(f"OK -> {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
