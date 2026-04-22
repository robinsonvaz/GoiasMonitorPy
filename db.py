"""Database helpers — MySQL via pymysql."""
from __future__ import annotations

import json
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

import pymysql
import pymysql.cursors
from werkzeug.security import generate_password_hash

from config import (
    MYSQL_HOST,
    MYSQL_PORT,
    MYSQL_USER,
    MYSQL_PASSWORD,
    MYSQL_DATABASE,
    LOCAL_ADMIN_EMAIL,
    LOCAL_ADMIN_PASSWORD,
    LOCAL_ADMIN_NAME,
)


def _connect(db: str | None = None) -> pymysql.Connection:  # type: ignore[type-arg]
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def get_conn() -> Generator[pymysql.Connection, None, None]:  # type: ignore[type-arg]
    conn = _connect(MYSQL_DATABASE)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(
    sql: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()  # type: ignore[return-value]


def query_one(
    sql: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> dict[str, Any] | None:
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(
    sql: str,
    params: tuple[Any, ...] | list[Any] | None = None,
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount  # type: ignore[return-value]


def execute_many(
    sql: str,
    params_list: list[tuple[Any, ...]] | list[list[Any]],
) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
            return cur.rowcount  # type: ignore[return-value]


def parse_json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def ensure_local_schema() -> None:
    with _connect(None) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}`"
                " CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id CHAR(36) NOT NULL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    full_name VARCHAR(255) NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            cur.execute("SELECT COUNT(*) AS total FROM users")
            row: dict[str, Any] | None = cur.fetchone()
            total: int = row["total"] if row else 0
            if total == 0:
                admin_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO users (id, email, full_name, password_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        admin_id,
                        LOCAL_ADMIN_EMAIL.strip().lower(),
                        LOCAL_ADMIN_NAME.strip(),
                        generate_password_hash(LOCAL_ADMIN_PASSWORD),
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO profiles (id, user_id, full_name, avatar_url, created_at, updated_at)
                    VALUES (%s, %s, %s, NULL, NOW(6), NOW(6))
                    """,
                    (str(uuid.uuid4()), admin_id, LOCAL_ADMIN_NAME.strip()),
                )
        conn.commit()



def _connect(db: str | None = None):
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextmanager
def get_conn():
    conn = _connect(MYSQL_DATABASE)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query_all(sql: str, params: tuple | list | None = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def query_one(sql: str, params: tuple | list | None = None):
    rows = query_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list | None = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount


def execute_many(sql: str, params_list: list[tuple] | list[list]):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, params_list)
            return cur.rowcount


def parse_json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def ensure_local_schema() -> None:
    with _connect(None) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id CHAR(36) NOT NULL PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    full_name VARCHAR(255) NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            cur.execute("SELECT COUNT(*) AS total FROM users")
            total = cur.fetchone()["total"]
            if total == 0:
                admin_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO users (id, email, full_name, password_hash)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        admin_id,
                        LOCAL_ADMIN_EMAIL.strip().lower(),
                        LOCAL_ADMIN_NAME.strip(),
                        generate_password_hash(LOCAL_ADMIN_PASSWORD),
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO profiles (id, user_id, full_name, avatar_url, created_at, updated_at)
                    VALUES (%s, %s, %s, NULL, NOW(6), NOW(6))
                    """,
                    (str(uuid.uuid4()), admin_id, LOCAL_ADMIN_NAME.strip()),
                )
