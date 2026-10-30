from __future__ import annotations

import csv
import io
import json
import unicodedata
import zipfile
from html import escape
from typing import Any


def risks_to_geojson(risks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": risk.get("geometry"),
                "properties": {
                    "id": risk.get("id"),
                    "title": risk.get("title"),
                    "category": risk.get("category"),
                    "level": risk.get("level"),
                    "description": risk.get("description"),
                    "standard_name": risk.get("clause", {}).get("standard_name"),
                    "clause_id": risk.get("clause", {}).get("clause_id"),
                    "is_placeholder": risk.get("clause", {}).get("is_placeholder"),
                },
            }
            for risk in risks
            if risk.get("geometry")
        ],
    }


def risks_to_csv(risks: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    fields = [
        "id",
        "title",
        "category",
        "level",
        "description",
        "impact",
        "recommendation",
        "standard_name",
        "clause_id",
        "clause_summary",
        "is_placeholder",
        "calculation",
        "actual_value",
        "threshold",
        "unit",
        "object_ids",
        "knowledge_graph_chain",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for risk in risks:
        clause = risk.get("clause", {})
        evidence = risk.get("evidence", {})
        kg = risk.get("knowledge_graph", {})
        writer.writerow(
            {
                "id": risk.get("id"),
                "title": risk.get("title"),
                "category": risk.get("category"),
                "level": risk.get("level"),
                "description": risk.get("description"),
                "impact": risk.get("impact"),
                "recommendation": risk.get("recommendation"),
                "standard_name": clause.get("standard_name"),
                "clause_id": clause.get("clause_id"),
                "clause_summary": clause.get("summary"),
                "is_placeholder": clause.get("is_placeholder"),
                "calculation": evidence.get("calculation"),
                "actual_value": evidence.get("actual_value"),
                "threshold": evidence.get("threshold"),
                "unit": evidence.get("unit"),
                "object_ids": ",".join(evidence.get("object_ids", [])),
                "knowledge_graph_chain": " -> ".join(kg.get("chain", [])),
            }
        )
    return output.getvalue()


def risks_to_html(project: dict[str, Any]) -> str:
    risks = project.get("risks", [])
    rows = []
    for risk in risks:
        clause = risk.get("clause", {})
        evidence = risk.get("evidence", {})
        kg = risk.get("knowledge_graph", {})
        rows.append(
            "<tr>"
            f"<td>{escape(risk.get('level', ''))}</td>"
            f"<td>{escape(risk.get('title', ''))}</td>"
            f"<td>{escape(risk.get('description', ''))}</td>"
            f"<td>{escape(clause.get('standard_name', ''))}<br>{escape(clause.get('clause_id', ''))}</td>"
            f"<td>{escape(evidence.get('calculation', ''))}<br>{escape(str(evidence.get('actual_value', '')))} / {escape(str(evidence.get('threshold', '')))} {escape(evidence.get('unit', ''))}</td>"
            f"<td>{escape(' → '.join(kg.get('chain', [])))}</td>"
            f"<td>{escape(risk.get('recommendation', ''))}</td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<meta charset="utf-8">
<title>{escape(project.get("name", "审查报告"))}</title>
<style>
body {{ font-family: "Microsoft YaHei", Arial, sans-serif; margin: 28px; color: #1f2937; }}
h1 {{ font-size: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #cbd5e1; padding: 8px; vertical-align: top; }}
th {{ background: #f1f5f9; }}
.note {{ color: #64748b; }}
</style>
<h1>{escape(project.get("name", "通信基建设计智能审查报告"))}</h1>
<p class="note">风险数量：{len(risks)}。标记为占位标准的依据用于原型演示，后续可替换为真实行业标准。</p>
<table>
<thead><tr><th>等级</th><th>风险</th><th>说明</th><th>法规依据</th><th>计算证据</th><th>知识图谱证据链</th><th>整改建议</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</html>"""


def risks_to_docx(project: dict[str, Any]) -> bytes:
    body = [
        _p(project.get("name", "通信基建设计智能审查报告")),
        _p(f"风险数量：{len(project.get('risks', []))}"),
    ]
    for risk in project.get("risks", []):
        clause = risk.get("clause", {})
        evidence = risk.get("evidence", {})
        kg = risk.get("knowledge_graph", {})
        body.extend(
            [
                _p(f"{risk.get('level')} - {risk.get('title')}"),
                _p(risk.get("description", "")),
                _p(f"依据：{clause.get('standard_name')} {clause.get('clause_id')} {clause.get('summary')}"),
                _p(f"证据：{evidence.get('calculation')}，实际值 {evidence.get('actual_value')}，阈值 {evidence.get('threshold')} {evidence.get('unit', '')}"),
                _p(f"知识图谱证据链：{' → '.join(kg.get('chain', [])) or '未生成'}"),
                _p(f"建议：{risk.get('recommendation', '')}"),
            ]
        )
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
%s
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
</w:body></w:document>""" % "".join(body)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", CONTENT_TYPES)
        zf.writestr("_rels/.rels", RELS)
        zf.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def risks_to_xlsx(risks: list[dict[str, Any]]) -> bytes:
    csv_text = risks_to_csv(risks)
    rows = list(csv.reader(io.StringIO(csv_text)))
    sheet_rows = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row, start=1):
            ref = f"{_col(c)}{r}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet_rows)}</sheetData></worksheet>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", XLSX_CONTENT_TYPES)
        zf.writestr("_rels/.rels", XLSX_RELS)
        zf.writestr("xl/workbook.xml", XLSX_WORKBOOK)
        zf.writestr("xl/_rels/workbook.xml.rels", XLSX_WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def risks_to_pdf(project: dict[str, Any]) -> bytes:
    lines = [project.get("name", "通信基建设计智能审查报告"), f"风险数量：{len(project.get('risks', []))}", ""]
    for risk in project.get("risks", []):
        clause = risk.get("clause", {})
        evidence = risk.get("evidence", {})
        kg = risk.get("knowledge_graph", {})
        report_line = (
            f"{risk.get('level')} {risk.get('title')} | {risk.get('description')} | "
            f"依据 {clause.get('standard_name')} {clause.get('clause_id')} | "
            f"证据 {evidence.get('calculation')} {evidence.get('actual_value')}/{evidence.get('threshold')} | "
            f"图谱 {' → '.join(kg.get('chain', []))} | "
            f"建议 {risk.get('recommendation')}"
        )
        lines.extend(_wrap_pdf_line(report_line, width=64))
        lines.append("")
    return _simple_pdf(lines)


def _p(text: str) -> str:
    return f"<w:p><w:r><w:t>{escape(str(text))}</w:t></w:r></w:p>"


def _col(number: int) -> str:
    result = ""
    while number:
        number, rem = divmod(number - 1, 26)
        result = chr(65 + rem) + result
    return result


def _simple_pdf(lines: list[str]) -> bytes:
    content = []
    y = 780
    for line in lines[:45]:
        text = _pdf_utf16_hex(str(line))
        content.append(f"BT /F1 10 Tf 50 {y} Td <{text}> Tj ET")
        y -= 16
    stream = "\n".join(content).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>",
        (
            b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
            b"/Encoding /UniGB-UCS2-H /DescendantFonts [5 0 R] >>"
        ),
        (
            b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
            b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> "
            b"/FontDescriptor 6 0 R >>"
        ),
        b"<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 /Ascent 880 /Descent -120 /CapHeight 700 /StemV 80 >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = io.BytesIO()
    pdf.write(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(pdf.tell())
        pdf.write(f"{index} 0 obj\n".encode())
        pdf.write(obj)
        pdf.write(b"\nendobj\n")
    xref = pdf.tell()
    pdf.write(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        pdf.write(f"{offset:010d} 00000 n \n".encode())
    pdf.write(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return pdf.getvalue()


def _pdf_utf16_hex(text: str) -> str:
    return text.encode("utf-16-be", errors="replace").hex().upper()


def _wrap_pdf_line(text: str, width: int = 64) -> list[str]:
    lines: list[str] = []
    current = ""
    current_width = 0
    for char in text:
        char_width = 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        if current and current_width + char_width > width:
            lines.append(current)
            current = char
            current_width = char_width
        else:
            current += char
            current_width += char_width
    if current:
        lines.append(current)
    return lines


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
XLSX_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""
XLSX_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
XLSX_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="风险清单" sheetId="1" r:id="rId1"/></sheets></workbook>"""
XLSX_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>"""
