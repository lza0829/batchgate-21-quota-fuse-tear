import sqlite3

from app.db import connect

SEED_JOBS = [
    (
        "ingest_orders",
        "ingest_orders.json",
        "[]",
        1,
        1,
        "无依赖：写出订单水位",
        1.0,
        None,
    ),
    (
        "dim_customer",
        "dim_customer.json",
        "[]",
        1,
        1,
        "无依赖：写出客户维表水位",
        2.0,
        None,
    ),
    (
        "fact_order_daily",
        "fact_order_daily.json",
        '["ingest_orders","dim_customer"]',
        1,
        1,
        "依赖两路上游成功后才执行（底座仅查上游成功）",
        3.0,
        None,
    ),
]


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Additive migration: old local DBs keep their data."""
    job_cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "cost_weight" not in job_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN cost_weight REAL NOT NULL DEFAULT 0")
    if "fixed_cost" not in job_cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN fixed_cost REAL")

    orch_cols = {
        r["name"] for r in conn.execute("PRAGMA table_info(orchestrations)").fetchall()
    }
    for name, ddl in (
        ("quota_scope", "TEXT"),
        ("quota_limit", "REAL"),
        ("cost_total", "REAL"),
        ("skipped_fuse", "INTEGER"),
    ):
        if name not in orch_cols:
            conn.execute(f"ALTER TABLE orchestrations ADD COLUMN {name} {ddl}")

    # one-time backfill of cost settings for the seeded sample jobs
    flag = conn.execute(
        "SELECT value FROM settings WHERE key='cost_seed_backfilled'"
    ).fetchone()
    if not flag:
        for row in SEED_JOBS:
            name, _, _, _, _, _, weight, fixed = row
            conn.execute(
                "UPDATE jobs SET cost_weight=? WHERE name=? AND cost_weight=0 AND fixed_cost IS NULL",
                (weight, name),
            )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            ("cost_seed_backfilled", "1"),
        )


def init_db():
    conn = connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            fixture_path TEXT NOT NULL,
            depends_on_json TEXT NOT NULL,
            max_attempts INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            cost_weight REAL NOT NULL DEFAULT 0,
            fixed_cost REAL
        );
        CREATE TABLE IF NOT EXISTS orchestrations(
            id INTEGER PRIMARY KEY,
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            report_json TEXT NOT NULL,
            quota_scope TEXT,
            quota_limit REAL,
            cost_total REAL,
            skipped_fuse INTEGER
        );
        CREATE TABLE IF NOT EXISTS job_attempts(
            id INTEGER PRIMARY KEY,
            orchestration_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            attempt_no INTEGER NOT NULL,
            status TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS watermarks(
            job_id INTEGER PRIMARY KEY,
            watermark_ts TEXT,
            artifact_rows INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS cost_ledger(
            id INTEGER PRIMARY KEY,
            orchestration_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            attempt_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            cost_mode TEXT NOT NULL,
            cost_weight REAL NOT NULL DEFAULT 0,
            fixed_cost REAL,
            unit_price REAL NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cost_ledger_orch ON cost_ledger(orchestration_id);
        CREATE INDEX IF NOT EXISTS idx_attempts_orch ON job_attempts(orchestration_id);
        """
    )
    _ensure_columns(conn)
    if conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 0:
        jobs = SEED_JOBS
        conn.executemany(
            """
            INSERT INTO jobs(name, fixture_path, depends_on_json, max_attempts, enabled, note,
                             cost_weight, fixed_cost)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            jobs,
        )
        for row in conn.execute("SELECT id FROM jobs").fetchall():
            conn.execute(
                "INSERT OR IGNORE INTO watermarks(job_id, watermark_ts, artifact_rows, updated_at) VALUES (?,?,?,?)",
                (row["id"], None, 0, None),
            )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            ("default_max_attempts", "1"),
        )
        conn.executemany(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            [
                ("unit_price", "1.00"),
                ("quota_scope", "run"),
                ("quota_limit", ""),
            ],
        )
    conn.commit()
    conn.close()
