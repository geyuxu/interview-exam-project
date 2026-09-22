"""Load product snapshots and calculate independent orders using Decimal."""

import json
import re
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path

from .models import OrderDataset

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ZERO = Decimal("0")
CENT = Decimal("0.01")
GST_RATE = Decimal("0.10")


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def load_dataset() -> OrderDataset:
    return OrderDataset.model_validate_json((DATA_DIR / "orders.json").read_text(encoding="utf-8"))


def load_products() -> dict[str, dict]:
    rows = json.loads((DATA_DIR / "products.json").read_text(encoding="utf-8"))["rows"]
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("SKU"), str) or not isinstance(row.get("ProductName"), str) or not isinstance(row.get("Description", ""), str) for row in rows):
        raise ValueError("商品目录格式无效")
    products = {row["SKU"]: row for row in rows}
    if len(products) != len(rows):
        raise ValueError("商品目录中 SKU 重复")
    return products


def price_of(product: dict | None) -> Decimal | None:
    try:
        value = Decimal(str(product["RRP"])) if product else None
        return value if value is not None and value.is_finite() and 0 <= value <= 100000000 else None
    except (InvalidOperation, KeyError, TypeError):
        return None


def measurement(raw: str, units: dict[str, Decimal]) -> Decimal | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([^\s]+)\s*", str(raw))
    if not match or match[2] not in units:
        return None
    value = Decimal(match[1]) * units[match[2]]
    return value if 0 < value <= 100000000 else None


def shipping_estimate(lines: list[dict], postcode: str, carrier: str, enabled: bool) -> dict:
    result = {"fee": "0.00", "state": "not_estimated", "reason": "未启用运费估算", "chargeable_kg": None}
    if carrier == "tnt":
        return {**result, "reason": "TNT 未实现，相关运费按题目要求为零"}
    if not enabled:
        return result
    weight, volume = ZERO, ZERO
    for line in lines:
        p = line["product"]
        if not p:
            return {**result, "reason": "商品资料缺失，无法估算运费"}
        unit_weight = measurement(p.get("weight", ""), {"g": Decimal("0.001"), "kg": Decimal("1")})
        unit_volume = measurement(p.get("volume", ""), {"mm³": Decimal("0.001"), "cm³": Decimal("1"), "m³": Decimal("1000000")})
        if unit_volume is None:
            dimensions = [measurement(p.get(key, ""), {"mm": Decimal("0.1"), "cm": Decimal("1"), "m": Decimal("100")}) for key in ("length", "width", "height")]
            if all(dimension is not None for dimension in dimensions):
                unit_volume = dimensions[0] * dimensions[1] * dimensions[2]
                if unit_volume > 100000000:
                    unit_volume = None
        if unit_weight is None or unit_volume is None:
            return {**result, "reason": "重量或尺寸单位缺失/不支持，无法估算运费"}
        weight += unit_weight * line["quantity"]
        volume += unit_volume * line["quantity"]
    chargeable = max(weight + Decimal("0.2"), volume * Decimal("1.2") / Decimal("5000"))
    billed = chargeable.to_integral_value(rounding=ROUND_CEILING)
    zone_fee = Decimal("3") if postcode[0] != "2" else ZERO
    fee = Decimal("8") + Decimal("2.5") * billed + zone_fee
    return {"fee": money(fee), "state": "estimated", "reason": "演示估算：基础费 + 计费重量 + 邮区附加费；非承运商报价", "chargeable_kg": str(chargeable.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP))}


def build_orders(dataset: OrderDataset, products: dict[str, dict], estimate: bool = False) -> list[dict]:
    output = []
    for order in dataset.orders:
        lines, warnings = [], []
        subtotal = ZERO
        displayed_lines = ZERO
        for item in (line for line in dataset.line_items if line.order_no == order.order_no):
            product = products.get(item.sku)
            price = price_of(product)
            unit = price / (1 + GST_RATE) if price is not None else None
            line_total = unit * item.quantity if unit is not None else None
            if line_total is not None:
                subtotal += line_total
                displayed_lines += line_total.quantize(CENT, rounding=ROUND_HALF_UP)
            else:
                warnings.append(f"{item.sku}：商品不存在或 RRP 无效，订单金额不完整")
            lines.append({**item.model_dump(), "name": product.get("ProductName", item.sku).strip() if product else item.sku,
                          "description": product.get("Description", "").strip() if product else "",
                          "product": product, "matched": price is not None,
                          "rrp": money(price) if price is not None else None,
                          "unit_ex_gst": money(unit) if unit is not None else None,
                          "line_subtotal": money(line_total) if line_total is not None else None})
        shipments = []
        for shipment in (s for s in dataset.shipments if s.order_no == order.order_no):
            shipment_lines = [line for line in lines if line["shipment_id"] == shipment.id]
            shipments.append({**shipment.model_dump(), "skus": [line["sku"] for line in shipment_lines],
                              "shipping": shipping_estimate(shipment_lines, order.postcode, shipment.carrier, estimate)})
        shipment_fee = sum((Decimal(s["shipping"]["fee"]) for s in shipments), ZERO)
        gst = (subtotal * GST_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
        rounded_subtotal = subtotal.quantize(CENT, rounding=ROUND_HALF_UP)
        output.append({**order.model_dump(mode="json"), "currency": "AUD", "origin_postcode": "2111",
                       "items": [{k: v for k, v in line.items() if k != "product"} for line in lines],
                       "shipments": shipments, "warnings": warnings, "quantity": sum(line["quantity"] for line in lines),
                       "totals": {"complete": not warnings, "subtotal": money(subtotal) if not warnings else None,
                                  "gst": money(gst) if not warnings else None, "shipment_fee": money(shipment_fee),
                                  "rounding_adjustment": money(rounded_subtotal - displayed_lines) if not warnings else None,
                                  "total": money(rounded_subtotal + gst + shipment_fee) if not warnings else None}})
    return output
