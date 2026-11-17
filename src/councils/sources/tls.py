"""Completing a council site's certificate chain, as browsers do.

Some councils' servers send their own certificate without the intermediate certificate that links it to a trusted
root (Newham, Plymouth, Boston and others, November 2026). Browsers fetch the missing intermediate from the address
the certificate itself gives ("Authority Information Access"); Python doesn't, so those sites fail with
CERTIFICATE_VERIFY_FAILED. ``completed_context`` fetches the missing intermediates the same way and returns a TLS
context that still verifies everything: the chain must end at one of the usual trusted roots, and the host name must
match. Nothing is trusted that a browser wouldn't trust.
"""

from __future__ import annotations

import logging
import os
import socket
import ssl
from functools import lru_cache

import certifi
import httpx
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, pkcs7
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtensionOID

log = logging.getLogger(__name__)

MAX_DEPTH = 3       # intermediates fetched, at most, for one site


def is_incomplete_chain(error: BaseException) -> bool:
    return "CERTIFICATE_VERIFY_FAILED" in str(error) and "unable to get local issuer certificate" in str(error)


def _leaf(host: str, port: int = 443, timeout: float = 30) -> x509.Certificate:
    """The certificate the server presents (read without verifying it: it is only used to find its issuer)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock, \
            ctx.wrap_socket(sock, server_hostname=host) as tls:
        der = tls.getpeercert(binary_form=True)
    return x509.load_der_x509_certificate(der)


def _issuer_urls(cert: x509.Certificate) -> list[str]:
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    except x509.ExtensionNotFound:
        return []
    return [d.access_location.value for d in aia
            if d.access_method == AuthorityInformationAccessOID.CA_ISSUERS
            and isinstance(d.access_location, x509.UniformResourceIdentifier)]


def _load(data: bytes) -> list[x509.Certificate]:
    """A downloaded issuer certificate: DER, PEM, or a PKCS#7 bundle (.p7c)."""
    for loader in (lambda d: [x509.load_der_x509_certificate(d)], lambda d: [x509.load_pem_x509_certificate(d)],
                   pkcs7.load_der_pkcs7_certificates, pkcs7.load_pem_pkcs7_certificates):
        try:
            return list(loader(data))
        except ValueError:
            continue
    return []


def _self_signed(cert: x509.Certificate) -> bool:
    return cert.issuer == cert.subject


@lru_cache(maxsize=64)
def completed_context(host: str, port: int = 443) -> ssl.SSLContext | None:
    """A verifying TLS context that also knows the intermediates ``host`` leaves out, or None if they can't be
    found."""
    try:
        cert = _leaf(host, port)
    except (OSError, ValueError) as e:
        log.info("%s: couldn't read its certificate: %s", host, e)
        return None
    found: list[x509.Certificate] = []
    for _ in range(MAX_DEPTH):
        urls = _issuer_urls(cert)
        if not urls or _self_signed(cert):
            break
        got: list[x509.Certificate] = []
        for url in urls:
            if not url.lower().startswith(("http://", "https://")):
                continue
            try:
                r = httpx.get(url, timeout=30, follow_redirects=True)
                r.raise_for_status()
            except httpx.HTTPError as e:
                log.info("%s: issuer certificate %s: %s", host, url, e)
                continue
            got = [c for c in _load(r.content) if c.subject == cert.issuer]
            if got:
                break
        if not got:
            break
        cert = got[0]
        if _self_signed(cert):
            break                   # a root: only the usual trusted roots are trusted, so it isn't added
        found.append(cert)
    if not found:
        return None
    ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or certifi.where())   # as httpx does
    # The intermediates join the store only to build the chain: it must still end at a trusted root. Python 3.13
    # accepts a chain ending at any certificate in the store (VERIFY_X509_PARTIAL_CHAIN), so that is turned off.
    ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0)
    ctx.load_verify_locations(cadata="".join(c.public_bytes(Encoding.PEM).decode() for c in found))
    log.info("%s: completed its certificate chain with %s", host,
             "; ".join(c.subject.rfc4514_string() for c in found))
    return ctx
