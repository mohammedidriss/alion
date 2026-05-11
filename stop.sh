#!/usr/bin/env bash
# Stop Alion backend + frontend.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.alion.pids"

if [ ! -f "$PIDFILE" ]; then
  echo "No running instance found."
  exit 0
fi

echo "Stopping Alion..."
while IFS= read -r pid; do
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null && echo "  Stopped PID $pid"
    # Also kill child processes (uvicorn workers, next dev)
    pkill -P "$pid" 2>/dev/null || true
  fi
done < "$PIDFILE"

rm -f "$PIDFILE"
echo "Alion stopped."
