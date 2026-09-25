"""Automated Test Suite for Database Abstraction Layer.

Covers:
  1. RowWrapper semantics (key, index, attribute, dict, iter, case-insensitivity)
  2. SQL Dialect Translator (parameter tokenization, quotes, comments, datetime translation)
  3. SQLiteAdapter (execute, executemany, executescript, rowcount, lastrowid, DDL helpers)
  4. Exception normalization (IntegrityError, OperationalError, backward compatibility)
  5. PostgreSQLAdapter dialect translation and staging simulation
  6. Thread-safe SQLiteConnectionPool (checkout, checkin, liveness, concurrency)
  7. Transaction Manager with nested savepoints
  8. Schema Translator and PostgreSQL schema compatibility verification
"""

import os
import sqlite3
import threading
import pytest

from services.database import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    PostgreSQLAdapter,
    RowWrapper,
    SQLiteAdapter,
    SQLiteConnectionPool,
    generate_postgres_schema,
    get_db_adapter,
    transaction,
    translate_sql,
    translate_table_ddl,
)


# ==============================================================================
# 1. ROW WRAPPER TESTS
# ==============================================================================

class TestRowWrapper:
    """Verifies RowWrapper drop-in parity with sqlite3.Row and dict mappings."""

    def test_key_and_index_access(self):
        row = RowWrapper(["id", "name", "email"], [101, "Alice Smith", "alice@example.com"])
        assert row["id"] == 101
        assert row["name"] == "Alice Smith"
        assert row["email"] == "alice@example.com"
        assert row[0] == 101
        assert row[1] == "Alice Smith"
        assert row[2] == "alice@example.com"

    def test_case_insensitive_key_access(self):
        row = RowWrapper(["User_Id", "Email_Address"], [42, "user@test.org"])
        assert row["user_id"] == 42
        assert row["USER_ID"] == 42
        assert row["EMAIL_ADDRESS"] == "user@test.org"
        assert row["email_address"] == "user@test.org"

    def test_attribute_access(self):
        row = RowWrapper(["id", "domain", "status"], [1, "Full Stack", "Selected"])
        assert row.id == 1
        assert row.domain == "Full Stack"
        assert row.status == "Selected"

    def test_dict_conversion(self):
        row = RowWrapper(["code", "score"], ["PY", 95])
        as_dict = dict(row)
        assert as_dict == {"code": "PY", "score": 95}
        assert row.to_dict() == {"code": "PY", "score": 95}

    def test_iteration_values_parity(self):
        # sqlite3.Row iterates over values, not keys
        row = RowWrapper(["a", "b", "c"], [10, 20, 30])
        assert list(row) == [10, 20, 30]

    def test_keys_values_items_get(self):
        row = RowWrapper(["id", "role"], [1, "admin"])
        assert row.keys() == ["id", "role"]
        assert row.values() == [1, "admin"]
        assert row.items() == [("id", 1), ("role", "admin")]
        assert row.get("role") == "admin"
        assert row.get("missing", "default_val") == "default_val"
        assert "role" in row
        assert "missing" not in row

    def test_invalid_key_raises_keyerror(self):
        row = RowWrapper(["id"], [1])
        with pytest.raises(KeyError):
            _ = row["non_existent"]


# ==============================================================================
# 2. SQL DIALECT TRANSLATOR TESTS
# ==============================================================================

