# -*- coding: utf-8 -*-
"""把 papers/ 下的 PDF 重命名为规范的 arxivID_ShortTitle.pdf"""
import json
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
PAPERS = os.path.join(PROJECT, "docs", "papers")
RANKED = os.path.join(HERE, "arxiv_ranked.json")
STATUS = os.path.join(HERE, "arxiv_download_status.json")

# 手工指定的简短英文名（更可读、便于引用）
SHORT = {
    "2608.02472": "CTRAG_In-Context_RAG_for_Automated_Compliance_Checking",
    "2506.20551": "LLM_Driven_Code_Compliance_Checking_in_BIM",
    "2504.05951": "Representing_Normative_Regulations_in_OWL_DL_for_ACC",
    "2305.10113": "Neuro-Symbolic_AI_for_Compliance_Checking_of_Electrical_Panels",
    "2512.20275": "G-SPEC_Graph-Symbolic_Policy_Enforcement_5G_Networks",
    "2607.00015": "Automated_AI_Framework_for_Floor_Plan_Compliance_Checks",
    "1910.00334": "French_Smart_Building_Code_Semantic_Rules",
    "2607.15647": "Neuro-Symbolic_AI_for_LEED_Compliance_Deterministic_Numeric",
    "2609.04216": "Engineering_as_Code_Software_Engineering_Methodology",
    "2606.12065": "Automating_Geometry-Intensive_Compliance_Checking_in_BIM",
    "2609.01618": "Multi-Agent_RAG_for_Telecom_Cloud_Knowledge_Base",
    "2606.08728": "AI_for_Mathematical_Reasoning_Survey_Neuro-symbolic",
    "2604.23563": "CyberCane_Neuro-Symbolic_RAG_Formal_Ontology",
    "2602.16650": "RAG_of_Polymer_Knowledge_Expert_System",
    "2605.20815": "GraphRAG_on_Consumer_Hardware_Local_LLMs",
    "2407.21060": "LLMs_for_the_Interpretation_of_Building_Regulations",
    "2603.04663": "Neuro-Symbolic_Financial_Reasoning_Deterministic_Fact_Ledgers",
    "2603.19276": "GraphRAG_for_Automated_Short_Answer_Grading",
    "2607.19740": "Neuro-Symbolic_AI_for_Korean_Criminal_Law",
    "2507.13625": "BifrostRAG_Dual_Knowledge_Graphs_Construction_Safety",
    "2608.00937": "Neuro-Symbolic_Participation_Governance_Verifiable_Agents",
    "2605.28120": "LegalGraphRAG_Multi-Agent_GraphRAG_Legal_Reasoning",
    "2511.18701": "ObjectAlign_Neuro-Symbolic_Object_Consistency_Verification",
    "2605.02472": "Neuro-Symbolic_Offloading_Structural_Auditability_Legal",
    "2505.19804": "Compliance-to-Code_Financial_Compliance_via_Code_Generation",
    "2609.05139": "NS-ST-GraphRAG_Spatio-Temporal_GraphRAG",
    "2501.14735": "ARCEAK_Automated_Rule_Checking_with_Architectural_Knowledge",
    "2511.08274": "Multi-Agent_GraphRAG_Text-to-Cypher_Labeled_Property_Graphs",
    "2603.03686": "AI4S-SDS_Neuro-Symbolic_Solvent_Design_System",
    "2609.09503": "Agentic_AI_Semantic_Commissioning_Digital_Twin",
    "2606.30093": "TIGRAG_Token_Co-occurrence_Graph_RAG",
    "2507.03608": "Benchmarking_Vector_Graph_Hybrid_RAG_for_ORAN",
    "2606.28390": "Topo4Vec_Quality_Assessment_of_Geospatial_Vector_Data",
    "2605.15109": "Traversal_Context_and_Provenance_in_Agentic_GraphRAG",
}

with open(STATUS, encoding="utf-8") as f:
    status = json.load(f)

files = os.listdir(PAPERS)
mapping = {}
for aid, info in status.items():
    if info["status"] not in ("ok", "cached"):
        continue
    old = info.get("file", "")
    if old not in files:
        # 尝试按 ID 前缀匹配
        cand = [f for f in files if f.startswith(aid)]
        if not cand:
            print(f"!! not found for {aid}")
            continue
        old = cand[0]
    short = SHORT.get(aid, re.sub(r"[^\w\-]", "", info["title"])[:60])
    new = f"{aid}_{short}.pdf"
    if old != new:
        try:
            os.rename(os.path.join(PAPERS, old), os.path.join(PAPERS, new))
            print(f"rename: {old}  ->  {new}")
        except Exception as e:
            print(f"!! rename fail {old}: {e}")
            new = old
    status[aid]["file"] = new
    mapping[aid] = new

with open(STATUS, "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)
print(f"\nrenamed {len(mapping)}")
