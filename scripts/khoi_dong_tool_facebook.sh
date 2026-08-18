#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  Facebook News Auto Remix — Script khởi động
#  100% Python — không cần Node.js
# ═══════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$SCRIPT_DIR"

echo "╔═══════════════════════════════════════════════════╗"
echo "║  📰 Facebook News Auto Remix Pipeline             ║"
echo "║  100% Python | Độc lập với TikTok                  ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

# ── Dùng venv của project chính (mannyAccount) ──
if [ -f "$PARENT_DIR/.venv/bin/activate" ]; then
    source "$PARENT_DIR/.venv/bin/activate"
    echo "✅ Dùng venv: $PARENT_DIR/.venv"
elif [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
    echo "✅ Dùng venv: .venv"
fi

# ── Kiểm tra Playwright ──
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "📦 Cài Playwright..."
    pip install -q playwright
fi

echo ""
echo "🚀 Khởi động giao diện..."
echo "   (Nhấn Ctrl+C để thoát)"
echo ""

python3 "$SCRIPT_DIR/../apps/creator_facebook/fb_desktop_app.py"