class TestDialectTranslator:
    """Verifies parameter tokenization and dialect conversions."""

    def test_basic_parameter_translation(self):
        sql = "SELECT * FROM users WHERE email = ? AND status = ?"
        translated = translate_sql(sql, "postgres")
        assert translated == "SELECT * FROM users WHERE email = %s AND status = %s"

    def test_preserves_question_mark_in_string_literal(self):
        sql = "SELECT * FROM support_tickets WHERE title = 'What is this?' AND user_id = ?"
        translated = translate_sql(sql, "postgres")
        assert translated == "SELECT * FROM support_tickets WHERE title = 'What is this?' AND user_id = %s"

    def test_preserves_question_mark_in_escaped_string_literal(self):
        sql = "INSERT INTO logs (msg, level) VALUES ('Isn''t it ? mysterious', ?)"
        translated = translate_sql(sql, "postgres")
        assert translated == "INSERT INTO logs (msg, level) VALUES ('Isn''t it ? mysterious', %s)"

    def test_preserves_question_mark_in_comments(self):
        sql = "-- Should we check status here? Yes\nSELECT * FROM tasks WHERE id = ?"
        translated = translate_sql(sql, "postgres")
        assert translated == "-- Should we check status here? Yes\nSELECT * FROM tasks WHERE id = %s"

        sql_block = "/* Is this query cached? */ SELECT * FROM courses WHERE code = ?"
        translated_block = translate_sql(sql_block, "postgres")
        assert translated_block == "/* Is this query cached? */ SELECT * FROM courses WHERE code = %s"

    def test_datetime_function_translation(self):
        sql1 = "INSERT INTO events (created_at) VALUES (datetime('now','localtime'))"
        assert "CURRENT_TIMESTAMP" in translate_sql(sql1, "postgres")

        sql2 = "UPDATE apps SET updated_at = datetime('now')"
        assert "CURRENT_TIMESTAMP" in translate_sql(sql2, "postgres")

        sql3 = "SELECT * FROM attendance WHERE date = date('now')"
        assert "CURRENT_DATE" in translate_sql(sql3, "postgres")

    def test_reverse_translation_for_sqlite(self):
        sql = "SELECT * FROM users WHERE id = %s AND active = %s"
        assert translate_sql(sql, "sqlite") == "SELECT * FROM users WHERE id = ? AND active = ?"


# ==============================================================================
# 3. SQLITE ADAPTER & EXCEPTION TESTS
# ==============================================================================

class TestSQLiteAdapter:
    """Verifies SQLiteAdapter execution, result wrapping, and error normalization."""

    @pytest.fixture
    def adapter(self):
        conn = sqlite3.connect(":memory:")
        adapter = SQLiteAdapter(conn)
        adapter.executescript("""
            CREATE TABLE test_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                credits INTEGER DEFAULT 0
            );
        """)
        yield adapter
        adapter.close()

    def test_execute_fetchone_and_rowcount(self, adapter):
        adapter.execute(
            "INSERT INTO test_users (email, name, credits) VALUES (?, ?, ?)",
            ("bob@example.com", "Bob", 50),
        )
        assert adapter.lastrowid == 1
        assert adapter.rowcount == 1

        cur = adapter.execute("SELECT * FROM test_users WHERE email = ?", ("bob@example.com",))
        row = cur.fetchone()
        assert isinstance(row, RowWrapper)
        assert row["name"] == "Bob"
        assert row["credits"] == 50
        assert row.id == 1

    def test_executemany_and_fetchall(self, adapter):
        data = [
            ("user1@test.com", "User 1", 10),
            ("user2@test.com", "User 2", 20),
            ("user3@test.com", "User 3", 30),
        ]
        adapter.executemany(
            "INSERT INTO test_users (email, name, credits) VALUES (?, ?, ?)",
            data,
        )
        cur = adapter.execute("SELECT * FROM test_users ORDER BY credits DESC")
        rows = cur.fetchall()
        assert len(rows) == 3
        assert [r["credits"] for r in rows] == [30, 20, 10]

    def test_fetchmany_and_iteration(self, adapter):
        for i in range(5):
            adapter.execute(
                "INSERT INTO test_users (email, name) VALUES (?, ?)",
                (f"u{i}@test.com", f"Name {i}"),
            )
        cur = adapter.execute("SELECT email FROM test_users ORDER BY id ASC")
        chunk = cur.fetchmany(2)
        assert len(chunk) == 2
        assert chunk[0]["email"] == "u0@test.com"

        # Direct iteration on cursor
        cur_all = adapter.execute("SELECT name FROM test_users ORDER BY id ASC")
        names = [r["name"] for r in cur_all]
        assert len(names) == 5

    def test_table_exists_and_ensure_column(self, adapter):
        assert adapter.table_exists("test_users") is True
        assert adapter.table_exists("non_existent_table") is False

        cols = adapter.get_column_names("test_users")
        assert "phone" not in cols

        adapter.ensure_column("test_users", "phone", "TEXT")
        cols_after = adapter.get_column_names("test_users")
        assert "phone" in cols_after

    def test_integrity_error_normalization_and_backward_compatibility(self, adapter):
        adapter.execute("INSERT INTO test_users (email, name) VALUES (?, ?)", ("dup@test.com", "First"))

        # Must raise IntegrityError
        with pytest.raises(IntegrityError):
            adapter.execute("INSERT INTO test_users (email, name) VALUES (?, ?)", ("dup@test.com", "Second"))

        # Backward compatibility: must ALSO be catchable via sqlite3.IntegrityError
        caught = False
        try:
            adapter.execute("INSERT INTO test_users (email, name) VALUES (?, ?)", ("dup@test.com", "Third"))
        except sqlite3.IntegrityError:
            caught = True
        assert caught is True


