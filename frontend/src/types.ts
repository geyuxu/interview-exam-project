export interface LineItem {
  sku: string;
  name: string;
  description: string;
  quantity: number;
  shipment_id: string;
  matched: boolean;
  rrp: string | null;
  unit_ex_gst: string | null;
  line_subtotal: string | null;
}

export interface Shipment {
  id: string;
  carrier: "startrack" | "auspost" | "tnt";
  tracking_no: string;
  skus: string[];
  shipping: {
    fee: string;
    state: string;
    reason: string;
    chargeable_kg: string | null;
  };
}

export interface Order {
  order_no: string;
  order_date: string;
  status: string;
  company: string;
  customer: string;
  phone: string;
  email: string;
  address: string;
  postcode: string;
  origin_postcode: string;
  quantity: number;
  items: LineItem[];
  shipments: Shipment[];
  warnings: string[];
  totals: {
    complete: boolean;
    subtotal: string | null;
    gst: string | null;
    shipment_fee: string;
    rounding_adjustment: string | null;
    total: string | null;
  };
}

export interface Tracking {
  state: string;
  status: string | null;
  last_update: string | null;
  events: {
    description: string;
    date: string | null;
    location: string | null;
    article_id: string | null;
  }[];
  message: string;
  environment: string | null;
  checked_at: string;
  cached?: boolean;
}
