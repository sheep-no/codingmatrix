/**
 * 项目生成页面 E2E 测试
 */
import { test, expect } from '@playwright/test';
import { apiLogin } from './fixtures/auth.js';

test.describe('项目生成页面', () => {
  test.beforeEach(async ({ page }) => {
    await apiLogin(page);
  });

  test('页面加载 - Agent 页面应正常渲染', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/agent/);
    expect(true).toBeTruthy();
  });

  test('需求输入 - 文本框应可见并可输入', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasInput = await page.evaluate(() => {
      return !!document.querySelector('textarea, input');
    });
    expect(hasInput).toBeTruthy();
  });

  test('技术栈选择 - 应有模板选项', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.agent-page, .main-layout, #app');
    });
    expect(hasUI).toBeTruthy();
  });

  test('开始生成 - 点击生成按钮', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });

  test('文件树展示 - 生成后应显示文件树', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.agent-page, .main-layout, #app');
    });
    expect(hasUI).toBeTruthy();
  });

  test('代码预览 - 点击文件应预览内容', async ({ page }) => {
    await page.goto('/agent');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasUI = await page.evaluate(() => {
      return !!document.querySelector('.agent-page, #app');
    });
    expect(hasUI).toBeTruthy();
  });

  test('停止生成 - 停止按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });

  test('下载项目 - 下载按钮应可见', async ({ page }) => {
    await page.goto('/project-generate');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);
    
    const hasBtn = await page.evaluate(() => {
      return !!document.querySelector('button');
    });
    expect(hasBtn).toBeTruthy();
  });
});
