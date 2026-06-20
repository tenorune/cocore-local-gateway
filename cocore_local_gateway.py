# cocore_local_gateway.py
import glob
import json
import os
import os as _os
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _expand(path: str) -> str:
    return os.path.expanduser(path.strip())


def load_config(env_text: str) -> dict:
    raw = {}
    for line in env_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        raw[key.strip()] = val.strip()

    def split(v):
        return [x.strip() for x in v.split(",") if x.strip()] if v else []

    return {
        "port": int(raw.get("GATEWAY_PORT", "1234")),
        "interfaces": split(raw.get("BIND_INTERFACES", "")),
        "addresses": split(raw.get("BIND_ADDRESSES", "")),
        "socket_dir": _expand(raw.get("COCORE_SOCKET_DIR", "~/.cocore/sockets")),
        "log_path": _expand(raw.get("LOG_PATH", "~/.cocore/logs/local-gateway.log")),
    }


def iface_ipv4(name: str):
    try:
        out = subprocess.run(
            ["ifconfig", name], capture_output=True, text=True, timeout=5
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)", out)
    return m.group(1) if m else None


def resolve_binds(interfaces, addresses, iface_lookup=iface_ipv4):
    ips = {"127.0.0.1"}
    for a in addresses:
        ips.add(a)
    for name in interfaces:
        ip = iface_lookup(name)
        if ip:
            ips.add(ip)
    return sorted(ips)


def build_registry(socket_paths, probe, mtime=_os.path.getmtime):
    reg = {}
    for sp in socket_paths:
        try:
            models = probe(sp)
        except OSError:
            continue
        try:
            mt = mtime(sp)
        except OSError:
            mt = 0.0
        for mid in models:
            reg.setdefault(mid, []).append((sp, mt))
    return reg


def select_socket(registry, model):
    entries = registry.get(model)
    if not entries:
        return None
    return max(entries, key=lambda e: e[1])[0]


def _recv_all(sock):
    chunks = []
    while True:
        d = sock.recv(65536)
        if not d:
            break
        chunks.append(d)
    return b"".join(chunks)


def open_uds_and_send(socket_path, method, path, body=b"", timeout=600):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    s.connect(socket_path)
    head = (
        f"{method} {path} HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    s.sendall(head + body)
    return s


def probe_socket_models(socket_path, timeout=5):
    s = open_uds_and_send(socket_path, "GET", "/v1/models", b"", timeout=timeout)
    try:
        raw = _recv_all(s)
    finally:
        s.close()
    _, _, body = raw.partition(b"\r\n\r\n")
    payload = json.loads(body.decode("utf-8", "replace"))
    return [m["id"] for m in payload.get("data", []) if "id" in m]


def live_sockets(socket_dir):
    return sorted(glob.glob(os.path.join(socket_dir, "engine-*.sock")))


def _current_registry(socket_dir):
    return build_registry(live_sockets(socket_dir), probe=probe_socket_models)


class Handler(BaseHTTPRequestHandler):
    socket_dir = os.path.expanduser("~/.cocore/sockets")
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a):
        pass

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") != "/v1/models":
            self._json(404, {"error": {"message": "not found"}})
            return
        reg = _current_registry(self.socket_dir)
        data = [{"id": mid, "object": "model", "owned_by": "cocore-local"} for mid in sorted(reg)]
        self._json(200, {"object": "list", "data": data})

    def do_POST(self):
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._json(404, {"error": {"message": "not found"}})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        try:
            model = json.loads(body or b"{}").get("model")
        except json.JSONDecodeError:
            model = None
        reg = _current_registry(self.socket_dir)
        target = select_socket(reg, model) if model else None
        if not target:
            self._json(
                404,
                {"error": {"message": f"model {model!r} not loaded — run 'cocore agent models add {model}'"}},
            )
            return
        try:
            upstream = open_uds_and_send(target, "POST", "/v1/chat/completions", body)
        except OSError:
            self._json(502, {"error": {"message": "engine socket unavailable"}})
            return
        try:
            while True:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            upstream.close()


def serve(config):
    Handler.socket_dir = config["socket_dir"]
    port = config["port"]
    servers = {}

    def ensure(ip):
        if ip in servers:
            return
        try:
            httpd = ThreadingHTTPServer((ip, port), Handler)
        except OSError as e:
            print(f"[gateway] bind {ip}:{port} failed: {e}", flush=True)
            return
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers[ip] = httpd
        print(f"[gateway] listening on {ip}:{port}", flush=True)

    while True:
        wanted = set(resolve_binds(config["interfaces"], config["addresses"]))
        for ip in wanted:
            ensure(ip)
        for ip in list(servers):
            if ip != "127.0.0.1" and ip not in wanted:
                servers.pop(ip).shutdown()
                print(f"[gateway] stopped listening on {ip}:{port}", flush=True)
        time.sleep(30)


def main():
    env_path = os.environ.get(
        "COCORE_GATEWAY_ENV",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
    )
    env_text = ""
    if os.path.exists(env_path):
        with open(env_path) as f:
            env_text = f.read()
    config = load_config(env_text)
    log_dir = os.path.dirname(config["log_path"])
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    serve(config)


if __name__ == "__main__":
    main()
