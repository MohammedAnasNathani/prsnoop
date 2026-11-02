#!/usr/bin/env bash
# prsnoop showcase terminal.
# Opens an interactive shell with the token loaded and prsnoop on PATH,
# so every prsnoop command works here without any menu.
set -u

REPO="/Users/mohammedanasnathani/Downloads/Sem 7 (Worktree)/04_OSS_Lab/our_project/prsnoop"

# Make prsnoop resolvable no matter which shell spawned this.
export PATH="$HOME/.local/bin:$HOME/.venvs/prsnoop/bin:/opt/homebrew/bin:$PATH"
if ! command -v prsnoop >/dev/null 2>&1 && [ -x "$HOME/.venvs/prsnoop/bin/prsnoop" ]; then
  PATH="$HOME/.venvs/prsnoop/bin:$PATH"; export PATH
fi

cd "$REPO" 2>/dev/null || true

# Token so the API gives 5000 req/hr instead of 60, and cached runs stay instant.
if [ -z "${PRSNOOP_TOKEN:-}" ]; then
  PRSNOOP_TOKEN="$(gh auth token 2>/dev/null || true)"
  export PRSNOOP_TOKEN
fi

# Keep fetched data hot for a whole session instead of the default 15 minutes.
export PRSNOOP_CACHE_TTL="${PRSNOOP_CACHE_TTL:-14400}"

G=$'\033[38;5;47m'; D=$'\033[2;37m'; A=$'\033[38;5;214m'; W=$'\033[1;97m'; R=$'\033[0m'

clear
printf "%s" "$G"
cat <<'EOF'
   ____  ____  ___                    
  |  _ \|  _ \/ __| _ __   ___   ___  _ __
  | |_) | |_) \___ \| '_ \ / _ \ / _ \| '_ \
  |  __/|  _ < ___) | | | | (_) | (_) | |_) |
  |_|   |_| \_\____/|_| |_|\___/ \___/| .__/
                                      |_|
EOF
printf "%s" "$R"
printf "  %sSHOWCASE TERMINAL%s · prsnoop %s\n" "$W" "$R" "$(prsnoop --version 2>/dev/null | awk '{print $2}')"
printf "  %s260 tests · 0 dependencies · 30 subcommands · 7 formats%s\n\n" "$D" "$R"

if [ -n "${PRSNOOP_TOKEN:-}" ]; then
  printf "  token   %sready%s  (5000 req/hr, ETag cache on)\n" "$G" "$R"
else
  printf "  token   %snot found%s  run: gh auth login\n" "$A" "$R"
fi
printf "  folder  %s\n" "$PWD"
printf "  shell   %s\n\n" "${SHELL:-/bin/zsh}"

printf "%sSTART HERE · copy-paste any line%s\n" "$W" "$R"
printf "  %sprsnoop simonw --days 30%s        %stable report%s\n" "$G" "$R" "$D" "$R"
printf "  %sprsnoop score simonw%s            %shealth score + burnout%s\n" "$G" "$R" "$D" "$R"
printf "  %sprsnoop wrapped simonw --days 30%s %syear in review%s\n" "$G" "$R" "$D" "$R"
printf "  %sprsnoop repo MohammedAnasNathani/prsnoop --days 90%s  %sour own repo%s\n" "$G" "$R" "$D" "$R"
printf "  %sprsnoop --help%s                  %sall 30 subcommands%s\n\n" "$G" "$R" "$D" "$R"

printf "%sBEFORE YOU PRESENT%s  %s(run this once, then every command answers instantly)%s\n" "$W" "$R" "$D" "$R"
printf "  %sbash presentation/warm.sh%s   %sprefetch the cache, about 20s, then it stays warm%s\n\n" "$G" "$R" "$D" "$R"

printf "%sALSO%s\n" "$W" "$R"
printf "  %sbash presentation/demo.sh%s   the guided menu (letters p m r t need no typing)\n" "$G" "$R"
printf "  %sopen presentation/v15/index.html%s   the review deck\n\n" "$G" "$R"
printf "  %sThe first fetch of a fresh user takes about 20s (GitHub round trips). Watch the counter.%s\n" "$D" "$R"
printf "  %sYou are now in a normal shell. Every prsnoop command works.%s\n\n" "$D" "$R"

exec "${SHELL:-/bin/zsh}" -i
