# -*- coding: utf-8 -*-
"""
arXiv 论文批量检索脚本
用法: python arxiv_search.py
输出: arxiv_raw_results.json  与  arxiv_candidates.json
"""
import json
import time
import urllib.parse
import urllib.request
import re
import os
import xml.etree.ElementTree as ET

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}

API = "http://export.arxiv.org/api/query"

QUERIES = [
    # ---- 方向 A: 自动化合规审查 (Automated Compliance Checking, ACC) ----
    ("A1", 'all:"automated compliance checking" AND all:"building code"'),
    ("A2", 'all:"compliance checking" AND all:"construction" AND all:"regulation"'),
    ("A3", 'all:"building code compliance" AND all:"machine learning"'),
    ("A4", 'all:"design code compliance" OR all:"code compliance checking"'),
    ("A5", 'all:"regulatory compliance" AND all:"BIM"'),

    # ---- 方向 B: LLM 用于规范/法规审查 ----
    ("B1", 'all:"large language model" AND all:"building code" AND all:"compliance"'),
    ("B2", 'all:"LLM" AND all:"regulation" AND all:"compliance checking"'),
    ("B3", 'all:"large language models" AND all:"construction safety" AND all:"regulation"'),
    ("B4", 'all:"retrieval augmented generation" AND all:"regulation" AND all:"compliance"'),
    ("B5", 'all:"legal judgment" OR all:"legal reasoning" AND all:"LLM"'),
    ("B6", 'all:"automated code compliance" AND all:"large language model"'),

    # ---- 方向 C: 规则引擎 + 大模型混合架构 ----
    ("C1", 'all:"rule-based" AND all:"large language model" AND all:"hybrid"'),
    ("C2", 'all:"neuro-symbolic" AND all:"verification"'),
    ("C3", 'all:"symbolic reasoning" AND all:"LLM" AND all:"constraint"'),
    ("C4", 'all:"deterministic" AND all:"LLM" AND all:"audit"'),
    ("C5", 'all:"rule engine" AND all:"LLM"'),

    # ---- 方向 D: RAG / GraphRAG / 知识图谱证据链 ----
    ("D1", 'all:"GraphRAG" OR all:"graph retrieval augmented generation"'),
    ("D2", 'all:"knowledge graph" AND all:"retrieval augmented generation" AND all:"evidence"'),
    ("D3", 'all:"citation" AND all:"attribution" AND all:"retrieval augmented generation"'),
    ("D4", 'all:"knowledge graph" AND all:"standard" AND all:"engineering"'),

    # ---- 方向 E: GIS / 空间数据质量校验 ----
    ("E1", 'all:"spatial data quality" AND all:"validation"'),
    ("E2", 'all:"geospatial" AND all:"data quality" AND all:"automated"'),
    ("E3", 'all:"topology" AND all:"validation" AND all:"GIS"'),
    ("E4", 'all:"utility network" AND all:"GIS" AND all:"validation"'),
    ("E5", 'all:"pipeline" AND all:"spatial" AND all:"compliance"'),
    ("E6", 'all:"geographic information" AND all:"conformance" AND all:"standard"'),
    ("E7", 'all:"QGIS" OR all:"OpenGIS" AND all:"server" AND all:"automation"'),

    # ---- 方向 F: 多语言 embedding / 语义检索 / 跨语言 ----
    ("F1", 'all:"multilingual embedding" AND all:"retrieval"'),
    ("F2", 'all:"cross-lingual retrieval" AND all:"dense retrieval"'),
    ("F3", 'all:"bge-m3" OR all:"BGE M3"'),
    ("F4", 'all:"sentence embedding" AND all:"semantic search" AND all:"long document"'),
    ("F5", 'all:"Chinese" AND all:"German" AND all:"terminology" AND all:"translation"'),

    # ---- 方向 G: 幻觉抑制 / 可靠性与可追溯 ----
    ("G1", 'all:"hallucination" AND all:"large language model" AND all:"mitigation" AND all:"grounding"'),
    ("G2", 'all:"hallucination" AND all:"retrieval augmented generation" AND all:"factuality"'),
    ("G3", 'all:"LLM" AND all:"verifier" AND all:"self-consistency"'),
    ("G4", 'all:"trustworthy" AND all:"LLM" AND all:"enterprise" AND all:"audit trail"'),

    # ---- 方向 H: LLM Agent 工作流 / 编排 ----
    ("H1", 'all:"LLM agent" AND all:"workflow" AND all:"orchestration"'),
    ("H2", 'all:"LangGraph" OR all:"state machine" AND all:"LLM agent"'),
    ("H3", 'all:"tool-using" AND all:"agent" AND all:"planning" AND all:"LLM"'),
    ("H4", 'all:"agent" AND all:"MCP" AND all:"model context protocol"'),

    # ---- 方向 I: 工程文档/图纸自动化处理 ----
    ("I1", 'all:"engineering drawing" AND all:"automated" AND all:"interpretation"'),
    ("I2", 'all:"document understanding" AND all:"standard" AND all:"clause"'),
    ("I3", 'all:"requirement extraction" AND all:"regulatory document"'),
    ("I4", 'all:"norm" AND all:"clause" AND all:"NLP" AND all:"compliance"'),

    # ---- 方向 J: 电力/通信/管网工程专项 ----
    ("J1", 'all:"power transmission line" AND all:"clearance" AND all:"automated"'),
    ("J2", 'all:"telecommunication" AND all:"infrastructure" AND all:"design" AND all:"compliance"'),
    ("J3", 'all:"underground utility" AND all:"clearance" AND all:"GIS"'),
]


