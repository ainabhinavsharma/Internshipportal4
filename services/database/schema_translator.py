"""SQLite to PostgreSQL Schema Translation Engine.

Translates SQLite DDL definitions into compliant, production-grade PostgreSQL DDL.
Handles auto-increment primary keys, timestamp defaults, BLOB to BYTEA conversions,
and index syntax normalization.
"""

from __future__ import annotations

import re
from typing import List, Tuple


def translate_column_definition(col_def: str) -> str:
    """Translate an individual SQLite column definition into PostgreSQL dialect."""
    out = col_def

    # 1. Primary key auto-increment
    # INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
    out = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "SERIAL PRIMARY KEY",
        out,
        flags=re.IGNORECASE,
    )
    # Standalone INTEGER PRIMARY KEY -> SERIAL PRIMARY KEY (if not specified as int)
    out = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\b",
        "SERIAL PRIMARY KEY",
        out,
        flags=re.IGNORECASE,
    )

    # 2. DateTime defaults
    # DEFAULT (datetime('now','localtime')) -> DEFAULT CURRENT_TIMESTAMP
    out = re.sub(
        r"DEFAULT\s*\(\s*datetime\s*\(\s*['\"]now['\"]\s*,\s*['\"]localtime['\"]\s*\)\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"DEFAULT\s*datetime\s*\(\s*['\"]now['\"]\s*,\s*['\"]localtime['\"]\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"DEFAULT\s*\(\s*datetime\s*\(\s*['\"]now['\"]\s*\)\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"DEFAULT\s*datetime\s*\(\s*['\"]now['\"]\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        out,
        flags=re.IGNORECASE,
    )

    # strftime defaults
    out = re.sub(
        r"DEFAULT\s*\(\s*strftime\s*\(.*?\)\s*\)",
        "DEFAULT CURRENT_TIMESTAMP",
        out,
        flags=re.IGNORECASE,
    )

    # 3. Data type mappings
    out = re.sub(r"\bBLOB\b", "BYTEA", out, flags=re.IGNORECASE)

    return out


def translate_table_ddl(sqlite_ddl: str) -> str:
    """Translates a full SQLite CREATE TABLE statement into PostgreSQL DDL."""
    if not sqlite_ddl or not sqlite_ddl.strip():
        return ""

    ddl = sqlite_ddl.strip()

    # Normalize whitespace
    ddl = re.sub(r"[\r\n]+", "\n", ddl)

    # Remove SQLite table options like WITHOUT ROWID or STRICT
    ddl = re.sub(r"\)\s*WITHOUT\s+ROWID\s*;", ");", ddl, flags=re.IGNORECASE)
    ddl = re.sub(r"\)\s*STRICT\s*;", ");", ddl, flags=re.IGNORECASE)

    # Parse table body
    match = re.search(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*)\)", ddl, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback regex without IF NOT EXISTS
        match = re.search(r"CREATE\s+TABLE\s+(\w+)\s*\((.*)\)", ddl, re.DOTALL | re.IGNORECASE)
        if not match:
            return ddl

    table_name = match.group(1)
    body = match.group(2)

    # Split body into clauses (respecting nested parentheses in CHECK or DEFAULT)
    clauses = _split_sql_clauses(body)
    translated_clauses = []

    for clause in clauses:
        c = clause.strip()
        if not c:
            continue
        # Table-level constraints (UNIQUE, FOREIGN KEY, PRIMARY KEY, CHECK)
        upper = c.upper()
        if (
            upper.startswith("UNIQUE")
            or upper.startswith("CONSTRAINT")
            or upper.startswith("FOREIGN KEY")
            or upper.startswith("PRIMARY KEY")
            or upper.startswith("CHECK")
        ):
            translated_clauses.append(c)
        else:
            # Column definition
            translated_clauses.append(translate_column_definition(c))

    formatted_body = ",\n    ".join(translated_clauses)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {formatted_body}\n);"


def translate_index_ddl(sqlite_index_ddl: str) -> str:
    """Translates a SQLite CREATE INDEX statement into PostgreSQL DDL."""
    if not sqlite_index_ddl or not sqlite_index_ddl.strip():
        return ""
    ddl = sqlite_index_ddl.strip()
    if not ddl.endswith(";"):
        ddl += ";"
    return ddl


def _split_sql_clauses(body: str) -> List[str]:
    """Splits table definition body into clauses respecting nested parentheses and quotes."""
    clauses: List[str] = []
    current: List[str] = []
    depth = 0
    in_quote = False
    quote_char = ""

    for ch in body:
        if ch in ("'", '"'):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
            current.append(ch)
            continue

        if not in_quote:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                clauses.append("".join(current).strip())
                current = []
                continue

        current.append(ch)

    if current:
        trailing = "".join(current).strip()
        if trailing:
            clauses.append(trailing)

    return clauses


def generate_postgres_schema(
    tables: List[Tuple[str, str]],
    indexes: List[Tuple[str, str]],
) -> str:
    """Generates a complete, executable PostgreSQL schema script from SQLite DDL pairs."""
    header = [
        "-- ============================================================================",
        "-- DBERT INTERNSHIP PORTAL 4 — POSTGRESQL STAGING & PRODUCTION SCHEMA",
        "-- Auto-generated by services.database.schema_translator",
        "-- ============================================================================",
        "",
        "SET client_encoding = 'UTF8';",
        "SET standard_conforming_strings = on;",
        "SET check_function_bodies = false;",
        "SET client_min_messages = warning;",
        "",
        "-- Enable UUID extension if needed",
        "CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";",
        "",
    ]

    body: List[str] = []

    # Tables
    body.append("-- ----------------------------------------------------------------------------")
    body.append(f"-- TABLES ({len(tables)} definitions)")
    body.append("-- ----------------------------------------------------------------------------\n")
    for name, ddl in tables:
        translated = translate_table_ddl(ddl)
        body.append(f"-- Table: {name}")
        body.append(translated)
        body.append("")

    # Indexes
    body.append("-- ----------------------------------------------------------------------------")
    body.append(f"-- INDEXES ({len(indexes)} definitions)")
    body.append("-- ----------------------------------------------------------------------------\n")
    for name, ddl in indexes:
        translated = translate_index_ddl(ddl)
        body.append(f"-- Index: {name}")
        body.append(translated)
        body.append("")

    return "\n".join(header + body)
