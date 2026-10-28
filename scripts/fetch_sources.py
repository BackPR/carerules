"""Download the official center-licensing rulebooks listed in data/source-candidates.json into raw/pdf/.
Only full rule texts (no FAQs, fact sheets or summaries). Files are untrusted input: saved as-is, never executed."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(sys.argv[1])
PICK = {  # state -> substring of the source label that marks the full center rulebook
    "AL": "Licensing and Performance Standards for Day Care Centers",
    "AR": "Minimum Licensing Requirements for Out-of-School Time",
    "CO": "8 CCR 1402-1 full text",
    "DC": "Final Rulemaking, Licensing of Child Development Facilities",
    "HI": "HAR ch. 17-892.2",
    "IA": "441 IAC 109",
    "ME": "10-148 CMR Ch. 32",
    "MS": "Regulations Governing Licensure of Child Care Facilities",
    "MO": "5 CSR 25-500",
    "NH": "He-C 4002 NH Child Care Licensing Rule",
    "NJ": "N.J.A.C. 3A:52",
    "NM": "8.9.4 NMAC as amended",
    "NC": "Chapter 9 Child Care Rules",
    "ND": "75-03-10 (child care centers)",
    "OK": "Pub. 14-05",
    "OR": "CCLD-0084",
    "SC": "Chapter 114",
    "TN": "Rule 1240-04-01",
    "TX": "Minimum Standards for Child-Care Centers",
    "WI": None,
}
cands = json.loads((ROOT / "data/source-candidates.json").read_text())
manifest = []
for st, key in PICK.items():
    if not key:
        continue
    hits = [c for c in cands if c["state"] == st and key in c["label"]]
    if not hits:
        print("NO MATCH", st, key); continue
    c = hits[0]
    out = ROOT / "raw/pdf" / f"{st}.pdf"
    r = subprocess.run(["curl", "-sSL", "--max-time", "120", "-A", "CareRules-research/1.0 (+https://backpr.com)",
                        "-o", str(out), "-w", "%{http_code} %{content_type} %{size_download}", c["url"]],
                       capture_output=True, text=True)
    head = out.read_bytes()[:5] if out.exists() else b""
    print(st, r.stdout, "PDF" if head == b"%PDF-" else f"NOT-PDF {head!r}", r.stderr.strip()[:120])
    manifest.append({"state": st, "label": c["label"], "url": c["url"], "file": f"raw/pdf/{st}.pdf",
                     "status": r.stdout, "is_pdf": head == b"%PDF-"})
(ROOT / "data/manifest.json").write_text(json.dumps(manifest, indent=1))
