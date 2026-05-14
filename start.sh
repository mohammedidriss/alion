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

# Backend (FastAPI) — launched in a Terminal.app tab so the process
# inherits Terminal's macOS camera TCC grant. Without this, the
# background-forked process loses the "responsible application"
# link and cv2.VideoCapture() gets denied.
osascript -e "
tell application \"Terminal\"
    do script \"cd $DIR && source .venv/bin/activate && exec uvicorn api.main:app --reload --port 8000 --log-level info\"
end tell
" >/dev/null 2>&1

# Give the backend a moment to bind the port
sleep 2

# Frontend (Next.js) — logs go to file to avoid polling noise
cd "$DIR/apps/dashboard"
npm run dev > "$DIR/.frontend.log" 2>&1 &
FRONTEND_PID=$!

# Save PIDs (backend PID found dynamically via lsof)
BACKEND_PID=$(lsof -ti :8000 2>/dev/null | head -1)
echo "$BACKEND_PID" > "$PIDFILE"
echo "$FRONTEND_PID" >> "$PIDFILE"

disown "$FRONTEND_PID"

echo ""
echo "Alion is running:"
echo "  Backend:  http://localhost:8000  (PID ${BACKEND_PID:-pending})"
echo "  Frontend: http://localhost:3000  (PID $FRONTEND_PID)"
echo ""
echo "Logs:  Backend logs in the Terminal tab; frontend: tail -f .frontend.log"
echo "Stop:  ./stop.sh"
