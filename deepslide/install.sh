#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

run_audit_fix() {
  if [ -f package-lock.json ]; then
    npm audit fix --ignore-scripts || true
  fi
}

# Install backend dependencies
echo "Installing backend dependencies..."
cd backend
pip install -r requirements.txt
cd ..

# Install frontend dependencies
echo "Installing frontend dependencies..."
cd frontend
npm install
run_audit_fix
cd ..

echo "Installing next-ai-draw-io dependencies..."
cd ../next-ai-draw-io
npm install --ignore-scripts
run_audit_fix
cd ../deepslide

echo "All dependencies installed."
