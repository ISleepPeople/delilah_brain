"""
System tool implementations (Phase 6.1 Tool APIs v1).

These are intentionally conservative:
- health_check: shallow checks only (HTTP/TCP), no side effects
- get_versions: report runtime versions, no shelling out
- snapshot_capture: write a small snapshot bundle to recovery/ (READ_ONLY from services; writes files locally)
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import os
import platform
import socket
import time
from pathlib import Path

try:
    import requests  # type: ignore
except Exception:
    requests = None  # noqa: N816


def _tcp_check(host: str, port: int, timeout_s: float = 1.5) -> Dict[str, Any]:
    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return {"ok": True, "host": host, "port": port, "latency_ms": int((time.time() - started) * 1000)}
    except Exception as e:
        return {"ok": False, "host": host, "port": port, "error": str(e)}


def _http_check(url: str, timeout_s: float = 2.5) -> Dict[str, Any]:
    if requests is None:
        return {"ok": False, "url": url, "error": "requests not installed"}
    started = time.time()
    try:
        r = requests.get(url, timeout=timeout_s)
        return {
            "ok": r.status_code < 500,
            "url": url,
            "status_code": r.status_code,
            "latency_ms": int((time.time() - started) * 1000),
        }
    except Exception as e:
        return {"ok": False, "url": url, "error": str(e)}


def system_health_check(args: Dict[str, Any]) -> Dict[str, Any]:
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


def system_get_versions(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "hostname": platform.node(),
        "app_env": {
            "DELILAH_GIT_SHA": os.environ.get("DELILAH_GIT_SHA"),
            "DELILAH_ENV": os.environ.get("DELILAH_ENV"),
        },
    }


def system_snapshot_capture(args: Dict[str, Any]) -> Dict[str, Any]:
    label = (args or {}).get("label") or "snapshot"
    ts = time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())
    root = Path("/home/dad/delilah_workspace")
    out_dir = root / "recovery" / f"phase6_snapshot_{label}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Minimal, non-secret snapshot targets (extend later)
    targets = [
        root / "docker-compose.yml",
        root / "docker-compose.delilah_infra.yml",
        root / "requirements.delilah_brain_v2.txt",
        root / "PROJECT_STATE.md",
        root / "ARCHETECTURAL_DECISIONS.md",
        root / "README_LLM.md",
        root / "RULES.MD",
    ]

    copied = []
    missing = []
    for p in targets:
        if p.exists():
            dest = out_dir / p.name
            dest.write_bytes(p.read_bytes())
            copied.append(str(dest))
        else:
            missing.append(str(p))

    # Capture versions inline
    (out_dir / "versions.json").write_text(str(system_get_versions({})))

    return {
        "ok": True,
        "label": label,
        "path": str(out_dir),
        "copied": copied,
        "missing": missing,
    }
