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
const orderStatus = (status: string) =>
  ({ Completed: "已完成", "In Transit": "运输中" })[status] ?? status;
const trackingLabel = (result?: Tracking) =>
  result
    ? ({
        available: "查询成功",
        not_implemented: "未实现",
        not_configured: "未配置",
        unavailable: "暂不可用",
      }[result.state] ?? "暂不可用")
    : "等待查询";

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
                  ? `${item.field ?? "输入"}: ${item.message ?? "校验失败"}`
                  : "校验失败",
              )
              .join("；")
          : typeof detail === "string"
            ? detail
            : "请求失败，请稍后重试",
      );
    }
    const validated = schema.safeParse(body);
    if (!validated.success)
      throw new Error("服务返回的数据结构不正确，请重试或检查后端");
    return validated.data;
  } catch (err) {
    if (err instanceof SyntaxError)
      throw new Error("服务返回了无效数据，请确认后端已启动");
    if (err instanceof DOMException && err.name === "AbortError")
      throw new Error("请求超时或已取消，请重试");
    if (err instanceof TypeError)
      throw new Error("无法连接服务，请确认后端已启动");
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
        err instanceof Error ? err.message : "无法连接服务，请确认后端已启动";
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
        message: err instanceof Error ? err.message : "查询失败，请重试",
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
      throw new Error("请选择小于 1 MB 的订单 JSON 文件");
    const dataset: unknown = JSON.parse(
      (await file.text()).replace(/^\uFEFF/, ""),
    );
    if (!dataset || typeof dataset !== "object" || Array.isArray(dataset))
      throw new Error(
        "文件必须是包含 orders、shipments 和 line_items 的 JSON 对象",
      );
    await loadOrders(dataset, true);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "订单文件读取失败";
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
      <a class="brand" href="/" aria-label="订单工作台首页"
        ><span class="brand-mark">a.</span
        ><span>AERIS<span class="brand-sub">ORDER WORKSPACE</span></span></a
      >
      <div class="sidebar-heading">
        <span>订单管理</span><span class="count">{{ orders.length }}</span>
      </div>
      <label class="search"
        ><span aria-hidden="true">⌕</span
        ><input
          v-model="query"
          aria-label="搜索订单"
          placeholder="搜索订单、客户或 SKU"
          type="search"
      /></label>
      <nav class="order-list" aria-label="订单列表">
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
          没有匹配的订单
        </p>
      </nav>
      <div class="sidebar-footer">
        <span class="small-dot"></span> 澳洲业务 · AUD
        <div>IT CODING ASSESSMENT</div>
      </div>
    </aside>

    <main class="main">
      <header class="topbar">
        <span
          >工作台 <span class="separator">/</span>
          <strong>订单详情</strong></span
        ><span class="environment">评估项目</span>
      </header>
      <div class="content">
        <div class="page-heading">
          <div>
            <p class="eyebrow">ORDERS & DELIVERY</p>
            <h1>订单详情</h1>
            <p class="muted">查看商品明细、金额与配送进度。</p>
          </div>
          <div class="actions">
            <a
              class="button secondary"
              href="/api/orders/template"
              download="orders.json"
              >下载订单模板</a
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
              导入 JSON</button
            ><button
              class="button secondary"
              :disabled="loading"
              @click="loadOrders()"
            >
              刷新订单
            </button>
          </div>
        </div>

        <div v-if="error" class="alert error" role="alert">
          <strong>操作未完成</strong><span>{{ error }}</span
          ><button class="text-button" @click="loadOrders()">重试</button>
        </div>
        <div v-if="imported" class="alert info">
          <span
            >正在查看导入订单。数据仅保留在当前页面，物流通过承运商接口查询。</span
          ><button class="text-button" @click="loadOrders(null, true)">
            返回题目订单
          </button>
        </div>
        <div v-if="loading" class="loading" role="status">
          正在读取订单与商品数据…
        </div>

        <template v-else-if="active">
          <section class="order-header card">
            <div>
              <div class="order-title">
                <h2>{{ active.order_no }}</h2>
                <span
                  class="badge"
                  :class="active.status === 'Completed' ? 'green' : 'blue'"
                  >{{ orderStatus(active.status) }}</span
                >
              </div>
              <p class="muted">
                {{ active.company }}<span class="separator">·</span>下单日期
                {{ date(active.order_date) }}
              </p>
            </div>
            <div class="header-total">
              <span>订单总额 · AUD</span
              ><strong>{{ money(active.totals.total) }}</strong>
            </div>
          </section>

          <div class="stats">
            <div>
              <span>商品种类 / 行数</span
              ><strong>{{
                active.items.length.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>商品总件数</span
              ><strong>{{
                active.quantity.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>配送批次</span
              ><strong>{{
                active.shipments.length.toString().padStart(2, "0")
              }}</strong>
            </div>
            <div>
              <span>发货邮编 → 收货邮编</span
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
                  <h2>商品明细</h2>
                  <span class="subtle"
                    >{{ active.items.length }} 个 SKU · RRP 含 GST</span
                  >
                </div>
                <p class="table-scroll-hint">左右滑动可查看数量和金额 →</p>
                <div class="table-scroll">
                  <table>
                    <caption class="visually-hidden">
                      订单商品及未税金额
                    </caption>
                    <thead>
                      <tr>
                        <th scope="col">商品</th>
                        <th scope="col">数量</th>
                        <th scope="col">RRP / 未税单价</th>
                        <th scope="col">未税小计</th>
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
                              :aria-label="`Product ${index + 1} 占位图`"
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
                                >资料缺失</span
                              >
                              <details
                                v-if="
                                  item.description && item.description !== '.'
                                "
                                class="product-description"
                              >
                                <summary>商品描述</summary>
                                <p>{{ item.description }}</p>
                              </details>
                            </div>
                          </div>
                        </td>
                        <td class="numeric">{{ item.quantity }}</td>
                        <td class="numeric price">
                          <span>{{ money(item.rrp) }}</span
                          ><small>{{ money(item.unit_ex_gst) }} 未税</small>
                        </td>
                        <td class="numeric line-total">
                          {{ money(item.line_subtotal) }}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="table-note">
                  中性商品占位图 · 金额内部保留精度，显示时舍入到分。<span
                    v-if="
                      active.totals.rounding_adjustment &&
                      active.totals.rounding_adjustment !== '0.00'
                    "
                    >行小计显示值之和与订单未税小计存在
                    {{ money(active.totals.rounding_adjustment) }}
                    展示尾差；订单按未舍入金额汇总。</span
                  >
                </div>
              </section>

              <section class="card tracking-section">
                <div class="section-heading">
                  <h2>物流追踪</h2>
                  <span class="subtle">按配送批次查询</span>
                </div>
                <p class="section-intro">
                  Australia Post / StarTrack
                  使用测试环境，返回结果不代表真实包裹状态。
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
                          ? "查询中"
                          : trackingLabel(tracking[shipment.id])
                      }}</span
                    >
                  </div>
                  <div class="shipment-skus">
                    包含 {{ shipment.skus.join(" · ") }}
                  </div>
                  <div>
                    <div class="tracking-result" aria-live="polite">
                      <strong v-if="tracking[shipment.id]?.status">{{
                        tracking[shipment.id]?.status
                      }}</strong>
                      <p>
                        {{
                          trackingLoading[shipment.id]
                            ? "正在向承运商查询…"
                            : (tracking[shipment.id]?.message ??
                              "等待查询物流信息")
                        }}
                      </p>
                      <p
                        v-if="tracking[shipment.id]?.error_code"
                        class="subtle"
                      >
                        接口错误码：{{ tracking[shipment.id]?.error_code }}
                      </p>
                      <p v-if="tracking[shipment.id]?.cached" class="subtle">
                        本次为 60 秒内的缓存结果
                      </p>
                      <p
                        v-if="tracking[shipment.id]?.last_update"
                        class="subtle"
                      >
                        最近更新：{{ tracking[shipment.id]?.last_update }}
                      </p>
                    </div>
                    <details
                      v-if="tracking[shipment.id]?.events.length"
                      class="events"
                    >
                      <summary>
                        查看
                        {{ tracking[shipment.id]?.events.length }} 条物流事件
                      </summary>
                      <ol>
                        <li
                          v-for="(event, index) in tracking[shipment.id]
                            ?.events"
                          :key="index"
                        >
                          <strong>{{ event.description }}</strong
                          ><span>{{ event.location }}</span
                          ><time>{{ event.date ?? "未提供时间" }}</time>
                        </li>
                      </ol>
                    </details>
                  </div>
                  <div class="shipment-footer">
                    <span>该批运费 {{ money(shipment.shipping.fee) }}</span
                    ><button
                      v-if="shipment.carrier !== 'tnt'"
                      class="text-button"
                      :disabled="trackingLoading[shipment.id]"
                      @click="queryTracking(shipment)"
                    >
                      重新查询 ↗
                    </button>
                  </div>
                </article>
                <p class="section-footnote">
                  查询结果缓存 60 秒。事件时间保留承运商原始格式及其时区信息。
                </p>
              </section>
            </div>

            <div class="secondary-column">
              <section class="card shipping-address">
                <div class="section-heading">
                  <h2>收货信息</h2>
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
                  <span class="small-dot"></span> 发货地 Ryde, NSW 2111
                </div>
              </section>

              <section class="card summary-card">
                <div class="section-heading">
                  <h2>金额汇总</h2>
                  <span class="subtle">AUD</span>
                </div>
                <div class="summary-body">
                  <div class="summary-row">
                    <span>未税小计</span
                    ><strong>{{ money(active.totals.subtotal) }}</strong>
                  </div>
                  <div class="summary-row">
                    <span>GST <small>10%</small></span
                    ><strong>{{ money(active.totals.gst) }}</strong>
                  </div>
                  <div class="summary-row">
                    <span
                      >运费
                      <small>{{ estimate ? "估算" : "未估算" }}</small></span
                    ><strong>{{ money(active.totals.shipment_fee) }}</strong>
                  </div>
                  <div class="grand-total">
                    <span>订单总额</span
                    ><strong>{{ money(active.totals.total) }}</strong>
                  </div>
                  <p v-if="!active.totals.complete" class="missing">
                    商品资料不完整，暂不提供订单总额。
                  </p>
                  <label class="estimate-toggle"
                    ><input
                      v-model="estimate"
                      type="checkbox"
                      @change="loadOrders()"
                    /><span>启用运费估算</span></label
                  >
                  <p class="summary-note">
                    {{
                      estimate
                        ? "估算金额仅供演示，非承运商报价。TNT 相关运费为零。"
                        : "未启用估算时，运费按题目允许的回退值 A$0.00 展示。"
                    }}
                  </p>
                  <details class="fee-details">
                    <summary>查看运费计算说明</summary>
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
                        计费重量 {{ shipment.shipping.chargeable_kg }} kg
                      </p>
                    </div>
                  </details>
                </div>
              </section>
            </div>
          </div>
          <footer class="page-footer">
            <span>商品来自指定 SQL 数据源的本地快照 · 各订单独立结算</span
            ><span>Australian dollars · GST included in RRP</span>
          </footer>
        </template>
        <div v-else-if="!error" class="empty-state">
          <h2>没有找到订单</h2>
          <p>尝试其他订单编号、客户名或 SKU。</p>
          <button class="button secondary" @click="query = ''">清除搜索</button>
        </div>
      </div>
    </main>
  </div>
</template>
