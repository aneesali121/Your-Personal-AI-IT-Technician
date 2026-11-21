"""IT utilities. Each function performs a real check or generates real command text.
Nothing here executes commands on the local machine."""

import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import dns.exception
import dns.resolver
import httpx

HOST_RE = re.compile(
    r"^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
DNS_TYPES = {"A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA", "PTR"}
COMMON_PORTS = {
    21: "FTP", 22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP",
    443: "HTTPS", 465: "SMTPS", 587: "SMTP submission", 993: "IMAPS", 995: "POP3S",
    1433: "MS SQL", 3306: "MySQL", 3389: "RDP", 5432: "PostgreSQL", 6379: "Redis",
    8080: "HTTP alternate", 8443: "HTTPS alternate",
}


def valid_host(host: str) -> bool:
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(HOST_RE.match(host))


async def ip_info(host: str) -> dict:
    if not valid_host(host):
        raise ValueError("Enter a valid host name or IP address.")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
        addresses = sorted({info[4][0].split("%")[0] for info in infos})
    results = []
    for addr in addresses:
        ip = ipaddress.ip_address(addr)
        results.append({
            "address": addr,
            "version": ip.version,
            "private": ip.is_private,
            "loopback": ip.is_loopback,
            "public": ip.is_global,
        })
    return {"host": host, "addresses": results}


def dns_lookup(name: str, rtype: str = "A") -> dict:
    rtype = rtype.upper()
    if not valid_host(name):
        raise ValueError("Enter a valid domain name.")
    if rtype not in DNS_TYPES:
        raise ValueError(f"Unsupported record type. Use one of: {', '.join(sorted(DNS_TYPES))}.")
    try:
        answer = dns.resolver.resolve(name, rtype, lifetime=5)
        records = [r.to_text() for r in answer]
        return {"name": name, "type": rtype, "records": records}
    except dns.resolver.NXDOMAIN:
        return {"name": name, "type": rtype, "records": [], "note": "Domain does not exist (NXDOMAIN)."}
    except dns.resolver.NoAnswer:
        return {"name": name, "type": rtype, "records": [], "note": f"No {rtype} records found."}
    except dns.exception.Timeout:
        return {"name": name, "type": rtype, "records": [], "note": "DNS query timed out."}


async def http_status(url: str) -> dict:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a valid http or https URL.")
    target = parsed.geturl()
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            async with client.stream("GET", target, headers={"User-Agent": "IT-Technician-Agent/1.0"}) as r:
                elapsed = round((time.perf_counter() - start) * 1000)
                return {
                    "url": target,
                    "status": r.status_code,
                    "reason": r.reason_phrase,
                    "response_time_ms": elapsed,
                    "location": r.headers.get("location"),
                    "server": r.headers.get("server"),
                    "content_type": r.headers.get("content-type"),
                    "meaning": HTTP_MEANINGS.get(r.status_code - r.status_code % 100, ""),
                }
    except httpx.TimeoutException:
        return {"url": target, "status": None, "error": "Request timed out after 10 seconds."}
    except httpx.HTTPError as exc:
        return {"url": target, "status": None, "error": f"Connection failed: {exc.__class__.__name__}"}


HTTP_MEANINGS = {
    100: "Informational", 200: "Success", 300: "Redirection",
    400: "Client error (check the request, URL, or permissions)",
    500: "Server error (check the server or application logs)",
}


async def port_check(host: str, port: int) -> dict:
    if not valid_host(host):
        raise ValueError("Enter a valid host name or IP address.")
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535.")
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=5)
        writer.close()
        await writer.wait_closed()
        state = "open"
    except asyncio.TimeoutError:
        state = "filtered or timed out"
    except OSError:
        state = "closed or unreachable"
    return {"host": host, "port": port, "state": state, "service": COMMON_PORTS.get(port)}


def password_strength(password: str) -> dict:
    """Heuristic estimate only. The password is evaluated in memory and not stored."""
    length = len(password)
    classes = {
        "lowercase": bool(re.search(r"[a-z]", password)),
        "uppercase": bool(re.search(r"[A-Z]", password)),
        "digits": bool(re.search(r"\d", password)),
        "symbols": bool(re.search(r"[^A-Za-z0-9]", password)),
    }
    pool = 26 * classes["lowercase"] + 26 * classes["uppercase"] + 10 * classes["digits"] + 32 * classes["symbols"]
    import math
    entropy_bits = round(length * math.log2(pool)) if pool and length else 0

    suggestions = []
    if length < 12:
        suggestions.append("Use at least 12 characters; longer is better.")
    if not classes["uppercase"] or not classes["lowercase"]:
        suggestions.append("Mix uppercase and lowercase letters.")
    if not classes["digits"]:
        suggestions.append("Add numbers.")
    if not classes["symbols"]:
        suggestions.append("Add symbols.")
    if re.search(r"(.)\1{2,}", password):
        suggestions.append("Avoid repeated characters such as 'aaa'.")
    if password.lower() in {"password", "123456", "qwerty", "letmein", "admin"}:
        suggestions.append("This is a very common password. Do not use it anywhere.")
        entropy_bits = min(entropy_bits, 10)

    if entropy_bits < 40:
        label, score = "Weak", 1
    elif entropy_bits < 60:
        label, score = "Fair", 2
    elif entropy_bits < 80:
        label, score = "Strong", 3
    else:
        label, score = "Very strong", 4
    return {
        "length": length,
        "score": score,
        "label": label,
        "estimated_entropy_bits": entropy_bits,
        "character_classes": classes,
        "suggestions": suggestions,
        "note": "Heuristic estimate. Real-world strength also depends on whether the password appears in breach lists.",
    }


def network_commands(os_name: str, host: str) -> dict:
    if not valid_host(host):
        raise ValueError("Enter a valid host name or IP address.")
    os_name = os_name.lower()
    if os_name == "windows":
        commands = [
            {"label": "Ping", "command": f"ping -n 4 {host}",
             "explanation": "Sends 4 ICMP echo requests. Shows reachability and round-trip time."},
            {"label": "Traceroute", "command": f"tracert {host}",
             "explanation": "Lists each router hop to the destination. Useful for finding where packets stop."},
        ]
    elif os_name in ("linux", "macos"):
        commands = [
            {"label": "Ping", "command": f"ping -c 4 {host}",
             "explanation": "Sends 4 ICMP echo requests. Shows reachability and round-trip time."},
            {"label": "Traceroute", "command": f"traceroute {host}",
             "explanation": "Lists each router hop. On some Linux systems you may need: sudo apt install traceroute"},
        ]
    else:
        raise ValueError("Choose windows, linux, or macos.")
    return {"host": host, "os": os_name, "commands": commands}
