from fastapi import APIRouter, HTTPException

from app.db import connect
from app.engines.cost import money
from app.repositories import jobs as jobs_repo
from app.schemas.entities import CostBody, MaxAttemptsBody

router = APIRouter(tags=["jobs"])


def _decorate(conn, job: dict) -> dict:
    from app.services.orchestrate_service import quota_config

    cfg = quota_config(conn)
    expected = (
        money(job["fixed_cost"])
        if job["fixed_cost"] is not None
        else money(float(job["cost_weight"] or 0) * cfg["unit_price"])
    )
    out = dict(job)
    out["cost_estimate"] = expected
    out["cost_mode"] = "fixed" if job["fixed_cost"] is not None else "weighted"
    out["unit_price"] = cfg["unit_price"]
    return out


@router.get("/jobs")
def list_jobs():
    conn = connect()
    try:
        return [_decorate(conn, j) for j in jobs_repo.list_jobs(conn)]
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/max-attempts")
def patch_max_attempts(job_id: int, body: MaxAttemptsBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        jobs_repo.update_max_attempts(conn, job_id, body.max_attempts)
        conn.commit()
        return _decorate(conn, jobs_repo.get_job(conn, job_id))
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/cost")
def patch_cost(job_id: int, body: CostBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        fixed = None if body.fixed_cost is None else money(body.fixed_cost)
        jobs_repo.update_cost(
            conn,
            job_id,
            cost_weight=float(body.cost_weight),
            fixed_cost=fixed,
        )
        conn.commit()
        return _decorate(conn, jobs_repo.get_job(conn, job_id))
    finally:
        conn.close()
