import { expect, test } from "@playwright/test"

const enabled = process.env.PLAYWRIGHT_REAL_API === "1"
test.skip(!enabled, "set PLAYWRIGHT_REAL_API=1 with a dedicated fake-generator FastAPI test server")
test("real native first-fact journey", async ({ page }) => {
  await page.goto("/")
  await page.getByLabel("你此刻想带进 Cui 的问题").fill("Why does retrieval practice change recall?")
  await page.getByRole("button", { name: "继续" }).click()
  await expect(page).toHaveURL(/\/workspaces\//)
  await page.getByLabel("形成一个由你亲自写下的 claim").fill("Retrieval practice improves later recall.")
  await page.getByRole("button", { name: "确认提交检验" }).click()
  await expect(page).toHaveURL(/\/review-rounds\//)
  await expect(page.getByText("审查这一条 claim")).toBeVisible()
})
