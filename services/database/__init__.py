"""Database Abstraction Package.

Exports:
  - DatabaseAdapter, SQLiteAdapter, PostgreSQLAdapter, CursorAdapter, RowWrapper
  - get_db_adapter, translate_sql
  - SQLiteConnectionPool, get_connection_pool, close_all_pools, transaction
  - DatabaseError, IntegrityError, OperationalError, ProgrammingError
  - translate_table_ddl, generate_postgres_schema
"""

from .adapter import (
    CursorAdapter,
    DatabaseAdapter,
    DatabaseError,
    IntegrityError,
    OperationalError,
    PostgreSQLAdapter,
    ProgrammingError,
    RowWrapper,
    SQLiteAdapter,
    get_db_adapter,
    translate_sql,
)
from .connection_pool import (
    SQLiteConnectionPool,
    close_all_pools,
    get_connection_pool,
    transaction,
)
from .schema_translator import (
    generate_postgres_schema,
    translate_column_definition,
    translate_index_ddl,
    translate_table_ddl,
)

__all__ = [
    "DatabaseAdapter",
    "SQLiteAdapter",
    "PostgreSQLAdapter",
    "CursorAdapter",
    "RowWrapper",
    "get_db_adapter",
    "translate_sql",
    "SQLiteConnectionPool",
    "get_connection_pool",
    "close_all_pools",
    "transaction",
    "DatabaseError",
    "IntegrityError",
    "OperationalError",
    "ProgrammingError",
    "translate_table_ddl",
    "translate_index_ddl",
    "translate_column_definition",
    "generate_postgres_schema",
]
