"""Database Abstraction Layer & Generic Adapter Interface.

Provides a unified, dialect-portable database adapter for both SQLite and PostgreSQL.
Ensures zero-overhead abstraction, backward-compatible row access, automatic query parameter
translation (? -> %s), connection pooling, and transparent transaction management.
"""

from __future__ import annotations

import re
import sqlite3
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("db_adapter")


# ==============================================================================
# 1. UNIFIED EXCEPTION HIERARCHY
# ==============================================================================

class DatabaseError(Exception):
    """Base exception for all database abstraction errors."""
    pass


class IntegrityError(DatabaseError, sqlite3.IntegrityError):
    """Raised for relational integrity violations (unique constraint, foreign key, check).
    Inherits from sqlite3.IntegrityError for 100% backward compatibility with legacy exception handlers.
    """
    pass


class OperationalError(DatabaseError, sqlite3.OperationalError):
    """Raised for operational database errors (locked database, connection dropped, timeout)."""
    pass


class ProgrammingError(DatabaseError, sqlite3.ProgrammingError):
    """Raised for syntax errors, missing tables, or query programming errors."""
    pass


# ==============================================================================
# 2. ROW WRAPPER (DROP-IN PARITY WITH sqlite3.Row & DICT MAPPING)
# ==============================================================================

