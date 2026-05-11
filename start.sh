#!/usr/bin/env bash
# Start Alion backend + frontend. Run from project root.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/.alion.pids"

# Kill any previous run
if [ -f "$PIDFILE" ]; then
  echo "Stopping previous instance..."
  "$DIR/stop.sh" 2>/dev/null || true
fi

echo "Starting Alion..."

# Backend (FastAPI)
cd "$DIR"
uv run uvicorn api.main:app --reload --port 8000 > "$DIR/.backend.log" 2>&1 &
BACKEND_PID=$!

# Frontend (Next.js) — logs go to file to avoid polling noise
cd "$DIR/apps/dashboard"
npm run dev > "$DIR/.frontend.log" 2>&1 &
FRONTEND_PID=$!

# Save PIDs
echo "$BACKEND_PID" > "$PIDFILE"
echo "$FRONTEND_PID" >> "$PIDFILE"

# Detach processes from this shell so they survive terminal close
disown "$BACKEND_PID"
disown "$FRONTEND_PID"

echo ""
echo "Alion is running:"
echo "  Backend:  http://localhost:8000  (PID $BACKEND_PID)"
echo "  Frontend: http://localhost:3000  (PID $FRONTEND_PID)"
echo ""
echo "Logs:  tail -f .backend.log .frontend.log"
echo "Stop:  ./stop.sh"
