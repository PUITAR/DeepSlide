#!/bin/bash

if [ -z "$OPENAI_API_KEY" ]; then
  echo "Error: OPENAI_API_KEY is not set."
  echo "Please set the OPENAI_API_KEY environment variable using the command:"
  echo "docker run -e OPENAI_API_KEY='your-api-key'."
  exit 1
fi

if [ "$PULL" = "True" ]; then
  echo "Pulling latest changes from the repository..."
  git pull
  pip install "pptagent[full]"
  npm install --prefix /PPTAgent/pptagent_ui
fi

cd pptagent_ui
# Launch Backend Server
uv run backend.py &

# Launch Frontend Server
npm run serve
