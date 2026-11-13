from pydantic import BaseModel, Field


class MaxAttemptsBody(BaseModel):
    max_attempts: int = Field(ge=1, le=10)


class CostBody(BaseModel):
    cost_weight: float = Field(ge=0, le=10000)
    fixed_cost: float | None = Field(default=None, ge=0, le=1000000)


class QuotaBody(BaseModel):
    quota_scope: str = Field(pattern="^(run|global)$")
    quota_limit: float | None = Field(default=None, ge=0, le=1000000)
    unit_price: float | None = Field(default=None, ge=0, le=1000000)
