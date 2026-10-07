#!/usr/bin/env bash
# Installs the Python packages the scripts need.
set -e
PKGS="duckdb pandas numpy openpyxl tabulate python-pptx"
python3 -m pip install --quiet --user $PKGS 2>/dev/null \
  || python3 -m pip install --quiet --break-system-packages $PKGS
python3 -c "import duckdb, pandas, tabulate, openpyxl, pptx; print('ready')"
