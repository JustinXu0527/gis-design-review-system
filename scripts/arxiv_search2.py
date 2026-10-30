# -*- coding: utf-8 -*-
"""
第二轮定向补充检索：聚焦赛事场景（通信/电力/管网基建 + GIS + 标准合规 + 中文标准）
合并进 arxiv_raw_results.json
"""
import json
import os
import time
import urllib.parse
import urllib.request
import re
import xml.etree.ElementTree as ET

NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
API = "http://export.arxiv.org/api/query"

QUERIES = [
    # 定向：光纤/通信管线工程
    ("K1", 'all:"fiber optic" AND all:"network design" AND all:"automated"'),
    ("K2", 'all:"telecommunication network" AND all:"planning" AND all:"optimization" AND all:"design"'),
    ("K3", 'all:"optical network" AND all:"GIS"'),
    # 定向：管线/管网设计与合规
    ("K4", 'all:"oil and gas pipeline" AND all:"design" AND all:"safety"'),
    ("K5", 'all:"pipeline design" AND all:"compliance"'),
    ("K6", 'all:"pipeline routing" AND all:"optimization" AND all:"constraints"'),
    ("K7", 'all:"water distribution network" AND all:"design" AND all:"constraint"'),
    # 定向：输电线路/电力走廊
    ("K8", 'all:"transmission line" AND all:"routing" AND all:"optimization"'),
    ("K9", 'all:"electric power grid" AND all:"geospatial"'),
    ("K10", 'all:"power grid" AND all:"compliance" AND all:"standard"'),
    # 定向：BIM/GIS 融合
    ("K11", 'all:"BIM" AND all:"GIS" AND all:"integration"'),
    ("K12", 'all:"digital twin" AND all:"infrastructure" AND all:"compliance"'),
    # 定向：中文/多语言标准检索
    ("K13", 'all:"Chinese" AND all:"building code" OR all:"Chinese standard"'),
    ("K14", 'all:"cross-language" AND all:"information retrieval" AND all:"engineering"'),
    ("K15", 'all:"domain-specific embedding" AND all:"technical document"'),
    # 定向：LLM 幻觉与可验证性
    ("K16", 'all:"LLM" AND all:"verifiable" AND all:"evidence" AND all:"chain"'),
    ("K17", 'all:"faithfulness" AND all:"retrieval augmented generation"'),
    ("K18", 'all:"abstention" AND all:"LLM" AND all:"uncertainty"'),
    # 定向：规则形式化与法律/规范文本
    ("K19", 'all:"legal text" AND all:"formalization" AND all:"rule extraction"'),
    ("K20", 'all:"ontology" AND all:"regulation" AND all:"automated reasoning"'),
    ("K21", 'all:"Semantic Web" AND all:"regulation" AND all:"compliance"'),
    # 定向：工程图纸/文档解析
    ("K22", 'all:"P&ID" OR all:"piping and instrumentation" AND all:"LLM"'),
    ("K23", 'all:"CAD" AND all:"large language model"'),
    ("K24", 'all:"vector data" AND all:"geometry" AND all:"validation" AND all:"automated"'),
    ("K25", 'all:"Shapely" OR all:"GEOS" OR all:"spatial database" AND all:"validation"'),
    # 定向：OGC / 空间数据标准
    ("K26", 'all:"OGC" AND all:"standards" AND all:"spatial data infrastructure"'),
    ("K27", 'all:"INSPIRE" OR all:"spatial data infrastructure" AND all:"quality"'),
    # 定向：LLM 做表格/数值计算可靠性
    ("K28", 'all:"large language model" AND all:"numerical reasoning" AND all:"tool"'),
    ("K29", 'all:"LLM" AND all:"calculator" AND all:"reliability"'),
    # 定向：审查流程自动化与人机协同
    ("K30", 'all:"human-in-the-loop" AND all:"compliance" AND all:"AI"'),
    ("K31", 'all:"design review" AND all:"automation" AND all:"engineering"'),
    ("K32", 'all:"quality assurance" AND all:"engineering design" AND all:"AI"'),
    # 定向：德国/欧洲标准
    ("K33", 'all:"DIN" OR all:"EN standard" AND all:"construction"'),
    ("K34", 'all:"Eurocode" OR all:"European standard" AND all:"automated"'),
]


def fetch(query, start=0, max_results=60, retries=4):
    params = {"search_query": query, "start": start, "max_results": max_results,
              "sortBy": "relevance", "sortOrder": "descending"}
    url = API + "?" + urllib.parse.urlencode(params)
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "arxiv-survey-bot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:
            print(f"    [retry {a+1}] {e}")
            time.sleep(5 + a * 5)
    return None


def parse(xml_bytes):
    out = []
    if not xml_bytes:
        return out
    root = ET.fromstring(xml_bytes)
    for entry in root.findall("atom:entry", NS):
        def txt(tag):
            el = entry.find(tag, NS)
            return el.text.strip() if el is not None and el.text else ""
        id_url = txt("atom:id")
        arxiv_id = re.sub(r"v\d+$", "", id_url.rsplit("/", 1)[-1]) if id_url else ""
        authors = [a.find("atom:name", NS).text.strip()
                   for a in entry.findall("atom:author", NS)
                   if a.find("atom:name", NS) is not None and a.find("atom:name", NS).text]
        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
        ce = entry.find("arxiv:comment", NS)
        je = entry.find("arxiv:journal_ref", NS)
        out.append({
            "arxiv_id": arxiv_id,
            "title": " ".join(txt("atom:title").split()),
            "summary": " ".join(txt("atom:summary").split()),
            "authors": authors,
            "published": txt("atom:published")[:10],
            "updated": txt("atom:updated")[:10],
            "primary_category": (entry.find("arxiv:primary_category", NS).get("term")
                                 if entry.find("arxiv:primary_category", NS) is not None else ""),
            "categories": [c.get("term") for c in entry.findall("atom:category", NS)],
            "pdf_url": pdf_url,
            "abs_url": "https://arxiv.org/abs/" + arxiv_id,
            "comment": " ".join(ce.text.split()) if ce is not None and ce.text else "",
            "journal_ref": " ".join(je.text.split()) if je is not None and je.text else "",
        })
    return out


HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "arxiv_raw_results.json")

with open(RAW, encoding="utf-8") as f:
    existing = json.load(f)
index = {r["arxiv_id"]: r for r in existing}
print(f"existing: {len(index)}")

added = 0
for tag, q in QUERIES:
    print(f"[{tag}] {q}")
    recs = parse(fetch(q))
    print(f"    -> {len(recs)}")
    for r in recs:
        r.setdefault("matched_queries", [])
        if r["arxiv_id"] not in index:
            index[r["arxiv_id"]] = r
            added += 1
        index[r["arxiv_id"]]["matched_queries"].append(tag)
    time.sleep(3.2)

result = list(index.values())
with open(RAW, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nadded {added}, total {len(result)}")
