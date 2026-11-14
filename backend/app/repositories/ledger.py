"""Billing ledger: one charge row per executed (successful) job attempt."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlite3


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def insert_charge(
    conn: sqlite3.Connection,
    *,
    orchestration_id: int,
    job_id: int,
    attempt_id: int,
    amount: float,
    cost_mode: str,
    cost_weight: float,
    fixed_cost: float | None,
    unit_price: float,
) -> int:
    # Only executed attempts are billed. Fuse/dependency skips never run and
    # must not reach this function: the orchestration service is the sole
    # caller and writes a charge exclusively on success.
    cur = conn.execute(
        """
        INSERT INTO cost_ledger(
            orchestration_id, job_id, attempt_id, amount, cost_mode,
            cost_weight, fixed_cost, unit_price, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            orchestration_id,
            job_id,
            attempt_id,
            amount,
            cost_mode,
            cost_weight,
            fixed_cost,
            unit_price,
            _now(),
        ),
    )
    return int(cur.lastrowid)


def list_charges(
    conn: sqlite3.Connection, orchestration_id: int | None = None
) -> list[dict[str, Any]]:
    base = """
        SELECT l.id, l.orchestration_id, l.job_id, j.name AS job_name,
               l.attempt_id, l.amount, l.cost_mode, l.cost_weight,
               l.fixed_cost, l.unit_price, l.created_at
        FROM cost_ledger l JOIN jobs j ON j.id=l.job_id
    """
    if orchestration_id is None:
        rows = conn.execute(base + " ORDER BY l.id").fetchall()
    else:
        rows = conn.execute(
            base + " WHERE l.orchestration_id=? ORDER BY l.id", (orchestration_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def total_charged(conn: sqlite3.Connection, orchestration_id: int | None = None) -> float:
    if orchestration_id is None:
        row = conn.execute("SELECT COALESCE(SUM(amount), 0) s FROM cost_ledger").fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) s FROM cost_ledger WHERE orchestration_id=?",
            (orchestration_id,),
        ).fetchone()
    return round(float(row["s"]), 2)


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(amount), 0) s FROM cost_ledger"
    ).fetchone()
    return {"entry_count": int(row["n"]), "total_cost": round(float(row["s"]), 2)}


def reconcile(conn: sqlite3.Connection, orchestration_id: int) -> dict[str, Any]:
    """Compare stored report aggregates against attempts and ledger rows."""
    charges = list_charges(conn, orchestration_id)
    attempts = conn.execute(
        "SELECT COUNT(*) c FROM job_attempts WHERE orchestration_id=?", (orchestration_id,)
    ).fetchone()["c"]
    return {
        "orchestration_id": orchestration_id,
        "entry_count": len(charges),
        "ledger_total": round(sum(c["amount"] for c in charges), 2),
        "attempt_count": int(attempts),
    }
