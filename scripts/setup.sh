#!/usr/bin/env bash
# Installs the Python packages analyze.py needs.
set -e
python3 -m pip install --quiet --user duckdb pandas openpyxl tabulate numpy 2>/dev/null \
  || python3 -m pip install --quiet --break-system-packages duckdb pandas openpyxl tabulate numpy
python3 -c "import duckdb, pandas, tabulate; print('ready')"
