# tests/test_gateway.py
import os
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


if __name__ == "__main__":
    unittest.main()
