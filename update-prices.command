#!/bin/sh
# Update the price data: collects listings, rebuilds the tracker, commits. See prices/update.py.
# Mac: double-click this file. Linux: ./update-prices.command   (add --auto for cron)
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then exec python3 prices/update.py "$@"; fi
echo "Python 3 is needed to update prices: https://www.python.org/downloads/"
read -r _
