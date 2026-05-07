#!/usr/bin/env bash
# Download bundled assets (RNNoise model, royalty-free intro/outro).
#
# Plan 1 status: STUB. The real fetch logic arrives in Plan 4 (audio_clean
# + package_final). This script's only job today is to confirm the asset
# directory layout exists and exit cleanly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
MUSIC_DIR="$ROOT/shared/assets/music"

mkdir -p "$MUSIC_DIR"
printf 'Asset directory ready: %s\n' "$MUSIC_DIR"
printf 'NOTE: bundled music + RNNoise model arrive in Plan 4 (audio cleanup + packaging).\n'
