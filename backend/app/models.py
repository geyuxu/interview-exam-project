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


class TrackingRequest(InputModel):
    carrier: Literal["startrack", "auspost", "tnt"]
    tracking_no: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9-]+$")


class Shipment(TrackingRequest):
    id: Identifier
    order_no: Identifier


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
            raise ValueError("Order numbers and shipment IDs must each be unique.")
        if any(shipment.order_no not in orders for shipment in self.shipments):
            raise ValueError("A shipment references an order that does not exist.")
        for line in self.line_items:
            shipment = shipments.get(line.shipment_id)
            if line.order_no not in orders or shipment is None:
                raise ValueError("A line item references an order or shipment that does not exist.")
            if shipment.order_no != line.order_no:
                raise ValueError("A line item cannot reference a shipment from another order.")
        if any(not any(line.order_no == number for line in self.line_items) for number in orders):
            raise ValueError("Each order must contain at least one line item.")
        if any(not any(line.shipment_id == key for line in self.line_items) for key in shipments):
            raise ValueError("Each shipment must have at least one line item.")
        return self
