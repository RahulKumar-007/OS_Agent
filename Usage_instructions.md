# 🚀 AEGIS Usage Instructions

## 1. Run Setup
```bash
chmod +x setup.sh && ./setup.sh
```

## 2. Start Backend
```bash
source backend/venv/bin/activate
cd backend && python main.py
```
Backend runs at `http://localhost:8000`

## 3. Start Frontend
```bash
python3 -m http.server 3000 --directory frontend
```
Open `http://localhost:3000` in your web browser.

## 4. Start Your LLM
- **LM Studio**: Load a model → Start server (default port 1234)
- **Ollama**: `ollama serve` → `ollama pull gemma3:4b`

## 5. Configure Paths (Optional)
Edit `backend/config.yaml` to specify your allowed and denied file paths for the agent.

## 6. Desktop Tools (Optional)
For clipboard, screenshots, notifications, and window management support on Linux:
```bash
sudo apt install xclip scrot wmctrl xdotool libnotify-bin x11-xserver-utils
```
