"""
core/auth/base.py

Defines the common interface every site auth handler must implement.
Each site (site_a.py, site_b.py, ...) inherits AuthHandler and overrides
the methods it needs according to that site's own login flow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests


class AuthError(Exception):
    """Generic error when login fails (wrong user/pass, captcha, blocked...)."""


class SessionExpiredError(AuthError):
    """Session/cookie has expired and needs a fresh login."""


def site_label(host: str) -> str:
    """The identifying label of a host: its first label without a leading "www.".

    A site keeps this label when it changes TLD (example.com -> example.net), so
    it is what identifies the site across domains.
    """
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(".", 1)[0]


def host_matches(host: str, domains) -> bool:
    """True when `host` belongs to a site configured with these `domains`.

    An exact host (or a subdomain of it) matches first; failing that, hosts
    sharing the site's leading label match as well, so a config listing
    `example.com` still matches `example.net`.
    """
    host = (host or "").lower()
    if not host:
        return False

    for domain in domains or ():
        domain = (domain or "").lower().lstrip(".")
        if not domain:
            continue

        if host == domain or host.endswith("." + domain):
            return True

        if site_label(host) == site_label(domain):
            return True

    return False


@dataclass
class AuthResult:
    """Result returned after a successful login."""
    session: requests.Session
    site_id: str
    username: Optional[str] = None
    extra: dict = field(default_factory=dict)  # token, expire_at, etc if needed


class AuthHandler(ABC):
    """
    Common interface for logging into a specific manga site.

    Each site subclass must define:
        - site_id: unique id (used as the session storage key, e.g. "site_a")
        - login(): perform the login, return an AuthResult
        - is_logged_in(): check whether the current session is still valid

    It may override as well:
        - refresh(): renew the session if the site supports a refresh token
        - build_session(): customize the default session (headers, proxy...)
    """

    site_id: str = ""
    # Domain(s) this handler covers, e.g. ("site-a.example.com",).
    # Used by AuthManager.site_id_for_url() to auto-detect which site a
    # pasted URL belongs to, without the GUI needing a manual site picker.
    domains: tuple[str, ...] = ()
    # Names of the request headers that carry the session's auth (set by the
    # handler). AuthManager.get_headers() forwards exactly these to aiohttp /
    # Playwright so a logged-in session is replayed by other clients.
    auth_header_names: tuple[str, ...] = ()

    # The host the site is actually being served from, recorded by AuthManager
    # when it matches a URL — the config may still list the site's old domain.
    active_host: str = ""

    def matches_host(self, host: str) -> bool:
        """True when `host` is this site (see host_matches)."""
        return host_matches(host, self.domains)

    def retarget(self, url: str) -> str:
        """Point a configured URL at the host in use, when the site has moved.

        Only URLs on one of this handler's own domains are rewritten, so the
        other hosts a config may mention (API endpoints, CDNs) are left alone.
        """
        if not url or not self.active_host:
            return url

        parsed = urlparse(url)
        if parsed.netloc.lower() == self.active_host:
            return url
        if not host_matches(parsed.netloc, self.domains):
            return url

        return parsed._replace(netloc=self.active_host).geturl()

    def build_session(self) -> requests.Session:
        """Create a default session. Override for special headers/proxy."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
        return session

    @abstractmethod
    def login(self, username: str, password: str) -> AuthResult:
        """Perform the login. Raise AuthError on failure."""
        raise NotImplementedError

    @abstractmethod
    def is_logged_in(self, session: requests.Session) -> bool:
        """Check whether the current session is still logged in."""
        raise NotImplementedError

    def refresh(self, session: requests.Session) -> requests.Session:
        """
        Renew a session (e.g. refresh token, ping the home page to renew a cookie).
        Default: do nothing and return the original session unchanged.
        Override if the site supports refreshing without re-entering user/pass.
        """
        return session