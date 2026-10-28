#!/bin/sh
# Full benchmark, cheapest first. The $13 cap in scripts/run.py stops everything if reached.
cd "$(dirname "$0")/.." || exit 1
set -x
python3 -I scripts/run.py closed --effort low --batch 30
python3 -I scripts/run.py doc --effort low --batch 30
python3 -I scripts/run.py agent --effort low
python3 -I scripts/run.py stack --effort low --batch 40
python3 -I scripts/run.py doc --effort high --batch 30
python3 -I scripts/regrade.py
python3 -I -c "import sys; sys.path.insert(0, '.'); from carerules import beam; print(f'spent \${beam.spent():.2f}')"
