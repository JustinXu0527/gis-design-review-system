# -*- coding: utf-8 -*-
"""
下载 Tier1 + Tier2 论文 PDF 到 docs/papers/
输出下载状态到 arxiv_download_status.json
"""
import json
import os
import re
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RANKED = os.path.join(HERE, "arxiv_ranked.json")
PROJECT = os.path.dirname(HERE)
OUTDIR = os.path.join(PROJECT, "docs", "papers")
os.makedirs(OUTDIR, exist_ok=True)


def safe_name(rec):
    t = rec["title"]
    t = re.sub(r"[^\w\s\-\u4e00-\u9fff]", "", t)
    t = re.sub(r"\s+", "_", t.strip())
    return f"{rec['arxiv_id']}_{t[:70]}"


def download(rec, retries=3):
    url = rec["pdf_url"] or f"https://arxiv.org/pdf/{rec['arxiv_id']}"
    fn = safe_name(rec) + ".pdf"
    path = os.path.join(OUTDIR, fn)
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        return {"status": "cached", "file": fn, "size": os.path.getsize(path)}
    for a in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (compatible; arxiv-fetch/1.0)"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if len(data) < 10000:
                raise ValueError(f"too small: {len(data)}")
            with open(path, "wb") as f:
                f.write(data)
            return {"status": "ok", "file": fn, "size": len(data)}
        except Exception as e:
            err = str(e)
            print(f"    [retry {a+1}] {rec['arxiv_id']}: {err[:90]}")
            time.sleep(4 + a * 4)
    return {"status": "failed", "file": "", "size": 0, "error": err}


with open(RANKED, encoding="utf-8") as f:
    tiers = json.load(f)

targets = tiers["tier1"] + tiers["tier2"]
print(f"targets: {len(targets)}")

status = {}
for i, rec in enumerate(targets, 1):
    print(f"[{i}/{len(targets)}] {rec['arxiv_id']} {rec['title'][:70]}")
    st = download(rec)
    st["title"] = rec["title"]
    st["abs_url"] = rec["abs_url"]
    st["score"] = rec["_score"]
    status[rec["arxiv_id"]] = st
    print(f"    -> {st['status']} {st.get('size',0)} bytes")
    time.sleep(1.5)

out = os.path.join(HERE, "arxiv_download_status.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)

ok = sum(1 for v in status.values() if v["status"] in ("ok", "cached"))
print(f"\nDownloaded {ok}/{len(targets)}")
print(f"Saved -> {out}")
