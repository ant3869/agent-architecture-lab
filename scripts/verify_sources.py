"""Check every entry of research/sources.toml against the network and write research/verification.json.

    python scripts/verify_sources.py

* arXiv entries: the title returned by the arXiv API must match the title in sources.toml.
* everything else: the URL must answer an HTTP GET with a 2xx/3xx status.

Network access is required. The result file is committed so readers can see when and
how each citation was last checked; this script is not part of the offline test suite.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import ssl
import subprocess
import tomllib
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (research-bot)", "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
CTX = ssl.create_default_context()


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
            return r.status, r.read(400_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, str(e)


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower().replace("$\\tau$", "tau").replace("τ", "tau")).strip()


def check_arxiv(sources: list[dict]) -> dict[str, dict]:
    ids = ",".join(s["arxiv"] for s in sources)
    status, body = fetch(f"https://export.arxiv.org/api/query?id_list={ids}&max_results={len(sources)}")
    titles = {}
    for entry in re.findall(r"(?s)<entry>(.*?)</entry>", body):
        aid = re.search(r"<id>.*?/abs/([0-9.]+)", entry).group(1)
        titles[aid] = " ".join(html.unescape(re.search(r"(?s)<title>(.*?)</title>", entry).group(1)).split())
    out = {}
    for s in sources:
        got = titles.get(s["arxiv"], "")
        out[s["key"]] = {"method": "arxiv-api", "http": status, "ok": bool(got) and norm(got) == norm(s["title"]), "title_found": got}
    return out


def raw_github(url: str) -> str | None:
    """github.com pages may refuse automated clients; the same content is served raw."""
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.+)$", url)
    if m:
        return f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/{m[3]}/{m[4]}"
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/?$", url)
    return f"https://raw.githubusercontent.com/{m[1]}/{m[2]}/HEAD/README.md" if m else None


def check_url(s: dict) -> tuple[str, dict]:
    status, _ = fetch(s["url"])
    method = "http-get"
    if not 200 <= status < 400 and raw_github(s["url"]):
        status, _ = fetch(raw_github(s["url"]))
        method = "http-get (raw.githubusercontent.com)"
    if not 200 <= status < 400 and shutil.which("curl"):  # some sites reject urllib's TLS fingerprint
        proc = subprocess.run(["curl", "-sSL", "-m", "40", "-A", UA["User-Agent"], "-o", "/dev/null", "-w", "%{http_code}", s["url"]], capture_output=True, text=True)
        if proc.stdout.strip().isdigit():
            status, method = int(proc.stdout.strip()), "curl"
    return s["key"], {"method": method, "http": status, "ok": 200 <= status < 400}


def main() -> int:
    sources = tomllib.loads((ROOT / "research" / "sources.toml").read_text())["source"]
    results = check_arxiv([s for s in sources if s.get("arxiv")])
    with ThreadPoolExecutor(8) as pool:
        results.update(dict(pool.map(check_url, [s for s in sources if not s.get("arxiv")])))
    failed = sorted(k for k, v in results.items() if not v["ok"])
    out = {"checked_on": dt.date.today().isoformat(), "total": len(results), "ok": len(results) - len(failed), "failed": failed, "results": dict(sorted(results.items()))}
    (ROOT / "research" / "verification.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"{out['ok']}/{out['total']} sources verified; failed: {failed or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
