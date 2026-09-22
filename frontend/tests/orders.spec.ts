import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const input = () =>
  JSON.parse(
    readFileSync(
      new URL("../../backend/data/orders.json", import.meta.url),
      "utf8",
    ),
  );
const upload = (data: unknown) => ({
  name: "orders.json",
  mimeType: "application/json",
  buffer: Buffer.from(JSON.stringify(data)),
});

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    throw error;
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "PO-20251130-00072", exact: true }),
  ).toBeVisible();
});

test("source data, independent totals, search and multi-shipment", async ({
  page,
}) => {
  await expect(page.locator("tbody tr")).toHaveCount(5);
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,131.00");
  await page.getByRole("button", { name: /Cann Life Dispensary/ }).click();
  await expect(page.locator("tbody tr")).toHaveCount(4);
  await expect(page.locator(".shipment-card")).toHaveCount(2);
  await expect(page.getByText("Not integrated", { exact: true })).toBeVisible();
  await expect(page.locator(".grand-total strong")).toHaveText("A$1,655.00");
  await page.getByLabel("Estimate shipping", { exact: true }).check();
  await expect(page.locator(".grand-total strong")).toHaveText("A$1,671.00");
  await page.getByRole("searchbox").fill("TBAMET10");
  await expect(page.locator(".order-button")).toHaveCount(1);
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,147.00");
  await page.getByRole("searchbox").fill("NO-SUCH-ORDER");
  await expect(
    page.getByRole("heading", { name: "No orders found" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("download and import real input structure, missing SKU and invalid quantity", async ({
  page,
}) => {
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download template" }).click();
  expect((await downloadEvent).suggestedFilename()).toBe("orders.json");
  const data = input();
  data.line_items[0].sku = "UNKNOWN-TEST-SKU";
  await page.locator("input[type=file]").setInputFiles(upload(data));
  await expect(
    page.getByText(
      "Product data is incomplete. The order total is unavailable.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(page.locator(".grand-total strong")).toHaveText("—");
  data.line_items[0].quantity = 0;
  await page.locator("input[type=file]").setInputFiles(upload(data));
  await expect(
    page.getByRole("alert").filter({ hasText: "quantity" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Back to initial orders" }).click();
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,131.00");
});

test("malformed successful responses and offline failures recover without corrupting state", async ({
  page,
}) => {
  await page.route("**/api/orders?*", (route) =>
    route.fulfill({ json: { orders: null } }),
  );
  await page.getByRole("button", { name: "Refresh orders" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "unexpected data structure",
  );
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,131.00");
  await page.unroute("**/api/orders?*");
  await page.route("**/api/orders?*", (route) => route.abort());
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Cannot connect to the server",
  );
  await page.unroute("**/api/orders?*");
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,131.00");
});

test("imported tracking uses supplied consignment; test fixture stays in tests", async ({
  page,
}) => {
  const calls: string[] = [];
  await page.route("**/api/tracking", async (route) => {
    calls.push(route.request().postDataJSON().tracking_no);
    await route.fulfill({
      json: {
        state: "available",
        status: "Synthetic test status",
        last_update: "2026-01-02T10:00:00+11:00",
        events: [
          {
            description: "Synthetic test event",
            date: "2026-01-02T10:00:00+11:00",
            location: "Test location",
            article_id: "TEST",
          },
        ],
        message: "Test fixture only",
        environment: "testbed",
        checked_at: "2026-01-02T00:00:00Z",
      },
    });
  });
  const data = input();
  data.shipments[0].tracking_no = "IMPORTED123";
  await page.locator("input[type=file]").setInputFiles(upload(data));
  await expect(
    page.getByText("Synthetic test status", { exact: true }),
  ).toBeVisible();
  expect(calls).toContain("IMPORTED123");
  await page.locator(".events summary").click();
  await expect(
    page.getByText("Synthetic test event", { exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/tracking");
  await page.route("**/api/tracking", (route) =>
    route.fulfill({ json: { state: "available", events: null } }),
  );
  await page.getByRole("button", { name: /Refresh tracking/ }).click();
  await expect(
    page.getByText(
      "The server returned an unexpected data structure. Please retry or check the backend.",
      {
        exact: true,
      },
    ),
  ).toBeVisible();
});

test("JSON BOM and invalid file handling", async ({ page }) => {
  await page.locator("input[type=file]").setInputFiles({
    name: "bad.json",
    mimeType: "application/json",
    buffer: Buffer.from("{ broken"),
  });
  await expect(page.getByRole("alert")).toBeVisible();
  await page.locator("input[type=file]").setInputFiles({
    name: "bom.json",
    mimeType: "application/json",
    buffer: Buffer.from("\ufeff" + JSON.stringify(input())),
  });
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.locator(".grand-total strong")).toHaveText("A$2,131.00");
});
