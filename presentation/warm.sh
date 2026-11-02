#!/usr/bin/env bash
# Warm the prsnoop cache so every demo command answers instantly.
# Run this ~1 minute before you present.
#
# A cold fetch is slow because the GitHub API itself is slow: one round trip
# per pull request to pull diff stats, roughly 0.4s each, so a user with 80
# PRs costs about 20s no matter what we do. This script pays that once.
#
# The default cache TTL is 900s (15 minutes), which is not long enough to
# cover a review slot. PRSNOOP_CACHE_TTL below stretches it to four hours so
# the cache survives the whole session.
set -u

export PRSNOOP_CACHE_TTL="${PRSNOOP_CACHE_TTL:-14400}"

REPO="/Users/mohammedanasnathani/Downloads/Sem 7 (Worktree)/04_OSS_Lab/our_project/prsnoop"
export PATH="$HOME/.local/bin:$HOME/.venvs/prsnoop/bin:/opt/homebrew/bin:$PATH"
cd "$REPO" 2>/dev/null || true

if [ -z "${PRSNOOP_TOKEN:-}" ]; then
  PRSNOOP_TOKEN="$(gh auth token 2>/dev/null || true)"
  export PRSNOOP_TOKEN
fi

G=$'\033[38;5;47m'; D=$'\033[2;37m'; W=$'\033[1;97m'; R=$'\033[0m'

if [ -z "${PRSNOOP_TOKEN:-}" ]; then
  printf "%stoken not found. run: gh auth login%s\n" "$D" "$R"
fi

printf "%sWARMING THE CACHE%s  %s(first fetch takes about 20s, then it stays instant for the session)%s\n\n" "$W" "$R" "$D" "$R"

CMDS=(
  "prsnoop simonw --days 30"
  "prsnoop me --days 30"
  "prsnoop repo MohammedAnasNathani/prsnoop --days 90"
  "prsnoop compare antfu simonw --days 30"
  "prsnoop team antfu simonw --last month"
  "prsnoop radar simonw/datasette"
  "prsnoop changelog simonw/datasette"
)

start=$(date +%s)
for c in "${CMDS[@]}"; do
  printf "  %-52s" "$c"
  if $c >/dev/null 2>&1; then
    printf "%sready%s\n" "$G" "$R"
  else
    printf "%sfailed (skipping)%s\n" "$D" "$R"
  fi
done
end=$(date +%s)
printf "\n%sdone in %ss. now run the demo, every command answers from cache.%s\n" "$G" "$((end - start))" "$R"
printf "%scache held for 4h. for a single command keep it alive with: PRSNOOP_CACHE_TTL=14400 prsnoop ...%s\n" "$D" "$R"
