"""极简 XLSX 生成器（纯标准库，不依赖 openpyxl）。

xlsx 本质是一个 ZIP 包，内含若干 XML。这里只实现识别报告需要的最小子集：
  - 多张工作表
  - 字符串 / 数字 / 百分比三种单元格
  - 首行加粗表头
  - 冻结首行 + 自动列宽

之所以自己写而不引 openpyxl：exe 体积敏感（openpyxl 及其依赖约 +3MB），
且本工具强调「零第三方依赖、全离线」。
"""
from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

# ── XML 片段模板 ──
_CT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

_WB_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{rels}
<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# 样式表：0=正文 1=表头(加粗+底色) 2=百分比 3=整数千分位
_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="0.0%"/>
<numFmt numFmtId="165" formatCode="#,##0"/>
</numFmts>
<fonts count="2">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1F3864"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFDCE6F1"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

_CORE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{title}</dc:title>
<dc:creator>方舟慧眼</dc:creator>
<cp:lastModifiedBy>方舟慧眼</cp:lastModifiedBy>
</cp:coreProperties>"""

_ST = "percent"      # 样式 2：百分比
_INT = "int"         # 样式 3：千分位整数
_PLAIN = ""          # 正文


def _col_name(idx: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA"""
    name = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        name = chr(65 + rem) + name
    return name


def _width_of(text: str) -> int:
    """按内容估算列宽（中文按 2 个字符计）。"""
    n = 0
    for ch in text:
        n += 2 if ord(ch) > 0x2E80 else 1
    return max(6, min(52, n + 2))


class Sheet:
    """一张工作表。rows 为二维列表，单元格可以是 str / int / float / ('pct', v) / ('int', v)。"""

    def __init__(self, title: str, rows: list[list], freeze: bool = True):
        self.title = title
        self.rows = rows
        self.freeze = freeze

    def widths(self) -> list[int]:
        n = max((len(r) for r in self.rows), default=0)
        w = [8] * n
        for r in self.rows:
            for i, c in enumerate(r):
                if isinstance(c, tuple):
                    c = c[1] if len(c) > 1 else c[0]
                w[i] = max(w[i], _width_of(str(c)))
        return w

    def xml(self) -> str:
        out = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        ]
        if self.freeze:
            out.append(
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
                "</sheetView></sheetViews>"
            )
        w = self.widths()
        if w:
            cols = "".join(
                f'<col min="{i+1}" max="{i+1}" width="{x}" customWidth="1"/>'
                for i, x in enumerate(w)
            )
            out.append(f"<cols>{cols}</cols>")
        out.append("<sheetData>")
        for ri, row in enumerate(self.rows, start=1):
            cells = []
            for ci, c in enumerate(row):
                ref = f"{_col_name(ci)}{ri}"
                style = 0
                if ri == 1:
                    cells.append(f'<c r="{ref}" s="1" t="inlineStr"><is><t>{escape(str(c))}</t></is></c>')
                    continue
                if isinstance(c, tuple):
                    kind, v = c
                    if kind == "percent":
                        style, c = 2, float(v)
                    elif kind == "int":
                        style, c = 3, int(v)
                    else:
                        c = v
                if isinstance(c, bool):
                    c = str(c)
                if isinstance(c, (int, float)):
                    cells.append(f'<c r="{ref}" s="{style}"><v>{c}</v></c>')
                else:
                    cells.append(
                        f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                        f"{escape(str(c))}</t></is></c>"
                    )
            out.append(f'<row r="{ri}">{"".join(cells)}</row>')
        out.append("</sheetData></worksheet>")
        return "".join(out)


def build(sheets: list[Sheet], title: str = "方舟慧眼识别报告") -> bytes:
    """打包成 xlsx 字节流。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        overrides = "\n".join(
            f'<Override PartName="/xl/worksheets/sheet{i+1}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(len(sheets))
        )
        z.writestr("[Content_Types].xml", _CT.format(overrides=overrides))
        z.writestr("_rels/.rels", _RELS)
        z.writestr("docProps/core.xml", _CORE.format(title=escape(title)))
        z.writestr("xl/styles.xml", _STYLES)

        sheet_tags = "".join(
            f'<sheet name="{escape(s.title[:31])}" sheetId="{i+1}" r:id="rIdS{i+1}"/>'
            for i, s in enumerate(sheets)
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheet_tags}</sheets></workbook>",
        )
        rels = "".join(
            f'<Relationship Id="rIdS{i+1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i+1}.xml"/>'
            for i in range(len(sheets))
        )
        z.writestr("xl/_rels/workbook.xml.rels", _WB_RELS.format(rels=rels))
        for i, s in enumerate(sheets):
            z.writestr(f"xl/worksheets/sheet{i+1}.xml", s.xml())
    return buf.getvalue()
