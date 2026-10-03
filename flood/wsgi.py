"""Production WSGI transport; shares the tested dispatcher and repository with local UI."""
from dataclasses import dataclass
from email.message import Message
from http import HTTPStatus
import ipaddress
import os
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from .cli import database_path
from .domain import DomainError, now
from .repository import Repository, dump
from .server import Handler


@dataclass(frozen=True)
class Config:
    origin: str
    production: bool = True
    trusted_proxies: tuple[str, ...] = ()

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if not parsed.hostname or parsed.path not in {'', '/'} or parsed.query or parsed.fragment or parsed.username:
            raise DomainError('FLOOD_PUBLIC_ORIGIN must contain only scheme and host')
        if self.production and (parsed.scheme != 'https' or os.environ.get('FLOOD_SECURE_COOKIES') != '1'):
            raise DomainError('Production requires an HTTPS origin and Secure cookies')
        for address in self.trusted_proxies:
            ipaddress.ip_network(address)

    @classmethod
    def environment(cls):
        production = os.environ.get('FLOOD_ENV', 'production') == 'production'
        origin = os.environ.get('FLOOD_PUBLIC_ORIGIN', '')
        return cls(origin.rstrip('/'), production, tuple(x.strip() for x in os.environ.get('FLOOD_TRUSTED_PROXIES', '').split(',') if x.strip()))


class RequestHandler(Handler):
    def __init__(self, server, environ):
        self.server = server
        self.command = environ['REQUEST_METHOD']
        self.path = environ.get('PATH_INFO', '/') + ('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else '')
        self.client_address = (environ.get('REMOTE_ADDR', ''), 0)
        self.headers = Message()
        for key, value in environ.items():
            if key.startswith('HTTP_'):
                self.headers[key[5:].replace('_', '-')] = value
        self.headers['Content-Type'] = environ.get('CONTENT_TYPE', '')
        self.headers['Content-Length'] = environ.get('CONTENT_LENGTH', '0') or '0'
        self.rfile = environ['wsgi.input']
        self.result = None
        self.response_headers = []
        self.status = 200

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass

    def send(self, *args, **kwargs):
        from io import BytesIO
        self.wfile = BytesIO()
        super().send(*args, **kwargs)
        self.result = self.wfile.getvalue()


class Application:
    def __init__(self, repo, config):
        self.config = config
        self.server = SimpleNamespace(repo=repo, preview=False, origin=config.origin)

    def trusted_peer(self, address):
        try:
            peer = ipaddress.ip_address(address)
            return any(peer in ipaddress.ip_network(network) for network in self.config.trusted_proxies)
        except ValueError:
            return False

    def __call__(self, environ, start_response):
        environ = dict(environ)
        handler = RequestHandler(self.server, environ)
        path = environ.get('PATH_INFO', '/')
        try:
            # The original Host is validated; forwarded host never overrides it.
            expected = urlsplit(self.config.origin).netloc.lower()
            if environ.get('HTTP_HOST', '').lower() != expected:
                raise DomainError('Untrusted request host', 400)
            peer = environ.get('REMOTE_ADDR', '')
            trusted = self.trusted_peer(peer)
            scheme = environ.get('wsgi.url_scheme', 'http')
            if trusted:
                proto = environ.get('HTTP_X_FORWARDED_PROTO', '')
                if proto and proto not in {'http', 'https'}:
                    raise DomainError('Invalid proxy protocol', 400)
                scheme = proto or scheme
                forwarded = environ.get('HTTP_X_FORWARDED_FOR', '')
                if forwarded:
                    # Caddy overwrites this with one directly observed client address.
                    try:
                        client = str(ipaddress.ip_address(forwarded))
                    except ValueError:
                        raise DomainError('Invalid proxy client address', 400)
                    handler.client_address = (client, 0)
            local_probe = path in {'/health/live', '/health/ready'} and peer in {'127.0.0.1', '::1'}
            if self.config.production and scheme != 'https' and not local_probe:
                raise DomainError('HTTPS is required', 426)
            if environ.get('HTTP_TRANSFER_ENCODING') and environ.get('CONTENT_LENGTH'):
                raise DomainError('Ambiguous request framing', 400)
            try: length=int(environ.get('CONTENT_LENGTH') or '0')
            except ValueError: raise DomainError('Invalid Content-Length',400)
            if length<0 or length>65536: raise DomainError('Request body exceeds 64 KiB',413)
            if handler.command in {'POST', 'PATCH'} and not environ.get('CONTENT_LENGTH'):
                raise DomainError('Content-Length is required', 411)
            if path == '/health/live' and handler.command == 'GET':
                handler.send({'status': 'HEALTHY'})
            elif path == '/health/ready' and handler.command == 'GET':
                ready = self.ready()
                handler.send({'status': 'HEALTHY' if ready else 'BLOCKED'}, 200 if ready else 503)
            else:
                handler.handle_request()
        except DomainError as exc:
            handler.send({'error': str(exc)}, exc.status)
        except Exception:
            handler.send({'error': 'Service unavailable'}, 503)
        headers = [(k, v) for k, v in handler.response_headers if k.lower() not in {'connection', 'transfer-encoding'}]
        headers = [(k, 'no-store' if k.lower() == 'cache-control' and path.startswith('/health/') else v) for k, v in headers]
        if self.config.production:
            headers.append(('Strict-Transport-Security', 'max-age=31536000'))
        headers.append(('Permissions-Policy', 'camera=(), microphone=(), geolocation=()'))
        start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}', headers)
        print(dump({'event': 'request', 'status': handler.status, 'time': now()}), flush=True)
        return [handler.result or b'']

    def ready(self):
        try:
            repo = self.server.repo
            schema = repo.rows('PRAGMA user_version')[0]['user_version']
            accounts = repo.rows("SELECT COUNT(*) AS n FROM users WHERE active=1 AND role='administrator'")[0]['n']
            return schema == 2 and accounts > 0 and os.access(Path(repo.path).parent, os.W_OK)
        except Exception:
            return False


def create_app():
    return Application(Repository(database_path()), Config.environment())
