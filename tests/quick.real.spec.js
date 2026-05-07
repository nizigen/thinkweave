const { test, expect } = require('@playwright/test');

test('quick real flow', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('task_auth_token', 'local-dev-admin-token');
  });
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'domcontentloaded' });
  await page.fill('input[placeholder="输入主题标题"]', 'Quick Playwright Real Test ' + Date.now());
  await page.selectOption('select:nth-of-type(2)', 'quick');
  await page.fill('input[type="number"]', '1200');
  await page.click('button:has-text("开始生成")');

  await expect(page).toHaveURL(/\/monitor\//, { timeout: 30000 });
  const start = Date.now();
  let status = '';

  while (Date.now() - start < 90000) {
    const kpiText = await page.locator('.kpis').innerText();
    const m = kpiText.match(/状态:\s*([^\n]+)/);
    status = m ? m[1].trim() : '';
    if (['running', 'completed', 'failed', 'done'].includes(status)) break;
    await page.waitForTimeout(1500);
    await page.reload({ waitUntil: 'domcontentloaded' });
  }

  console.log('PLAYWRIGHT_QUICK_STATUS=' + status);
  expect(['running', 'completed', 'failed', 'done']).toContain(status);
});
