#!/usr/bin/env bash
# Verify all runtime dependencies for the podcast cutter skills.
# Exits 0 if everything is present; nonzero otherwise.

set -uo pipefail

ok=0
fail=0
warn() { printf '  [missing] %s — install with: %s\n' "$1" "$2"; fail=$((fail + 1)); }
good() { printf '  [ok]      %s\n' "$1"; ok=$((ok + 1)); }

printf 'Checking dependencies...\n'

if command -v node >/dev/null 2>&1; then
  ver=$(node -v)
  good "node $ver"
else
  warn "node not found" "brew install node  (or: nvm install --lts)"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ver=$(ffmpeg -version 2>/dev/null | head -1)
  good "$ver"
else
  warn "ffmpeg not found" "brew install ffmpeg  (or: apt install ffmpeg)"
fi

if command -v python3 >/dev/null 2>&1; then
  ver=$(python3 --version)
  good "$ver"
else
  warn "python3 not found" "brew install python3  (or: apt install python3)"
fi

if command -v ffprobe >/dev/null 2>&1; then
  good "ffprobe (bundled with ffmpeg)"
else
  warn "ffprobe not found" "brew install ffmpeg  (ffprobe ships with ffmpeg)"
fi

printf '\n%d ok, %d missing.\n' "$ok" "$fail"
exit "$fail"