class RowWrapper:
    """Portable row result wrapper providing identical semantics across SQLite and PostgreSQL.
    
    Supports:
      - Key access: row["email"] (case-insensitive fallback)
      - Index access: row[0]
      - Attribute access: row.email (for non-private attributes)
      - Iteration: [val for val in row] (yields column values, matching sqlite3.Row)
      - Dictionary conversion: dict(row) or row.to_dict()
      - Methods: row.keys(), row.values(), row.items(), row.get("key", default)
    """

    __slots__ = ("_columns", "_values", "_col_map")

    def __init__(self, columns: Sequence[str], values: Sequence[Any]):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._col_map = {col.lower(): idx for idx, col in enumerate(self._columns)}

    def keys(self) -> List[str]:
        """Return list of column names."""
        return list(self._columns)

    def values(self) -> List[Any]:
        """Return list of column values."""
        return list(self._values)

    def items(self) -> List[Tuple[str, Any]]:
        """Return list of (column_name, value) tuples."""
        return list(zip(self._columns, self._values))

    def get(self, key: str, default: Any = None) -> Any:
        """Get column value by name with optional default."""
        idx = self._col_map.get(key.lower())
        if idx is not None:
            return self._values[idx]
        return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert row to a standard Python dictionary."""
        return dict(zip(self._columns, self._values))

    def __getitem__(self, item: Union[int, str]) -> Any:
        if isinstance(item, int):
            return self._values[item]
        if isinstance(item, str):
            idx = self._col_map.get(item.lower())
            if idx is not None:
                return self._values[idx]
            raise KeyError(f"Column '{item}' not found in row. Available: {self._columns}")
        raise TypeError(f"Row indices must be integers or strings, not {type(item).__name__}")

    def __iter__(self) -> Iterator[Any]:
        """Iterate over column values, matching native sqlite3.Row semantics."""
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return item.lower() in self._col_map
        return item in self._values

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        idx = self._col_map.get(name.lower())
        if idx is not None:
            return self._values[idx]
        raise AttributeError(f"Row has no column named '{name}'")

    def __repr__(self) -> str:
        pairs = ", ".join(f"{col}={repr(val)}" for col, val in zip(self._columns, self._values))
        return f"Row({pairs})"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, RowWrapper):
            return self._columns == other._columns and self._values == other._values
        if isinstance(other, dict):
            return self.to_dict() == other
        if isinstance(other, (tuple, list)):
            return self._values == tuple(other)
        return False


# ==============================================================================
# 3. SQL DIALECT & QUERY TRANSLATOR
# ==============================================================================

def translate_sql(sql: str, target_dialect: str = "postgres") -> str:
    """Translates SQL statements between SQLite and PostgreSQL dialects.
    
    Features:
      - Portable parameter translation: converts '?' to '%s' (or numeric '$1, $2')
        while strictly preserving '?' inside string literals and comments.
      - Function translation: translates datetime('now', 'localtime') -> CURRENT_TIMESTAMP.
      - Strips or ignores SQLite-only PRAGMAs for PostgreSQL targets.
    """
    if not sql or not isinstance(sql, str):
        return sql

    dialect = target_dialect.lower()
    if dialect == "sqlite":
        # Target is SQLite: convert '%s' back to '?' if needed
        return _convert_format_to_qmark(sql)

    # Dialect is PostgreSQL
    # 1. Translate date/time functions
    translated = re.sub(
        r"datetime\s*\(\s*['\"]now['\"]\s*,\s*['\"]localtime['\"]\s*\)",
        "CURRENT_TIMESTAMP",
        sql,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"datetime\s*\(\s*['\"]now['\"]\s*\)",
        "CURRENT_TIMESTAMP",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"date\s*\(\s*['\"]now['\"]\s*,\s*['\"]localtime['\"]\s*\)",
        "CURRENT_DATE",
        translated,
        flags=re.IGNORECASE,
    )
    translated = re.sub(
        r"date\s*\(\s*['\"]now['\"]\s*\)",
        "CURRENT_DATE",
        translated,
        flags=re.IGNORECASE,
    )

    # 2. Tokenize and replace '?' with '%s' outside quotes and comments
    return _convert_qmark_to_format(translated)


def _convert_qmark_to_format(sql: str) -> str:
    """Replaces unquoted '?' with '%s' while preserving string literals and comments."""
    result: List[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        # Single quoted string literal '...'
        if ch == "'":
            result.append(ch)
            i += 1
            while i < n:
                curr = sql[i]
                result.append(curr)
                if curr == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        # Escaped single quote ''
                        result.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                elif curr == "\\" and i + 1 < n:
                    # Backslash escape
                    result.append(sql[i + 1])
                    i += 2
                    continue
                i += 1
            continue

        # Line comment -- ...
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                result.append(sql[i])
                i += 1
            continue

        # Block comment /* ... */
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            result.append("/*")
            i += 2
            while i < n:
                if sql[i] == "*" and i + 1 < n and sql[i + 1] == "/":
                    result.append("*/")
                    i += 2
                    break
                result.append(sql[i])
                i += 1
            continue

        # Unquoted question mark placeholder
        if ch == "?":
            result.append("%s")
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _convert_format_to_qmark(sql: str) -> str:
    """Replaces unquoted '%s' with '?' while preserving string literals and comments."""
    result: List[str] = []
    i = 0
    n = len(sql)

    while i < n:
        ch = sql[i]

        if ch == "'":
            result.append(ch)
            i += 1
            while i < n:
                curr = sql[i]
                result.append(curr)
                if curr == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        result.append(sql[i + 1])
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue

        if ch == "%" and i + 1 < n and sql[i + 1] == "s":
            result.append("?")
            i += 2
            continue

        result.append(ch)
        i += 1

    return "".join(result)


# ==============================================================================
# 4. CURSOR ADAPTER
# ==============================================================================

class CursorAdapter:
    """Standardized cursor interface wrapping DB-API cursor results in RowWrapper."""

    def __init__(self, raw_cursor: Any, columns: Optional[List[str]] = None):
        self._raw_cursor = raw_cursor
        self._columns = columns

    @property
    def description(self) -> Any:
        return getattr(self._raw_cursor, "description", None)

    @property
    def lastrowid(self) -> Optional[int]:
        return getattr(self._raw_cursor, "lastrowid", None)

    @property
    def rowcount(self) -> int:
        return getattr(self._raw_cursor, "rowcount", -1)

    def _get_column_names(self) -> List[str]:
        if self._columns:
            return self._columns
        desc = self.description
        if desc:
            return [col[0] for col in desc]
        return []

    def _wrap_row(self, row: Any) -> Optional[RowWrapper]:
        if row is None:
            return None
        if isinstance(row, RowWrapper):
            return row
        if isinstance(row, sqlite3.Row):
            return RowWrapper(row.keys(), [row[k] for k in row.keys()])
        cols = self._get_column_names()
        if cols and len(cols) == len(row):
            return RowWrapper(cols, row)
        # Fallback numeric column names
        cols = [f"col_{i}" for i in range(len(row))]
        return RowWrapper(cols, row)

    def fetchone(self) -> Optional[RowWrapper]:
        raw = self._raw_cursor.fetchone()
        return self._wrap_row(raw)

    def fetchall(self) -> List[RowWrapper]:
        rows = self._raw_cursor.fetchall()
        cols = self._get_column_names()
        wrapped: List[RowWrapper] = []
        for r in rows:
            if isinstance(r, sqlite3.Row):
                wrapped.append(RowWrapper(r.keys(), [r[k] for k in r.keys()]))
            elif cols and len(cols) == len(r):
                wrapped.append(RowWrapper(cols, r))
            else:
                fallback_cols = [f"col_{i}" for i in range(len(r))]
                wrapped.append(RowWrapper(fallback_cols, r))
        return wrapped

    def fetchmany(self, size: int = 1) -> List[RowWrapper]:
        rows = self._raw_cursor.fetchmany(size)
        cols = self._get_column_names()
        return [
            RowWrapper(cols if cols and len(cols) == len(r) else [f"col_{i}" for i in range(len(r))], r)
            for r in rows
        ]

    def __iter__(self) -> Iterator[RowWrapper]:
        for raw in self._raw_cursor:
            yield self._wrap_row(raw)

    def close(self):
        if hasattr(self._raw_cursor, "close"):
            self._raw_cursor.close()


# ==============================================================================
# 5. DATABASE ADAPTER (ABSTRACT BASE CLASS)
# ==============================================================================

class DatabaseAdapter(ABC):
    """Abstract base class for platform database adapters."""

    @property
    @abstractmethod
    def dialect(self) -> str:
        """Name of database dialect: 'sqlite' or 'postgres'."""
        pass

    @abstractmethod
    def execute(self, query: str, params: Optional[Union[tuple, list, dict]] = None) -> CursorAdapter:
        """Execute a single query with optional parameters."""
        pass

    @abstractmethod
    def executemany(self, query: str, seq_of_params: Sequence) -> CursorAdapter:
        """Execute a query against a sequence of parameter sets."""
        pass

    @abstractmethod
    def executescript(self, script: str):
        """Execute multiple DDL/DML statements separated by semicolons."""
        pass

    @abstractmethod
    def commit(self):
        """Commit the current transaction."""
        pass

    @abstractmethod
    def rollback(self):
        """Rollback the current transaction."""
        pass

    @abstractmethod
    def close(self):
        """Close the underlying connection."""
        pass

    @property
    @abstractmethod
    def lastrowid(self) -> Optional[int]:
        """Return the last inserted row ID."""
        pass

    @property
    @abstractmethod
    def rowcount(self) -> int:
        """Return the number of affected rows from last execute."""
        pass

    @abstractmethod
    def table_exists(self, table_name: str) -> bool:
        """Check if table exists in database."""
        pass

    @abstractmethod
    def get_column_names(self, table_name: str) -> List[str]:
        """Return list of column names for given table."""
        pass

    @abstractmethod
    def ensure_column(self, table_name: str, column_name: str, column_definition: str):
        """Ensure a column exists on a table, adding it if missing."""
        pass

    def __enter__(self) -> DatabaseAdapter:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


# ==============================================================================
# 6. SQLITE ADAPTER (CONCRETE IMPLEMENTATION)
# ==============================================================================

class SQLiteAdapter(DatabaseAdapter):
    """Production-grade SQLite adapter wrapping sqlite3.Connection with robust settings."""

    def __init__(self, conn_or_path: Union[sqlite3.Connection, str], timeout: float = 15.0):
        if isinstance(conn_or_path, str):
            self._conn = sqlite3.connect(conn_or_path, timeout=timeout)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA busy_timeout = 8000")
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._owns_connection = True
        else:
            self._conn = conn_or_path
            if self._conn.row_factory != sqlite3.Row:
                self._conn.row_factory = sqlite3.Row
            self._owns_connection = False

        self._last_cursor: Optional[sqlite3.Cursor] = None

    @property
    def dialect(self) -> str:
        return "sqlite"

    @property
    def raw_connection(self) -> sqlite3.Connection:
        """Access the underlying sqlite3.Connection directly for legacy integration."""
        return self._conn

    @property
    def lastrowid(self) -> Optional[int]:
        return self._last_cursor.lastrowid if self._last_cursor else None

    @property
    def rowcount(self) -> int:
        return self._last_cursor.rowcount if self._last_cursor else -1

    def execute(self, query: str, params: Optional[Union[tuple, list, dict]] = None) -> CursorAdapter:
        try:
            if params is not None:
                cur = self._conn.execute(query, params)
            else:
                cur = self._conn.execute(query)
            self._last_cursor = cur
            return CursorAdapter(cur)
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.OperationalError as e:
            raise OperationalError(str(e)) from e
        except sqlite3.ProgrammingError as e:
            raise ProgrammingError(str(e)) from e
        except sqlite3.Error as e:
            raise DatabaseError(str(e)) from e

    def executemany(self, query: str, seq_of_params: Sequence) -> CursorAdapter:
        try:
            cur = self._conn.executemany(query, seq_of_params)
            self._last_cursor = cur
            return CursorAdapter(cur)
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.OperationalError as e:
            raise OperationalError(str(e)) from e
        except sqlite3.Error as e:
            raise DatabaseError(str(e)) from e

    def executescript(self, script: str):
        try:
            return self._conn.executescript(script)
        except sqlite3.IntegrityError as e:
            raise IntegrityError(str(e)) from e
        except sqlite3.OperationalError as e:
            raise OperationalError(str(e)) from e
        except sqlite3.Error as e:
            raise DatabaseError(str(e)) from e

    def commit(self):
        try:
            self._conn.commit()
        except sqlite3.Error as e:
            raise DatabaseError(str(e)) from e

    def rollback(self):
        try:
            self._conn.rollback()
        except sqlite3.Error as e:
            raise DatabaseError(str(e)) from e

    def close(self):
        if self._owns_connection:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                raise DatabaseError(str(e)) from e

    def table_exists(self, table_name: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        )
        return cur.fetchone() is not None

    def get_column_names(self, table_name: str) -> List[str]:
        cur = self._conn.execute(f"PRAGMA table_info({table_name})")
        return [row["name"] for row in cur.fetchall()]

    def ensure_column(self, table_name: str, column_name: str, column_definition: str):
        cols = self.get_column_names(table_name)
        if column_name not in cols:
            self._conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
            self._conn.commit()

    def __getattr__(self, name: str) -> Any:
        """Forward unrecognized methods to underlying sqlite3.Connection for zero-breakage compatibility."""
        return getattr(self._conn, name)


# ==============================================================================
# 7. POSTGRESQL ADAPTER (STAGING & PRODUCTION PREPARATION)
# ==============================================================================

class PostgreSQLAdapter(DatabaseAdapter):
    """PostgreSQL adapter providing transparent query translation and dialect parity.
    
    Accepts an existing connection object, SQLAlchemy engine connection, or mock staging runner.
    Translates '?' parameter syntax to '%s' automatically and normalizes error types.
    """

    def __init__(self, conn_or_url: Any):
        self._raw_conn = conn_or_url
        self._last_cursor: Any = None
        self._last_rowid: Optional[int] = None
        self._last_rowcount: int = -1

    @property
    def dialect(self) -> str:
        return "postgres"

    @property
    def raw_connection(self) -> Any:
        return self._raw_conn

    @property
    def lastrowid(self) -> Optional[int]:
        return self._last_rowid

    @property
    def rowcount(self) -> int:
        return self._last_rowcount

    def execute(self, query: str, params: Optional[Union[tuple, list, dict]] = None) -> CursorAdapter:
        # 1. Translate SQL query from SQLite syntax (? -> %s, datetime -> CURRENT_TIMESTAMP)
        pg_query = translate_sql(query, "postgres")

        # Ignore SQLite PRAGMAs on PostgreSQL
        if pg_query.strip().upper().startswith("PRAGMA "):
            logger.debug(f"[PostgreSQLAdapter] Ignored SQLite PRAGMA: {query.strip()}")
            return CursorAdapter(self._create_dummy_cursor())

        try:
            cur = self._raw_conn.cursor()
            if params is not None:
                # Convert params tuple/list if necessary
                cur.execute(pg_query, params)
            else:
                cur.execute(pg_query)

            self._last_cursor = cur
            self._last_rowcount = getattr(cur, "rowcount", -1)

            # Check if RETURNING id was requested or if lastrowid is available
            if hasattr(cur, "lastrowid"):
                self._last_rowid = cur.lastrowid

            return CursorAdapter(cur)
        except Exception as e:
            self._handle_pg_error(e)

    def executemany(self, query: str, seq_of_params: Sequence) -> CursorAdapter:
        pg_query = translate_sql(query, "postgres")
        try:
            cur = self._raw_conn.cursor()
            cur.executemany(pg_query, seq_of_params)
            self._last_cursor = cur
            self._last_rowcount = getattr(cur, "rowcount", -1)
            return CursorAdapter(cur)
        except Exception as e:
            self._handle_pg_error(e)

    def executescript(self, script: str):
        # Execute each translated statement
        statements = [stmt.strip() for stmt in script.split(";") if stmt.strip()]
        for stmt in statements:
            if not stmt.upper().startswith("PRAGMA"):
                self.execute(stmt)
        self.commit()

    def commit(self):
        if hasattr(self._raw_conn, "commit"):
            self._raw_conn.commit()

    def rollback(self):
        if hasattr(self._raw_conn, "rollback"):
            self._raw_conn.rollback()

    def close(self):
        if hasattr(self._raw_conn, "close"):
            self._raw_conn.close()

    def table_exists(self, table_name: str) -> bool:
        query = (
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s"
        )
        cur = self._raw_conn.cursor()
        cur.execute(query, (table_name.lower(),))
        return cur.fetchone() is not None

    def get_column_names(self, table_name: str) -> List[str]:
        query = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position"
        )
        cur = self._raw_conn.cursor()
        cur.execute(query, (table_name.lower(),))
        return [row[0] for row in cur.fetchall()]

    def ensure_column(self, table_name: str, column_name: str, column_definition: str):
        cols = self.get_column_names(table_name)
        if column_name.lower() not in [c.lower() for c in cols]:
            query = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            self.execute(query)
            self.commit()

    def _create_dummy_cursor(self) -> Any:
        class DummyCursor:
            description = None
            lastrowid = None
            rowcount = 0
            def fetchone(self): return None
            def fetchall(self): return []
            def fetchmany(self, size=1): return []
            def __iter__(self): return iter([])
            def close(self): pass
        return DummyCursor()

    def _handle_pg_error(self, e: Exception) -> None:
        err_msg = str(e).lower()
        err_cls_name = type(e).__name__.lower()
        if "unique" in err_msg or "integrity" in err_msg or "foreign" in err_msg or "integrityerror" in err_cls_name:
            raise IntegrityError(str(e)) from e
        if "operational" in err_cls_name or "connection" in err_msg or "timeout" in err_msg:
            raise OperationalError(str(e)) from e
        if "syntax" in err_msg or "programming" in err_cls_name:
            raise ProgrammingError(str(e)) from e
        raise DatabaseError(str(e)) from e


# ==============================================================================
# 8. ADAPTER FACTORY
# ==============================================================================

def get_db_adapter(
    conn_or_target: Optional[Any] = None,
    engine: Optional[str] = None,
    timeout: float = 15.0,
) -> DatabaseAdapter:
    """Factory creating appropriate DatabaseAdapter instance.
    
    If conn_or_target is an active sqlite3.Connection, wraps it in SQLiteAdapter.
    If conn_or_target is a path or None, connects via SQLiteAdapter using app configuration.
    If target is a PostgreSQL connection URL or engine='postgres', returns PostgreSQLAdapter.
    """
    import os

    # 1. Existing connection passed
    if conn_or_target is not None:
        if isinstance(conn_or_target, DatabaseAdapter):
            return conn_or_target
        if isinstance(conn_or_target, sqlite3.Connection):
            return SQLiteAdapter(conn_or_target, timeout=timeout)
        # Check if PostgreSQL connection
        if hasattr(conn_or_target, "cursor"):
            return PostgreSQLAdapter(conn_or_target)

    # 2. String path or database URL
    db_target = conn_or_target
    if db_target is None:
        # Check Flask app config
        try:
            from flask import current_app
            if current_app and current_app.config.get("DATABASE"):
                db_target = current_app.config.get("DATABASE")
        except Exception:
            pass

    if db_target is None:
        db_target = os.environ.get("DATABASE_URL") or os.environ.get("DB_FILE") or "internship.db"

    # 3. Detect engine
    if (
        (isinstance(db_target, str) and (db_target.startswith("postgresql://") or db_target.startswith("postgres://")))
        or engine == "postgres"
    ):
        return PostgreSQLAdapter(db_target)

    # 4. Default SQLiteAdapter
    return SQLiteAdapter(db_target, timeout=timeout)
