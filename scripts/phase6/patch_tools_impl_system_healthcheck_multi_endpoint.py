from __future__ import annotations

from pathlib import Path
import time
import py_compile
import sys

FILE = Path("/home/dad/delilah_workspace/tools/impl_system.py")
BACKUP_DIR = Path("/home/dad/delilah_workspace/backups/phase6")

def die(msg: str) -> None:
    print(f"PATCH ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)

def main() -> None:
    if not FILE.exists():
        die(f"missing {FILE}")

    src = FILE.read_text(errors="replace")

    # Anchor 1: insert helper functions after _http_check
    anchor_http = "def _http_check(url: str, timeout_s: float = 2.5) -> Dict[str, Any]:\n"
    if anchor_http not in src:
        die("missing anchor: _http_check()")

    if "def _default_gateway_ip() -> Optional[str]:" in src:
        print("PATCH OK: multi-endpoint helpers already present; no changes.")
        raise SystemExit(0)

    insert_after_http_end = None
    # Find end of _http_check by locating the next blank line + 'def system_health_check'
    idx = src.find(anchor_http)
    next_def = src.find("\n\ndef system_health_check", idx)
    if next_def == -1:
        die("could not find system_health_check() after _http_check()")
    insert_after_http_end = next_def + 2  # keep one blank line before helpers

    helpers = '''
def _default_gateway_ip() -> Optional[str]:
    """
    Best-effort Docker gateway detection for Linux containers.
    If unavailable, returns None.
    """
    try:
        route = Path("/proc/net/route").read_text().splitlines()
        for line in route[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[1] == "00000000":  # default route
                gw_hex = parts[2]
                # little-endian hex -> dotted quad
                b = bytes.fromhex(gw_hex)
                ip = ".".join(str(x) for x in b[::-1])
                return ip
    except Exception:
        return None
    return None


def _tcp_check_any(hosts: list[str], port: int, timeout_s: float = 1.5) -> Dict[str, Any]:
    tried = []
    last = None
    for h in hosts:
        if not h:
            continue
        res = _tcp_check(h, port, timeout_s=timeout_s)
        tried.append({"host": h, "ok": bool(res.get("ok"))})
        last = res
        if res.get("ok"):
            res["tried"] = tried
            return res
    out = last or {"ok": False, "host": None, "port": port, "error": "no hosts to try"}
    out["tried"] = tried
    return out


def _http_check_any(urls: list[str], timeout_s: float = 2.5) -> Dict[str, Any]:
    tried = []
    last = None
    for u in urls:
        if not u:
            continue
        res = _http_check(u, timeout_s=timeout_s)
        tried.append({"url": u, "ok": bool(res.get("ok"))})
        last = res
        if res.get("ok"):
            res["tried"] = tried
            return res
    out = last or {"ok": False, "url": None, "error": "no urls to try"}
    out["tried"] = tried
    return out

'''

    src = src[:insert_after_http_end] + helpers + src[insert_after_http_end:]

    # Anchor 2: replace the system_health_check body (minimal, deterministic)
    old_block = '''def system_health_check(args: Dict[str, Any]) -> Dict[str, Any]:
    # Default addresses (can be overridden later via config/env)
    brain_url = os.environ.get("DELILAH_BRAIN_URL", "http://127.0.0.1:8800/health")
    qdrant_url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333/healthz")

    # These ports are common defaults; if you use different ones, we can wire from env later.
    postgres_host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    postgres_port = int(os.environ.get("POSTGRES_PORT", "5432"))
    n8n_host = os.environ.get("N8N_HOST", "127.0.0.1")
    n8n_port = int(os.environ.get("N8N_PORT", "5678"))

    out: Dict[str, Any] = {
        "brain": _http_check(brain_url),
        "qdrant": _http_check(qdrant_url),
        "postgres": _tcp_check(postgres_host, postgres_port),
        "n8n": _tcp_check(n8n_host, n8n_port),
    }

    # overall ok if brain and qdrant ok; postgres/n8n can be optional in early phases
    out["ok"] = bool(out["brain"].get("ok")) and bool(out["qdrant"].get("ok"))
    return out
'''
    if old_block not in src:
        die("system_health_check block does not match expected text; aborting to avoid a bad patch")

    new_block = '''def system_health_check(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Health checks are shallow (HTTP/TCP) and conservative.

    Container networking note:
    - Inside a container, 127.0.0.1 is the container, not the host.
    - We therefore try multiple endpoints in a safe order:
      service DNS -> localhost -> host.docker.internal -> docker gateway.
    """
    brain_url = os.environ.get("DELILAH_BRAIN_URL", "http://127.0.0.1:8800/health")

    gw = _default_gateway_ip() or "172.17.0.1"

    # Qdrant: prefer service DNS, then fallbacks
    qdrant_env = os.environ.get("QDRANT_URL")
    qdrant_urls = [qdrant_env] if qdrant_env else []
    qdrant_urls += [
        "http://qdrant:6333/healthz",
        "http://127.0.0.1:6333/healthz",
        "http://host.docker.internal:6333/healthz",
        f"http://{gw}:6333/healthz",
    ]

    postgres_port = int(os.environ.get("POSTGRES_PORT", "5432"))
    n8n_port = int(os.environ.get("N8N_PORT", "5678"))

    postgres_env = os.environ.get("POSTGRES_HOST")
    n8n_env = os.environ.get("N8N_HOST")

    postgres_hosts = [postgres_env] if postgres_env else []
    postgres_hosts += ["postgres", "127.0.0.1", "host.docker.internal", gw]

    n8n_hosts = [n8n_env] if n8n_env else []
    n8n_hosts += ["n8n", "127.0.0.1", "host.docker.internal", gw]

    out: Dict[str, Any] = {
        "brain": _http_check_any([brain_url]),
        "qdrant": _http_check_any(qdrant_urls),
        "postgres": _tcp_check_any(postgres_hosts, postgres_port),
        "n8n": _tcp_check_any(n8n_hosts, n8n_port),
    }

    # overall ok if brain and qdrant ok; postgres/n8n remain non-blocking in Phase 6
    out["ok"] = bool(out["brain"].get("ok")) and bool(out["qdrant"].get("ok"))
    return out
'''
    src = src.replace(old_block, new_block, 1)

    tmp = FILE.with_suffix(".py.new")
    tmp.write_text(src)
    py_compile.compile(str(tmp), doraise=True)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    backup = BACKUP_DIR / f"impl_system.py.pre_healthcheck_multi_endpoint.{ts}.bak"
    backup.write_text(FILE.read_text(errors="replace"))

    FILE.write_text(src)
    tmp.unlink(missing_ok=True)

    print(f"PATCH OK: system_health_check now uses multi-endpoint targets (backup: {backup})")

if __name__ == "__main__":
    main()