def fetch(query, start=0, max_results=60, retries=3):
    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "arxiv-survey-bot/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as e:
            print(f"    [retry {attempt+1}] {e}")
            time.sleep(3 + attempt * 3)
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
        arxiv_id_full = id_url.rsplit("/", 1)[-1] if id_url else ""
        # 去掉版本号
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id_full)
        authors = [a.find("atom:name", NS).text.strip()
                   for a in entry.findall("atom:author", NS)
                   if a.find("atom:name", NS) is not None and a.find("atom:name", NS).text]
        cats = [c.get("term") for c in entry.findall("atom:category", NS)]
        pdf_url = ""
        for link in entry.findall("atom:link", NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
        comment_el = entry.find("arxiv:comment", NS)
        journal_el = entry.find("arxiv:journal_ref", NS)
        out.append({
            "arxiv_id": arxiv_id,
            "title": " ".join(txt("atom:title").split()),
            "summary": " ".join(txt("atom:summary").split()),
            "authors": authors,
            "published": txt("atom:published")[:10],
            "updated": txt("atom:updated")[:10],
            "primary_category": (entry.find("arxiv:primary_category", NS).get("term")
                                 if entry.find("arxiv:primary_category", NS) is not None else ""),
            "categories": cats,
            "pdf_url": pdf_url,
            "abs_url": "https://arxiv.org/abs/" + arxiv_id,
            "comment": " ".join(comment_el.text.split()) if comment_el is not None and comment_el.text else "",
            "journal_ref": " ".join(journal_el.text.split()) if journal_el is not None and journal_el.text else "",
        })
    return out


def main():
    all_records = {}
    for tag, q in QUERIES:
        print(f"[{tag}] {q}")
        xml_bytes = fetch(q, max_results=60)
        recs = parse(xml_bytes)
        print(f"    -> {len(recs)} records")
        for r in recs:
            r.setdefault("matched_queries", [])
            if r["arxiv_id"] not in all_records:
                all_records[r["arxiv_id"]] = r
            all_records[r["arxiv_id"]]["matched_queries"].append(tag)
        time.sleep(3.2)  # arXiv API 礼貌间隔

    result = list(all_records.values())
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "arxiv_raw_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\nTOTAL UNIQUE: {len(result)}")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
