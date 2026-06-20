# cocore_local_gateway.py
import os


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
