# -*- coding: utf-8 -*-
"""生成 HTML 版论文清单"""
import json
import os
import html

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
RANKED = os.path.join(HERE, "arxiv_ranked.json")
STATUS = os.path.join(HERE, "arxiv_download_status.json")

with open(RANKED, encoding="utf-8") as f:
    tiers = json.load(f)
with open(STATUS, encoding="utf-8") as f:
    status = json.load(f)

# 模块归组（手工）
GROUPS = [
    ("A", "A 级 · 赛题直接对口（必读必引）", "tier1"),
    ("B1", "B 级 · 自动化合规审查与规则形式化", None),
    ("B2", "B 级 · 规则引擎 + 大模型混合架构", None),
    ("B3", "B 级 · 知识图谱证据链 / GraphRAG", None),
    ("B4", "B 级 · GIS 空间数据治理", None),
    ("B5", "B 级 · Agent 编排 / MCP / 工程文档", None),
]

ASSIGN = {
    "B1": ["2607.15647", "2606.12065", "2501.14735", "2407.21060", "1910.00334", "2505.19804"],
    "B2": ["2603.04663", "2605.02472", "2607.19740", "2608.00937", "2603.03686"],
    "B3": ["2507.13625", "2605.28120", "2511.08274", "2605.15109", "2603.19276", "2602.16650",
           "2609.05139", "2606.30093", "2605.20815", "2609.01618", "2604.23563"],
    "B4": ["2606.28390", "2603.26845", "2603.01022", "2510.05617"],
    "B5": ["2609.09503", "2609.04216", "2507.03608"],
}

EXTRA = {
    "2603.13307": "施工领域 LLM 幻觉抑制（强烈建议升为必读）",
    "2603.22528": "工程图纸 P&ID 的 LLM 交互",
    "2605.00827": "MCP 工作流引擎：智能与执行分离",
    "2607.19297": "LangGraph 工作流设计模式",
    "2510.11004": "结构工程工作流 LLM Agent",
    "2604.28087": "神经符号因果规则合成与验证",
    "2510.06002": "确定性法律 Agent 与可审计推理",
    "2608.00705": "多跳需求追溯的 RAG 鲁棒性",
    "2608.26836": "可验证逻辑推理与符号求解器",
    "2507.03226": "大规模知识图谱构建与混合检索",
    "2603.14828": "检索漂移与幻觉抑制",
    "2609.01617": "混合 RAG + 知识图谱扩展 + RRF 融合",
    "2606.27281": "本地小模型神经符号推理",
    "2508.20453": "MCP 工具调用基准测试",
    "2601.07192": "动态构建证据图",
    "2606.01613": "证据门控多模态 Agentic RAG",
    "2605.29313": "可审计多智能体协作",
    "2609.19961": "通信网络约束下的神经符号 Agent",
    "2605.26575": "跨语言检索不对称性",
    "2506.02404": "GraphRAG 领域推理评测基准",
    "2603.01022": "岩土工程 MCP 可信框架",
    "2604.06279": "物理约束 GraphRAG",
    "2403.04795": "消防工程 LLM 领域知识评测",
    "2205.08572": "约束逻辑编程做 BIM 校验",
    "2605.15109": "Agentic GraphRAG 溯源与引证忠实性",
}

AUTHOR_SHORT = {}


def row(r, tag=""):
    aid = r["arxiv_id"]
    st = status.get(aid, {})
    local = st.get("file", "")
    size = st.get("size", 0)
    size_s = f"{size/1024/1024:.1f} MB" if size else "—"
    dl = ('<span class="ok">已下载</span>' if st.get("status") in ("ok", "cached")
          else '<span class="no">未下载</span>')
    au = "; ".join(r["authors"][:2]) + (" 等" if len(r["authors"]) > 2 else "")
    hits = "、".join(r.get("_hits", [])[:8])
    note = EXTRA.get(aid, "")
    return f"""
    <tr>
      <td class="id"><a href="https://arxiv.org/abs/{aid}" target="_blank">{aid}</a></td>
      <td class="ti">{html.escape(r['title'])}
        {f'<div class="note">{html.escape(note)}</div>' if note else ''}
        <div class="hits">命中：{html.escape(hits)}</div>
      </td>
      <td class="au">{html.escape(au)}</td>
      <td class="dt">{r['published']}</td>
      <td class="sc">{r['_score']}</td>
      <td class="dl">{dl}<div class="sz">{size_s}</div></td>
    </tr>"""


