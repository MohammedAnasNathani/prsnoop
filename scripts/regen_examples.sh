#!/usr/bin/env bash

# Exit immediately if a command exits with a non-zero status
set -e

TARGET_USER="simonw"
EXAMPLES_DIR="examples"

echo "Regenerating example reports for GitHub user: ${TARGET_USER}..."

# Ensure examples directory exists
mkdir -p "${EXAMPLES_DIR}"

# 1. Regenerate Markdown Report
python -m prsnoop "${TARGET_USER}" --no-reviews -f markdown -o "${EXAMPLES_DIR}/simonw_30d.md"

# 2. Regenerate HTML Report
python -m prsnoop "${TARGET_USER}" --no-reviews -f html -o "${EXAMPLES_DIR}/simonw_30d.html"

# 3. Regenerate CSV Report
python -m prsnoop "${TARGET_USER}" --no-reviews -f csv -o "${EXAMPLES_DIR}/simonw_30d.csv"

# 4. Regenerate JSON Report
python -m prsnoop "${TARGET_USER}" --no-reviews -f json -o "${EXAMPLES_DIR}/simonw_30d.json"

# 5. Regenerate Badges
python -m prsnoop "${TARGET_USER}" --no-reviews -f badge -o "${EXAMPLES_DIR}/antfu_badges.md"

echo "All example reports in /${EXAMPLES_DIR} regenerated successfully!"