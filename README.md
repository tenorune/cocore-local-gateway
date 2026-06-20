# cocore-local-gateway

Serve the MLX models your [cocore](https://cocore.dev) agent runs locally to your
own tools — over a standard OpenAI-compatible endpoint — without touching ollama
and without round-tripping through the cocore network.

The cocore agent runs each model as an OpenAI-compatible `vllm_mlx` server bound to
a **Unix domain socket** (`~/.cocore/sockets/engine-*.sock`) with no local TCP port.
This gateway bridges those sockets to one TCP endpoint, bound to localhost plus an
overlay interface you choose (ZeroTier, Tailscale, etc.).

## Install

```bash
git clone <this-repo> ~/Public/cocore-local-gateway
cd ~/Public/cocore-local-gateway
cp .env.example .env          # edit BIND_INTERFACES / port to taste
./install.sh                  # loads a LaunchAgent (auto-start, auto-restart)
```

Verify:

```bash
curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool
```

## Configuration (`.env`)

| Var | Meaning |
|---|---|
| `GATEWAY_PORT` | TCP port (default 1234) |
| `BIND_INTERFACES` | Overlay interface(s) to bind, e.g. `feth3363` (ZeroTier), `utun3` (Tailscale) |
| `BIND_ADDRESSES` | Or explicit addresses; `127.0.0.1` is always bound |
| `COCORE_SOCKET_DIR` | Engine socket dir (default `~/.cocore/sockets`) |
| `LOG_PATH` | Proxy log file |

No API key anywhere — access control is the bind set. Never binds `0.0.0.0`.

## Clients

### curl
```bash
curl -N http://127.0.0.1:1234/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"mlx-community/Qwen2.5-7B-Instruct-4bit","messages":[{"role":"user","content":"hi"}],"stream":true}'
```

### OpenCode
Merge into `~/.config/opencode/opencode.jsonc`:
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "cocore-local": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "co/core (local)",
      "options": { "baseURL": "http://127.0.0.1:1234/v1", "apiKey": "local" },
      "models": {
        "mlx-community/Qwen2.5-7B-Instruct-4bit":   { "name": "Qwen2.5 7B (local)" },
        "mlx-community/Qwen3.5-9B-MLX-4bit":        { "name": "Qwen3.5 9B (local)" },
        "mlx-community/Qwen2.5-0.5B-Instruct-4bit": { "name": "Qwen2.5 0.5B (local)" }
      }
    }
  }
}
```

### pi
Install the companion extension [`pi-cocore-local`](../pi-cocore-local) — it registers
a `cocore-local` provider pointed at this gateway.

### OFF GRID (iPhone, over your overlay)
With `BIND_INTERFACES` set to your overlay interface, OFF GRID auto-discovers the
gateway on port 1234, or add `http://<your-overlay-ip>:1234` manually. It pulls the
model list and streams responses.

## Notes
- A model is reachable only while its cocore engine is loaded (`cocore agent models`).
- `vllm_mlx` engines are single-worker; concurrent requests to one model queue.
