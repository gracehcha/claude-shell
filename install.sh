#!/bin/zsh
# Claude Shell — one-command installer
# Usage: /bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/gracehcha/claude-shell/main/install.sh)"

set -e

REPO="https://github.com/gracehcha/claude-shell.git"
DEST="$HOME/claude-shell"

echo ""
echo "Claude Shell installer"
echo "----------------------"

# Check for claude CLI
if ! command -v claude &>/dev/null && [[ ! -f "$HOME/.local/bin/claude" ]]; then
  echo "ERROR: 'claude' CLI not found."
  echo "Install Claude Code first: https://claude.ai/code"
  exit 1
fi

# Clone or update
if [[ -d "$DEST/.git" ]]; then
  echo "Updating existing install at $DEST ..."
  git -C "$DEST" pull --ff-only
else
  echo "Cloning into $DEST ..."
  git clone "$REPO" "$DEST"
fi

chmod +x "$DEST/claude-code-server.py"

echo ""
echo "Done! Start the UI with:"
echo "  python3 $DEST/claude-code-server.py"
echo ""
echo "It will open automatically in your browser at http://localhost:27000"
