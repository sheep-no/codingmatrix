/**
 * 工具面板交互 E2E 测试
 * 覆盖: 图表编辑器、Nginx配置、Docker配置、系统检测、任务队列等聊天内工具
 */
import { test, expect } from '@playwright/test';
import { apiLogin, logout } from './fixtures/auth.js';

test.describe('工具面板交互', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.locator('#toolkit').click();
  });

  test('图表编辑器 - 点击打开', async ({ page }) => {
    await page.locator('text=图表编辑器').click();
    await page.waitForTimeout(500);

    const chartEditorVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="chart"], [class*="ChartEditor"]');
    });
    expect(chartEditorVisible).toBeTruthy();
  });

  test('Nginx 配置 - 点击打开', async ({ page }) => {
    await page.locator('text=Nginx 配置').click();
    await page.waitForTimeout(500);

    const nginxVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="nginx"], [class*="NginxConfig"]');
    });
    expect(nginxVisible).toBeTruthy();
  });

  test('Docker 配置 - 点击打开', async ({ page }) => {
    await page.locator('text=Docker 配置').click();
    await page.waitForTimeout(500);

    const dockerVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="docker"], [class*="Dockerfile"]');
    });
    expect(dockerVisible).toBeTruthy();
  });

  test('系统检测 - 点击打开', async ({ page }) => {
    await page.locator('text=系统检测').click();
    await page.waitForTimeout(500);

    const sysInfoVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="system-info"], [class*="SystemInfo"]');
    });
    expect(sysInfoVisible).toBeTruthy();
  });

  test('AI 虚拟姬 - 点击打开', async ({ page }) => {
    await page.locator('text=AI 虚拟姬').click();
    await page.waitForTimeout(500);

    const girlVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="virtual"], [class*="VirtualGirl"], [class*="GirlAi"]');
    });
    expect(girlVisible).toBeTruthy();
  });

  test('任务队列 - 点击打开', async ({ page }) => {
    await page.locator('text=任务队列').click();
    await page.waitForTimeout(500);

    const taskQueueVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="task"], [class*="TaskQueue"]');
    });
    expect(taskQueueVisible).toBeTruthy();
  });

  test('AI 云助手 - 点击打开', async ({ page }) => {
    await page.locator('text=AI 云助手').click();
    await page.waitForTimeout(500);

    const aicloudVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="aicloud"], [class*="Aicloud"]');
    });
    expect(aicloudVisible).toBeTruthy();
  });

  test('系统监控 - 点击打开', async ({ page }) => {
    await page.locator('text=系统监控').click();
    await page.waitForTimeout(500);

    const monitorVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="monitor"], [class*="SystemMonitor"]');
    });
    expect(monitorVisible).toBeTruthy();
  });

  test('临时工作流 - 点击打开', async ({ page }) => {
    await page.locator('text=临时工作流').click();
    await page.waitForTimeout(500);

    const workflowVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="workflow"], [class*="Workflow"]');
    });
    expect(workflowVisible).toBeTruthy();
  });

  test('AI 项目生成 - 点击打开', async ({ page }) => {
    await page.locator('text=AI 项目生成').click();
    await page.waitForTimeout(500);

    const projectGenVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="project"], [class*="ProjectGenerator"]');
    });
    expect(projectGenVisible).toBeTruthy();
  });

  test('PPT 生成 - 点击打开', async ({ page }) => {
    await page.locator('text=PPT 生成').click();
    await page.waitForTimeout(500);

    const pptVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="ppt"], [class*="PPTGenerator"]');
    });
    expect(pptVisible).toBeTruthy();
  });

  test('AI 绘画 - 点击打开', async ({ page }) => {
    await page.locator('text=AI 绘画').click();
    await page.waitForTimeout(500);

    const imageVisible = await page.evaluate(() => {
      return !!document.querySelector('[class*="image"], [class*="ImageGenerator"]');
    });
    expect(imageVisible).toBeTruthy();
  });
});