sections = []

# A 级
rows_a = "".join(row(r) for r in tiers["tier1"])
sections.append(f"""
<h2 id="A">A 级 · 赛题直接对口（{len(tiers['tier1'])} 篇）</h2>
<p class="desc">这一档是本批检索中最值得投入时间精读的论文。建议至少读摘要 + 引言 + 结论。</p>
<table><thead><tr><th>arXiv ID</th><th>标题 / 相关性标注</th><th>作者</th><th>发表</th><th>得分</th><th>本地 PDF</th></tr></thead>
<tbody>{rows_a}</tbody></table>""")

names = {"B1": "自动化合规审查与规则形式化", "B2": "规则引擎 + 大模型混合架构",
         "B3": "知识图谱证据链 / GraphRAG", "B4": "GIS 空间数据治理",
         "B5": "Agent 编排 / MCP / 工程文档理解"}
for gid, ids in ASSIGN.items():
    recs = [r for r in tiers["tier1"] + tiers["tier2"] if r["arxiv_id"] in ids]
    recs.sort(key=lambda x: -x["_score"])
    rows = "".join(row(r) for r in recs)
    sections.append(f"""
<h2 id="{gid}">B 级 · {names[gid]}（{len(recs)} 篇）</h2>
<table><thead><tr><th>arXiv ID</th><th>标题 / 相关性标注</th><th>作者</th><th>发表</th><th>得分</th><th>本地 PDF</th></tr></thead>
<tbody>{rows}</tbody></table>""")

# 精选 C 级
allrecs = {r["arxiv_id"]: r for r in tiers["tier1"] + tiers["tier2"] + tiers["tier3"]}
c_ids = [k for k in EXTRA if k not in {r["arxiv_id"] for r in tiers["tier1"] + tiers["tier2"]}]
c_recs = [allrecs[k] for k in c_ids if k in allrecs]
c_recs.sort(key=lambda x: -x["_score"])
rows_c = "".join(row(r) for r in c_recs)
sections.append(f"""
<h2 id="C">C 级精选补充（{len(c_recs)} 篇，已下载）</h2>
<p class="desc">相关性略低，但对特定模块有直接借鉴价值。</p>
<table><thead><tr><th>arXiv ID</th><th>标题 / 相关性标注</th><th>作者</th><th>发表</th><th>得分</th><th>本地 PDF</th></tr></thead>
<tbody>{rows_c}</tbody></table>""")

