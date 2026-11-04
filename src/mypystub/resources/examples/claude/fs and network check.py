# File system checks (read-only) and network connectivity tests, standard library only.
import os
import shutil
import socket
import time

print("=== File system (read-only) ===")
cwd = os.getcwd()
print("Working dir:", cwd)
print("Writable:", os.access(cwd, os.W_OK))
print("Readable:", os.access(cwd, os.R_OK))
print(
    "Exists this script:",
    os.path.exists(__file__) if "__file__" in globals() else "n/a",
)

try:
    entries = os.listdir(cwd)
    print("Entries in working dir:", len(entries))
    for name in sorted(entries)[:20]:
        path = os.path.join(cwd, name)
        kind = "dir" if os.path.isdir(path) else "file"
        size = os.path.getsize(path) if kind == "file" else 0
        print(f"  {kind:4} {size:8} {name}")
except OSError as err:
    print("listdir failed:", err)

try:
    usage = shutil.disk_usage(cwd)
    print("Disk total (MB):", usage.total // (1024 * 1024))
    print("Disk free  (MB):", usage.free // (1024 * 1024))
except OSError as err:
    print("disk_usage failed:", err)

print("Temp dir:", os.environ.get("TMPDIR", os.environ.get("TEMP", "unset")))

print()
print("=== Network (read-only) ===")
hosts = [("one.one.one.one", 443), ("dns.google", 443), ("www.python.org", 443)]
for host, port in hosts:
    start = time.time()
    try:
        ip = socket.gethostbyname(host)
        dns_ms = (time.time() - start) * 1000
        print(f"DNS {host}: {ip} ({dns_ms:.0f} ms)")
    except socket.gaierror as err:
        print(f"DNS {host}: failed ({err})")
        continue

    start = time.time()
    try:
        with socket.create_connection((host, port), timeout=5):
            tcp_ms = (time.time() - start) * 1000
            print(f"TCP {host}:{port}: open ({tcp_ms:.0f} ms)")
    except OSError as err:
        print(f"TCP {host}:{port}: failed ({err})")

print("Local hostname:", socket.gethostname())
