import { z } from "zod";

const money = z.string().regex(/^\d+\.\d{2}$/);
const nullableMoney = money.nullable();
export const ShipmentSchema = z.object({
  id: z.string(),
  carrier: z.enum(["startrack", "auspost", "tnt"]),
  tracking_no: z.string(),
  skus: z.array(z.string()),
  shipping: z.object({
    fee: money,
    state: z.enum(["estimated", "not_estimated"]),
    reason: z.string(),
    chargeable_kg: z.string().nullable(),
  }),
});
export const LineItemSchema = z.object({
  sku: z.string(),
  name: z.string(),
  description: z.string(),
  quantity: z.number().int().positive(),
  shipment_id: z.string(),
  matched: z.boolean(),
  rrp: nullableMoney,
  unit_ex_gst: nullableMoney,
  line_subtotal: nullableMoney,
});
export const OrderSchema = z.object({
  order_no: z.string(),
  order_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
  status: z.string(),
  company: z.string(),
  customer: z.string(),
  phone: z.string(),
  email: z.string(),
  address: z.string(),
  postcode: z.string(),
  origin_postcode: z.string(),
  quantity: z.number().int(),
  currency: z.literal("AUD"),
  items: z.array(LineItemSchema),
  shipments: z.array(ShipmentSchema),
  warnings: z.array(z.string()),
  totals: z.object({
    complete: z.boolean(),
    subtotal: nullableMoney,
    gst: nullableMoney,
    shipment_fee: money,
    rounding_adjustment: z
      .string()
      .regex(/^-?\d+\.\d{2}$/)
      .nullable(),
    total: nullableMoney,
  }),
});
export const OrdersResponseSchema = z.object({
  orders: z.array(OrderSchema),
  source: z.enum(["assessment", "preview"]),
  estimate: z.boolean(),
});
export const TrackingSchema = z.object({
  state: z.enum([
    "available",
    "unavailable",
    "not_configured",
    "not_implemented",
  ]),
  status: z.string().nullable(),
  last_update: z.string().nullable(),
  events: z.array(
    z.object({
      description: z.string(),
      date: z.string().nullable(),
      location: z.string().nullable(),
      article_id: z.string().nullable(),
    }),
  ),
  message: z.string(),
  environment: z.string().nullable(),
  checked_at: z.string(),
  cached: z.boolean().optional(),
  http_status: z.number().int().nullable().optional(),
  error_code: z.string().nullable().optional(),
});
export type Order = z.infer<typeof OrderSchema>;
export type Shipment = z.infer<typeof ShipmentSchema>;
export type Tracking = z.infer<typeof TrackingSchema>;
