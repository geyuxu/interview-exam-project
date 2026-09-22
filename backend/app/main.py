"""HTTP entry point for the order assessment application."""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .middleware import RequestSizeLimit
from .models import OrderDataset, TrackingRequest
from .orders import build_orders, load_dataset, load_products
from .tracking import TrackingService

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
tracking_service = TrackingService()

app = FastAPI(
    title="Order Assessment API",
    description="订单、SKU 匹配、GST 计算、运费估算与承运商测试环境查询。",
    version="0.2.0",
)
app.add_middleware(RequestSizeLimit)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Return service availability without contacting external couriers."""
    return HealthResponse(status="ok", service="order-assessment-api")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"field": ".".join(map(str, error["loc"])), "message": error["msg"]}
                for error in exc.errors()
            ]
        },
    )


def read_source(loader):
    try:
        return loader()
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "本地订单或商品数据无效，请检查数据文件") from None


@app.get("/api/orders", tags=["orders"])
def orders(estimate: bool = False):
    dataset, products = read_source(load_dataset), read_source(load_products)
    return {
        "orders": build_orders(dataset, products, estimate),
        "source": "assessment",
        "estimate": estimate,
    }


@app.post("/api/orders/preview", tags=["orders"])
def preview(dataset: OrderDataset, estimate: bool = False):
    products = read_source(load_products)
    return {
        "orders": build_orders(dataset, products, estimate),
        "source": "preview",
        "estimate": estimate,
    }


@app.get("/api/shipments/{shipment_id}/tracking", tags=["tracking"])
def tracking(shipment_id: str):
    dataset = read_source(load_dataset)
    shipment = next((s for s in dataset.shipments if s.id == shipment_id), None)
    if shipment is None:
        raise HTTPException(404, "物流记录不存在")
    return tracking_service.get(shipment)


@app.get("/api/orders/template", tags=["orders"])
def template():
    dataset = read_source(load_dataset)
    return JSONResponse(
        dataset.model_dump(mode="json"),
        headers={"Content-Disposition": 'attachment; filename="orders.json"'},
    )


@app.post("/api/tracking", tags=["tracking"])
def track_imported(request: TrackingRequest):
    """Query a validated consignment without coupling to sample orders or SKUs."""
    return tracking_service.get(request)
