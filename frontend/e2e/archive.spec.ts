import { test, expect } from "@playwright/test"

const artifact = { id: "old-42", kind: "idea", goal: "old goal", title: "Old idea", created_at: "2025-01-01", updated_at: "2025-01-01" }

test("archive direct navigation renders read-only archive", async ({ page }) => {
  await page.route("**/api/v2/legacy-archive", route => route.fulfill({ json: { artifacts: [] } }))
  await page.goto("/archive")
  await expect(page.getByRole("heading", { name: "旧轨迹，保持原样。" })).toBeVisible()
  await expect(page.getByText("旧研究 archive · 只读")).toBeVisible()
})

test("legacy artifact deep link is read back through archive", async ({ page }) => {
  await page.route("**/api/v2/legacy-archive/artifacts/old-42/trajectory", route => route.fulfill({ json: { events: [] } }))
  await page.route("**/api/v2/legacy-archive/artifacts/old-42", route => route.fulfill({ json: { artifact } }))
  await page.route("**/api/v2/legacy-archive", route => route.fulfill({ json: { artifacts: [] } }))
  await page.goto("/artifact/old-42")
  await expect(page.getByText("已从退役路径")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Old idea" })).toBeVisible()
})

test("invalid archive subpath explains it instead of rendering archive", async ({ page }) => {
  await page.goto("/archive/not-a-real-route")
  await expect(page.getByRole("heading", { name: "这个位置不存在。" })).toBeVisible()
  await expect(page.getByText("/archive/not-a-real-route")).toBeVisible()
})

test("unknown route explains it and pushState query changes rerender", async ({ page }) => {
  await page.goto("/unknown")
  await expect(page.getByRole("heading", { name: "这个位置不存在。" })).toBeVisible()
  await page.evaluate(() => window.history.pushState({}, "", "/__prototype/research-universe?variant=B"))
  await expect(page.getByText(/PROTOTYPE · B/)).toBeVisible()
})
