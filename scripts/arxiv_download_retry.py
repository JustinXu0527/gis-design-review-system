# -*- coding: utf-8 -*-
"""
重试下载失败的论文：使用浏览器完整请求头 + 多镜像源回退
"""
import json
import os
import re
import time
import urllib.request
import ssl

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
OUTDIR = os.path.join(PROJECT, "docs", "papers")
STATUS = os.path.join(HERE, "arxiv_download_status.json")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,application/pdf,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
    "Referer": "https://arxiv.org/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Upgrade-Insecure-Requests": "1",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def safe_name(rec):
    t = re.sub(r"[^\w\s\-\u4e00-\u9fff]", "", rec["title"])
    t = re.sub(r"\s+", "_", t.strip())
    return f"{rec['arxiv_id']}_{t[:70]}"


def try_url(url, path, retries=3):
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180, context=CTX) as resp:
                chunks = []
                while True:
                    c = resp.read(1024 * 256)
                    if not c:
                        break
                    chunks.append(c)
                data = b"".join(chunks)
            if len(data) < 10000 or not data.startswith(b"%PDF"):
                raise ValueError(f"bad content: {len(data)} bytes, head={data[:8]!r}")
            with open(path, "wb") as f:
                f.write(data)
            return len(data)
        except Exception as e:
            last = str(e)
            print(f"      retry{a+1} {url[:60]}: {last[:80]}")
            time.sleep(3 + a * 4)
    return None


with open(STATUS, encoding="utf-8") as f:
    status = json.load(f)

failed = {k: v for k, v in status.items() if v["status"] == "failed"}
print(f"failed: {len(failed)}")

for i, (aid, info) in enumerate(failed.items(), 1):
    print(f"[{i}/{len(failed)}] {aid}")
    fn = f"{aid}_{re.sub(r'[^\\w\\s\\-]', '', info['title'])[:60].replace(' ', '_')}.pdf"
    path = os.path.join(OUTDIR, fn)
    candidates = [
        f"https://arxiv.org/pdf/{aid}",
        f"https://arxiv.org/pdf/{aid}v1",
        f"https://arxiv.org/pdf/{aid}v2",
        f"https://export.arxiv.org/pdf/{aid}",
        f"http://arxiv.org/pdf/{aid}",
    ]
    got = None
    for url in candidates:
        print(f"    -> {url}")
        size = try_url(url, path, retries=2)
        if size:
            got = size
            break
    if got:
        status[aid]["status"] = "ok"
        status[aid]["file"] = fn
        status[aid]["size"] = got
        print(f"    OK {got}")
    else:
        print(f"    STILL FAILED")
    time.sleep(2)

with open(STATUS, "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)

ok = sum(1 for v in status.values() if v["status"] in ("ok", "cached"))
print(f"\nTotal downloaded: {ok}/{len(status)}")
