import { expect, test } from "@playwright/test"

const enabled = process.env.PLAYWRIGHT_REAL_PARK_API === "1"
test.skip(!enabled, "set PLAYWRIGHT_REAL_PARK_API=1 with a dedicated PostgreSQL Slice 2 test server")

test("real sealed PARK release and Forge lineage journey", async ({ page }) => {
  const sentinel = `sealed raw ${Date.now()}`
  await page.goto("/park")
  await page.getByLabel("捕获原始文本").fill(sentinel)
  await page.getByRole("button", { name: "密封捕获" }).click()
  await expect(page.getByText(sentinel)).toHaveCount(0)
  await page.getByRole("link", { name: "查看密封原件" }).click()
  await expect(page.getByText(sentinel)).toBeVisible()
  await page.getByRole("button", { name: "主动放行" }).click()
  await page.getByLabel("新的开放问题").fill("这份观察在什么条件下成立？")
  await page.getByRole("button", { name: "确认放行" }).click()
  await expect(page).toHaveURL(/\/workspaces\//)
  await expect(page.getByText(/来自密封 PARK 原件的放行引用/)).toBeVisible()
  await page.getByRole("link", { name: "从此原件锻造自写 claim" }).click()
  await page.getByLabel("由你亲自写下的 claim").fill("该观察只在边界条件明确时成立。")
  await page.getByRole("button", { name: "提交检验" }).click()
  await expect(page).toHaveURL(/\/review-rounds\//)
  await expect(page.getByText("审查这一条 claim")).toBeVisible()
})
