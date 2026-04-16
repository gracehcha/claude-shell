# Claude Shell

A browser-based UI for Claude Code. Streams responses in real time, tracks tool use, and maintains conversation sessions — all backed by your local `claude` CLI.

## Install (one command)

```zsh
/bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/gracehcha/claude-shell/main/install.sh)"
```

This clones the repo to `~/claude-shell`. Run the same command again later to pull the latest changes.

## Requirements

- [Claude Code CLI](https://claude.ai/code) installed (`~/.local/bin/claude`)
- Python 3 (ships with macOS)
- AWS credentials configured if using Bedrock

## Start

```zsh
python3 ~/claude-shell/claude-code-server.py
```

Opens `http://localhost:27000` in your browser automatically.
