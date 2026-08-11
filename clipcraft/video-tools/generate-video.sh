#!/bin/bash
set -euo pipefail

JOB_ID="${1:?Usage: $0 <job-id>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if ! echo "$JOB_ID" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
  echo "ERROR: Invalid job ID format" >&2
  exit 1
fi

command -v ffmpeg >/dev/null 2>&1 || { echo "ERROR: ffmpeg not found" >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found" >&2; exit 1; }

exec python3 "$SCRIPT_DIR/render_video.py" "$JOB_ID"