# ==============================================================================
# 4. POSTGRESQL ADAPTER STAGING SIMULATION
# ==============================================================================

class TestPostgreSQLAdapterSimulation:
    """Verifies PostgreSQLAdapter query translation and staging behavior."""

    class MockPgCursor:
        def __init__(self):
            self.last_query = None
            self.last_params = None
            self.description = [("id",), ("name",), ("email",)]
            self.rowcount = 1
            self.lastrowid = 77

        def execute(self, query, params=None):
            self.last_query = query
            self.last_params = params

        def fetchone(self):
            return (77, "Charlie", "charlie@postgres.org")

        def fetchall(self):
            return [(77, "Charlie", "charlie@postgres.org")]

    class MockPgConnection:
        def __init__(self, cursor):
            self._cursor = cursor
            self.committed = False
            self.rolled_back = False

        def cursor(self):
            return self._cursor

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    def test_pg_adapter_translates_qmark_to_format(self):
        mock_cur = self.MockPgCursor()
        mock_conn = self.MockPgConnection(mock_cur)
        adapter = PostgreSQLAdapter(mock_conn)

        cur = adapter.execute(
            "SELECT * FROM interns WHERE email = ? AND active = ?",
            ("charlie@postgres.org", 1),
        )
        assert mock_cur.last_query == "SELECT * FROM interns WHERE email = %s AND active = %s"
        assert mock_cur.last_params == ("charlie@postgres.org", 1)

        row = cur.fetchone()
        assert isinstance(row, RowWrapper)
        assert row["name"] == "Charlie"
        assert row.email == "charlie@postgres.org"

    def test_pg_adapter_ignores_sqlite_pragmas(self):
        mock_cur = self.MockPgCursor()
        mock_conn = self.MockPgConnection(mock_cur)
        adapter = PostgreSQLAdapter(mock_conn)

        cur = adapter.execute("PRAGMA busy_timeout = 8000")
        assert cur.fetchone() is None
        assert mock_cur.last_query is None  # Never reached PostgreSQL cursor


# ==============================================================================
# 5. CONNECTION POOL TESTS
# ==============================================================================

class TestConnectionPool:
    """Verifies SQLiteConnectionPool checkout, checkin, liveness, and concurrency."""

    @pytest.fixture
    def pool(self, tmp_path):
        db_file = str(tmp_path / "pool_test.db")
        pool = SQLiteConnectionPool(db_path=db_file, max_connections=4, timeout=5.0)
        yield pool
        pool.close_all()

    def test_checkout_and_checkin(self, pool):
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE pool_item (id INTEGER PRIMARY KEY, val TEXT)")
            conn.execute("INSERT INTO pool_item (val) VALUES (?)", ("Alpha",))
            conn.commit()

        # Re-borrow from pool and verify data persists
        with pool.get_connection() as conn:
            row = conn.execute("SELECT val FROM pool_item WHERE id = 1").fetchone()
            assert row["val"] == "Alpha"

    def test_pool_respects_max_connections(self, pool):
        borrowed = []
        for _ in range(4):
            borrowed.append(pool.checkout(timeout=1.0))
        assert pool.total_connections == 4

        # 5th checkout should raise TimeoutError
        with pytest.raises(TimeoutError):
            pool.checkout(timeout=0.1)

        # Return one and checkout should succeed
        pool.checkin(borrowed.pop())
        re_borrowed = pool.checkout(timeout=1.0)
        assert re_borrowed is not None

        for conn in borrowed + [re_borrowed]:
            pool.checkin(conn)

    def test_concurrent_pool_access(self, pool):
        with pool.get_connection() as conn:
            conn.execute("CREATE TABLE concurrent_log (id INTEGER PRIMARY KEY, t_id TEXT)")
            conn.commit()

        errors = []

        def worker(thread_idx):
            try:
                for _ in range(5):
                    with pool.get_connection(timeout=3.0) as conn:
                        conn.execute("INSERT INTO concurrent_log (t_id) VALUES (?)", (f"thread_{thread_idx}",))
                        conn.commit()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        with pool.get_connection() as conn:
            count = conn.execute("SELECT COUNT(*) FROM concurrent_log").fetchone()[0]
            assert count == 40


