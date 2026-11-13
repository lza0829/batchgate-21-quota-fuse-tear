"""Cost accounting and quota fuse policy.

Money is kept as decimal-quantized floats (2 dp). A job's run cost is either a
fixed fee or a weight multiplied by the configured unit price. Quota can be
scoped to a single run or globally across all charged runs.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")


def money(value: float | int | str | Decimal) -> float:
    """Round a monetary value to 2 decimals with half-up rounding."""
    return float(Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP))


def job_cost(job: dict[str, Any], unit_price: float) -> dict[str, Any]:
    """Return the cost snapshot for one execution of ``job``.

    ``fixed_cost`` wins when set; otherwise the weighted mode applies
    ``cost_weight * unit_price``.
    """
    fixed = job.get("fixed_cost")
    weight = float(job.get("cost_weight") or 0.0)
    if fixed is not None:
        mode = "fixed"
        amount = money(fixed)
    else:
        mode = "weighted"
        amount = money(Decimal(str(weight)) * Decimal(str(unit_price)))
    return {
        "cost_mode": mode,
        "cost_weight": weight,
        "fixed_cost": None if fixed is None else money(fixed),
        "unit_price": money(unit_price),
        "amount": amount,
    }


def quota_gate(*, fused: bool, remaining: float | None, projected: float) -> str:
    """Decide whether a runnable job may start."""
    if remaining is None:
        return "allow"
    if projected > remaining:
        return "would_exceed"
    if fused and remaining <= 0:
        return "fuse_latched"
    return "allow"


def remaining_after(remaining: float | None, amount: float) -> float | None:
    if remaining is None:
        return None
    return money(remaining - amount)


def chargeable_amount(*, status: str, quote: dict[str, Any]) -> float:
    """Amount to bill for an attempt."""
    if status in ("success", "skipped_fuse", "failed"):
        return float(quote.get("amount") or 0.0)
    return 0.0
