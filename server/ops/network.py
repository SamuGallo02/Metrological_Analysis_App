"""Where the server can be reached from: LAN addresses, port check, hints for other devices."""
from __future__ import annotations

import socket
from typing import List


def lan_addresses() -> List[str]:
    """Private IPv4 addresses of this computer (the ones other devices on the same network can use)."""
    found = set()
    try:                                                         # the address used to reach the outside world
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))                     # UDP connect: nothing is sent
            found.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in found if not a.startswith(("127.", "169.254.", "0.")))


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def is_loopback(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


def urls(port: int, scheme: str = "http") -> List[str]:
    return [f"{scheme}://{a}:{port}" for a in lan_addresses()]