# ==============================================================================
# 6. TRANSACTION MANAGER TESTS
# ==============================================================================

class TestTransactionManager:
    """Verifies atomic transactions and nested savepoints."""

    @pytest.fixture
    def adapter(self):
        conn = sqlite3.connect(":memory:")
        adapter = SQLiteAdapter(conn)
        adapter.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, balance INTEGER)")
        adapter.execute("INSERT INTO accounts (id, balance) VALUES (1, 100), (2, 200)")
        adapter.commit()
        yield adapter
        adapter.close()

    def test_transaction_commits_on_success(self, adapter):
        with transaction(adapter):
            adapter.execute("UPDATE accounts SET balance = balance + 50 WHERE id = 1")

        row = adapter.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()
        assert row["balance"] == 150

    def test_transaction_rolls_back_on_exception(self, adapter):
        try:
            with transaction(adapter):
                adapter.execute("UPDATE accounts SET balance = balance + 500 WHERE id = 1")
                raise ValueError("Simulated business error")
        except ValueError:
            pass

        row = adapter.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()
        assert row["balance"] == 100  # Untouched

    def test_nested_transaction_savepoint_rollback(self, adapter):
        with transaction(adapter):
            # Outer update
            adapter.execute("UPDATE accounts SET balance = 500 WHERE id = 1")

            # Inner update that fails and rolls back to savepoint
            try:
                with transaction(adapter):
                    adapter.execute("UPDATE accounts SET balance = 999 WHERE id = 2")
                    raise RuntimeError("Inner transaction failure")
            except RuntimeError:
                pass  # Inner rolled back to savepoint

        # Outer transaction should have committed id=1 update, while id=2 was rolled back
        r1 = adapter.execute("SELECT balance FROM accounts WHERE id = 1").fetchone()
        r2 = adapter.execute("SELECT balance FROM accounts WHERE id = 2").fetchone()
        assert r1["balance"] == 500
        assert r2["balance"] == 200


# ==============================================================================
# 7. SCHEMA TRANSLATOR & COMPATIBILITY TESTS
# ==============================================================================

class TestSchemaTranslator:
    """Verifies SQLite DDL translation to compliant PostgreSQL DDL."""

    def test_translates_table_ddl(self):
        sqlite_ddl = """
        CREATE TABLE test_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            payload BLOB,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(user_email)
        );
        """
        translated = translate_table_ddl(sqlite_ddl)
        assert "SERIAL PRIMARY KEY" in translated
        assert "BYTEA" in translated
        assert "CURRENT_TIMESTAMP" in translated
        assert "UNIQUE(user_email)" in translated
        assert "AUTOINCREMENT" not in translated
        assert "datetime" not in translated

    def test_generates_postgres_schema_script(self):
        tables = [
            ("users", "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT);"),
        ]
        indexes = [
            ("idx_users_name", "CREATE INDEX idx_users_name ON users(name);"),
        ]
        script = generate_postgres_schema(tables, indexes)
        assert "DBERT INTERNSHIP PORTAL 4 — POSTGRESQL" in script
        assert "CREATE TABLE IF NOT EXISTS users" in script
        assert "CREATE INDEX idx_users_name ON users(name);" in script

    def test_production_schema_file_exists_and_valid(self):
        schema_path = os.path.join(os.path.dirname(__file__), "..", "docs", "POSTGRES_SCHEMA.sql")
        assert os.path.exists(schema_path)
        with open(schema_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "CREATE TABLE IF NOT EXISTS applications" in content
        assert "CREATE TABLE IF NOT EXISTS gl_concepts" in content
        assert "AUTOINCREMENT" not in content
        assert "PRAGMA" not in content
