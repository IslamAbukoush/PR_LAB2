"""
Multithreaded simple file server with:
 - per-request worker threads
 - optional simulated delay to emulate "work"
 - per-file request counters (naive mode or locked/safe mode)
 - per-client-IP rate limiting (requests per second)
 
Usage:
    python server.py --root public --port 5000 --simulate --max-rate 5
    python server.py --root public --unsafe    # run naive counters (no lock) to observe race
"""

import os
import socket
import urllib.parse
import argparse
import threading
import time
from collections import deque
from jinja2 import Environment, FileSystemLoader

# ---------- Arguments ----------
parser = argparse.ArgumentParser(description="Multithreaded simple file server (lab2)")
parser.add_argument("--root", default="public", help="Root directory to serve files from (default: public)")
parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default 0.0.0.0)")
parser.add_argument("--port", type=int, default=5000, help="Port to bind (default 5000)")
parser.add_argument("--simulate", action="store_true", help="Simulate ~1s work in handler (use for concurrency test)")
parser.add_argument("--unsafe", action="store_true", help="Use naive counters (no lock) to demonstrate race condition")
parser.add_argument("--max-rate", type=float, default=5.0, help="Rate limit per IP (requests per second). Default 5")
args = parser.parse_args()

ROOT_DIR = args.root
HOST = args.host
PORT = args.port
SIMULATE = args.simulate
UNSAFE_COUNTERS = args.unsafe
MAX_RATE = max(0.1, float(args.max_rate))

# ---------- Templates ----------
env = Environment(loader=FileSystemLoader("static"))
template = env.get_template("index.html")

# ---------- Icons (kept from original) ----------
ICON_MAP = {
    "folder": ("folder.png", "folder_selected.png"),
    ".pdf": ("pdf.png", "pdf_selected.png"),
    ".html": ("html.png", "html_selected.png"),
    ".png": ("png.png", "png_selected.png"),
    ".txt": ("txt.png", "txt_selected.png"),
}

def get_icon(file_path):
    if os.path.isdir(file_path):
        return ICON_MAP["folder"]
    ext = os.path.splitext(file_path)[1].lower()
    return ICON_MAP.get(ext, ("file.png", "file_selected.png"))

# ---------- Counters & Synchronization ----------
# COUNTERS maps relative-path -> int
COUNTERS = {}
counters_lock = threading.Lock()  # used when UNSAFE_COUNTERS is False

# ---------- Rate limiter ----------
# For each IP keep a deque of recent request timestamps
RATE_TABLE = {}  # ip -> deque([timestamps])
rate_lock = threading.Lock()  # protect RATE_TABLE
RATE_WINDOW = 1.0  # seconds window for rate limiting

def is_rate_limited(client_ip):
    """Return True if client_ip exceeded MAX_RATE requests per second."""
    now = time.time()
    with rate_lock:
        dq = RATE_TABLE.get(client_ip)
        if dq is None:
            dq = deque()
            RATE_TABLE[client_ip] = dq
        # prune old timestamps
        while dq and (now - dq[0]) > RATE_WINDOW:
            dq.popleft()
        # now dq contains timestamps within last RATE_WINDOW sec
        allowed = len(dq) < MAX_RATE
        if allowed:
            dq.append(now)
        return not allowed

# ---------- File listing and updating counters ----------
def list_files(path):
    """Return list of file dicts for template; each dict includes 'count' key."""
    try:
        items = os.listdir(path)
    except FileNotFoundError:
        return []
    files = []
    for item in sorted(items):
        full_path = os.path.join(path, item)
        rel_path = os.path.relpath(full_path, ROOT_DIR).replace("\\", "/")
        if rel_path == ".":
            rel_path = item
        icon, icon_selected = get_icon(full_path)
        is_dir = os.path.isdir(full_path)
        # Get current count (safe read)
        if UNSAFE_COUNTERS:
            count = COUNTERS.get(rel_path, 0)
        else:
            with counters_lock:
                count = COUNTERS.get(rel_path, 0)
        files.append({
            "name": item,
            "path": rel_path,
            "icon": icon,
            "icon_selected": icon_selected,
            "is_dir": is_dir,
            "count": count
        })
    return files

def increment_counter(rel_path):
    """Increment counter for rel_path. In UNSAFE mode this is done without lock to show race."""
    # Normalize
    rel_path = rel_path or "."
    if UNSAFE_COUNTERS:
        # naive increment (race-prone)
        old = COUNTERS.get(rel_path, 0)
        # small artificial delay to magnify race (only in unsafe mode)
        time.sleep(0.001)
        COUNTERS[rel_path] = old + 1
        print(f"[COUNTER-UNSAFE] {rel_path}: {old} -> {old+1}")
    else:
        with counters_lock:
            old = COUNTERS.get(rel_path, 0)
            COUNTERS[rel_path] = old + 1
            print(f"[COUNTER] {rel_path}: {old} -> {old+1}")

# ---------- Small helpers ----------
def read_request(conn):
    """Read incoming bytes until header end (or short timeout)."""
    conn.settimeout(1.0)
    try:
        data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\r\n\r\n" in data:
                break
        return data.decode(errors="ignore")
    except socket.timeout:
        return ""
    except Exception as e:
        print("Error reading request:", e)
        return ""

