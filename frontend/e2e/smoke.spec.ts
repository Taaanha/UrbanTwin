import { expect, test, type Page } from "@playwright/test";

/**
 * Smoke test for every screen: the page must render, throw no uncaught errors, log no console errors
 * (basemap tile failures are ignored because they depend on the network), and each map must have a real size.
 * This is the test that would have caught the "map is only dark blue" bug (a map container with zero height).
 */

const TOKEN = process.env.E2E_STAFF_TOKEN ?? "";

const MAP_PAGES = ["/", "/dashboard", "/intelligence", "/planner", "/simulation"];
const OTHER_PAGES = ["/track", "/overview", "/investigator", "/accountability", "/admin"];

const TILE_HOSTS = ["tile.openstreetmap.org", "arcgisonline.com"];

const logs: string[] = [];

function watch(page: Page) {
  const problems: string[] = [];
  page.on("pageerror", (error) => problems.push(`uncaught: ${error.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "warning" && /^\[(map|compare)\]/.test(msg.text())) logs.push(msg.text());
    if (msg.type() !== "error") return;
    const url = msg.location().url ?? "";
    if (TILE_HOSTS.some((h) => url.includes(h))) return;
    problems.push(`console: ${msg.text()} ${url}`);
  });
  return problems;
}

/** When a wait times out, say what the page actually showed and which errors/requests failed, instead of just "not found". */
async function explain(page: Page, problems: string[], failures: string[], error: unknown): Promise<never> {
  const text = (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 700);
  throw new Error(
    `${(error as Error).message.split("\n")[0]}\n  page errors: ${problems.join(" | ") || "none"}\n  failed requests: ${failures.join(" | ") || "none"}\n  map warnings: ${logs.join(" | ") || "none"}\n  page text: ${text}`,
  );
}

function watchRequests(page: Page) {
  const failures: string[] = [];
  page.on("requestfailed", (r) => { if (r.url().includes("/api/")) failures.push(`${r.method()} ${r.url()} ${r.failure()?.errorText}`); });
  page.on("response", (r) => { if (r.url().includes("/api/") && r.status() >= 400) failures.push(`${r.status()} ${r.url()}`); });
  return failures;
}

test.beforeEach(async ({ page }) => {
  if (TOKEN) {
    await page.addInitScript((token) => {
      sessionStorage.setItem("urbantwin.staffToken", token);
      sessionStorage.setItem("urbantwin.staffName", "e2e");
    }, TOKEN);
  }
});

for (const path of [...MAP_PAGES, ...OTHER_PAGES]) {
  test(`page ${path} renders cleanly`, async ({ page }) => {
    const problems = watch(page);
    await page.goto(path);
    await expect(page.locator("main").first()).toBeVisible();
    // not "networkidle": staff pages keep the live-alerts stream open, so the network never goes idle
    await page.waitForTimeout(1500);
    await expect(page.getByText("This page could not start")).toHaveCount(0);
    await expect(page.getByText("The map could not start")).toHaveCount(0);

    if (MAP_PAGES.includes(path)) {
      const map = page.locator(".maplibregl-map").first();
      await expect(map).toBeVisible();
      const box = await map.boundingBox();
      expect(box?.height ?? 0, "map container must not collapse to zero height").toBeGreaterThan(150);
      expect(box?.width ?? 0).toBeGreaterThan(150);
      await expect(page.locator(".maplibregl-canvas").first()).toBeVisible();
    }
    expect(problems, problems.join("\n")).toEqual([]);
  });
}

test("simulation: run a scenario, see the uncertainty range, switch to 3D and swipe-compare", async ({ page }) => {
  const problems = watch(page);
  const failures = watchRequests(page);
  await page.goto("/simulation");
  await page.getByRole("button", { name: "Run scenario" }).click();
  const done = page.getByText("Candidate scenario");
  const failed = page.locator("div.border-b >> .text-amber-300");
  await expect(done.or(failed).first()).toBeVisible({ timeout: 60_000 }).catch((e) => explain(page, problems, failures, e));
  expect(await failed.count() ? await failed.first().innerText() : "", "the scenario run reported an error").toBe("");
  await expect(done).toBeVisible();
  await expect(page.getByText(/plausible/).first()).toBeVisible();
  await page.getByRole("button", { name: "3D", exact: true }).click();
  await page.getByRole("button", { name: /Swipe compare/ }).click();
  await expect(page.getByRole("slider", { name: "Before and after divider" })).toBeVisible();
  await expect(page.locator(".maplibregl-map")).toHaveCount(2, { timeout: 30_000 }).catch((err) => explain(page, problems, failures, err));
  expect(problems, problems.join("\n")).toEqual([]);
});

test("simulation: flood what-if either asks for elevation data or shows a range", async ({ page }) => {
  const problems = watch(page);
  const failures = watchRequests(page);
  await page.goto("/simulation");
  await page.getByRole("button", { name: "Flood what-if (3D)" }).click();
  await expect(page.getByText("not a flood forecast", { exact: false }).first()).toBeVisible();
  const needsData = page.getByText("Elevation data needed");
  if (await needsData.count()) return; // data not downloaded on this machine yet: the prompt is the correct state
  await expect(page.getByText(/plausible/).first()).toBeVisible({ timeout: 30_000 }).catch((e) => explain(page, problems, failures, e));
  await expect(page.getByText(/surface model/).first()).toBeVisible();
});

test("dashboard: time-lapse opens and closes", async ({ page }) => {
  const problems = watch(page);
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /Time-lapse/ }).click();
  await expect(page.getByText(/reports/).first()).toBeVisible();
  await page.getByRole("button", { name: "Exit time-lapse" }).click();
  expect(problems, problems.join("\n")).toEqual([]);
});

test("ask the city answers with the query it ran", async ({ page }) => {
  await page.goto("/overview");
  await page.getByRole("button", { name: /Ask the city/ }).click();
  await page.getByPlaceholder(/Which ward/).fill("What is the most common problem?");
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByText("Query used")).toBeVisible();
});

test("overview shows the data-quality panel", async ({ page }) => {
  await page.goto("/overview");
  await expect(page.getByText("Data quality", { exact: true })).toBeVisible();
  await expect(page.getByText("Reviewed by a person", { exact: true })).toBeVisible();
});
