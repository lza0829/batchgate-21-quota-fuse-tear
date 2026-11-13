from decimal import Decimal

import pytest

from app import db as db_module
from app.engines.cost import job_cost, money, quota_gate, remaining_after
from app.seed import init_db


def test_money_rounding():
    assert money("1.005") == 1.01
    assert money(Decimal("2.674")) == 2.67


def test_job_cost_fixed_wins():
    job = {"cost_weight": 2.0, "fixed_cost": 5.0}
    out = job_cost(job, unit_price=1.0)
    assert out["cost_mode"] == "fixed" and out["amount"] == 5.0


def test_job_cost_weighted():
    out = job_cost({"cost_weight": 2.5, "fixed_cost": None}, unit_price=1.2)
    assert out["cost_mode"] == "weighted" and out["amount"] == 3.0


def test_quota_gate_policy():
    assert quota_gate(fused=False, remaining=None, projected=10) == "allow"
    assert quota_gate(fused=False, remaining=10, projected=10) == "allow"
    assert quota_gate(fused=False, remaining=10, projected=11) == "would_exceed"
    assert quota_gate(fused=True, remaining=None, projected=0) == "fuse_latched"


def test_remaining_after():
    assert remaining_after(None, 3) is None
    assert remaining_after(5.0, 2.0) == 3.0


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    init_db()
    return tmp_path / "app.db"


def _fetchone(sql, params=()):
    conn = db_module.connect()
    try:
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _run():
    from app.services.orchestrate_service import run_orchestration

    return run_orchestration()


def test_run_without_quota_completes(isolated_db):
    result = _run()
    report = result["report"]
    assert report["succeeded"] == 3
    assert report["skipped_fuse"] == 0
    assert report["fused"] is False
    assert report["cost_total"] == 6.0
    assert report["ledger_entry_count"] == 3
    assert report["attempt_count"] == 3


def test_run_quota_trips_fuse_and_stops_new_jobs(isolated_db):
    conn = db_module.connect()
    conn.execute("UPDATE settings SET value='4.00' WHERE key='quota_limit'")
    conn.commit()
    conn.close()

    result = _run()
    report = result["report"]
    # layer 0 runs dim_customer (2.00) then ingest_orders (1.00), leaving 1.00;
    # layer 1's fact_order_daily (3.00) does not fit and trips the fuse
    assert report["succeeded"] == 2
    assert report["skipped_fuse"] == 1
    assert report["fused"] is True
    assert report["fuse_trigger"] == "fact_order_daily"
    assert report["cost_total"] == 3.0
    assert report["ledger_entry_count"] == 2

    # executed upstreams keep their watermark; the fused job must not write one
    wm = _fetchone("SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL")
    assert wm["c"] == 2
    fused_attempt = _fetchone(
        "SELECT status, detail FROM job_attempts WHERE status='skipped_fuse'"
    )
    assert fused_attempt and "quota would be exceeded" in fused_attempt["detail"]
    fact_wm = _fetchone(
        """
        SELECT w.watermark_ts FROM watermarks w JOIN jobs j ON j.id=w.job_id
        WHERE j.name='fact_order_daily'
        """
    )
    assert fact_wm["watermark_ts"] is None


def test_fuse_latch_blocks_later_affordable_jobs(isolated_db):
    conn = db_module.connect()
    conn.execute("UPDATE settings SET value='1.50' WHERE key='quota_limit'")
    conn.commit()
    conn.close()
    result = _run()
    report = result["report"]
    # dim_customer (2.00) trips the fuse; ingest_orders (1.00) would still fit
    # the original budget but must not start after the latch
    assert report["succeeded"] == 0
    assert report["skipped_fuse"] == 3
    assert report["fuse_trigger"] == "dim_customer"
    assert report["cost_total"] == 0.0
    statuses = _fetch_one_attempts()
    assert all(a["status"] == "skipped_fuse" for a in statuses)
    latch_reason = _fetchone(
        """
        SELECT a.detail FROM job_attempts a JOIN jobs j ON j.id=a.job_id
        WHERE j.name='ingest_orders'
        """
    )["detail"]
    assert "already latched" in latch_reason


def test_quota_fuse_skips_dependent_jobs_even_if_upstreams_would_pass(isolated_db):
    conn = db_module.connect()
    conn.execute("UPDATE settings SET value='0.50' WHERE key='quota_limit'")
    conn.commit()
    conn.close()
    result = _run()
    report = result["report"]
    # first ready job is over budget already -> everything is fused
    assert report["succeeded"] == 0
    assert report["skipped_fuse"] == 3
    assert report["cost_total"] == 0.0
    assert all(
        a["status"] == "skipped_fuse"
        for a in _fetch_one_attempts()
    )


