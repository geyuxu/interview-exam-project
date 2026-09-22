<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { ZodType } from "zod";
import { OrdersResponseSchema, TrackingSchema } from "./contracts";
import type { Order, Shipment, Tracking } from "./contracts";

const orders = ref<Order[]>([]);
const selected = ref("");
const query = ref("");
const loading = ref(true);
const error = ref("");
const estimate = ref(false);
let appliedEstimate = false;
const imported = ref<unknown>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const tracking = ref<Record<string, Tracking>>({});
const trackingLoading = ref<Record<string, boolean>>({});
const controllers = new Set<AbortController>();
let orderRequest: AbortController | undefined;
let generation = 0;

const filtered = computed(() => {
  const term = query.value.trim().toLowerCase();
  return orders.value.filter((order) =>
    [
      order.order_no,
      order.company,
      order.customer,
      ...order.items.map((item) => item.sku),
    ].some((value) => value.toLowerCase().includes(term)),
  );
});
const active = computed(
  () =>
    filtered.value.find((order) => order.order_no === selected.value) ??
    filtered.value[0],
);
const money = (value: string | null) => {
  if (value === null) return "—";
  const negative = value.startsWith("-");
  const [integer = "0", fraction = "00"] = value.replace(/^-/, "").split(".");
  return `${negative ? "-" : ""}A$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;
};
const date = (value: string) => value.split("-").reverse().join("/");
const carrierName = (carrier: string) =>
  ({ startrack: "StarTrack", auspost: "Australia Post", tnt: "TNT" })[
    carrier
  ] ?? carrier;
const trackingLabel = (result?: Tracking) =>
  result
    ? ({
        available: "Available",
        not_implemented: "Not integrated",
        not_configured: "Not configured",
        unavailable: "Unavailable",
      }[result.state] ?? "Unavailable")
    : "Pending";

async function request<T>(
  path: string,
  schema: ZodType<T>,
  init: RequestInit = {},
  controller = new AbortController(),
): Promise<T> {
  controllers.add(controller);
  const timeout = window.setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, { ...init, signal: controller.signal });
    const body: unknown = await response.json();
    if (!response.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? body.detail
          : null;
      throw new Error(
        Array.isArray(detail)
          ? detail
              .slice(0, 3)
              .map((item) =>
                item && typeof item === "object"
                  ? `${item.field ?? "Input"}: ${item.message ?? "Validation failed"}`
                  : "Validation failed",
              )
              .join("；")
          : typeof detail === "string"
            ? detail
            : "Request failed. Please try again later.",
      );
    }
    const validated = schema.safeParse(body);
    if (!validated.success)
      throw new Error(
        "The server returned an unexpected data structure. Please retry or check the backend.",
      );
    return validated.data;
  } catch (err) {
    if (err instanceof SyntaxError)
      throw new Error(
        "The server returned invalid data. Please check that the backend is running.",
      );
    if (err instanceof DOMException && err.name === "AbortError")
      throw new Error(
        "The request timed out or was cancelled. Please try again.",
      );
    if (err instanceof TypeError)
      throw new Error(
        "Cannot connect to the server. Please check that the backend is running.",
      );
    throw err;
  } finally {
    window.clearTimeout(timeout);
    controllers.delete(controller);
  }
}

async function loadOrders(
  dataset: unknown = imported.value,
  resetSearch = false,
) {
  orderRequest?.abort();
  const controller = new AbortController();
  orderRequest = controller;
  loading.value = true;
  error.value = "";
  const requestedEstimate = estimate.value;
  try {
    const result = await request(
      `/api/orders${dataset ? "/preview" : ""}?estimate=${requestedEstimate}`,
      OrdersResponseSchema,
      dataset
        ? {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(dataset),
          }
        : {},
      controller,
    );
    if (controller !== orderRequest) return;
    const shipmentSignature = (list: Order[]) =>
      JSON.stringify(
        list.flatMap((order) =>
          order.shipments.map((shipment) => [
            shipment.id,
            shipment.carrier,
            shipment.tracking_no,
          ]),
        ),
      );
    if (
      dataset !== imported.value ||
      shipmentSignature(result.orders) !== shipmentSignature(orders.value)
    ) {
      generation++;
      tracking.value = {};
      trackingLoading.value = {};
    }
    imported.value = dataset;
    appliedEstimate = requestedEstimate;
    orders.value = result.orders;
    if (resetSearch) query.value = "";
    if (!result.orders.some((order) => order.order_no === selected.value))
      selected.value = result.orders[0]?.order_no ?? "";
  } catch (err) {
    if (controller === orderRequest) {
      estimate.value = appliedEstimate;
      error.value =
        err instanceof Error
          ? err.message
          : "Cannot connect to the server. Please check that the backend is running.";
    }
  } finally {
    if (controller === orderRequest) loading.value = false;
  }
}

async function queryTracking(shipment: Shipment) {
  if (trackingLoading.value[shipment.id]) return;
  const current = generation;
  trackingLoading.value[shipment.id] = true;
  try {
    const result = await request("/api/tracking", TrackingSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        carrier: shipment.carrier,
        tracking_no: shipment.tracking_no,
      }),
    });
    if (current === generation) tracking.value[shipment.id] = result;
  } catch (err) {
    if (current === generation)
      tracking.value[shipment.id] = {
        state: "unavailable",
        status: null,
        last_update: null,
        events: [],
        environment: null,
        message:
          err instanceof Error
            ? err.message
            : "Tracking request failed. Please try again.",
        checked_at: new Date().toISOString(),
      };
  } finally {
    if (current === generation) trackingLoading.value[shipment.id] = false;
  }
}

async function importFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    if (file.size > 1024 * 1024)
      throw new Error("Please select an order JSON file no larger than 1 MB.");
    const dataset: unknown = JSON.parse(
      (await file.text()).replace(/^\uFEFF/, ""),
    );
    if (!dataset || typeof dataset !== "object" || Array.isArray(dataset))
      throw new Error(
        "The file must be a JSON object containing orders, shipments and line_items.",
      );
    await loadOrders(dataset, true);
  } catch (err) {
    error.value =
      err instanceof Error ? err.message : "Could not read the order file.";
  } finally {
    input.value = "";
  }
}

watch(active, (order) => {
  order?.shipments.forEach((shipment) => {
    if (!tracking.value[shipment.id]) void queryTracking(shipment);
  });
});
onMounted(() => loadOrders());
onUnmounted(() => controllers.forEach((controller) => controller.abort()));
</script>

<template>
  <div class="workspace">
    <aside class="sidebar">
      <a class="brand" href="/" aria-label="Order workspace home"
        ><span class="brand-mark">a.</span
        ><span>AERIS<span class="brand-sub">ORDER WORKSPACE</span></span></a
      >
      <div class="sidebar-heading">
        <span>Orders</span><span class="count">{{ orders.length }}</span>
      </div>
      <label class="search"
        ><span aria-hidden="true">⌕</span
        ><input
          v-model="query"
          aria-label="Search orders"
          placeholder="Order, customer or SKU"
          type="search"
      /></label>
      <nav class="order-list" aria-label="Order list">
        <button
          v-for="order in filtered"
          :key="order.order_no"
          class="order-button"
          :class="{ selected: active?.order_no === order.order_no }"
          :aria-current="
            active?.order_no === order.order_no ? 'true' : undefined
          "
          @click="selected = order.order_no"
        >
          <span class="order-button-top"
            ><span>{{ order.company }}</span
            ><span
              class="status-dot"
              :class="{ complete: order.status === 'Completed' }"
            ></span
          ></span>
          <span class="order-number">{{ order.order_no }}</span>
          <span class="order-button-bottom"
            ><span>{{ order.customer }}</span
            ><span>{{ date(order.order_date) }}</span></span
          >
        </button>
        <p v-if="!filtered.length && !loading" class="sidebar-empty">
          No matching orders
        </p>
      </nav>
      <div class="sidebar-footer">
        <span class="small-dot"></span> Australia · AUD
        <div>IT CODING ASSESSMENT</div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <span
          >Workspace <span class="separator">/</span>
          <strong>Order details</strong></span
        ><span class="environment">Assessment project</span>
      </header>
      <div class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">ORDERS & DELIVERY</p>
            <h1>Order details</h1>
            <p class="muted">Review products, totals and delivery progress.</p>
          </div>
          <div class="actions">
            <a
              class="button secondary"
              href="/api/orders/template"
              download="orders.json"
              >Download template</a
            >
            <input
              ref="fileInput"
              class="visually-hidden"
              type="file"
              accept=".json,application/json"
              @change="importFile"
            /><button
              class="button secondary"
              :disabled="loading"
              @click="fileInput?.click()"
            >
              Import JSON</button
            ><button
              class="button secondary"
              :disabled="loading"
              @click="loadOrders()"
            >
              Refresh orders
            </button>
          </div>
        </div>

        <div v-if="error" class="alert error" role="alert">
          <strong>Action incomplete</strong><span>{{ error }}</span
          ><button class="text-button" @click="loadOrders()">Retry</button>
        </div>
        <div v-if="imported" class="alert info">
          <span
            >Viewing imported orders. Data stays in this page; tracking is
            queried through the carrier API.</span
          ><button class="text-button" @click="loadOrders(null, true)">
            Back to initial orders
          </button>
        </div>
        <div v-if="loading" class="loading" role="status">
          Loading orders and products…
        </div>

        <template v-else-if="active">
          <section class="order-header card">
            <div>
              <div class="order-title">
                <h2>{{ active.order_no }}</h2>
                <span
                  class="badge"
                  :class="active.status === 'Completed' ? 'green' : 'blue'"
                  >{{ active.status }}</span
                >
              </div>
              <p class="muted">
                {{ active.company }}<span class="separator">·</span>Ordered
                {{ date(active.order_date) }}
              </p>
            </div>
            <div class="header-total">
              <span>Order total · AUD</span
              ><strong>{{ money(active.totals.total) }}</strong>
            </div>
          </section>

          <div class="stats">
            <div>
              <span>Line items</span
              ><strong>{{
                active.items.length.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>Total units</span
              ><strong>{{
                active.quantity.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>Shipments</span
              ><strong>{{
                active.shipments.length.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>Origin → Destination postcode</span
              ><strong class="route"
                >{{ active.origin_postcode }} <span>→</span>
                {{ active.postcode }}</strong
              >
            </div>
          </div>

          <div
            v-for="warning in active.warnings"
            :key="warning"
            class="alert error"
            role="alert"
          >
            {{ warning }}
          </div>
          <div class="detail-grid">
            <div class="primary-column">
              <section class="card items-card">
                <div class="section-heading">
                  <h2>Products</h2>
                  <span class="subtle"
                    >{{ active.items.length }} SKUs · RRP includes GST</span
                  >
                </div>
                <p class="table-scroll-hint">
                  Swipe to see quantities and prices →
                </p>
                <div class="table-scroll">
                  <table>
                    <caption class="visually-hidden">
                      Order products and amounts excluding GST
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">Product</th>
                        <th scope="col">Qty</th>
                        <th scope="col">RRP / Unit ex GST</th>
                        <th scope="col">Subtotal ex GST</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(item, index) in active.items"
                        :key="`${item.sku}-${index}`"
                      >
                        <td>
                          <div class="product">
                            <div
                              class="product-image"
                              role="img"
                              :aria-label="`Product ${index + 1} placeholder image`"
                            >
                              <svg viewBox="0 0 40 48" aria-hidden="true">
                                <rect
                                  x="12"
                                  y="3"
                                  width="16"
                                  height="8"
                                  rx="2"
                                />
                                <rect
                                  x="9"
                                  y="12"
                                  width="22"
                                  height="32"
                                  rx="6"
                                />
                                <path d="M10 24h20v11H10" />
                                <path d="M16 28h8M20 25v7" /></svg
                              ><span>{{
                                String(index + 1).padStart(2, "0")
                              }}</span>
                            </div>
                            <div>
                              <span class="sku">{{ item.sku }}</span>
                              <h3>{{ item.name }}</h3>
                              <span class="shipment-tag">{{
                                item.shipment_id
                              }}</span
                              ><span v-if="!item.matched" class="missing"
                                >Missing data</span
                              >
                              <details
                                v-if="
                                  item.description && item.description !== '.'
                                "
                                class="product-description"
                              >
                                <summary>Description</summary>
                                <p>{{ item.description }}</p>
                              </details>
                            </div>
                          </div>
                        </td>
                        <td class="numeric">{{ item.quantity }}</td>
                        <td class="numeric price">
                          <span>{{ money(item.rrp) }}</span
                          ><small>{{ money(item.unit_ex_gst) }} ex GST</small>
                        </td>
                        <td class="numeric line-total">
                          {{ money(item.line_subtotal) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="table-note">
                  Product placeholder images. Amounts retain full precision and
                  are displayed to two decimal places.<span
                    v-if="
                      active.totals.rounding_adjustment &&
                      active.totals.rounding_adjustment !== '0.00'
                    "
                    >{{ " " }}The subtotal includes a display rounding
                    adjustment of
                    {{ money(active.totals.rounding_adjustment) }}
                    relative to the sum of displayed line totals. It is
                    calculated from unrounded amounts.</span
                  >
                </div>
              </section>

              <section class="card tracking-section">
                <div class="section-heading">
                  <h2>Shipment tracking</h2>
                  <span class="subtle">Track each shipment</span>
                </div>
                <p class="section-intro">
                  Australia Post / StarTrack use a test environment. Results do
                  not represent live parcel status.
                </p>
                <article
                  v-for="shipment in active.shipments"
                  :key="shipment.id"
                  class="shipment-card"
                >
                  <div class="shipment-header">
                    <div class="carrier-icon" :class="shipment.carrier">
                      {{
                        shipment.carrier === "tnt"
                          ? "TNT"
                          : shipment.carrier === "auspost"
                            ? "AP"
                            : "ST"
                      }}
                    </div>
                    <div class="shipment-identity">
                      <h3>
                        {{ carrierName(shipment.carrier) }}
                        <span>{{ shipment.id }}</span>
                      </h3>
                      <code>{{ shipment.tracking_no }}</code>
                    </div>
                    <span
                      class="badge"
                      :class="
                        tracking[shipment.id]?.state === 'available'
                          ? 'green'
                          : 'neutral'
                      "
                      >{{
                        trackingLoading[shipment.id]
                          ? "Loading"
                          : trackingLabel(tracking[shipment.id])
                      }}</span
                    >
                  </div>
                  <div class="shipment-skus">
                    Includes {{ shipment.skus.join(" · ") }}
                  </div>
                  <div>
                    <div class="tracking-result" aria-live="polite">
                      <strong v-if="tracking[shipment.id]?.status">{{
                        tracking[shipment.id]?.status
                      }}</strong>
                      <p>
                        {{
                          trackingLoading[shipment.id]
                            ? "Contacting the carrier…"
                            : (tracking[shipment.id]?.message ??
                              "Waiting for tracking information.")
                        }}
                      </p>
                      <p
                        v-if="tracking[shipment.id]?.error_code"
                        class="subtle"
                      >
                        API error code: {{ tracking[shipment.id]?.error_code }}
                      </p>
                      <p v-if="tracking[shipment.id]?.cached" class="subtle">
                        Cached result from the last 60 seconds.
                      </p>
                      <p
                        v-if="tracking[shipment.id]?.last_update"
                        class="subtle"
                      >
                        Last updated: {{ tracking[shipment.id]?.last_update }}
                      </p>
                    </div>
                    <details
                      v-if="tracking[shipment.id]?.events.length"
                      class="events"
                    >
                      <summary>
                        View
                        {{ tracking[shipment.id]?.events.length }} tracking
                        events
                      </summary>
                      <ol>
                        <li
                          v-for="(event, index) in tracking[shipment.id]
                            ?.events"
                          :key="index"
                        >
                          <strong>{{ event.description }}</strong
                          ><span>{{ event.location }}</span
                          ><time>{{ event.date ?? "Time not provided" }}</time>
                        </li>
                      </ol>
                    </details>
                  </div>
                  <div class="shipment-footer">
                    <span>Shipment fee {{ money(shipment.shipping.fee) }}</span
                    ><button
                      v-if="shipment.carrier !== 'tnt'"
                      class="text-button"
                      :disabled="trackingLoading[shipment.id]"
                      @click="queryTracking(shipment)"
                    >
                      Refresh tracking ↗
                    </button>
                  </div>
                </article>
                <p class="section-footnote">
                  Results are cached for 60 seconds. Event times retain the
                  carrier format and time zone information.
                </p>
              </section>
            </div>

            <div class="secondary-column">
              <section class="card shipping-address">
                <div class="section-heading">
                  <h2>Ship to</h2>
                  <span class="subtle">AU</span>
                </div>
                <div class="address-body">
                  <div class="avatar">
                    {{
                      active.customer
                        .split(" ")
                        .map((part) => part[0])
                        .join("")
                        .slice(0, 2)
                    }}
                  </div>
                  <h3>{{ active.customer }}</h3>
                  <p class="muted">{{ active.company }}</p>
                  <hr />
                  <address>{{ active.address }}<br />Australia</address>
                  <a :href="`tel:${active.phone.replaceAll(' ', '')}`">{{
                    active.phone
                  }}</a
                  ><a :href="`mailto:${active.email}`">{{ active.email }}</a>
                </div>
                <div class="origin">
                  <span class="small-dot"></span> From Ryde, NSW 2111
                </div>
              </section>

              <section class="card summary-card">
                <div class="section-heading">
                  <h2>Order summary</h2>
                  <span class="subtle">AUD</span>
                </div>
                <div class="summary-body">
                  <div class="summary-row">
                    <span>Subtotal ex GST</span
                    ><strong>{{ money(active.totals.subtotal) }}</strong>
                  </div>
                  <div class="summary-row">
                    <span>GST <small>10%</small></span
                    ><strong>{{ money(active.totals.gst) }}</strong>
                  </div>
                  <div class="summary-row">
                    <span
                      >Shipping
                      <small>{{
                        estimate ? "estimated" : "not estimated"
                      }}</small></span
                    ><strong>{{ money(active.totals.shipment_fee) }}</strong>
                  </div>
                  <div class="grand-total">
                    <span>Order total</span
                    ><strong>{{ money(active.totals.total) }}</strong>
                  </div>
                  <p v-if="!active.totals.complete" class="missing">
                    Product data is incomplete. The order total is unavailable.
                  </p>
                  <label class="estimate-toggle"
                    ><input
                      v-model="estimate"
                      type="checkbox"
                      @change="loadOrders()"
                    /><span>Estimate shipping</span></label
                  >
                  <p class="summary-note">
                    {{
                      estimate
                        ? "Estimates are illustrative, not carrier quotes. TNT shipping is zero."
                        : "Shipping defaults to A$0.00 when estimates are disabled."
                    }}
                  </p>
                  <details class="fee-details">
                    <summary>Shipping calculation details</summary>
                    <div
                      v-for="shipment in active.shipments"
                      :key="shipment.id"
                    >
                      <strong
                        >{{ shipment.id }} ·
                        {{ money(shipment.shipping.fee) }}</strong
                      >
                      <p>{{ shipment.shipping.reason }}</p>
                      <p v-if="shipment.shipping.chargeable_kg">
                        Chargeable weight
                        {{ shipment.shipping.chargeable_kg }} kg
                      </p>
                    </div>
                  </details>
                </div>
              </section>
            </div>
          </div>
          <footer class="page-footer">
            <span
              >Products from a SQL query snapshot · Each order is calculated
              separately</span
            ><span>Australian dollars · GST included in RRP</span>
          </footer>
        </template>
        <div v-else-if="!error" class="empty-state">
          <h2>No orders found</h2>
          <p>Try another order number, customer name or SKU.</p>
          <button class="button secondary" @click="query = ''">
            Clear search
          </button>
        </div>
      </div>
    </main>
  </div>
</template>
