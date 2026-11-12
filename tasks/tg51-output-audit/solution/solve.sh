#!/bin/bash
# The repaired and ported tg51calc replaces the legacy package, then produces the review.
set -euo pipefail
cp /solution/tg51calc/*.py /app/tg51calc/
cd /app
mkdir -p /app/output
python3 -m tg51calc /app/data /app/output/dose_per_mu.csv