def _fetch_one_attempts():
    conn = db_module.connect()
    try:
        rows = conn.execute("SELECT status FROM job_attempts").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def test_global_scope_counts_prior_spend(isolated_db):
    first = _run()  # spends 6.00 globally, no limit yet
    assert first["report"]["cost_total"] == 6.0

    conn = db_module.connect()
    conn.execute("UPDATE settings SET value='global' WHERE key='quota_scope'")
    conn.execute("UPDATE settings SET value='8.50' WHERE key='quota_limit'")
    conn.commit()
    conn.close()

    second = _run()
    report = second["report"]
    # 2.50 left of 8.50: dim_customer (2.00) runs, leaving 0.50;
    # ingest_orders (1.00) trips the fuse and latches it for fact_order_daily
    assert report["succeeded"] == 1
    assert report["fused"] is True
    assert report["cost_total"] == 2.0
    assert report["quota_remaining"] == 0.5
    assert report["skipped_fuse"] == 2


def test_cost_settings_persist_across_reconnect(isolated_db):
    conn = db_module.connect()
    conn.execute(
        "UPDATE jobs SET fixed_cost=7.50, cost_weight=9 WHERE name='dim_customer'"
    )
    conn.commit()
    conn.close()

    # fresh connection in a new orchestration sees the stored cost
    result = _run()
    dim = _fetchone(
        """
        SELECT l.amount, l.cost_mode, l.fixed_cost
        FROM cost_ledger l JOIN jobs j ON j.id=l.job_id
        WHERE j.name='dim_customer'
        """
    )
    assert dim["amount"] == 7.5 and dim["cost_mode"] == "fixed"
    assert result["report"]["cost_total"] == 11.5


def test_old_local_db_migrates_without_data_loss(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    legacy = sqlite3.connect(tmp_path / "app.db")
    legacy.executescript(
        """
        CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE jobs(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE,
            fixture_path TEXT NOT NULL, depends_on_json TEXT NOT NULL,
            max_attempts INTEGER NOT NULL DEFAULT 1,
            enabled INTEGER NOT NULL DEFAULT 1, note TEXT
        );
        CREATE TABLE orchestrations(
            id INTEGER PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL,
            finished_at TEXT, report_json TEXT NOT NULL
        );
        CREATE TABLE job_attempts(
            id INTEGER PRIMARY KEY, orchestration_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL, attempt_no INTEGER NOT NULL,
            status TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE watermarks(
            job_id INTEGER PRIMARY KEY, watermark_ts TEXT,
            artifact_rows INTEGER NOT NULL DEFAULT 0, updated_at TEXT
        );
        INSERT INTO jobs(name, fixture_path, depends_on_json, max_attempts, enabled, note)
        VALUES ('ingest_orders','ingest_orders.json','[]',1,1,'legacy'),
               ('dim_customer','dim_customer.json','[]',1,1,'legacy'),
               ('fact_order_daily','fact_order_daily.json',
                '["ingest_orders","dim_customer"]',1,1,'legacy');
        INSERT INTO orchestrations(status, started_at, finished_at, report_json)
        VALUES ('ok','2026-01-01T00:00:00Z','2026-01-01T00:00:01Z','{"succeeded":3}');
        INSERT INTO watermarks(job_id, watermark_ts, artifact_rows, updated_at)
        VALUES (1,'2026-01-01T00:00:00Z',3,'2026-01-01T00:00:00Z');
        """
    )
    legacy.commit()
    legacy.close()

    init_db()

    conn = db_module.connect()
    try:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert {"cost_weight", "fixed_cost"} <= cols
        orch_cols = {
            r["name"] for r in conn.execute("PRAGMA table_info(orchestrations)").fetchall()
        }
        assert {"quota_scope", "quota_limit", "cost_total", "skipped_fuse"} <= orch_cols
        assert conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"] == 3
        assert conn.execute("SELECT COUNT(*) c FROM orchestrations").fetchone()["c"] == 1
        weights = {
            r["name"]: r["cost_weight"]
            for r in conn.execute("SELECT name, cost_weight FROM jobs").fetchall()
        }
        assert weights == {
            "ingest_orders": 1.0,
            "dim_customer": 2.0,
            "fact_order_daily": 3.0,
        }
    finally:
        conn.close()

    # the legacy job carries its historical watermark through untouched
    assert _fetchone("SELECT watermark_ts FROM watermarks WHERE job_id=1")[
        "watermark_ts"
    ] == "2026-01-01T00:00:00Z"

    result = _run()
    assert result["report"]["succeeded"] == 3
    assert result["report"]["cost_total"] == 6.0
