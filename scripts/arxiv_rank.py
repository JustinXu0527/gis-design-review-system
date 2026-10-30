# -*- coding: utf-8 -*-
"""
对 arxiv_raw_results.json 做相关性打分与分层筛选，输出 arxiv_ranked.json
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "arxiv_raw_results.json")
OUT = os.path.join(HERE, "arxiv_ranked.json")

with open(RAW, encoding="utf-8") as f:
    records = json.load(f)

# ---------- 强相关关键词（多词短语优先，权重高） ----------
STRONG_PHRASES = [
    # 合规审查核心
    ("automated compliance checking", 14),
    ("compliance checking", 10),
    ("code compliance", 10),
    ("building code", 8),
    ("design code", 7),
    ("regulatory compliance", 7),
    ("regulation compliance", 7),
    ("compliance verification", 7),
    ("conformance checking", 6),
    ("rule checking", 6),
    ("automated code checking", 12),
    # 工程/建筑
    ("construction", 3),
    ("BIM", 5),
    ("building information model", 5),
    ("architecture engineering", 4),
    ("engineering design", 4),
    # 规则 + LLM 混合
    ("rule-based", 4),
    ("rule engine", 7),
    ("neuro-symbolic", 6),
    ("symbolic", 3),
    ("knowledge-based", 3),
    ("deterministic", 3),
    # 检索/证据
    ("retrieval-augmented", 4),
    ("retrieval augmented", 4),
    ("RAG", 3),
    ("graphrag", 6),
    ("knowledge graph", 4),
    ("evidence", 2),
    ("citation", 2),
    ("attribution", 2),
    ("traceability", 3),
    # GIS/空间
    ("geospatial", 5),
    ("spatial data", 4),
    ("GIS", 4),
    ("geographic information", 4),
    ("topology", 3),
    ("data quality", 4),
    ("validation", 2),
    ("OGC", 5),
    ("standards compliance", 8),
    ("utility network", 5),
    ("pipeline", 3),
    ("clearance", 4),
    ("right-of-way", 5),
    # 多语言
    ("multilingual", 3),
    ("cross-lingual", 4),
    ("bge-m3", 6),
    ("embedding", 2),
    # 幻觉/可靠性
    ("hallucination", 4),
    ("factuality", 3),
    ("grounding", 3),
    ("verifier", 3),
    ("self-consistency", 2),
    ("trustworthy", 2),
    # Agent/编排
    ("agent", 2),
    ("workflow", 2),
    ("orchestration", 2),
    ("langgraph", 5),
    ("tool use", 2),
    ("multi-agent", 3),
    ("MCP", 4),
    ("model context protocol", 5),
    # 文档理解
    ("document understanding", 4),
    ("clause", 4),
    ("norm", 2),
    ("requirement extraction", 5),
    ("specification", 3),
    # 电信/电力
    ("telecommunication", 4),
    ("power line", 3),
    ("transmission line", 4),
    # 中文标准
    ("Chinese standard", 6),
]

# ---------- 负向关键词（降权/排除） ----------
NEGATIVE = [
    ("protein", -8), ("molecule", -8), ("drug", -6), ("cancer", -10),
    ("medical", -5), ("clinical", -6), ("patient", -8), ("gene", -8),
    ("quantum", -6), ("galaxy", -10), ("astrophys", -10), ("cosmolog", -10),
    ("speech recognition", -4), ("image generation", -5), ("diffusion model", -5),
    ("recommendation system", -3), ("sentiment analysis", -4),
    ("game", -3), ("robot grasping", -5), ("autonomous driving", -4),
    ("language model pretraining", -3), ("benchmark suite", -2),
]


def score(rec):
    text = (rec["title"] + " " + rec["summary"]).lower()
    title = rec["title"].lower()
    s = 0
    hits = []
    for phrase, w in STRONG_PHRASES:
        if phrase in text:
            s += w
            hits.append(phrase)
            if phrase in title:      # 出现在标题中额外加权
                s += w * 0.6
    for phrase, w in NEGATIVE:
        if phrase in text:
            s += w
    # 被多个不同查询命中 => 跨方向匹配，加分
    s += min(len(rec.get("matched_queries", [])), 6) * 1.5
    # 时间新鲜度：近 3 年加分
    pub = rec.get("published", "")
    if pub >= "2023-01-01":
        s += 4
    elif pub >= "2021-01-01":
        s += 2
    rec["_score"] = round(s, 1)
    rec["_hits"] = hits
    return s


for r in records:
    score(r)

records.sort(key=lambda x: -x["_score"])

# ---------- 分层 ----------
tier1 = [r for r in records if r["_score"] >= 40]          # A 级：强相关，必读必引
tier2 = [r for r in records if 28 <= r["_score"] < 40]     # B 级：相关，重点参考
tier3 = [r for r in records if 20 <= r["_score"] < 28]     # C 级：方法论可借鉴
tier4 = [r for r in records if 12 <= r["_score"] < 20]     # D 级：背景
tier5 = [r for r in records if r["_score"] < 12]           # 其余

print(f"TierA (>=40) : {len(tier1)}")
print(f"TierB (28-39): {len(tier2)}")
print(f"TierC (20-27): {len(tier3)}")
print(f"TierD (12-19): {len(tier4)}")
print(f"TierE (<12)  : {len(tier5)}")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump({"tier1": tier1, "tier2": tier2, "tier3": tier3, "tier4": tier4},
              f, ensure_ascii=False, indent=2)

print("\n===== TOP 60 =====")
for i, r in enumerate(records[:60], 1):
    print(f"{i:3d}. [{r['_score']:5.1f}] {r['arxiv_id']:12s} {r['published']} {r['title'][:95]}")
