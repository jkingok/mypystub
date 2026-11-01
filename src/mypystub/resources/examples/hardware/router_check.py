"""Check whether your router answers, using the local network permission."""

import ipaddress
import socket


def local_address() -> str:
    """This device's address on the local network.

    Connecting a UDP socket sends nothing; it only picks the outgoing interface.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, never actually contacted
        return probe.getsockname()[0]


def likely_router(address: str) -> str:
    """Guess the router: the first host on this device's /24 network."""
    network = ipaddress.ip_network(f"{address}/24", strict=False)
    return str(next(network.hosts()))


def answers(host: str, port: int, timeout: float = 2.0) -> bool:
    """Whether `host` accepts a TCP connection on `port`.

    The first connection to a local address makes iOS ask for the local
    network permission.
    """
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> None:
    """Find the likely router and report which common ports answer."""
    here = local_address()
    router = likely_router(here)
    print(f"This device is {here}; checking {router}...")
    open_ports = [port for port in (80, 443, 53) if answers(router, port)]
    if open_ports:
        print(f"{router} answered on port(s) {', '.join(map(str, open_ports))}.")
    else:
        print(f"{router} did not answer. Is local network access allowed in Settings?")


# The launcher calls main(); the guard runs it with plain `python router_check.py`
if __name__ == "__main__":
    main()
