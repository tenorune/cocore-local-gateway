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
git clone <this-repo>
cd cocore-local-gateway       # or wherever you cloned it
cp .env.example .env          # edit BIND_INTERFACES / port to taste
./install.sh                  # loads a LaunchAgent (auto-start, auto-restart)
```

`install.sh` runs from wherever the repo lives — clone it anywhere you like.

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

The gateway is agnostic about which models you run — it advertises whatever cocore
engines are live. Discover the current IDs first; the examples below use a
`$MODEL` placeholder rather than any specific model.

```bash
# List whatever is loaded right now, and grab the first id into $MODEL
curl -s http://127.0.0.1:1234/v1/models | python3 -m json.tool
MODEL=$(curl -s http://127.0.0.1:1234/v1/models | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"][0]["id"])')
```

### curl
```bash
curl -N http://127.0.0.1:1234/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"stream\":true}"
```

### OpenCode
OpenCode can't auto-discover models from an OpenAI-compatible endpoint — you list
them yourself under `models`. The **keys must exactly match** the ids from
`GET /v1/models`; `name` is just the UI label.

Merge this into `~/.config/opencode/opencode.jsonc` (create the file if absent):
```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "cocore-local": {                       // provider id — any string
      "npm": "@ai-sdk/openai-compatible",   // the OpenAI-compatible adapter
      "name": "co/core (local)",            // label shown in the OpenCode UI
      "options": {
        "baseURL": "http://127.0.0.1:1234/v1",
        "apiKey": "local"                   // gateway ignores it, but the SDK wants a non-empty value
      },
      "models": {
        // ONE entry per id from GET /v1/models. The keys below are placeholders
        // showing the shape — replace them with the ids your cocore agent serves.
        "<org>/<your-first-model-id>":  { "name": "My local model" },
        "<org>/<your-second-model-id>": { "name": "My other local model" }
      }
    }
  }
}
```

Don't hand-type the `models` block — generate it from whatever is live:
```bash
curl -s http://127.0.0.1:1234/v1/models \
  | python3 -c 'import sys,json; print(json.dumps({m["id"]:{"name":m["id"].split("/")[-1]+" (local)"} for m in json.load(sys.stdin)["data"]}, indent=2))'
```
Paste the output as the value of `"models"`. Re-run it whenever you load or unload
models (`cocore agent models`), then restart OpenCode and run `/models` in the TUI to
confirm they appear under "co/core (local)".

The `name` is cosmetic and the ids come straight from the gateway, so there's nothing
model-specific to get right. You *can* add a per-model `"limit": { "context": N,
"output": N }` if OpenCode's default context sizing feels off — look the numbers up on
the model's own card rather than copying any from this README.

### pi
Install the companion extension [`pi-cocore-local`](https://github.com/tenorune/pi-cocore-local) — it registers
a `cocore-local` provider pointed at this gateway.

### OFF GRID (iPhone, over your overlay)
With `BIND_INTERFACES` set to your overlay interface, OFF GRID auto-discovers the
gateway on port 1234, or add `http://<your-overlay-ip>:1234` manually. It pulls the
model list and streams responses.

## Notes
- A model is reachable only while its cocore engine is loaded (`cocore agent models`).
- `vllm_mlx` engines are single-worker; concurrent requests to one model queue.
