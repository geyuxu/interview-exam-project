"""Validated input contracts; sample identifiers never appear in business logic."""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9 _.-]+$")]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Order(InputModel):
    order_no: Identifier
    order_date: date
    status: str = Field(min_length=1, max_length=80)
    company: str = Field(min_length=1, max_length=200)
    customer: str = Field(min_length=1, max_length=200)
    phone: str = Field(max_length=40)
    email: str = Field(max_length=254)
    address: str = Field(min_length=1, max_length=500)
    postcode: str = Field(pattern=r"^\d{4}$")


class Shipment(InputModel):
    id: Identifier
    order_no: Identifier
    carrier: Literal["startrack", "auspost", "tnt"]
    tracking_no: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9-]+$")


class LineItem(InputModel):
    order_no: Identifier
    sku: Identifier
    quantity: int = Field(strict=True, gt=0, le=100000)
    shipment_id: Identifier


class OrderDataset(InputModel):
    orders: list[Order] = Field(min_length=1, max_length=100)
    shipments: list[Shipment] = Field(max_length=500)
    line_items: list[LineItem] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_relations(self):
        orders = {order.order_no for order in self.orders}
        shipments = {shipment.id: shipment for shipment in self.shipments}
        if len(orders) != len(self.orders) or len(shipments) != len(self.shipments):
            raise ValueError("订单编号和物流 ID 必须各自唯一")
        if any(shipment.order_no not in orders for shipment in self.shipments):
            raise ValueError("物流记录关联的订单不存在")
        for line in self.line_items:
            shipment = shipments.get(line.shipment_id)
            if line.order_no not in orders or shipment is None:
                raise ValueError("商品行关联的订单或物流记录不存在")
            if shipment.order_no != line.order_no:
                raise ValueError("商品行不能引用其他订单的物流记录")
        if any(not any(line.order_no == number for line in self.line_items) for number in orders):
            raise ValueError("每笔订单至少需要一行商品")
        if any(not any(line.shipment_id == key for line in self.line_items) for key in shipments):
            raise ValueError("每个物流记录至少需要关联一行商品")
        return self
