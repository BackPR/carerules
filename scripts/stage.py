"""Assemble what gets published into build/: build/space (the Hugging Face Space) and build/dataset (the
dataset repo). Nothing is uploaded here; uploading is a separate, deliberate step.
Usage: python3 -I scripts/stage.py"""
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from carerules.items import all_items  # noqa: E402
from carerules.corpus import build_index, match  # noqa: E402
from carerules.document import read  # noqa: E402
from carerules.view import NAMES  # noqa: E402

BUILD = ROOT / "build"
DATA, CODE = BUILD / "dataset", BUILD / "github"
shutil.rmtree(BUILD, ignore_errors=True)
summary = ROOT / "results" / "RESULTS.md"
results_md = summary.read_text() if summary.exists() else "Results are being computed."
short = ROOT / "results" / "RESULTS-short.md"
results_short = short.read_text() if short.exists() else results_md
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def copy(src: str, dst: Path) -> None:
    s = ROOT / src
    if s.is_dir():
        shutil.copytree(s, dst, ignore=IGNORE, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(s, dst)


# Site: the static page served by the free Hugging Face Space and by care.backpr.com (same files).
SITE = BUILD / "site"
for d in ("text", "data/checklists", "samples/eval-results"):
    copy(d, SITE / d)
for f in ("static/style.css", "static/engine.js", "static/app.js", "data/sources.json",
          "samples/little-acorns-handbook.pdf", "samples/little-acorns.audit-high.json",
          "samples/little-acorns-pages.json"):
    copy(f, SITE / f)
copy("static/media", SITE / "static/media")
copy("static/fonts", SITE / "static/fonts")
copy("static/favicon.ico", SITE / "favicon.ico")
copy("static/index.html", SITE / "index.html")


def faq_jsonld(page: str) -> str:
    """Rebuild the FAQPage structured data from the visible Questions section, so the two never drift apart."""
    qa = re.findall(r'<details(?: id="states")?><summary>(.*?)</summary><p>(.*?)</p></details>', page[page.index('<div class="qa">'):], re.S)
    strip = lambda x: html.unescape(re.sub(r"<[^>]+>", "", x)).strip()  # noqa: E731
    faq = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": strip(q), "acceptedAnswer": {"@type": "Answer", "text": strip(a)}}
                                              for q, a in qa]}
    start = page.index('{"@type":"FAQPage"')
    end = page.index("]}]}</script>", start) + len("]}")
    return page[:start] + json.dumps(faq, ensure_ascii=False, separators=(",", ":")) + page[end:]


def bust(page: str) -> str:
    """Stamp each script and stylesheet link with its content hash, so a new deploy never runs against cached old files."""
    for f in ("static/style.css", "static/engine.js", "static/app.js"):
        page = page.replace(f'"{f}"', f'"{f}?v={hashlib.sha256((ROOT / f).read_bytes()).hexdigest()[:10]}"')
    return page


