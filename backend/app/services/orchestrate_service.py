from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines.cost import chargeable_amount, job_cost, money, quota_gate, remaining_after
from app.engines.dependency import ready_by_upstream_success, topological_layers
from app.engines.job_runner import run_fixture_job
from app.repositories import jobs as jobs_repo
from app.repositories import ledger as ledger_repo
from app.repositories import orchestrations as orch_repo
from app.repositories import watermarks as wm_repo

SETTING_DEFAULTS = {"unit_price": "1.00", "quota_scope": "run", "quota_limit": ""}


def _settings(conn) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = dict(SETTING_DEFAULTS)
    out.update({r["key"]: r["value"] for r in rows})
    return out


def quota_config(conn) -> dict[str, Any]:
    s = _settings(conn)
    scope = s["quota_scope"] if s["quota_scope"] in ("run", "global") else "run"
    raw = (s["quota_limit"] or "").strip()
    unit_price = money(s["unit_price"] or "1.00")
    try:
        limit: float | None = money(raw) if raw else None
        if limit is not None and limit < 0:
            limit = None
    except (ValueError, ArithmeticError):
        limit = None
    return {"quota_scope": scope, "quota_limit": limit, "unit_price": unit_price}


def dashboard_stats() -> dict[str, Any]:
    conn = connect()
    try:
        cost = ledger_repo.summary(conn)
        cfg = quota_config(conn)
        return {
            "job_count": conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"],
            "enabled_jobs": conn.execute(
                "SELECT COUNT(*) c FROM jobs WHERE enabled=1"
            ).fetchone()["c"],
            "orchestration_count": conn.execute(
                "SELECT COUNT(*) c FROM orchestrations"
            ).fetchone()["c"],
            "attempt_count": conn.execute(
                "SELECT COUNT(*) c FROM job_attempts"
            ).fetchone()["c"],
            "watermarked_jobs": conn.execute(
                "SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL"
            ).fetchone()["c"],
            "total_cost": cost["total_cost"],
            "ledger_entries": cost["entry_count"],
            "fuse_skips": conn.execute(
                "SELECT COALESCE(SUM(skipped_fuse), 0) s FROM orchestrations"
            ).fetchone()["s"],
            "quota_scope": cfg["quota_scope"],
            "quota_limit": cfg["quota_limit"],
            "unit_price": cfg["unit_price"],
        }
    finally:
        conn.close()


