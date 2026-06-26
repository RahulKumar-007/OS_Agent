#!/bin/bash
# ─────────────────────────────────────────────────
# FileAgent — Setup Script
# ─────────────────────────────────────────────────
set -e

echo "🚀 Setting up Local Filesystem Agent..."
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required. Install it first."
    exit 1
fi

echo "✅ Python: $(python3 --version)"

# Remove broken venv if activate doesn't exist
if [ -d "backend/venv" ] && [ ! -f "backend/venv/bin/activate" ]; then
    echo "🧹 Removing broken virtual environment..."
    rm -rf backend/venv
fi

# Create virtual environment
if [ ! -d "backend/venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv backend/venv
fi

# Activate and install deps
echo "📦 Installing backend dependencies..."
source backend/venv/bin/activate
pip install -r backend/requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "─────────────────────────────────────────"
echo "  To start the backend:"
echo "    source backend/venv/bin/activate"
echo "    cd backend && python main.py"
echo ""
echo "  To start the frontend:"
echo "    python3 -m http.server 3000 --directory frontend"
echo ""
echo "  Then open: http://localhost:3000"
echo "─────────────────────────────────────────"
