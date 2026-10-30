# -*- coding: utf-8 -*-
"""下载精选 Tier C 论文（对本项目具体模块有直接借鉴价值的）"""
import json
import os
import re
import time
import urllib.request
import ssl

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
OUTDIR = os.path.join(PROJECT, "docs", "papers")
os.makedirs(OUTDIR, exist_ok=True)

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "application/pdf,text/html,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",
    "Referer": "https://arxiv.org/",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# aid -> 规范文件名（不含 .pdf）
EXTRA = {
    "2603.13307": "Suppressing_Domain-Specific_Hallucination_in_Construction_LLMs",
    "2603.22528": "GraphRAG_for_Engineering_Diagrams_ChatPID",
    "2603.26845": "GISclaw_Open-Source_LLM_Agent_for_Geospatial_Analysis",
    "2605.00827": "Separating_Intelligence_from_Execution_MCP_Workflow_Engine",
    "2607.19297": "Graph-Based_Agentic_AI_with_LangGraph",
    "2510.06002": "Deterministic_Legal_Agents_Auditable_Reasoning",
    "2608.00705": "Triple-Robustness_of_RAG_for_Requirements_Traceability",
    "2604.28087": "Neuro-symbolic_Causal_Rule_Synthesis_Verification_Legal",
    "2507.03226": "Towards_Practical_GraphRAG_Efficient_KG_Hybrid_Retrieval",
    "2606.27281": "Resource-Aware_Neuro-Symbolic_Reasoning_Local_SLMs",
    "2608.26836": "SymbolLKG_Verifiable_Logical_Reasoning_Knowledge_Graph",
    "2508.20453": "MCP-Bench_Benchmarking_Tool-Using_LLM_Agents",
    "2603.14828": "Toward_Robust_GraphRAG_Mitigating_Retrieval_Drift_Hallucination",
    "2609.01617": "Hybrid_RAG_with_Knowledge_Graph_Expansion_RRF_Fusion",
    "2605.29313": "PatchBoard_Schema-Grounded_State_Mutation_Auditable_Multi-Agent",
    "2606.01613": "TechRAG_Evidence-Gated_Multimodal_Agentic_RAG",
    "2601.07192": "Relink_Query-Driven_Evidence_Graph_for_GraphRAG",
    "2609.19961": "Neuro-Symbolic_Agentic_AI_for_Networked_Low-Altitude_UAVs",
    "2605.26575": "Hubness_Cross-Lingual_Retrieval_Asymmetry_Multilingual_Embedding",
    "2506.02404": "GraphRAG-Bench_Domain-Specific_Reasoning_Evaluation",
    "2604.06279": "Plasma_GraphRAG_Physics-Grounded_Parameter_Selection",
    "2603.01022": "GeoMCP_Trustworthy_Framework_AI-Assisted_Geotechnical_Engineering",
    "2510.11004": "Automating_Structural_Engineering_Workflows_with_LLM_Agents",
    "2205.08572": "BIM_Using_Constraint_Logic_Programming",
    "2403.04795": "LLMs_in_Fire_Engineering_Technical_Questions_Domain_Knowledge",
}


def dl(aid, name, retries=2):
    fn = f"{aid}_{name}.pdf"
    path = os.path.join(OUTDIR, fn)
    if os.path.exists(path) and os.path.getsize(path) > 10000:
        return "cached", fn, os.path.getsize(path)
    for url in (f"https://arxiv.org/pdf/{aid}", f"https://export.arxiv.org/pdf/{aid}"):
        for a in range(retries):
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
                    buf = []
                    while True:
                        c = r.read(262144)
                        if not c:
                            break
                        buf.append(c)
                    data = b"".join(buf)
                if len(data) < 10000 or not data.startswith(b"%PDF"):
                    raise ValueError(f"bad {len(data)}")
                with open(path, "wb") as f:
                    f.write(data)
                return "ok", fn, len(data)
            except Exception as e:
                print(f"      retry{a+1} {url[-30:]}: {str(e)[:70]}")
                time.sleep(3)
    return "failed", "", 0


stats = {}
for i, (aid, name) in enumerate(EXTRA.items(), 1):
    print(f"[{i}/{len(EXTRA)}] {aid} {name}")
    st, fn, size = dl(aid, name)
    print(f"    -> {st} {size}")
    stats[aid] = {"status": st, "file": fn, "size": size, "short": name}
    time.sleep(1.2)

out = os.path.join(HERE, "arxiv_extra_status.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(stats, f, ensure_ascii=False, indent=2)

ok = sum(1 for v in stats.values() if v["status"] in ("ok", "cached"))
print(f"\nextra downloaded: {ok}/{len(EXTRA)}")
