#!/bin/bash
# Start backend and frontend in parallel
set -e

echo "Starting TenderMate development servers..."

# Start backend
cd "$(dirname "$0")/../backend"
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# Start frontend
cd "$(dirname "$0")/../frontend"
npm run dev &
FRONTEND_PID=$!

echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:5173"
echo "API docs: http://localhost:8000/docs"

# Wait for both
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