total = len(tiers["tier1"]) + len(tiers["tier2"])
papers_dir = os.path.join(PROJECT, "docs", "papers")
extra_down = len([f for f in os.listdir(papers_dir) if f.lower().endswith(".pdf")])

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>arXiv 相关论文清单 · 规审智警</title>
<style>
  :root {{
    --bg:#f6f7f9; --card:#ffffff; --line:#e3e6ea; --tx:#1c2024; --tx2:#5a6472;
    --acc:#1f6feb; --a:#b42318; --a-bg:#fef3f2; --b:#b54708; --b-bg:#fffaeb;
    --c:#175cd3; --c-bg:#eff8ff; --ok:#067647; --ok-bg:#ecfdf3;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 20px 80px; background:var(--bg); color:var(--tx);
    font:15px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  h1 {{ font-size:27px; margin:0 0 6px; letter-spacing:-.3px; }}
  .sub {{ color:var(--tx2); font-size:13.5px; margin-bottom:26px; }}
  .stats {{ display:flex; gap:14px; flex-wrap:wrap; margin-bottom:30px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
    padding:14px 20px; min-width:132px; }}
  .stat b {{ display:block; font-size:25px; line-height:1.15; color:var(--acc); }}
  .stat span {{ font-size:12.5px; color:var(--tx2); }}
  h2 {{ font-size:18px; margin:38px 0 10px; padding-left:11px; border-left:4px solid var(--acc); }}
  .desc {{ color:var(--tx2); font-size:13.5px; margin:0 0 14px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card);
    border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:13.5px; }}
  th {{ background:#eef1f5; text-align:left; padding:9px 11px; font-size:12.5px;
    color:var(--tx2); font-weight:600; white-space:nowrap; }}
  td {{ padding:11px; border-top:1px solid var(--line); vertical-align:top; }}
  tr:hover td {{ background:#fafbfc; }}
  .id a {{ color:var(--acc); text-decoration:none; font-family:ui-monospace,Consolas,monospace;
    font-size:12.5px; white-space:nowrap; }}
  .id a:hover {{ text-decoration:underline; }}
  .ti {{ font-weight:600; max-width:520px; }}
  .note {{ font-weight:400; color:var(--a); font-size:12.5px; margin-top:4px; }}
  .hits {{ font-weight:400; color:#96a0ad; font-size:11.5px; margin-top:4px; line-height:1.5; }}
  .au {{ color:var(--tx2); font-size:12.5px; max-width:170px; }}
  .dt {{ color:var(--tx2); font-size:12.5px; white-space:nowrap; }}
  .sc {{ font-family:ui-monospace,Consolas,monospace; color:var(--tx2); text-align:right; }}
  .dl {{ white-space:nowrap; font-size:12px; }}
  .ok {{ color:var(--ok); background:var(--ok-bg); padding:2px 7px; border-radius:5px; }}
  .no {{ color:var(--a); background:var(--a-bg); padding:2px 7px; border-radius:5px; }}
  .sz {{ color:#96a0ad; font-size:11px; margin-top:3px; }}
  .box {{ background:#fffaeb; border:1px solid #fde68a; border-radius:10px;
    padding:15px 19px; margin:26px 0; font-size:13.5px; }}
  .box b {{ color:var(--b); }}
  footer {{ margin-top:44px; padding-top:18px; border-top:1px solid var(--line);
    color:var(--tx2); font-size:12.5px; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>arXiv 相关论文检索清单</h1>
  <div class="sub">项目：规审智警 · 通信基建 GIS 设计成果智能化合规审查系统 &nbsp;|&nbsp;
    子赛题 3《基于行业标准的设计智能审查》&nbsp;|&nbsp; 检索日期 2026-09-16</div>

  <div class="stats">
    <div class="stat"><b>1792</b><span>候选去重总数</span></div>
    <div class="stat"><b>78</b><span>检索关键词组合</span></div>
    <div class="stat"><b>{total}</b><span>A+B 级重点论文</span></div>
    <div class="stat"><b>{extra_down}</b><span>已下载 PDF</span></div>
  </div>

  <div class="box">
    <b>时间有限怎么用：</b>优先精读 A 级 6 篇的摘要与结论；PPT 落地只需在技术亮点页加一行小字引用，
    或新增一页"相关工作对标"。答辩弹药见 Markdown 版清单第六节。
  </div>

  {''.join(sections)}

  <footer>
    全量 1792 篇结果见 <code>scripts/arxiv_ranked.json</code>；
    已下载 PDF 位于 <code>docs/papers/</code>（共 {extra_down} 个文件，约 186 MB）。
    <br>说明：arXiv 上"管线净距 / 电力交越"类工程专项研究几乎空白（多组精确查询返回 0 条），
    该方向经典工作多见于 ASCE / Automation in Construction 等期刊，未在本次覆盖范围内。
  </footer>
</div>
</body>
</html>"""

out = os.path.join(PROJECT, "docs", "arXiv相关论文清单.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"OK -> {out}")
print(f"A+B = {total}, C-extra = {len(c_recs)}, downloaded = {extra_down}")
