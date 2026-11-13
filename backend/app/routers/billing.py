from fastapi import APIRouter, HTTPException

from app.db import connect
from app.engines.cost import money
from app.repositories import ledger as ledger_repo
from app.schemas.entities import QuotaBody
from app.services.orchestrate_service import quota_config

router = APIRouter(tags=["billing"])


@router.get("/ledger")
def list_ledger(orchestration_id: int | None = None):
    conn = connect()
    try:
        rows = ledger_repo.list_charges(conn, orchestration_id)
        return {
            "entries": rows,
            "total_cost": round(sum(r["amount"] for r in rows), 2),
            "entry_count": len(rows),
            "orchestration_id": orchestration_id,
        }
    finally:
        conn.close()


def _quota_payload(conn) -> dict:
    cfg = quota_config(conn)
    spent = ledger_repo.total_charged(conn)
    cfg["global_spent"] = spent
    # a remaining figure only makes sense while the active scope is global
    cfg["global_remaining"] = (
        None
        if cfg["quota_scope"] != "global" or cfg["quota_limit"] is None
        else money(cfg["quota_limit"] - spent)
    )
    return cfg


@router.get("/quota")
def get_quota():
    conn = connect()
    try:
        return _quota_payload(conn)
    finally:
        conn.close()


@router.put("/quota")
def put_quota(body: QuotaBody):
    conn = connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            ("quota_scope", body.quota_scope),
        )
        conn.execute(
            "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
            (
                "quota_limit",
                "" if body.quota_limit is None else f"{money(body.quota_limit):.2f}",
            ),
        )
        if body.unit_price is not None:
            conn.execute(
                "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                ("unit_price", f"{money(body.unit_price):.2f}"),
            )
        conn.commit()
        return _quota_payload(conn)
    finally:
        conn.close()


@router.get("/orchestrations/{orch_id}/reconcile")
def reconcile(orch_id: int):
    conn = connect()
    try:
        from app.repositories import orchestrations as orch_repo

        orch = orch_repo.get_orchestration(conn, orch_id)
        if not orch:
            raise HTTPException(404, "not found")
        check = ledger_repo.reconcile(conn, orch_id)
        report = orch["report"]
        attempts = orch_repo.list_attempts(conn, orch_id)
        by_status: dict[str, int] = {}
        for a in attempts:
            by_status[a["status"]] = by_status.get(a["status"], 0) + 1
        checks = {
            "attempt_count": {
                "report": report.get("attempt_count"),
                "actual": len(attempts),
                "ok": report.get("attempt_count") == len(attempts),
            },
            "ledger_entry_count": {
                "report": report.get("ledger_entry_count"),
                "actual": check["entry_count"],
                "ok": report.get("ledger_entry_count") == check["entry_count"],
            },
            "cost_total": {
                "report": report.get("cost_total"),
                "actual": check["ledger_total"],
                "ok": abs(float(report.get("cost_total") or 0) - check["ledger_total"])
                <= 0.001,
            },
            "succeeded": {
                "report": report.get("succeeded"),
                "actual": by_status.get("success", 0),
                "ok": report.get("succeeded") == by_status.get("success", 0),
            },
            "skipped_fuse": {
                "report": report.get("skipped_fuse"),
                "actual": by_status.get("skipped_fuse", 0),
                "ok": report.get("skipped_fuse") == by_status.get("skipped_fuse", 0),
            },
        }
        return {
            "orchestration_id": orch_id,
            "status": orch["status"],
            "checks": checks,
            "consistent": all(c["ok"] for c in checks.values()),
        }
    finally:
        conn.close()