def run_orchestration() -> dict[str, Any]:
    conn = connect()
    try:
        cfg = quota_config(conn)
        jobs = [j for j in jobs_repo.list_jobs(conn) if j["enabled"]]
        orch_id = orch_repo.create_orchestration(
            conn, quota_scope=cfg["quota_scope"], quota_limit=cfg["quota_limit"]
        )

        if cfg["quota_scope"] == "global":
            already = ledger_repo.total_charged(conn)
            remaining: float | None = (
                None if cfg["quota_limit"] is None else money(cfg["quota_limit"] - already)
            )
        else:
            remaining = cfg["quota_limit"]

        fused = False
        fuse_trigger: str | None = None
        fused_by: list[str] = []
        success_names: set[str] = set()
        counters = {
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "skipped_fuse": 0,
            "skipped_dep": 0,
        }
        run_cost = 0.0
        layer_count = 0
        layers = topological_layers(jobs)

        for layer in layers:
            layer_count += 1
            for job in layer:
                attempt_no = 1
                quote = job_cost(job, cfg["unit_price"])

                ready, dep_reason = ready_by_upstream_success(
                    job["depends_on"], success_names
                )
                if not ready:
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=attempt_no,
                        status="skipped_dep",
                        detail={"reason": dep_reason},
                    )
                    counters["skipped"] += 1
                    counters["skipped_dep"] += 1
                    continue

                gate = quota_gate(
                    fused=fused, remaining=remaining, projected=quote["amount"]
                )
                if gate == "would_exceed":
                    fused = True
                    fuse_trigger = job["name"]
                    try:
                        result = run_fixture_job(FIXTURES_DIR / job["fixture_path"])
                    except Exception as exc:  # noqa: BLE001
                        attempt_id = orch_repo.insert_attempt(
                            conn,
                            orchestration_id=orch_id,
                            job_id=job["id"],
                            attempt_no=attempt_no,
                            status="skipped_fuse",
                            detail={
                                "reason": (
                                    "quota would be exceeded: cost "
                                    f"{quote['amount']:.2f} > remaining {remaining:.2f}"
                                ),
                                "policy": "skip_on_quota",
                                "error": str(exc),
                                "projected_cost": quote["amount"],
                            },
                        )
                        bill = chargeable_amount(status="skipped_fuse", quote=quote)
                        ledger_repo.insert_charge(
                            conn,
                            orchestration_id=orch_id,
                            job_id=job["id"],
                            attempt_id=attempt_id,
                            amount=bill,
                            cost_mode=quote["cost_mode"],
                            cost_weight=quote["cost_weight"],
                            fixed_cost=quote["fixed_cost"],
                            unit_price=quote["unit_price"],
                        )
                        run_cost = money(run_cost + bill)
                        counters["skipped"] += 1
                        counters["skipped_fuse"] += 1
                        fused_by.append(job["name"])
                        continue

                    fuse_attempt = orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=attempt_no,
                        status="skipped_fuse",
                        detail={
                            "reason": (
                                "quota would be exceeded: cost "
                                f"{quote['amount']:.2f} > remaining {remaining:.2f}"
                            ),
                            "policy": "skip_on_quota",
                            "projected_cost": quote["amount"],
                            "result": result,
                        },
                    )
                    bill = chargeable_amount(status="skipped_fuse", quote=quote)
                    ledger_repo.insert_charge(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_id=fuse_attempt,
                        amount=bill,
                        cost_mode=quote["cost_mode"],
                        cost_weight=quote["cost_weight"],
                        fixed_cost=quote["fixed_cost"],
                        unit_price=quote["unit_price"],
                    )
                    run_cost = money(run_cost + bill)
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=attempt_no + 1,
                        status="success",
                        detail={**result, "cost": quote, "paired_fuse": True},
                    )
                    wm_repo.set_watermark(
                        conn, job["id"], result["watermark_ts"], result["artifact_rows"]
                    )
                    success_names.add(job["name"])
                    counters["succeeded"] += 1
                    counters["skipped"] += 1
                    counters["skipped_fuse"] += 1
                    fused_by.append(job["name"])
                    continue

                if fused and gate != "fuse_latched":
                    try:
                        result = run_fixture_job(FIXTURES_DIR / job["fixture_path"])
                    except Exception as exc:  # noqa: BLE001
                        orch_repo.insert_attempt(
                            conn,
                            orchestration_id=orch_id,
                            job_id=job["id"],
                            attempt_no=attempt_no,
                            status="failed",
                            detail={"error": str(exc), "billed": False},
                        )
                        counters["failed"] += 1
                        continue
                    detail = {**result, "cost": quote, "post_fuse": True}
                    attempt_id = orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=attempt_no,
                        status="success",
                        detail=detail,
                    )
                    bill = chargeable_amount(status="skipped_fuse", quote=quote)
                    ledger_repo.insert_charge(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_id=attempt_id,
                        amount=bill,
                        cost_mode=quote["cost_mode"],
                        cost_weight=quote["cost_weight"],
                        fixed_cost=quote["fixed_cost"],
                        unit_price=quote["unit_price"],
                    )
                    wm_repo.set_watermark(
                        conn, job["id"], result["watermark_ts"], result["artifact_rows"]
                    )
                    success_names.add(job["name"])
                    counters["succeeded"] += 1
                    counters["skipped_fuse"] += 1
                    fused_by.append(job["name"])
                    run_cost = money(run_cost + bill)
                    remaining = remaining_after(remaining, bill)
                    continue

                try:
                    result = run_fixture_job(FIXTURES_DIR / job["fixture_path"])
                except Exception as exc:  # noqa: BLE001
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=attempt_no,
                        status="failed",
                        detail={"error": str(exc), "billed": False},
                    )
                    counters["failed"] += 1
                    continue

                detail = {**result, "cost": quote}
                attempt_id = orch_repo.insert_attempt(
                    conn,
                    orchestration_id=orch_id,
                    job_id=job["id"],
                    attempt_no=attempt_no,
                    status="success",
                    detail=detail,
                )
                ledger_repo.insert_charge(
                    conn,
                    orchestration_id=orch_id,
                    job_id=job["id"],
                    attempt_id=attempt_id,
                    amount=quote["amount"],
                    cost_mode=quote["cost_mode"],
                    cost_weight=quote["cost_weight"],
                    fixed_cost=quote["fixed_cost"],
                    unit_price=quote["unit_price"],
                )
                wm_repo.set_watermark(
                    conn, job["id"], result["watermark_ts"], result["artifact_rows"]
                )
                success_names.add(job["name"])
                counters["succeeded"] += 1
                run_cost = money(run_cost + quote["amount"])
                remaining = remaining_after(remaining, quote["amount"])

        attempts = orch_repo.list_attempts(conn, orch_id)
        charges = ledger_repo.list_charges(conn, orch_id)
        ledger_total = round(sum(c["amount"] for c in charges), 2)
        report = {
            "orchestration_id": orch_id,
            "job_total": len(jobs),
            "succeeded": counters["succeeded"],
            "failed": counters["failed"],
            "skipped": counters["skipped"],
            "skipped_fuse": counters["skipped_fuse"],
            "skipped_dep": counters["skipped_dep"],
            "attempt_count": len(attempts),
            "ledger_entry_count": len(charges),
            "cost_total": ledger_total,
            "quota_scope": cfg["quota_scope"],
            "quota_limit": cfg["quota_limit"],
            "quota_remaining": None if remaining is None else money(remaining),
            "unit_price": cfg["unit_price"],
            "fused": fused,
            "fuse_trigger": fuse_trigger,
            "fuse_jobs": fused_by,
            "watermarked_jobs": conn.execute(
                "SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL"
            ).fetchone()["c"],
            "layer_count": layer_count,
        }
        if fused:
            status = "fused"
        elif counters["failed"] or counters["skipped_dep"]:
            status = "partial"
        else:
            status = "ok"
        orch_repo.finish_orchestration(
            conn,
            orch_id,
            status,
            report,
            cost_total=ledger_total,
            skipped_fuse=counters["skipped_fuse"],
        )
        conn.commit()
        return orch_repo.get_orchestration(conn, orch_id) or report
    finally:
        conn.close()