(SITE / "index.html").write_text(bust(faq_jsonld((SITE / "index.html").read_text())))
(SITE / "robots.txt").write_text("User-agent: *\nAllow: /\nDisallow: /code\nDisallow: /beam\nSitemap: https://care.backpr.com/sitemap.xml\n")
(SITE / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                  "<url><loc>https://care.backpr.com/</loc></url>\n</urlset>\n")
# Served by care.backpr.com (Cloudflare reads _headers); the Hugging Face Space ignores it. Scripts may come only from
# /static/ and the two pinned libraries, so nothing injected into the page at the edge can read a handbook.
(SITE / "_headers").write_text("""/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Content-Security-Policy: default-src 'self'; script-src https://care.backpr.com/static/ https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/ https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.8.0/; worker-src blob: https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self' https://cdnjs.cloudflare.com; frame-ancestors 'self' https://huggingface.co; base-uri 'self'; form-action 'none'
""")
examples = []
for p in sorted((ROOT / "samples/eval-results").glob("[A-Z][A-Z].json")):
    st = p.stem
    title = (ROOT / "samples/eval" / st / "clean.md").read_text().splitlines()[0].lstrip("# ").strip()
    pages = read(ROOT / "samples/eval" / st / "defective.md")
    examples.append({"code": st, "name": NAMES.get(st, st), "title": title, "pages": len(pages)})
    copy(f"samples/eval/{st}/clean.md", SITE / f"samples/eval/{st}/clean.md")  # the "plant your own mistake" handbooks
    # The answer key shown under each example report: what was planted, and whether the check found it.
    defects = json.loads((ROOT / "samples/eval" / st / "defects.json").read_text())
    found = json.loads(p.read_text())["findings"]
    index, by_id = build_index(pages), {f["id"]: f for f in found}
    spans = [f["span"] for f in found if f["status"] == "conflict" and f.get("span")]
    key = {"conflicts": [], "removals": []}
    for c in defects["conflicts"]:
        m = match(index, c["planted"])
        key["conflicts"].append({"planted": c["planted"], "why": c["why"],
                                 "found": bool(m) and any(a < m[2] and m[1] < b for a, b in spans)})
    for r in defects["removals"]:
        f = by_id.get(r["item_id"], {})
        key["removals"].append({"requirement": f.get("requirement", r["item_id"]), "status": f.get("status")})
    (SITE / f"samples/eval-results/{st}.key.json").write_text(json.dumps(key, indent=1))
(SITE / "samples/eval-results/index.json").write_text(json.dumps(examples, indent=1))
SPACE = BUILD / "space"
shutil.copytree(SITE, SPACE)
# The hero video (Mixkit) is licensed for use on the website, not for redistribution: it goes to care.backpr.com only,
# never into the Space or a public repo (site-only/ is git-ignored).
if (ROOT / "site-only/media").exists():
    copy("site-only/media", SITE / "static/media")
# A judges' link with an access code would live outside the repo; by default the card points at the no-code live check.
judges = Path.home() / ".config/carerules/judges-link"
judges_link = judges.read_text().strip() if judges.exists() else "https://care.backpr.com/#test-handbook"
for f in ("LICENSE", "CREDITS.md"):
    copy(f, SPACE / f)
copy("CREDITS.md", DATA / "CREDITS.md")
(SPACE / "README.md").write_text((ROOT / "docs/space-card.md").read_text().replace("{{RESULTS}}", results_short)
                                 .replace("{{JUDGES_LINK}}", judges_link))

# Dataset: rules, checklists, the planted-defect handbooks, every run, and the question benchmark.
(DATA / "data").mkdir(parents=True)
with (DATA / "data/items.jsonl").open("w") as f:
    for it in all_items():
        f.write(json.dumps(it, ensure_ascii=False) + "\n")
copy("text", DATA / "rulebooks")
copy("data/sources.json", DATA / "rulebooks/sources.json")
copy("data/checklists", DATA / "checklists")
copy("samples/eval", DATA / "handbook_eval")
copy("results/inspector", DATA / "results/inspector")
for p in (ROOT / "results").glob("*-low.jsonl"):
    copy(str(p.relative_to(ROOT)), DATA / "results" / p.name)
copy("results/RESULTS.md", DATA / "results/RESULTS.md")
copy("results/real-handbook.json", DATA / "results/real-handbook.json")
copy("samples/little-acorns-handbook.pdf", DATA / "samples/little-acorns-handbook.pdf")
copy("samples/little-acorns.audit-high.json", DATA / "samples/little-acorns.audit-high.json")
(DATA / "README.md").write_text((ROOT / "docs/dataset-card.md").read_text().replace("{{RESULTS}}", results_md))

# GitHub: the README with results (the repo itself is the project folder).
CODE.mkdir(parents=True)
(CODE / "README.md").write_text((ROOT / "docs/github-readme.md").read_text().replace("{{RESULTS}}", results_md))
shutil.copy(CODE / "README.md", ROOT / "README.md")  # the repo's own README is the published one

for d in (SITE, DATA, CODE):
    files = [p for p in d.rglob("*") if p.is_file()]
    print(f"{d.relative_to(ROOT)}: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB")
