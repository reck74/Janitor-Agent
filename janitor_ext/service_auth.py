"""Obtain n8n cookies using profile secrets as data and correctly encoded JSON."""
from __future__ import annotations

import http.cookiejar
import json
import os
from pathlib import Path
import tempfile
import urllib.request


def n8n_login(home: Path) -> Path:
    from janitor_ext.install import read_secrets
    values = {**read_secrets(home / '.env'), **os.environ}
    password = values.get('N8N_USER_PASSWORD')
    if not password:
        raise ValueError('Configure N8N_USER_PASSWORD in the active Janitor profile')
    url = values.get('N8N_API_URL', 'http://127.0.0.1:5678').rstrip('/') + '/rest/login'
    payload = json.dumps({'emailOrLdapLoginId': values.get('N8N_USER_EMAIL', 'janitor@example.com'),
                          'password': password}).encode()
    fd, name = tempfile.mkstemp(prefix='janitor-n8n-session-', suffix='.txt')
    os.close(fd)
    path = Path(name)
    jar = http.cookiejar.MozillaCookieJar(str(path))
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        with opener.open(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError(f'n8n login failed: HTTP {response.status}')
        if not any(cookie.name == 'n8n-auth' for cookie in jar):
            raise ValueError('n8n login did not issue an authentication cookie')
        jar.save(ignore_discard=True, ignore_expires=True)
        path.chmod(0o600)
        return path
    except Exception:
        path.unlink(missing_ok=True)
        raise


def main():
    from janitor_ext.startup import janitor_home
    try:
        print(n8n_login(janitor_home()))
        return 0
    except (OSError, ValueError) as error:
        print(f'n8n authentication failed: {error}', file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
