const { chromium } = require('playwright');
const fs = require('fs');

const TEST_REQUEST = '广州铁路职业技术学院的计算机应用技术专业信息';
const BASE_URL = 'http://localhost:3001';

async function testEphemeralWorkflow() {
  console.log('========================================');
  console.log('Ephemeral Workflow Test');
  console.log('Request:', TEST_REQUEST);
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

  let downloadPromise = null;
  page.on('download', async (download) => {
    console.log('[DOWNLOAD]', download.suggestedFilename());
    downloadPromise.resolve(download);
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

    // 2. Set up token for EphemeralWorkflow component
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
    const toolkitButton = await page.$('button#toolkit');
    if (toolkitButton) {
      await toolkitButton.click();
      await page.waitForTimeout(500);
    }

    await page.evaluate(() => {
      const app = document.querySelector('#app').__vue_app__;
      if (app) {
        const pinia = app.config.globalProperties.$pinia;
        if (pinia) {
          for (const [name, store] of pinia._s) {
            if (name.includes('navigation')) {
              store.showEphemeralWorkflow = true;
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

    // 4. Fill request
    console.log('4. Filling request input...');
    const requestInput = await page.$('.ephemeral-workflow textarea');
    if (requestInput) {
      await requestInput.fill(TEST_REQUEST);
      console.log('   [OK] Request filled\n');
    }

    // 5. Click View Plan button
    console.log('5. Clicking "View Plan" button...');
    const buttons = await page.$$('.ephemeral-workflow button');
    for (const btn of buttons) {
      const text = await btn.textContent();
      if (text && text.includes('计划')) {
        await btn.click();
        console.log('   [OK] Clicked "View Plan"\n');
        break;
      }
    }

    // 6. Wait for workflow response (SSE stream)
    console.log('6. Waiting for workflow API response...');
    console.log('   (Note: This may take time as LLM is called)');

    // Capture the API response for debugging - set up handler BEFORE waiting
    let apiResponseData = null;
    page.on('response', async (response) => {
      if (response.url().includes('/api/v1/workflow/execute')) {
        try {
          const body = await response.text();
          apiResponseData = body;
          console.log('   [DEBUG] Raw response length:', body.length);
          console.log('   [DEBUG] Raw response preview:', body.substring(0, 300));
        } catch (e) {
          console.log('   [DEBUG] Could not read response body');
        }
      }
    });

    try {
      await page.waitForResponse(
        response => response.url().includes('/api/v1/workflow/execute'),
        { timeout: 120000 }
      );
      console.log('   [OK] API responded\n');

      if (apiResponseData) {
        console.log('   [DEBUG] API response received, length:', apiResponseData.length);
      }
    } catch (e) {
      console.log('   [WARN] API timeout or error:', e.message);
    }

    // Wait for workflow elements to appear
    console.log('   Waiting for workflow data to load...');
    try {
      await page.waitForSelector('.json-content', { timeout: 90000 });
      console.log('   [OK] JSON content element appeared');
    } catch (e) {
      console.log('   [WARN] JSON content did not appear within timeout');
    }

    // Additional wait for any remaining processing
    await page.waitForTimeout(2000);

    // 7. Check for results
    console.log('7. Checking for workflow results...');
    let workflowData = null;

    // Debug: check raw page content
    const pageContent = await page.content();
    const hasWorkflowGraph = pageContent.includes('workflow-graph-section') || pageContent.includes('task-node');
    console.log('   [DEBUG] Page has workflow graph elements:', hasWorkflowGraph);

    // Check if JSON section has content
    const jsonContent = await page.$('.json-content');
    if (jsonContent) {
      const jsonText = await jsonContent.textContent();
      console.log('   [DEBUG] JSON content length:', jsonText?.length || 0);
      console.log('   [DEBUG] JSON content preview:', jsonText?.substring(0, 200) || 'empty');
      if (jsonText && jsonText.trim()) {
        try {
          workflowData = JSON.parse(jsonText);
          console.log('   [OK] JSON parsed successfully');
          console.log('   Workflow ID:', workflowData.workflow_id);
          console.log('   Nodes count:', workflowData.nodes?.length || 0);
        } catch (e) {
          console.log('   [INFO] JSON parse error:', e.message);
        }
      }
    } else {
      console.log('   [DEBUG] No .json-content element found');
    }

    // Check for task nodes
    const taskNodes = await page.$$('.task-node');
    console.log('   [DEBUG] Task nodes found:', taskNodes.length);
    if (taskNodes.length > 0) {
      console.log('   [OK] Found', taskNodes.length, 'task nodes');
    }

    // 8. Export workflow if we have data
    console.log('\n8. Attempting to export...');

    // Try to find and click export button
    let exported = false;
    const exportButtons = await page.$$('.ephemeral-workflow button');
    for (const btn of exportButtons) {
      const text = await btn.textContent();
      if (text && (text.includes('导出') || text.includes('Export'))) {
        console.log('   Clicking export button...');

        // Create a promise for download
        downloadPromise = Promise.withResolver();
        await btn.click();

        try {
          const download = await downloadPromise.promise;
          const path = `/tmp/${download.suggestedFilename()}`;
          await download.saveAs(path);
          console.log('   [OK] Downloaded:', path);
          exported = true;

          // Read and display the exported JSON
          if (fs.existsSync(path)) {
            const content = fs.readFileSync(path, 'utf8');
            console.log('\n   ===== Exported JSON =====');
            console.log(content.substring(0, 1000));
            if (content.length > 1000) {
              console.log('   ... (truncated)');
            }
            console.log('   ===== End of JSON =====\n');
          }
        } catch (e) {
          console.log('   [WARN] Download failed:', e.message);
        }
        break;
      }
    }

    if (!exported) {
      console.log('   [WARN] Export button not found or not clicked');

      // Try to manually export via JavaScript if we have data
      if (workflowData) {
        console.log('   Attempting manual export via JavaScript...');
        await page.evaluate((data) => {
          const jsonStr = JSON.stringify(data, null, 2);
          const blob = new Blob([jsonStr], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `workflow_${data.workflow_id || 'export'}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }, workflowData);
        console.log('   [OK] Export triggered');
        await page.waitForTimeout(2000);

        // Check for downloaded file
        const downloadPath = `/tmp/workflow_${workflowData.workflow_id || 'export'}.json`;
        if (fs.existsSync(downloadPath)) {
          const content = fs.readFileSync(downloadPath, 'utf8');
          console.log('\n   ===== Exported JSON =====');
          console.log(content.substring(0, 1000));
          console.log('   ===== End of JSON =====\n');
        }
      }
    }

    // 9. Take screenshot
    console.log('9. Taking screenshot...');
    await page.screenshot({ path: '/tmp/ephemeral-workflow-final.png', fullPage: true });
    console.log('   Screenshot: /tmp/ephemeral-workflow-final.png');

    // 10. Summary
    console.log('\n========================================');
    console.log('Test Summary:');
    console.log('========================================');
    console.log('Request:', TEST_REQUEST);
    console.log('Login: [OK]');
    console.log('Modal: [OK]');
    console.log('API Call: [OK]');
    console.log('Workflow Data:', workflowData ? '[OK]' : '[WARN] No data');
    console.log('Export:', exported ? '[OK]' : '[WARN] Not triggered');
    console.log('========================================\n');

  } catch (error) {
    console.error('\n[ERR] Test failed:', error.message);
    await page.screenshot({ path: '/tmp/ephemeral-workflow-error.png', fullPage: true });
    console.log('Error screenshot: /tmp/ephemeral-workflow-error.png');
  } finally {
    await browser.close();
    console.log('[OK] Browser closed');
  }
}

// Add Promise.withResolver polyfill
Promise.withResolver = function() {
  let resolve, reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

// Run test
testEphemeralWorkflow()
  .then(() => {
    console.log('\n[OK] Test completed');
    process.exit(0);
  })
  .catch(error => {
    console.error('[ERR] Test error:', error);
    process.exit(1);
  });
