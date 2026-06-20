# cocore_local_gateway.py
import json
import os
import os as _os
import re
import socket
import subprocess


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
