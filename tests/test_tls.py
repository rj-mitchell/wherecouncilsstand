"""A site that leaves out its intermediate certificate (Newham, Plymouth, Boston …): the intermediate is fetched from
the address in the site's certificate, as browsers do, and the chain is still verified to a trusted root."""

import datetime as dt
import http.server
import socket
import ssl
import threading

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import AuthorityInformationAccessOID, NameOID

from councils.sources import tls


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, key, signer, ca, aia=None, san=None):
    now = dt.datetime.now(dt.UTC)
    b = (x509.CertificateBuilder().subject_name(_name(subject)).issuer_name(_name(issuer)).public_key(key.public_key())
         .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
         .not_valid_after(now + dt.timedelta(days=30))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ca:
        b = b.add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                          content_commitment=False, key_encipherment=False, data_encipherment=False,
                                          key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
        b = b.add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
    b = b.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()), critical=False)
    if aia:
        b = b.add_extension(x509.AuthorityInformationAccess([x509.AccessDescription(
            AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(aia))]), critical=False)
    if san:
        b = b.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), critical=False)
    return b.sign(signer, hashes.SHA256())


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def site(tmp_path):
    """A root, an intermediate served over HTTP, and a TLS site on localhost that sends only its own certificate."""
    root_key, mid_key, leaf_key = (ec.generate_private_key(ec.SECP256R1()) for _ in range(3))
    root = _cert("Test Root", "Test Root", root_key, root_key, ca=True)
    mid = _cert("Test Intermediate", "Test Root", mid_key, root_key, ca=True)

    der = mid.public_bytes(serialization.Encoding.DER)

    class Issuer(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.send_header("Content-Type", "application/pkix-cert")
            self.end_headers()
            self.wfile.write(der)

        def log_message(self, *a):
            pass

    issuer = http.server.HTTPServer(("127.0.0.1", 0), Issuer)
    threading.Thread(target=issuer.serve_forever, daemon=True).start()
    leaf = _cert("localhost", "Test Intermediate", leaf_key, mid_key, ca=False,
                 aia=f"http://127.0.0.1:{issuer.server_port}/mid.cer", san="localhost")
    (tmp_path / "leaf.pem").write_bytes(_pem(leaf))             # the site sends only this, not the intermediate
    (tmp_path / "leaf.key").write_bytes(leaf_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (tmp_path / "root.pem").write_bytes(_pem(root))

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(tmp_path / "leaf.pem", tmp_path / "leaf.key")
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    stop = threading.Event()

    def serve():
        listener.settimeout(0.2)
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            try:
                with server_ctx.wrap_socket(conn, server_side=True) as s:
                    s.recv(1)
            except (OSError, ssl.SSLError):
                pass

    threading.Thread(target=serve, daemon=True).start()
    tls.completed_context.cache_clear()
    yield port, tmp_path / "root.pem"
    stop.set()
    issuer.shutdown()
    listener.close()
    tls.completed_context.cache_clear()


def _connect(ctx, port):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock, \
            ctx.wrap_socket(sock, server_hostname="localhost"):
        return True


def test_the_missing_intermediate_is_fetched_and_the_chain_verified(site, monkeypatch):
    port, root = site
    monkeypatch.setenv("SSL_CERT_FILE", str(root))
    plain = ssl.create_default_context(cafile=str(root))
    with pytest.raises(ssl.SSLCertVerificationError) as err:
        _connect(plain, port)                                  # what Python does on its own
    assert tls.is_incomplete_chain(err.value)
    ctx = tls.completed_context("localhost", port)
    assert ctx is not None and _connect(ctx, port)


def test_the_chain_must_still_end_at_a_trusted_root(site, monkeypatch):
    """With the test root not trusted, the fetched intermediate doesn't become a trust anchor of its own."""
    port, _root = site
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)        # the usual roots only
    ctx = tls.completed_context("localhost", port)
    assert ctx is not None
    with pytest.raises(ssl.SSLCertVerificationError):
        _connect(ctx, port)


def test_the_modern_gov_client_connects_again_with_the_completed_chain(tmp_path, monkeypatch):
    from dataclasses import replace

    import httpx

    from councils.config import load_settings
    from councils.sources import modgov

    made = []

    class FakeHttp:
        def __init__(self, verify=None, **kw):
            self.verify = verify
            made.append(self)

        def get(self, url, **kw):
            if self.verify is None:
                raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get "
                                         "local issuer certificate (_ssl.c:1010)")
            return httpx.Response(200, text="<committees/>")

        def close(self):
            pass

    monkeypatch.setattr(modgov.httpx, "Client", FakeHttp)
    monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "allowed")
    monkeypatch.setattr(modgov.robots, "crawl_delay", lambda url, ua: 0.0)
    asked = []
    monkeypatch.setattr(modgov.tls, "completed_context", lambda host: asked.append(host) or "a context")
    s = replace(load_settings(**{"modgov.min_interval_seconds": 0}), data_dir=tmp_path)
    with modgov.Client(s, "E06000026", "https://democracy.plymouth.gov.uk") as c:
        assert c._get("GetCommittees") == "<committees/>"
    assert asked == ["democracy.plymouth.gov.uk"] and [h.verify for h in made] == [None, "a context"]
