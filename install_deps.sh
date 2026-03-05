#!/bin/bash
# Install Python deps
echo "Installing Python dependencies..."
cd deepslide-v3/backend
pip install -r requirements.txt

# Install Node deps
echo "Installing Node dependencies..."
cd ../frontend
export PATH=/home/ym/DeepSlide/node-v22.12.0-linux-x64/bin:$PATH
npm install
