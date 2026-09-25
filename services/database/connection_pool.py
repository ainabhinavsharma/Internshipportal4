"""Connection Pooling & Transaction Management.

Provides thread-safe connection pooling for SQLite and PostgreSQL engines,
along with a robust, savepoint-aware transaction context manager.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Union

from .adapter import DatabaseAdapter, SQLiteAdapter, get_db_adapter

logger = logging.getLogger("db_pool")


# ==============================================================================
# 1. SQLITE THREAD-SAFE CONNECTION POOL
# ==============================================================================

class SQLiteConnectionPool:
    """Thread-safe connection pool for SQLite databases.
    
    Features:
      - Bounded FIFO queue of pre-configured SQLiteAdapter connections.
      - Dynamic expansion up to `max_connections`.
      - Connection liveness verification ('SELECT 1') on checkout.
      - Transparent return to pool on context exit.
    """

    def __init__(
        self,
        db_path: str,
        max_connections: int = 10,
        timeout: float = 30.0,
        busy_timeout: int = 8000,
    ):
        self.db_path = db_path
        self.max_connections = max(1, max_connections)
        self.timeout = timeout
        self.busy_timeout = busy_timeout

        self._pool: queue.Queue[SQLiteAdapter] = queue.Queue(maxsize=self.max_connections)
        self._created_count = 0
        self._lock = threading.Lock()
        self._is_closed = False

    def _create_connection(self) -> SQLiteAdapter:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {self.busy_timeout}")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        return SQLiteAdapter(conn)

    def checkout(self, timeout: Optional[float] = None) -> SQLiteAdapter:
        """Acquire a connection from the pool, creating one if capacity remains."""
        if self._is_closed:
            raise RuntimeError("Connection pool is closed.")

        wait_time = timeout if timeout is not None else self.timeout

        # Try to get existing connection from pool
        try:
            adapter = self._pool.get_nowait()
            if self._validate_connection(adapter):
                return adapter
            # Discard invalid connection
            with self._lock:
                self._created_count -= 1
        except queue.Empty:
            pass

        # Check if we can create a new connection
        with self._lock:
            if self._created_count < self.max_connections:
                self._created_count += 1
                try:
                    return self._create_connection()
                except Exception:
                    self._created_count -= 1
                    raise

        # Wait for an available connection from queue
        try:
            adapter = self._pool.get(block=True, timeout=wait_time)
            if self._validate_connection(adapter):
                return adapter
            # Discard invalid and retry create
            with self._lock:
                self._created_count -= 1
            return self.checkout(timeout=wait_time)
        except queue.Empty:
            raise TimeoutError(f"Connection pool exhausted (max={self.max_connections}, wait={wait_time}s)")

    def checkin(self, adapter: SQLiteAdapter):
        """Return a borrowed connection to the pool."""
        if self._is_closed:
            try:
                adapter.close()
            except Exception:
                pass
            return

        try:
            # Ensure no dangling uncommitted transaction
            try:
                adapter.rollback()
            except Exception:
                pass
            self._pool.put_nowait(adapter)
        except queue.Full:
            # Pool already full, close this redundant connection
            with self._lock:
                self._created_count -= 1
            try:
                adapter.close()
            except Exception:
                pass

    def _validate_connection(self, adapter: SQLiteAdapter) -> bool:
        """Verify connection is still alive and responsive."""
        try:
            adapter.execute("SELECT 1")
            return True
        except Exception:
            try:
                adapter.close()
            except Exception:
                pass
            return False

    @contextmanager
    def get_connection(self, timeout: Optional[float] = None) -> Iterator[SQLiteAdapter]:
        """Context manager for borrowing and safely returning a pooled connection."""
        conn = self.checkout(timeout=timeout)
        try:
            yield conn
        finally:
            self.checkin(conn)

    def close_all(self):
        """Close and discard all connections in the pool."""
        with self._lock:
            self._is_closed = True
            while not self._pool.empty():
                try:
                    adapter = self._pool.get_nowait()
                    adapter.close()
                except Exception:
                    pass
            self._created_count = 0

    @property
    def total_connections(self) -> int:
        return self._created_count

    @property
    def available_connections(self) -> int:
        return self._pool.qsize()


# ==============================================================================
# 2. TRANSACTION MANAGER (ATOMIC + NESTED SAVEPOINTS)
# ==============================================================================

# Thread-local storage for transaction depth
_local_tx = threading.local()


@contextmanager
def transaction(
    conn_or_adapter: Optional[Union[DatabaseAdapter, sqlite3.Connection]] = None,
) -> Iterator[Union[DatabaseAdapter, sqlite3.Connection]]:
    """Robust transaction context manager with automatic nested savepoint handling.
    
    Usage:
      with transaction(conn) as tx:
          conn.execute("INSERT INTO ...")
          # nested transactions automatically use savepoints
          with transaction(conn):
              conn.execute("UPDATE ...")
      # Automatically committed on clean exit, rolled back on any exception.
    """
    target = conn_or_adapter or get_db_adapter()
    
    if not hasattr(_local_tx, "active_targets"):
        _local_tx.active_targets = {}

    target_id = id(target)
    depth = _local_tx.active_targets.get(target_id, 0)
    savepoint_name = f"sp_{uuid.uuid4().hex[:8]}" if depth > 0 else None

    # Begin transaction or create savepoint
    if depth == 0:
        # Top-level transaction
        _local_tx.active_targets[target_id] = 1
    else:
        # Nested transaction -> use savepoint
        _local_tx.active_targets[target_id] = depth + 1
        target.execute(f"SAVEPOINT {savepoint_name}")

    try:
        yield target
        if depth == 0:
            target.commit()
        else:
            target.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception:
        if depth == 0:
            target.rollback()
        else:
            target.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
        raise
    finally:
        current_depth = _local_tx.active_targets.get(target_id, 1)
        if current_depth <= 1:
            _local_tx.active_targets.pop(target_id, None)
        else:
            _local_tx.active_targets[target_id] = current_depth - 1


# ==============================================================================
# 3. GLOBAL POOL REGISTRY
# ==============================================================================

_POOL_REGISTRY: Dict[str, SQLiteConnectionPool] = {}
_REGISTRY_LOCK = threading.Lock()


def get_connection_pool(
    db_path: str = "internship.db",
    max_connections: int = 10,
) -> SQLiteConnectionPool:
    """Retrieve or create a singleton SQLiteConnectionPool for a given path."""
    with _REGISTRY_LOCK:
        if db_path not in _POOL_REGISTRY:
            _POOL_REGISTRY[db_path] = SQLiteConnectionPool(
                db_path=db_path,
                max_connections=max_connections,
            )
        return _POOL_REGISTRY[db_path]


def close_all_pools():
    """Close and drain all active connection pools across the process."""
    with _REGISTRY_LOCK:
        for pool in _POOL_REGISTRY.values():
            try:
                pool.close_all()
            except Exception as e:
                logger.warning(f"Error closing pool: {e}")
        _POOL_REGISTRY.clear()
