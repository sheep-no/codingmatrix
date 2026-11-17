const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';
const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';

// 真实模型生成长流程，仅在提供 TEST_SILICONFLOW_API_KEY 时启用
const { HAS_SILICONFLOW_KEY: HAS_REAL_KEY } = require('./fixtures/liveKeys.js');
const { syncRealApiKeys } = require('./fixtures/liveAgent.js');

test.describe('Agent 继续功能端到端测试', () => {
  test.skip(!HAS_REAL_KEY, '需要真实 LLM 凭证（TEST_SILICONFLOW_API_KEY）')

  test('简单需求：生成 → 继续 → 继续+变更', async ({ page }) => {
    test.setTimeout(1200000); // 三轮真实生成，20 分钟超时

    // ========== 1. 登录并设置环境 ==========
    await page.goto(`${BASE_URL}/`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(2000);

    const loginResult = await page.evaluate(async ({ email, password }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';
      const resp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ email, password }),
      });
      if (!resp.ok) return { success: false, error: await resp.text() };
      return { success: true, data: await resp.json() };
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    expect(loginResult.success).toBe(true);
    const token = loginResult.data.access_token;

    await page.evaluate((token) => {
      const expiry = Date.now() + 30 * 60 * 1000;
      sessionStorage.setItem('_token', token);
      sessionStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('access_token', token);
      localStorage.setItem('_token_expiry', String(expiry));
      localStorage.setItem('username', 'admin');
      localStorage.setItem('email', 'mr_yang@example.com');
      localStorage.setItem('permission_level', 'superadmin');
    }, token);
    await syncRealApiKeys(page);

    // ========== 2. 进入 Agent 页面 ==========
    await page.goto(`${BASE_URL}/agent`);
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(3000);

    // 确保 Pinia store 从 localStorage 加载了 API Key 数据
    // 直接调用 store 的 loadFromStorage() 避免时序问题
    const storeLoaded = await page.evaluate(() => {
      try {
        const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
        if (!pinia) return { ok: false, reason: 'no pinia' };
        // 尝试通过 _s map 访问 store
        let store = pinia._s?.get('apikey');
        if (!store) {
          // 回退：通过 state 直接设置
          const stored = localStorage.getItem('codingmatrix_apikeys');
          if (stored && pinia.state.value.apikey) {
            pinia.state.value.apikey.tokens = JSON.parse(stored);
            return { ok: true, method: 'state_direct' };
          }
          return { ok: false, reason: 'no apikey store' };
        }
        store.loadFromStorage();
        return { ok: true, method: 'loadFromStorage', hasKey: store.hasSiliconflowKey, tokenCount: store.tokens.length };
      } catch (e) {
        return { ok: false, reason: e.message };
      }
    });
    console.log(`[Setup] Store load result: ${JSON.stringify(storeLoaded)}`);
    await page.waitForTimeout(500);

    // ========== 3. 辅助函数 ==========

    // 监听浏览器控制台输出
    const consoleLogs = [];
    page.on('console', msg => {
      consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
    });
    page.on('pageerror', err => {
      consoleLogs.push(`[ERROR] ${err.message}`);
    });

    // 监听网络请求
    const networkRequests = [];
    page.on('request', req => {
      if (req.url().includes('orchestrate') || req.url().includes('agent')) {
        networkRequests.push(`[REQ] ${req.method()} ${req.url()} ${req.headers()['authorization'] ? 'HAS_AUTH' : 'NO_AUTH'}`);
      }
    });
    page.on('response', res => {
      if (res.url().includes('orchestrate')) {
        networkRequests.push(`[RES] ${res.status()} ${res.url()}`);
      }
    });

    // 记录每轮请求是否为增量续跑
    const streamBodies = [];
    page.on('request', req => {
      if (req.url().includes('/agent/orchestrate/stream')) {
        try {
          const body = req.postDataJSON();
          streamBodies.push({ incremental: body.incremental, is_resume: body.is_resume, project_path: body.project_path });
        } catch {
          streamBodies.push({ parseError: true });
        }
      }
    });

    // 获取文件信息：检查 DOM 中的 .file-item 元素
    const getFileInfo = () => page.evaluate(() => {
      const fileItems = document.querySelectorAll('.file-item .file-name');
      return {
        files: Array.from(fileItems).map(el => el.textContent?.trim()).filter(Boolean),
        fileCount: fileItems.length,
      };
    });

    // 检查是否正在生成
    const isGeneratingNow = () => page.evaluate(() => {
      return !!document.querySelector('button[aria-label="停止生成"]');
    });

    // 等待文件出现（主要检测方式）
    // 策略：持续轮询直到文件出现，或直到生成结束后再等一段时间让 Vue 更新 DOM
    const waitForFiles = (timeoutMs = 180000) => page.evaluate(
      ({ timeout }) => new Promise((resolve) => {
        const start = Date.now();
        let generationDoneAt = null;

        const check = () => {
          const fileItems = document.querySelectorAll('.file-item .file-name');
          const generating = !!document.querySelector('button[aria-label="停止生成"]');

          // 文件已出现
          if (fileItems.length > 0) {
            resolve({
              files: Array.from(fileItems).map(el => el.textContent?.trim()).filter(Boolean),
              fileCount: fileItems.length,
              generating,
              reason: 'files_found',
            });
            return;
          }

          if (generating) {
            // 仍在生成中，继续等待
            generationDoneAt = null;
            setTimeout(check, 500);
          } else if (generationDoneAt === null) {
            // 生成刚结束，给 Vue 2 秒更新 DOM
            generationDoneAt = Date.now();
            setTimeout(check, 500);
          } else if (Date.now() - generationDoneAt > 2000) {
            // 生成结束超过 2 秒，Vue 应该已经更新了
            // 再次检查文件
            const finalItems = document.querySelectorAll('.file-item .file-name');
            resolve({
              files: Array.from(finalItems).map(el => el.textContent?.trim()).filter(Boolean),
              fileCount: finalItems.length,
              generating: false,
              reason: finalItems.length > 0 ? 'files_found_late' : 'generation_done_no_files',
            });
          } else if (Date.now() - start > timeout) {
            resolve({
              files: [],
              fileCount: 0,
              generating,
              reason: 'timeout',
            });
          } else {
            setTimeout(check, 500);
          }
        };
        check();
      }),
      { timeout: timeoutMs }
    );

    // 点击生成按钮
    const clickGenerate = async () => {
      await confirmDecisionIfPresent();

      const generateBtn = page.locator('button[aria-label="发送需求"]');
      await expect(generateBtn).toBeEnabled({ timeout: 10000 });

      // 检查按钮状态和 prompt 值
      const btnState = await page.evaluate(() => {
        const btn = document.querySelector('button[aria-label="发送需求"]');
        const textarea = document.querySelector('textarea.prompt-textarea');
        return {
          btnDisabled: btn?.disabled,
          btnText: btn?.textContent?.trim(),
          promptValue: textarea?.value,
          promptLength: textarea?.value?.length,
        };
      });
      console.log(`[ClickGenerate] Button state: ${JSON.stringify(btnState)}`);

      await generateBtn.click();
      console.log('[ClickGenerate] Button clicked');

      // 等一下看 isGenerating 是否变为 true
      await page.waitForTimeout(1000);
      const genState = await page.evaluate(() => {
        return { hasStopBtn: !!document.querySelector('button[aria-label="停止生成"]') };
      });
      console.log(`[ClickGenerate] After click state: ${JSON.stringify(genState)}`);
    };

    // 确认生成前的决策卡片（默认值 + 确认）
    const confirmDecisionIfPresent = async () => {
      const decisionConfirm = page.locator('.decision-card .btn-decision-primary');
      if (!(await decisionConfirm.first().isVisible({ timeout: 1000 }).catch(() => false))) {
        return false;
      }
      const useDefault = page.locator('.decision-card .btn-decision-secondary');
      if (await useDefault.first().isVisible({ timeout: 1000 }).catch(() => false)) {
        await useDefault.first().click();
      }
      await decisionConfirm.first().click();
      await page.waitForTimeout(1000);
      console.log('[Decision] 已确认决策卡片');
      return true;
    };

    // 等待生成自然结束：停止按钮消失即代表生成结束
    const waitForIdle = async (timeoutMs = 420000) => {
      const deadline = Date.now() + timeoutMs;
      const stopBtn = page.locator('button[aria-label="停止生成"]');
      let idleTicks = 0;

      while (Date.now() < deadline) {
        await confirmDecisionIfPresent();

        if (!(await stopBtn.isVisible().catch(() => false))) {
          idleTicks += 1;
        } else {
          idleTicks = 0;
        }
        if (idleTicks >= 2) {
          console.log('[waitForIdle] 生成已结束');
          return true;
        }

        await page.waitForTimeout(1000);
      }

      console.log('[waitForIdle] 超时，生成未结束');
      return false;
    };

    // ========== 4. 第一次生成：简单需求 ==========
    const textarea = page.locator('textarea.prompt-textarea');
    await expect(textarea).toBeVisible({ timeout: 10000 });

    // 使用单文件需求，确保能在超时内自然结束
    await textarea.fill('创建一个 Hello World 的 Python 脚本，只有一个 main.py');
    await page.waitForTimeout(500);

    await clickGenerate();
    console.log('[Step 1] 点击开始生成');

    // 先等15秒看网络请求
    await page.waitForTimeout(15000);
    console.log(`[Debug] Network requests: ${JSON.stringify(networkRequests)}`);
    console.log(`[Debug] Console logs (last 20): ${JSON.stringify(consoleLogs.slice(-20))}`);
    console.log(`[Debug] isGenerating still true: ${await isGeneratingNow()}`);

    // 等待文件出现
    const firstResult = await waitForFiles(180000);
    console.log(`[Step 2] 第一次生成: ${firstResult.fileCount} 个文件, reason=${firstResult.reason}, generating=${firstResult.generating}`);

    // 等待第一轮自然结束，才能进入增量继续流程
    expect(await waitForIdle()).toBe(true);

    // 等一下让 Vue 更新 DOM
    await page.waitForTimeout(2000);
    const firstFinal = await getFileInfo();
    console.log(`[Step 2] 第一次最终: ${firstFinal.fileCount} 个文件`);
    if (firstFinal.files.length > 0) {
      console.log(`  文件: ${firstFinal.files.join(', ')}`);
    }

    // ========== 5. 测试"继续"功能（增量） ==========
    console.log('[Step 3] 测试继续功能...');
    await textarea.fill('继续');
    await page.waitForTimeout(500);

    await clickGenerate();

    const secondResult = await waitForFiles(180000);
    console.log(`[Step 4] 继续后: ${secondResult.fileCount} 个文件, reason=${secondResult.reason}`);

    expect(await waitForIdle()).toBe(true);

    await page.waitForTimeout(2000);
    const secondFinal = await getFileInfo();
    console.log(`[Step 4] 继续最终: ${secondFinal.fileCount} 个文件`);

    // ========== 6. 测试"继续 + 变更需求"功能 ==========
    console.log('[Step 5] 测试继续+变更需求...');
    await textarea.fill('继续，加一个打印当前日期的函数');
    await page.waitForTimeout(500);

    await clickGenerate();

    const thirdResult = await waitForFiles(180000);
    console.log(`[Step 6] 继续+变更后: ${thirdResult.fileCount} 个文件, reason=${thirdResult.reason}`);

    expect(await waitForIdle()).toBe(true);

    await page.waitForTimeout(2000);
    const thirdFinal = await getFileInfo();
    console.log(`[Step 6] 继续+变更最终: ${thirdFinal.fileCount} 个文件`);

    // ========== 7. 输出测试结果 ==========
    console.log('\n===== 浏览器控制台日志 =====');
    consoleLogs.forEach(log => console.log(`  ${log}`));
    console.log('============================\n');

    const totalCount = firstFinal.fileCount + secondFinal.fileCount + thirdFinal.fileCount;
    console.log('\n===== 测试结果汇总 =====');
    console.log(`请求增量标记: ${JSON.stringify(streamBodies)}`);
    console.log(`第一次生成文件数: ${firstFinal.fileCount}`);
    console.log(`继续后文件数: ${secondFinal.fileCount}`);
    console.log(`继续+变更后文件数: ${thirdFinal.fileCount}`);
    console.log(`总文件数: ${totalCount}`);
    const allFiles = [...new Set([...firstFinal.files, ...secondFinal.files, ...thirdFinal.files])];
    console.log(`所有文件: ${allFiles.join(', ')}`);
    console.log('========================\n');

    // 验证：三轮流程都产出了文件
    expect(totalCount).toBeGreaterThan(0);
    expect(firstFinal.fileCount).toBeGreaterThan(0);
    expect(secondFinal.fileCount).toBeGreaterThan(0);
    expect(thirdFinal.fileCount).toBeGreaterThan(0);
    // 第二轮和第三轮必须走增量续跑，而不是重新建项目
    expect(streamBodies.length).toBe(3);
    expect(streamBodies[1].incremental).toBe(true);
    expect(streamBodies[2].incremental).toBe(true);
  });
});
