import socket
import unittest
from unittest.mock import patch
from infra.provider_ipv6 import install, PROVIDERS


class ProviderIPv6Tests(unittest.TestCase):
    def test_provider_resolution_requires_ipv6_and_preserves_metadata(self):
        calls = []
        ipv6 = (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('::1', 443, 0, 0))
        ipv4 = (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 80))
        def resolver(host, port, family, type, proto, flags):
            calls.append((host, family))
            return [ipv6] if family == socket.AF_INET6 else [ipv4]
        with patch.object(socket, 'getaddrinfo'):
            resolve = install(resolver)
            for host in PROVIDERS:
                self.assertEqual(resolve(host, 443, type=socket.SOCK_STREAM), [ipv6])
                self.assertEqual(calls[-1], (host, socket.AF_INET6))
            self.assertEqual(resolve('169.254.169.254', 80, socket.AF_INET), [ipv4])
            self.assertEqual(calls[-1], ('169.254.169.254', socket.AF_INET))
            self.assertEqual(resolve('unrelated.example', 80), [ipv4])

    def test_provider_ipv4_requests_and_absent_ipv6_fail_closed(self):
        with patch.object(socket, 'getaddrinfo'):
            resolve = install(lambda *args: [])
            with self.assertRaises(OSError):
                resolve('sheets.googleapis.com', 443, socket.AF_INET)
            with self.assertRaises(OSError):
                resolve('sheets.googleapis.com', 443)
            # A resolver returning the wrong family must never allow IPv4 fallback.
            resolve = install(lambda *args: [(socket.AF_INET, 1, 6, '', ('127.0.0.1', 443))])
            with self.assertRaises(OSError):
                resolve('iamcredentials.googleapis.com', 443)
