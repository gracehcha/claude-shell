#!/usr/bin/env python3
"""
Claude Code UI — local bridge server
Pipes prompts through the real `claude` CLI and streams output back as SSE.
Run: python3 ~/Desktop/claude-code-server.py
"""

import http.server, json, os, subprocess, threading, traceback, queue

PORT  = 27000
CLAUDE = os.path.expanduser("~/.local/bin/claude")
UI_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-code-ui.html")

# session_id -> last claude --session-id so conversation continues
sessions = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"  {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(UI_FILE, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length))
        except Exception:
            self.send_response(400); self.end_headers(); return

        if self.path == "/chat":
            self._handle_chat(data)
        elif self.path == "/reset":
            sessions.pop(data.get("session", "default"), None)
            self.send_response(200); self._cors()
            self.send_header("Content-Type", "application/json")
            self.end_headers(); self.wfile.write(b'{"ok":true}')
        else:
            self.send_response(404); self.end_headers()

    def _send_sse(self, event_type, payload):
        line = f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
        try:
            self.wfile.write(line.encode())
            self.wfile.flush()
        except Exception:
            pass

    def _handle_chat(self, data):
        session_key = data.get("session", "default")
        message     = data.get("message", "").strip()
        if not message:
            self.send_response(400); self.end_headers(); return

        # SSE response headers
        self.send_response(200)
        self._cors()
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        send = self._send_sse

        # Build claude command — resume session if we have one
        cmd = [
            CLAUDE,
            "--print",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--dangerously-skip-permissions",
        ]
        prior_session = sessions.get(session_key)
        if prior_session:
            cmd += ["--resume", prior_session, "--fork-session"]
        cmd.append(message)

        # Inherit the full environment so AWS creds, BEDROCK flags, etc. are present
        env = dict(os.environ)
        # Ensure ~/.local/bin is on PATH
        env["PATH"] = os.path.expanduser("~/.local/bin") + ":" + env.get("PATH", "")

        print(f"  [server] Running: {' '.join(cmd[:6])} ...")
        print(f"  [server] CLAUDE_CODE_USE_BEDROCK={env.get('CLAUDE_CODE_USE_BEDROCK','')}")
        print(f"  [server] AWS_PROFILE={env.get('AWS_PROFILE','')}")

        # stderr queue so we can interleave it as log events
        stderr_q = queue.Queue()

        def drain_stderr(pipe):
            for line in pipe:
                stderr_q.put(line.rstrip("\n"))
            stderr_q.put(None)  # sentinel

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )

            stderr_thread = threading.Thread(target=drain_stderr, args=(proc.stderr,), daemon=True)
            stderr_thread.start()

            for raw_line in proc.stdout:
                # Flush any pending stderr as log events first
                while not stderr_q.empty():
                    sl = stderr_q.get_nowait()
                    if sl is not None and sl.strip():
                        send("log", {"text": sl})

                raw_line = raw_line.rstrip("\n")
                if not raw_line:
                    continue
                try:
                    evt = json.loads(raw_line)
                except json.JSONDecodeError:
                    send("log", {"text": raw_line})
                    continue

                t = evt.get("type", "")

                # Text tokens streaming in
                if t == "stream_event":
                    e = evt.get("event", {})
                    if e.get("type") == "content_block_delta":
                        delta = e.get("delta", {})
                        if delta.get("type") == "text_delta":
                            send("delta", {"text": delta["text"]})

                # Tool use — show the tool name + input as a status row
                elif t == "tool_use":
                    tool_name  = evt.get("name", "tool")
                    tool_input = evt.get("input", {})
                    label = _tool_label(tool_name, tool_input)
                    send("tool_start", {"label": label})

                elif t == "tool_result":
                    send("tool_done", {})

                # Save session id so next turn resumes it
                elif t == "result":
                    sid = evt.get("session_id")
                    if sid:
                        sessions[session_key] = sid
                    if evt.get("is_error"):
                        send("error", {"message": evt.get("result", "Unknown error")})
                    else:
                        send("done", {})

            proc.wait()

            # Flush remaining stderr
            stderr_thread.join(timeout=2)
            while not stderr_q.empty():
                sl = stderr_q.get_nowait()
                if sl is not None and sl.strip():
                    send("log", {"text": sl})

            rc = proc.returncode
            print(f"  [server] Process exited with code {rc}")
            if rc != 0:
                send("error", {"message": f"claude exited with code {rc} — check server terminal for details"})
            else:
                # Ensure done is sent if we never got a result event
                send("done", {})

        except FileNotFoundError:
            send("error", {"message": f"claude CLI not found at {CLAUDE} — is it installed?"})
        except Exception as e:
            traceback.print_exc()
            send("error", {"message": str(e)})


def _tool_label(name, inp):
    """Return a human-readable label for a tool call."""
    if name == "Read":
        return f"Reading {_short_path(inp.get('file_path',''))}"
    if name == "Edit":
        return f"Editing {_short_path(inp.get('file_path',''))}"
    if name == "Write":
        return f"Writing {_short_path(inp.get('file_path',''))}"
    if name == "Bash":
        cmd = inp.get("command","")
        return f"Running: {cmd[:60]}{'…' if len(cmd)>60 else ''}"
    if name == "Glob":
        return f"Searching {inp.get('pattern','')}"
    if name == "Grep":
        return f"Searching for '{inp.get('pattern','')[:40]}'"
    if name == "WebFetch":
        return f"Fetching {inp.get('url','')[:60]}"
    if name == "WebSearch":
        return f"Searching web: {inp.get('query','')[:50]}"
    if name == "Task":
        return f"Agent: {inp.get('description','task')[:60]}"
    return name


def _short_path(p):
    home = os.path.expanduser("~")
    if p.startswith(home):
        p = "~" + p[len(home):]
    parts = p.replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) > 2 else p


if __name__ == "__main__":
    server = http.server.HTTPServer(("localhost", PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"\n✦ Claude Code UI")
    print(f"  Open in browser → {url}")
    print(f"  Press Ctrl+C to stop\n")
    import subprocess as _sp
    _sp.Popen(["open", url])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
