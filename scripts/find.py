"""Helper for building the answer key. Usage:
  python3 -I scripts/find.py search <STATE> "<words>"      top pages for a query (BM25)
  python3 -I scripts/find.py page <STATE> <PAGE>            print one PDF page of the text
  python3 -I scripts/find.py quote <STATE> "<quote>"        page where a quote appears word for word, or NOT FOUND"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from carerules.corpus import Index, find_quote, pages  # noqa: E402

cmd, state = sys.argv[1], sys.argv[2]
if cmd == "search":
    for score, p in Index([state]).search(sys.argv[3], k=6):
        print(f"page {p.number}  score {score:.1f}  {' '.join(p.text.split())[:160]}")
elif cmd == "page":
    n = int(sys.argv[3])
    print(next(p.text for p in pages(state) if p.number == n))
elif cmd == "quote":
    page = find_quote(state, sys.argv[3])
    print(f"page {page}" if page else "NOT FOUND")
