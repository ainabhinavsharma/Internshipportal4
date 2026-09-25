"""
services/performance_service.py
Phase 19: Performance Profiler & Benchmark Engine.

Measures and profiles:
1. TTFB (Time to First Byte) & Endpoint Latencies (min, avg, p95, max).
2. Database Query Execution Time, Total Query Count, and N+1 Detection.
3. Response Payload Sizes (bytes) and Static Asset Inventory.
4. Unbounded Query Detection and Missing Index Recommendations.
"""

import time
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Callable


# Standard SLA Latency Thresholds (milliseconds)
SLA_THRESHOLDS_MS = {
    "public_page": 250.0,    # HTML pages (e.g. /, /courses, /jobs)
    "api_endpoint": 150.0,   # JSON APIs (e.g. /api/public/courses)
    "api_json": 150.0,       # Alias for api_endpoint
    "auth_page": 200.0,      # Login/Auth pages
    "auth_action": 200.0,    # Alias for auth_page
    "db_query_max": 50.0,    # Single query execution limit
}


class QueryProfiler:
    """
    Hooks into SQLite connection execution to trace and count executed queries,
    measure individual statement timings, and detect N+1 repetition.
    Can be used as a context manager with a sqlite3 connection.
    """
    def __init__(self, conn=None):
        self.conn = conn
        self.queries: List[Dict[str, Any]] = []
        self.total_time_ms: float = 0.0

    def __enter__(self):
        if self.conn:
            self.conn.set_trace_callback(self.trace_query)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.set_trace_callback(None)

    @property
    def query_count(self) -> int:
        return len(self.queries)

    def trace_query(self, statement: str):
        cleaned = " ".join(statement.strip().split())
        if cleaned:
            self.queries.append({
                "sql": cleaned,
                "timestamp": time.perf_counter()
            })

    def find_n_plus_one_candidates(self, threshold: int = 3) -> List[Tuple[str, int]]:
        """Returns list of (sql, count) for queries executed >= threshold times."""
        counts: Dict[str, int] = {}
        for q in self.queries:
            sql = q["sql"]
            counts[sql] = counts.get(sql, 0) + 1
        return [(sql, cnt) for sql, cnt in counts.items() if cnt >= threshold]

    def analyze(self) -> Dict[str, Any]:
        """Analyzes recorded queries for counts, duplicates (N+1), and patterns."""
        count = len(self.queries)
        counts_by_statement: Dict[str, int] = {}
        for q in self.queries:
            sql = q["sql"]
            norm = sql
            counts_by_statement[norm] = counts_by_statement.get(norm, 0) + 1

        n_plus_one_suspects = [
            {"sql": sql, "occurrences": occ}
            for sql, occ in counts_by_statement.items()
            if occ > 3
        ]

        unbounded_queries = [
            q["sql"]
            for q in self.queries
            if "select" in q["sql"].lower() and "limit" not in q["sql"].lower() and "count(" not in q["sql"].lower()
        ]

        return {
            "total_queries": count,
            "queries": self.queries,
            "n_plus_one_suspects": n_plus_one_suspects,
            "has_n_plus_one": len(n_plus_one_suspects) > 0,
            "unbounded_queries": unbounded_queries,
        }


def benchmark_endpoint(
    client,
    path: str,
    method: str = "GET",
    iterations: int = 5,
    headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Benchmarks an endpoint across multiple iterations to measure TTFB and response size.
    Returns latency statistics: min, max, avg, samples, and payload byte size.
    """
    latencies: List[float] = []
    payload_size = 0
    status_code = 0

    for _ in range(iterations):
        t_start = time.perf_counter()
        if method.upper() == "GET":
            resp = client.get(path, headers=headers or {})
        else:
            resp = client.post(path, headers=headers or {})
        t_end = time.perf_counter()

        elapsed_ms = (t_end - t_start) * 1000.0
        latencies.append(elapsed_ms)
        payload_size = len(resp.data or b"")
        status_code = resp.status_code

    latencies.sort()
    avg_latency = sum(latencies) / len(latencies)
    # p95 approximation
    p95_idx = int(len(latencies) * 0.95)
    p95_latency = latencies[min(p95_idx, len(latencies) - 1)]

    return {
        "path": path,
        "method": method,
        "status_code": status_code,
        "iterations": iterations,
        "payload_bytes": payload_size,
        "min_ms": round(latencies[0], 2),
        "avg_ms": round(avg_latency, 2),
        "p95_ms": round(p95_latency, 2),
        "max_ms": round(latencies[-1], 2),
        "samples": latencies,
        "latencies": latencies,
    }


def audit_static_assets(static_dir: str = "static") -> Dict[str, Any]:
    """
    Scans the static asset directory to inventory images, scripts, and stylesheets,
    reporting byte sizes and identifying large assets (> 500KB).
    """
    base_path = Path(static_dir)
    if not base_path.exists():
        return {"error": f"Directory {static_dir} does not exist"}

    assets: List[Dict[str, Any]] = []
    total_bytes = 0
    large_assets: List[Dict[str, Any]] = []

    for file_path in base_path.rglob("*"):
        if file_path.is_file():
            size = file_path.stat().st_size
            total_bytes += size
            rel_path = file_path.relative_to(base_path).as_posix()
            ext = file_path.suffix.lower()

            if ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"]:
                category = "image"
            elif ext == ".css":
                category = "stylesheet"
            elif ext in [".js", ".mjs"]:
                category = "javascript"
            elif ext in [".woff", ".woff2", ".ttf"]:
                category = "font"
            else:
                category = "other"

            info = {
                "name": file_path.name,
                "path": rel_path,
                "category": category,
                "size_bytes": size,
                "size_kb": round(size / 1024.0, 1),
            }
            assets.append(info)
            if size > 500 * 1024:  # > 500 KB
                large_assets.append(info)

    assets.sort(key=lambda x: x["size_bytes"], reverse=True)

    return {
        "total_assets": len(assets),
        "total_bytes": total_bytes,
        "total_size_bytes": total_bytes,
        "total_kb": round(total_bytes / 1024.0, 1),
        "large_assets": large_assets,
        "large_asset_count": len(large_assets),
        "assets": assets,
    }


def get_performance_recommendations(benchmark_results: List[Dict[str, Any]], asset_audit: Dict[str, Any]) -> List[str]:
    """
    Generates actionable performance recommendations based on benchmark latencies
    and static asset metrics.
    """
    recommendations: List[str] = []

    for b in benchmark_results:
        path = b["path"]
        avg = b["avg_ms"]
        threshold = SLA_THRESHOLDS_MS.get("api_endpoint" if path.startswith("/api") else "public_page", 250.0)
        if avg > threshold:
            recommendations.append(
                f"Route '{path}' average latency ({avg}ms) exceeds SLA threshold ({threshold}ms). Consider indexing or caching."
            )

    if asset_audit.get("large_asset_count", 0) > 0:
        for large in asset_audit["large_assets"]:
            recommendations.append(
                f"Asset '{large['path']}' is {large['size_kb']} KB. Optimize image dimensions or apply WebP compression."
            )

    return recommendations
