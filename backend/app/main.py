"""HTTP entry point for the order assessment application."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Order Assessment API",
    description="订单、商品匹配、GST 计算与物流查询服务。当前为项目初始化版本。",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Return service availability without contacting external couriers."""
    return HealthResponse(status="ok", service="order-assessment-api")
