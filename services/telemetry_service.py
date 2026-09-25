"""
services/telemetry_service.py
Phase 21: Observability, Telemetry & Logging Engine.

Tracks, monitors, and aggregates:
1. HTTP request lifecycle (rates, status codes, 2xx/3xx/4xx/5xx distributions).
2. Latency profiles (average, p50, p95, p99, min, max response time).
3. Failure categorization:
   - db_failures
   - email_failures
   - payment_failures
   - ai_failures
   - login_failures
   - upload_failures
   - auth_failures
   - csrf_rejects
4. System health and readiness probes (/health, /ready).
5. Thread-safe in-memory metric collections with zero performance overhead.
"""

import time
import threading
from typing import Dict, List, Any, Tuple, Optional
from collections import deque

# Maximum recent latency samples preserved for percentile computations
MAX_LATENCY_SAMPLES = 2000


class TelemetryCollector:
    """Thread-safe centralized telemetry accumulator."""

    def __init__(self):
        self._lock = threading.RLock()
        self.start_time = time.time()
        self.total_requests = 0
        self.status_buckets = {
            "2xx": 0,
            "3xx": 0,
            "4xx": 0,
            "5xx": 0
        }
        self.status_codes: Dict[int, int] = {}
        self.failures = {
            "db_failures": 0,
            "email_failures": 0,
            "payment_failures": 0,
            "ai_failures": 0,
            "login_failures": 0,
            "upload_failures": 0,
            "auth_failures": 0,
            "csrf_rejects": 0,
            "rate_limit_blocks": 0
        }
        self.endpoint_hits: Dict[str, int] = {}
        self.latencies: deque = deque(maxlen=MAX_LATENCY_SAMPLES)

    def record_request(self, method: str, path: str, status_code: int, duration_ms: float):
        """Records the completion of an HTTP request with its status and duration."""
        with self._lock:
            self.total_requests += 1

            # Status bucket
            bucket = f"{status_code // 100}xx"
            if bucket in self.status_buckets:
                self.status_buckets[bucket] += 1

            # Specific status code counter
            self.status_codes[status_code] = self.status_codes.get(status_code, 0) + 1

            # Path hit counter (normalized path prefix to prevent cardinality explosion)
            norm_path = path.split("?")[0]
            if len(norm_path) > 1 and norm_path.endswith("/"):
                norm_path = norm_path[:-1]
            self.endpoint_hits[norm_path] = self.endpoint_hits.get(norm_path, 0) + 1

            # Record duration sample
            self.latencies.append(duration_ms)

            # Auto-categorize client & server errors
            if status_code == 401 or status_code == 403:
                self.failures["auth_failures"] += 1
            elif status_code == 429:
                self.failures["rate_limit_blocks"] += 1
            elif status_code >= 500:
                self.failures["db_failures"] += 1

    def record_failure(self, category: str, details: Optional[Dict[str, Any]] = None):
        """Explicitly increments a domain-specific failure counter."""
        with self._lock:
            if category in self.failures:
                self.failures[category] += 1
            else:
                self.failures[category] = 1

    def get_latency_stats(self) -> Dict[str, float]:
        """Calculates min, avg, p50, p95, p99, and max from recent latency samples."""
        with self._lock:
            if not self.latencies:
                return {
                    "count": 0,
                    "avg_ms": 0.0,
                    "min_ms": 0.0,
                    "max_ms": 0.0,
                    "p50_ms": 0.0,
                    "p95_ms": 0.0,
                    "p99_ms": 0.0
                }

            sorted_samples = sorted(self.latencies)
            count = len(sorted_samples)
            avg_ms = sum(sorted_samples) / count

            def percentile(p: float) -> float:
                idx = int(p * count)
                idx = min(idx, count - 1)
                return sorted_samples[idx]

            return {
                "count": count,
                "avg_ms": round(avg_ms, 2),
                "min_ms": round(sorted_samples[0], 2),
                "max_ms": round(sorted_samples[-1], 2),
                "p50_ms": round(percentile(0.50), 2),
                "p95_ms": round(percentile(0.95), 2),
                "p99_ms": round(percentile(0.99), 2)
            }

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns a complete dictionary snapshot of system telemetry."""
        with self._lock:
            uptime_seconds = int(time.time() - self.start_time)
            total = max(1, self.total_requests)
            error_5xx_rate = round((self.status_buckets["5xx"] / total) * 100.0, 2)
            error_4xx_rate = round((self.status_buckets["4xx"] / total) * 100.0, 2)

            snapshot = {
                "uptime_seconds": uptime_seconds,
                "total_requests": self.total_requests,
                "status_buckets": dict(self.status_buckets),
                "status_codes": dict(self.status_codes),
                "rates": {
                    "5xx_error_rate_pct": error_5xx_rate,
                    "4xx_client_error_rate_pct": error_4xx_rate
                },
                "failures": dict(self.failures),
                "latencies": self.get_latency_stats()
            }
            return snapshot

    def reset(self):
        """Resets all metrics (primarily used by test suites)."""
        with self._lock:
            self.start_time = time.time()
            self.total_requests = 0
            self.status_buckets = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
            self.status_codes.clear()
            for k in self.failures:
                self.failures[k] = 0
            self.endpoint_hits.clear()
            self.latencies.clear()


# Global singleton collector
_collector = TelemetryCollector()


def record_request(method: str, path: str, status_code: int, duration_ms: float):
    _collector.record_request(method, path, status_code, duration_ms)


def record_failure(category: str, details: Optional[Dict[str, Any]] = None):
    _collector.record_failure(category, details)


def get_telemetry_snapshot() -> Dict[str, Any]:
    return _collector.get_snapshot()


def get_latency_stats() -> Dict[str, float]:
    return _collector.get_latency_stats()


def reset_telemetry():
    _collector.reset()


def check_liveness() -> Tuple[bool, Dict[str, Any]]:
    """
    Lightweight liveness probe for load balancers / container orchestrators.
    Confirms web process is responsive without DB load.
    """
    uptime = int(time.time() - _collector.start_time)
    return True, {
        "status": "ok",
        "service": "dbert-portal",
        "uptime_seconds": uptime,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }


def check_readiness(conn) -> Tuple[bool, Dict[str, Any]]:
    """
    Comprehensive readiness probe confirming database connectivity, WAL mode,
    table accessibility, and event outbox health.
    """
    checks = {
        "database_connected": False,
        "wal_mode": False,
        "tables_accessible": False,
        "outbox_healthy": False
    }
    details = {}

    try:
        # 1. Database Connectivity
        res = conn.execute("SELECT 1").fetchone()
        if res and res[0] == 1:
            checks["database_connected"] = True

        # 2. WAL Mode
        mode_row = conn.execute("PRAGMA journal_mode").fetchone()
        mode = mode_row[0].lower() if mode_row else ""
        checks["wal_mode"] = mode == "wal"
        details["journal_mode"] = mode

        # 3. Essential Tables Check
        required_tables = {"applications", "enrollments", "intern_accounts", "event_outbox"}
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?,?,?,?)",
            tuple(required_tables)
        ).fetchall()
        found_tables = {r["name"] if isinstance(r, dict) else r[0] for r in rows}
        checks["tables_accessible"] = required_tables.issubset(found_tables)
        details["tables_found"] = len(found_tables)

        # 4. Outbox Health (Dead-Letter queue count)
        dead_count = conn.execute(
            "SELECT COUNT(*) AS c FROM event_outbox WHERE status='dead_letter'"
        ).fetchone()
        dead_letters = dead_count["c"] if isinstance(dead_count, dict) else dead_count[0]
        pending_count = conn.execute(
            "SELECT COUNT(*) AS c FROM event_outbox WHERE status='pending'"
        ).fetchone()
        pending = pending_count["c"] if isinstance(pending_count, dict) else pending_count[0]

        checks["outbox_healthy"] = dead_letters < 50  # Alert threshold
        details["outbox_pending"] = pending
        details["outbox_dead_letters"] = dead_letters

        is_ready = all(checks.values())
        return is_ready, {
            "status": "ready" if is_ready else "degraded",
            "checks": checks,
            "details": details,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
    except Exception as e:
        record_failure("db_failures", {"error": str(e)})
        return False, {
            "status": "not_ready",
            "error": str(e),
            "checks": checks,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
