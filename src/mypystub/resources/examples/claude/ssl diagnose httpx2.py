# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "httpx2",
#     "certifi",
#     "truststore",
# ]
# ///
# SSL / certificate diagnostics for httpx2. Tests each trust route separately
# so you can see which one works on this runtime.
import os
import ssl
import sys

URL = "https://pypi.org/simple/httpx2/"

print("=== Runtime ===")
print("Python:", sys.version.split()[0])
print("OpenSSL:", ssl.OPENSSL_VERSION)
paths = ssl.get_default_verify_paths()
print(
    "Default cafile:",
    paths.cafile,
    "exists:",
    bool(paths.cafile) and os.path.exists(paths.cafile),
)
print(
    "Default capath:",
    paths.capath,
    "exists:",
    bool(paths.capath) and os.path.isdir(paths.capath),
)
for var in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"):
    print(var + ":", os.environ.get(var, "unset"))

print()
print("=== Packages ===")
import httpx2

print(
    "httpx2 version:",
    httpx2.__version__ if hasattr(httpx2, "__version__") else "unknown",
)
import certifi

print("certifi bundle:", certifi.where(), "exists:", os.path.exists(certifi.where()))
try:
    import truststore

    print("truststore: installed")
except ImportError:
    truststore = None
    print("truststore: NOT installed")


def check(label, **kwargs):
    try:
        with httpx2.Client(timeout=10, **kwargs) as client:
            response = client.get(URL)
            print(f"{label}: OK (HTTP {response.status_code})")
    except httpx2.ConnectError as err:
        print(f"{label}: connect error ({err})")
    except Exception as err:  # noqa: BLE001 (a diagnostic reports every failure)
        print(f"{label}: {type(err).__name__} ({err})")


print()
print("=== Trust routes to pypi.org ===")

# 1. httpx2 default (uses runtime / certifi defaults, depending on version)
check("httpx2 default")

# 2. Explicit certifi bundle
check("certifi bundle", verify=certifi.where())

# 3. OS trust store via truststore
if truststore is not None:
    try:
        truststore.inject_into_ssl()
        check("truststore (OS store)")
    except Exception as err:  # noqa: BLE001 (a diagnostic reports every failure)
        print("truststore (OS store):", type(err).__name__, err)
else:
    print("truststore (OS store): skipped")

# 4. Unverified control, to separate network from certificate problems
check("unverified (diagnostic only)", verify=False)

print()
print("=== Interpretation ===")
print(
    "- Default fails, certifi works: pass verify=certifi.where() or set SSL_CERT_FILE."
)
print(
    "- Default fails, truststore works: call truststore.inject_into_ssl() at startup."
)
print("- Only unverified works: certificate trust problem on this runtime.")
print("- Everything fails: network or blocking problem, not certificates.")
