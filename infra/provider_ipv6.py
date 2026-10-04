"""IPv6-only resolution for fixed provider endpoints on the IPv6 pilot host."""
import socket

PROVIDERS = frozenset({'iamcredentials.googleapis.com', 'sheets.googleapis.com', 'api.telegram.org'})


def install(resolver=None):
    resolver = resolver or socket.getaddrinfo

    def resolve(host, port, family=0, type=0, proto=0, flags=0):
        if host not in PROVIDERS:
            return resolver(host, port, family, type, proto, flags)
        if family not in (socket.AF_UNSPEC, socket.AF_INET6):
            raise OSError('IPv4 provider transport is disabled on this host')
        addresses = resolver(host, port, socket.AF_INET6, type, proto, flags)
        addresses = [address for address in addresses if address[0] == socket.AF_INET6]
        if not addresses:
            raise OSError('Provider IPv6 transport is unavailable')
        return addresses

    socket.getaddrinfo = resolve
    return resolve
