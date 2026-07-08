#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# AEGIS — Autonomous OS Intelligence Agent
# Setup Script
# ─────────────────────────────────────────────────────────────────
set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo ""
echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}${BOLD}║   AEGIS — OS Intelligence Agent Setup    ║${NC}"
echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""

# ─── Python ────────────────────────────────────────────────────────────────

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is required. Install it first (sudo apt install python3).${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version)
echo -e "${GREEN}✅ Python: ${PYTHON_VERSION}${NC}"

# ─── Virtual Environment ───────────────────────────────────────────────────

# Remove broken venv if activate doesn't exist
if [ -d "backend/venv" ] && [ ! -f "backend/venv/bin/activate" ]; then
    echo -e "${YELLOW}🧹 Removing broken virtual environment...${NC}"
    rm -rf backend/venv
fi

if [ ! -d "backend/venv" ]; then
    echo -e "${CYAN}📦 Creating virtual environment...${NC}"
    python3 -m venv backend/venv
fi

# ─── Python Dependencies ──────────────────────────────────────────────────

echo -e "${CYAN}📦 Installing Python dependencies...${NC}"
source backend/venv/bin/activate
pip install --quiet --upgrade pip
pip install -r backend/requirements.txt
echo -e "${GREEN}✅ Python dependencies installed${NC}"

# ─── Data Directories ─────────────────────────────────────────────────────

echo -e "${CYAN}📂 Creating data directories...${NC}"
mkdir -p backend/data
mkdir -p ~/.jarvis/knowledge_base
echo -e "${GREEN}✅ Directories ready${NC}"

# ─── Optional System Dependencies ─────────────────────────────────────────

echo ""
echo -e "${BOLD}🔍 Checking optional system tools (Phase 2 Desktop features)...${NC}"

check_tool() {
    local name=$1
    local pkg=$2
    if command -v "$name" &> /dev/null; then
        echo -e "  ${GREEN}✅ ${name}${NC}"
    else
        echo -e "  ${YELLOW}⚠️  ${name} not found — install with: sudo apt install ${pkg}${NC}"
    fi
}

check_tool "xclip"       "xclip"
check_tool "scrot"       "scrot"
check_tool "wmctrl"      "wmctrl"
check_tool "xdotool"     "xdotool"
check_tool "notify-send" "libnotify-bin"
check_tool "xrandr"      "x11-xserver-utils"
check_tool "docker"      "docker.io"
check_tool "git"         "git"
check_tool "code"        "code  (install from https://code.visualstudio.com)"

echo ""
echo -e "${YELLOW}ℹ️  To install all optional desktop tools at once:${NC}"
echo -e "   ${BOLD}sudo apt install xclip scrot wmctrl xdotool libnotify-bin x11-xserver-utils${NC}"

# ─── LM Studio / Ollama hint ───────────────────────────────────────────────

echo ""
echo -e "${BOLD}🤖 LLM Backend (choose one):${NC}"
echo -e "  ${CYAN}LM Studio${NC}  → Download from https://lmstudio.ai — load a model → start server"
echo -e "  ${CYAN}Ollama${NC}     → Install from https://ollama.ai — run: ollama pull gemma3:4b"

# ─── Done ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}✅ Setup complete!${NC}"
echo ""
echo -e "${CYAN}${BOLD}─────────────────────────────────────────────────────────${NC}"
echo -e "${BOLD}  STEP 1 — Start Backend${NC}"
echo -e "    source backend/venv/bin/activate"
echo -e "    cd backend && python main.py"
echo ""
echo -e "${BOLD}  STEP 2 — Start Frontend${NC}"
echo -e "    python3 -m http.server 3000 --directory frontend"
echo -e "    Open:  http://localhost:3000"
echo ""
echo -e "${BOLD}  STEP 3 — Start Your LLM${NC}"
echo -e "    LM Studio: load model → Start Local Server (port 1234)"
echo -e "    Ollama:    ollama serve   (port 11434)"
echo ""
echo -e "${BOLD}  STEP 4 (optional) — Configure Paths${NC}"
echo -e "    Edit: backend/config.yaml"
echo -e "${CYAN}${BOLD}─────────────────────────────────────────────────────────${NC}"
echo ""
