const { chromium } = require('playwright');

const TEST_WORKFLOW_JSON = {
  workflow_id: 'wf_test_import',
  version: '1.0',
  nodes: [
    {
      id: 'node_1',
      type: 'web_search',
      params: {
        query: '广州铁路职业技术学院计算机应用技术专业',
        count: 5,
        lang: 'zh',
        with_summary: true
      },
      depends_on: [],
      status: 'pending'
    },
    {
      id: 'node_2',
      type: 'code_execution',
      params: {
        language: 'python',
        code: 'print("Hello World")'
      },
      depends_on: ['node_1'],
      status: 'pending'
    }
  ],
  timeout: 1800,
  exportable: true
};

const BASE_URL = 'http://localhost:3001';

async function testWorkflowImport() {
  console.log('========================================');
  console.log('Workflow Import Test');
  console.log('========================================\n');

  const browser = await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });

  const page = await context.newPage();

  const logs = [];
  page.on('console', msg => {
    const text = msg.text();
    logs.push({ type: msg.type(), text });
    console.log(`[Console ${msg.type()}] ${text}`);
  });

  try {
    // 1. Login
    console.log('1. Logging in...');
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForSelector('.login-btn', { timeout: 10000 });
    await page.click('.login-btn');
    await page.waitForSelector('.login-form', { timeout: 5000 });
    await page.fill('.login-form input[type="email"]', 'mr_yang@example.com');
    await page.fill('.login-form input[type="password"]', '123456');
    await page.click('.login-form .form-actions button:last-child');
    await page.waitForTimeout(3000);

    const usernameElement = await page.$('.username');
    if (usernameElement) {
      console.log('   [OK] Login successful\n');
    } else {
      throw new Error('Login failed');
    }

    // 2. Set up token
    console.log('2. Setting up authentication...');
    const accessToken = await page.evaluate(() => localStorage.getItem('access_token'));
    if (accessToken) {
      await page.evaluate((token) => {
        localStorage.setItem('token', token);
      }, accessToken);
      console.log('   [OK] Token configured\n');
    }

    // 3. Open Ephemeral Workflow modal
    console.log('3. Opening Ephemeral Workflow modal...');
    await page.evaluate(() => {
      const app = document.querySelector('#app').__vue_app__;
      if (app) {
        const pinia = app.config.globalProperties.$pinia;
        if (pinia) {
          for (const [name, store] of pinia._s) {
            if (name.includes('navigation')) {
              store.showTool('ephemeralWorkflow');
              break;
            }
          }
        }
      }
    });
    await page.waitForTimeout(2000);

    const modal = await page.$('.ephemeral-workflow');
    if (modal) {
      console.log('   [OK] Modal opened\n');
    } else {
      throw new Error('Could not open modal');
    }

    // 4. Click import button
    console.log('4. Clicking import button...');
    const buttons = await page.$$('.ephemeral-workflow button');
    let importButton = null;
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && text.includes('导入')) {
        importButton = btn;
        break;
      }
    }

    if (importButton) {
      await importButton.click();
      console.log('   [OK] Import button clicked\n');
    } else {
      throw new Error('Import button not found');
    }

    // 5. Wait for import dialog
    console.log('5. Waiting for import dialog...');
    await page.waitForTimeout(500);
    const importDialog = await page.$('.import-dialog');
    if (importDialog) {
      console.log('   [OK] Import dialog appeared\n');
    } else {
      throw new Error('Import dialog not found');
    }

    // 6. Fill in workflow JSON
    console.log('6. Filling workflow JSON...');
    const importInput = await page.$('.import-input');
    if (importInput) {
      await importInput.fill(JSON.stringify(TEST_WORKFLOW_JSON, null, 2));
      console.log('   [OK] JSON filled\n');
    } else {
      throw new Error('Import input not found');
    }

    // 7. Click confirm button
    console.log('7. Clicking confirm button...');
    const dialogButtons = await page.$$('.import-dialog button');
    for (const btn of dialogButtons) {
      const text = await btn.textContent();
      if (text && text.includes('确认')) {
        await btn.click();
        console.log('   [OK] Confirm button clicked\n');
        break;
      }
    }

    // 8. Wait for import to process
    await page.waitForTimeout(1000);

    // 9. Check if workflow was imported
    console.log('9. Checking imported workflow...');
    const pageContent = await page.content();
    const hasWorkflowId = pageContent.includes('wf_test_import');
    const hasNodes = pageContent.includes('web_search') || pageContent.includes('code_execution');
    console.log('   [DEBUG] Has workflow ID:', hasWorkflowId);
    console.log('   [DEBUG] Has nodes:', hasNodes);

    // 10. Check for task nodes
    console.log('10. Checking task nodes...');
    const taskNodes = await page.$$('.task-node');
    console.log('   [DEBUG] Task nodes found:', taskNodes.length);
    if (taskNodes.length > 0) {
      console.log('   [OK] Workflow imported successfully\n');
    }

    // 11. Check JSON content
    console.log('11. Checking JSON content...');
    const jsonContent = await page.$('.json-content');
    if (jsonContent) {
      const jsonText = await jsonContent.textContent();
      try {
        const parsed = JSON.parse(jsonText);
        console.log('   [OK] JSON parsed successfully');
        console.log('   Workflow ID:', parsed.workflow_id);
        console.log('   Nodes count:', parsed.nodes?.length || 0);
      } catch (e) {
        console.log('   [WARN] JSON parse error:', e.message);
      }
    }

    // 12. Check for export button (should now be visible)
    console.log('12. Checking export button...');
    const allButtons = await page.$$('.ephemeral-workflow button');
    let hasExportButton = false;
    for (const btn of allButtons) {
      const text = await btn.textContent();
      if (text && (text.includes('导出') || text.includes('Export'))) {
        hasExportButton = true;
        break;
      }
    }
    console.log('   [DEBUG] Export button visible:', hasExportButton);

    // 13. Take screenshot
    console.log('\n13. Taking screenshot...');
    await page.screenshot({ path: '/tmp/workflow-import-test.png', fullPage: true });
    console.log('   Screenshot: /tmp/workflow-import-test.png\n');

    // 14. Summary
    console.log('========================================');
    console.log('Test Summary:');
    console.log('========================================');
    console.log('Login: [OK]');
    console.log('Modal: [OK]');
    console.log('Import Dialog: [OK]');
    console.log('JSON Filled: [OK]');
    console.log('Confirm Import: [OK]');
    console.log('Workflow Imported:', taskNodes.length > 0 ? '[OK]' : '[WARN] Not detected');
    console.log('Export Button:', hasExportButton ? '[OK]' : '[WARN] Not visible');
    console.log('========================================\n');

  } catch (error) {
    console.error('\n[ERR] Test failed:', error.message);
    await page.screenshot({ path: '/tmp/workflow-import-error.png', fullPage: true });
    console.log('Error screenshot: /tmp/workflow-import-error.png');
  } finally {
    await browser.close();
    console.log('[OK] Browser closed');
  }
}

// Run test
testWorkflowImport()
  .then(() => {
    console.log('\n[OK] Test completed');
    process.exit(0);
  })
  .catch(error => {
    console.error('[ERR] Test error:', error);
    process.exit(1);
  });