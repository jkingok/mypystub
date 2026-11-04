# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
# SSL / certificate diagnostics. Standard library first; optional checks for
# certifi and httpx are guarded so the script still runs without them.
import os
import socket
import ssl
import sys

HOST = "pypi.org"
PORT = 443

print("=== OpenSSL / ssl module ===")
print("Python:", sys.version.split()[0])
print("OpenSSL:", ssl.OPENSSL_VERSION)
paths = ssl.get_default_verify_paths()
print("Default cafile:", paths.cafile)
print("Default capath:", paths.capath)
print("Default cafile exists:", bool(paths.cafile) and os.path.exists(paths.cafile))
print("Default capath exists:", bool(paths.capath) and os.path.isdir(paths.capath))
print("SSL_CERT_FILE:", os.environ.get("SSL_CERT_FILE", "unset"))
print("SSL_CERT_DIR:", os.environ.get("SSL_CERT_DIR", "unset"))
print("REQUESTS_CA_BUNDLE:", os.environ.get("REQUESTS_CA_BUNDLE", "unset"))

print()
print("=== certifi ===")
certifi_path = None
try:
    import certifi

    certifi_path = certifi.where()
    print("certifi installed, bundle:", certifi_path)
    print("bundle exists:", os.path.exists(certifi_path))
except ImportError:
    print("certifi: NOT installed")

print()
print("=== httpx ===")
try:
    import httpx  # pyright: ignore[reportMissingImports]

    print("httpx version:", httpx.__version__)
except ImportError:
    print("httpx: NOT installed")

print()
print("=== Certificate verification tests ===")


def try_connect(label, context):
    try:
        with (
            socket.create_connection((HOST, PORT), timeout=8) as sock,
            context.wrap_socket(sock, server_hostname=HOST) as tls,
        ):
            cert = tls.getpeercert()
            subject = dict(x[0] for x in cert.get("subject", ())) if cert else {}
            print(f"{label}: OK (cert CN: {subject.get('commonName', 'n/a')})")
    except ssl.SSLCertVerificationError as err:
        print(f"{label}: verify failed ({err.verify_message})")
    except ssl.SSLError as err:
        print(f"{label}: SSL error ({err})")
    except OSError as err:
        print(f"{label}: network error ({err})")


# 1. Default context, using the runtime's own CA store
try_connect("Default system CAs", ssl.create_default_context())

# 2. Explicit certifi bundle, if available
if certifi_path and os.path.exists(certifi_path):
    try_connect("certifi bundle", ssl.create_default_context(cafile=certifi_path))
else:
    print("certifi bundle: skipped")

# 3. Unverified context, to separate network from certificate problems
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
try_connect("No verification (diagnostic only)", ctx)

print()
print("=== Interpretation ===")
print("- If 'No verification' works but the others fail: CA store problem.")
print("- If 'certifi bundle' works but 'Default system CAs' fails: set cafile or")
print("  add certifi as a dependency and pass verify=certifi.where() to httpx.")
print(
    "- If everything fails, including 'No verification': network or blocking problem."
)
