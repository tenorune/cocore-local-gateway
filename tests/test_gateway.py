# tests/test_gateway.py
import os
import os as _os
import socket as _socket
import tempfile
import threading
import unittest
import cocore_local_gateway as g


class TestConfig(unittest.TestCase):
    def test_parses_interfaces_and_expands_paths(self):
        env = (
            "GATEWAY_PORT=1234\n"
            "BIND_INTERFACES=feth3363,utun3\n"
            "COCORE_SOCKET_DIR=~/.cocore/sockets\n"
            "LOG_PATH=~/.cocore/logs/local-gateway.log\n"
            "# a comment\n"
            "\n"
        )
        cfg = g.load_config(env)
        self.assertEqual(cfg["port"], 1234)
        self.assertEqual(cfg["interfaces"], ["feth3363", "utun3"])
        self.assertEqual(cfg["addresses"], [])
        self.assertTrue(cfg["socket_dir"].endswith("/.cocore/sockets"))
        self.assertNotIn("~", cfg["socket_dir"])

    def test_addresses_optional_and_defaults(self):
        cfg = g.load_config("BIND_ADDRESSES=127.0.0.1,10.0.0.2\n")
        self.assertEqual(cfg["port"], 1234)
        self.assertEqual(cfg["addresses"], ["127.0.0.1", "10.0.0.2"])
        self.assertEqual(cfg["interfaces"], [])


class TestBinds(unittest.TestCase):
    def test_always_includes_localhost_and_dedupes(self):
        fake = {"feth3363": "10.121.33.197", "down0": None}
        ips = g.resolve_binds(
            interfaces=["feth3363", "down0"],
            addresses=["127.0.0.1"],
            iface_lookup=lambda n: fake.get(n),
        )
        self.assertEqual(ips, ["10.121.33.197", "127.0.0.1"])

    def test_localhost_added_even_when_absent(self):
        ips = g.resolve_binds(interfaces=[], addresses=[], iface_lookup=lambda n: None)
        self.assertEqual(ips, ["127.0.0.1"])


def _serve_uds_once(sock_path, response_bytes, capture):
    srv = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        capture["request"] = conn.recv(65536)
        conn.sendall(response_bytes)
        conn.close()
        srv.close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


class TestRegistry(unittest.TestCase):
    def test_underscore_id_resolved_from_probe_not_filename(self):
        # filename-parsing would corrupt "Q4_K_XL"; probing is authoritative
        weird = "unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_XL"
        mtimes = {"/s/a.sock": 100.0, "/s/b.sock": 200.0}
        probe = lambda p: [weird] if p == "/s/a.sock" else ["mlx-community/Qwen2.5-7B-Instruct-4bit"]
        reg = g.build_registry(
            ["/s/a.sock", "/s/b.sock"], probe=probe, mtime=lambda p: mtimes[p]
        )
        self.assertIn(weird, reg)
        self.assertEqual(g.select_socket(reg, weird), "/s/a.sock")

    def test_picks_most_recent_socket_for_duplicate_model(self):
        m = "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
        mtimes = {"/s/old.sock": 100.0, "/s/new.sock": 300.0}
        reg = g.build_registry(
            ["/s/old.sock", "/s/new.sock"], probe=lambda p: [m], mtime=lambda p: mtimes[p]
        )
        self.assertEqual(g.select_socket(reg, m), "/s/new.sock")

    def test_dead_socket_skipped(self):
        def probe(p):
            if p == "/s/dead.sock":
                raise OSError("connection refused")
            return ["mlx-community/Qwen2.5-7B-Instruct-4bit"]
        reg = g.build_registry(
            ["/s/dead.sock", "/s/live.sock"], probe=probe, mtime=lambda p: 1.0
        )
        self.assertIsNone(g.select_socket(reg, "missing/model"))
        self.assertEqual(
            g.select_socket(reg, "mlx-community/Qwen2.5-7B-Instruct-4bit"), "/s/live.sock"
        )


class TestUds(unittest.TestCase):
    def test_probe_returns_model_ids(self):
        d = tempfile.mkdtemp()
        sp = _os.path.join(d, "engine.sock")
        body = '{"object":"list","data":[{"id":"mlx-community/Qwen2.5-7B-Instruct-4bit"}]}'
        resp = (
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n{body}"
        ).encode()
        cap = {}
        t = _serve_uds_once(sp, resp, cap)
        ids = g.probe_socket_models(sp)
        t.join(timeout=5)
        self.assertEqual(ids, ["mlx-community/Qwen2.5-7B-Instruct-4bit"])
        self.assertIn(b"GET /v1/models", cap["request"])

    def test_relay_sends_request_and_streams_response(self):
        d = tempfile.mkdtemp()
        sp = _os.path.join(d, "engine.sock")
        resp = b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\nHELLO-STREAM"
        cap = {}
        t = _serve_uds_once(sp, resp, cap)
        s = g.open_uds_and_send(sp, "POST", "/v1/chat/completions", b'{"model":"x"}')
        received = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            received += chunk
        s.close()
        t.join(timeout=5)
        self.assertIn(b"HELLO-STREAM", received)
        self.assertIn(b"POST /v1/chat/completions", cap["request"])
        self.assertIn(b'{"model":"x"}', cap["request"])


if __name__ == "__main__":
    unittest.main()
