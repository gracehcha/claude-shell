#!/bin/zsh
# Claude Code UI — local bridge server
# Listens on port 27000, opens Terminal + runs claude when the UI sends a prompt.
# Run this once: bash ~/Desktop/claude-code-server.sh

export PATH="$HOME/.local/bin:$PATH"

echo "Claude Code bridge running on http://localhost:27000"
echo "Open claude-code-ui.html in your browser, then submit a prompt."
echo "Press Ctrl+C to stop."

while true; do
  # Read one HTTP request
  REQUEST=$(echo "" | nc -l 27000 2>/dev/null & NC_PID=$!
    sleep 0.5
    # Read request body via /dev/stdin trick - use python for reliable JSON parsing
    wait $NC_PID 2>/dev/null
  )

  # Use python3 as the actual server — more reliable than nc for HTTP
  python3 - <<'PYEOF'
import http.server, json, subprocess, urllib.parse, os

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # silence access log

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            prompt = data.get('prompt', '')
        except Exception:
            prompt = ''

        if prompt:
            safe = prompt.replace("'", "'\\''")
            cmd = f"export PATH=\"$HOME/.local/bin:$PATH\" && claude '{safe}'"
            apple = f'tell application "Terminal" to do script "{cmd.replace(chr(34), chr(92)+chr(34))}"'
            subprocess.Popen(['osascript', '-e', apple])

        self.send_response(200)
        self._cors()
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')

httpd = http.server.HTTPServer(('localhost', 27000), Handler)
print("Bridge ready.", flush=True)
httpd.serve_forever()
PYEOF
  break
done
