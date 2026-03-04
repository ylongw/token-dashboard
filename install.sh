#!/bin/bash
# install.sh — Token Dashboard one-command setup
# Usage: bash install.sh [--port 8901] [--runtime-dir ~/.token-dashboard]

set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${RUNTIME_DIR:-$HOME/.token-dashboard}"
PORT="${PORT:-8901}"

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --port) PORT="$2"; shift 2 ;;
    --runtime-dir) RUNTIME_DIR="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

echo "=== Token Dashboard Install ==="
echo "  Repo:    $REPO_DIR"
echo "  Runtime: $RUNTIME_DIR"
echo "  Port:    $PORT"
echo ""

# 1. Create runtime dirs
mkdir -p "$RUNTIME_DIR"/{data,logs,public,scripts}

# 2. Write server.py with correct BASE_DIR
sed "s|BASE_DIR = .*|BASE_DIR = \"$RUNTIME_DIR\"|" \
    "$REPO_DIR/server.py" > "$RUNTIME_DIR/server.py"

# 3. Copy frontend + aggregation script
cp "$REPO_DIR/public/index.html" "$RUNTIME_DIR/public/"
cp "$REPO_DIR/scripts/aggregate.py" "$RUNTIME_DIR/scripts/"

echo "✓ Runtime files written to $RUNTIME_DIR"

# 4. Run first aggregation
echo "→ Running initial aggregation..."
python3 "$RUNTIME_DIR/scripts/aggregate.py" && echo "✓ Aggregation complete"

# 5. Install LaunchAgents (macOS only)
if [[ "$OSTYPE" == "darwin"* ]]; then
  PLIST_DIR="$HOME/Library/LaunchAgents"
  mkdir -p "$PLIST_DIR"

  for template in "$REPO_DIR"/com.token-dashboard.*.plist; do
    label=$(basename "$template" .plist)
    dest="$PLIST_DIR/$label.plist"

    sed \
      -e "s|\${HOME}|$HOME|g" \
      -e "s|$HOME/Documents/dec/token-dashboard|$REPO_DIR|g" \
      -e "s|$REPO_DIR/server.py|$RUNTIME_DIR/server.py|g" \
      -e "s|$REPO_DIR/scripts/aggregate.py|$RUNTIME_DIR/scripts/aggregate.py|g" \
      -e "s|<string>8901</string>|<string>$PORT</string>|g" \
      -e "s|\(logs/[a-z.]*\)|\1|g" \
      "$template" | \
    sed \
      -e "s|WorkingDirectory.*|WorkingDirectory|g" \
      > /tmp/plist_tmp.plist

    # Fix WorkingDirectory and log paths
    python3 - << PYEOF
import re
with open('/tmp/plist_tmp.plist') as f:
    content = f.read()
# Fix logs paths to point to runtime
content = content.replace('$REPO_DIR/logs/', '$RUNTIME_DIR/logs/')
# Skip cloudflared plist path fix (it uses ~/.cloudflared)
with open('$dest', 'w') as f:
    f.write(content)
PYEOF

    # Unload if already loaded, then load
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$dest"
    echo "✓ LaunchAgent loaded: $label"
  done

  echo ""
  echo "=== Done! ==="
  echo "  Local:  http://localhost:$PORT"
  echo ""
  echo "  For external access, set up Cloudflare Tunnel:"
  echo "    cloudflared tunnel create token-dashboard"
  echo "    # edit ~/.cloudflared/token-dashboard.yml"
  echo "    launchctl bootstrap gui/\$(id -u) $PLIST_DIR/com.token-dashboard.cloudflared.plist"
else
  echo ""
  echo "=== Done! (non-macOS: start manually) ==="
  echo "  python3 $RUNTIME_DIR/server.py &"
  echo "  # Add a cron job for aggregation:"
  echo "  # 0 * * * * python3 $RUNTIME_DIR/scripts/aggregate.py"
  echo ""
  echo "  Dashboard: http://localhost:$PORT"
fi