def make_response(status_code=200, content=b"", content_type="text/html; charset=utf-8"):
    status_text = {200: "200 OK", 404: "404 Not Found", 429: "429 Too Many Requests"}.get(status_code, f"{status_code}")
    headers = (
        f"HTTP/1.1 {status_text}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(content)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode()
    return headers + content

# ---------- Main request handler (per-thread) ----------
def handle_client(conn, addr):
    client_ip, client_port = addr[0], addr[1]
    try:
        request = read_request(conn)
        if not request:
            conn.close()
            return
        first_line = request.split("\r\n")[0]
        parts = first_line.split(" ")
        if len(parts) < 3:
            conn.sendall(make_response(400, b"Bad Request"))
            conn.close()
            return
        method, path, _ = parts
        path = urllib.parse.unquote(path.lstrip("/"))
        # quick rate-limit check
        if is_rate_limited(client_ip):
            print(f"[RATE_LIMIT] {client_ip} exceeded rate ({MAX_RATE}/s) - denying request for {path}")
            body = b"<html><body><h1>429 Too Many Requests</h1></body></html>"
            conn.sendall(make_response(429, body))
            conn.close()
            return

        # Optionally simulate work
        if SIMULATE:
            # 1s approximate work to test concurrency
            time.sleep(1.0)

        # check for query part
        is_download = "download=true" in path
        if "?" in path:
            path = path.split("?")[0]

        fs_path = os.path.join(ROOT_DIR, path)

        # increment counters (use rel path; for directories count the directory name)
        rel_key = path or "."
        increment_counter(rel_key)

        print(f"[REQUEST] {client_ip}:{client_port} {method} /{path}")

        # Serve static files from /static/ (as in original)
        if path.startswith("static/"):
            try:
                # serve file as binary
                with open(path, "rb") as f:
                    content = f.read()
                ext = os.path.splitext(path)[1].lower()
                content_type = "text/css" if ext == ".css" else "image/png"
                conn.sendall(make_response(200, content, content_type))
            except FileNotFoundError:
                conn.sendall(make_response(404, b"Not found"))
            finally:
                conn.close()
            return

        # Serve directories
        if os.path.isdir(fs_path):
            files = list_files(fs_path)
            body = template.render(files=files)
            conn.sendall(make_response(200, body.encode("utf-8"), "text/html; charset=utf-8"))
            conn.close()
            return

        # Serve files
        if os.path.isfile(fs_path):
            ext = os.path.splitext(fs_path)[1].lower()
            try:
                if is_download:
                    with open(fs_path, "rb") as f:
                        content = f.read()
                    filename = os.path.basename(fs_path)
                    headers = (
                        f"HTTP/1.1 200 OK\r\n"
                        "Content-Type: application/octet-stream\r\n"
                        f"Content-Disposition: attachment; filename=\"{filename}\"\r\n"
                        f"Content-Length: {len(content)}\r\n"
                        "Connection: close\r\n"
                        "\r\n"
                    ).encode()
                    conn.sendall(headers + content)
                elif ext == ".png":
                    with open(fs_path, "rb") as f:
                        content = f.read()
                    conn.sendall(make_response(200, content, "image/png"))
                elif ext == ".pdf":
                    with open(fs_path, "rb") as f:
                        content = f.read()
                    conn.sendall(make_response(200, content, "application/pdf"))
                elif ext == ".html":
                    with open(fs_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    conn.sendall(make_response(200, content.encode("utf-8"), "text/html; charset=utf-8"))
                elif ext == ".txt":
                    # minimal conversion to html pre block
                    with open(fs_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    body = f"<html><body><pre>{content}</pre></body></html>"
                    conn.sendall(make_response(200, body.encode("utf-8"), "text/html; charset=utf-8"))
                else:
                    body = "<html><body><h1>404 Not Found</h1></body></html>"
                    conn.sendall(make_response(404, body.encode("utf-8"), "text/html; charset=utf-8"))
            except Exception as e:
                print("Error serving file:", e)
                conn.sendall(make_response(500, b"Internal Server Error"))
            finally:
                conn.close()
            return

        # Fallback 404
        body = "<html><body><h1>404 Not Found</h1></body></html>"
        conn.sendall(make_response(404, body.encode("utf-8"), "text/html; charset=utf-8"))
        conn.close()
    except Exception as e:
        print("Unhandled exception in handler:", e)
        try:
            conn.close()
        except:
            pass

# ---------- Main server loop ----------
def main():
    print(f"Starting multithreaded server on http://{HOST}:{PORT}/ serving folder '{ROOT_DIR}'")
    print(f"SIMULATE={'ON' if SIMULATE else 'OFF'}  UNSAFE_COUNTERS={'ON' if UNSAFE_COUNTERS else 'OFF'}  MAX_RATE={MAX_RATE}/s")
    # ensure root exists
    if not os.path.isdir(ROOT_DIR):
        print("Root directory does not exist:", ROOT_DIR)
        return

    # create socket and listen
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(128)
        print("Server ready. Press Ctrl+C to stop.")
        try:
            while True:
                conn, addr = s.accept()
                # spawn thread per connection
                th = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
                th.start()
        except KeyboardInterrupt:
            print("Shutting down server...")

if __name__ == "__main__":
    main()
