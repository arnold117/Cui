import { expect, test } from "@playwright/test"

const enabled = process.env.PLAYWRIGHT_REAL_API === "1"
test.skip(!enabled, "set PLAYWRIGHT_REAL_API=1 with a dedicated fake-generator FastAPI test server")
test("real native first-fact journey", async ({ page }) => {
  await page.goto("/")
  await page.getByLabel("你此刻想带进 Cui 的问题").fill("Why does retrieval practice change recall?")
  await page.getByRole("button", { name: "继续" }).click()
  await expect(page).toHaveURL(/\/workspaces\//)
  await page.getByRole("button", { name: /^覆盖与 claim/ }).click()
  await page.getByLabel("由你写下的 claim").fill("Retrieval practice improves later recall.")
  await page.getByRole("button", { name: "固化 claim 并开审查轮" }).click()
  await expect(page).toHaveURL(/\/workspaces\/[^/]+\/rounds\/[^/]+$/)
  await expect(page.getByRole("complementary", { name: "聚焦面" }).getByRole("tab", { name: "应答" })).toBeVisible()
})
