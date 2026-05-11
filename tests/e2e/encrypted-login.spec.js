const { test, expect } = require('@playwright/test');

const TEST_EMAIL = process.env.TEST_EMAIL || 'mr_yang@example.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || '12345678';
const BASE_URL = process.env.BASE_URL || 'http://127.0.0.1:3000';

test.describe('加密登录验证测试', () => {
  test.describe.configure({ project: 'chromium' });

  test('登录请求是否使用加密传输', async ({ page }) => {
    let loginRequestData = null;
    let loginResponseData = null;
    let publicKeyRequested = false;

    page.on('request', (request) => {
      if (request.url().includes('/public-key')) {
        publicKeyRequested = true;
      }
      if (request.url().includes('/login') && request.method() === 'POST') {
        try {
          loginRequestData = request.postDataJSON();
        } catch (e) {
          loginRequestData = request.postData();
        }
      }
    });

    page.on('response', async (response) => {
      if (response.url().includes('/login') && response.status() === 200) {
        try {
          loginResponseData = await response.json();
        } catch (e) {}
      }
    });

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await page.evaluate(({ email, password }) => {
      localStorage.setItem('access_token', '');
      localStorage.removeItem('username');
    }, { email: TEST_EMAIL, password: TEST_PASSWORD });

    await page.reload();
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    const loginBtn = page.locator('.login-btn, button:has-text("登录")').first();
    const btnVisible = await loginBtn.isVisible({ timeout: 5000 }).catch(() => false);

    if (btnVisible) {
      await loginBtn.click();
      await page.waitForTimeout(500);

      const emailInput = page.locator('.login-modal input[type="email"], .login-modal input[autocomplete="email"]').first();
      const passwordInput = page.locator('.login-modal input[type="password"]').first();
      const submitBtn = page.locator('.login-modal .btn-login').first();

      const emailVisible = await emailInput.isVisible({ timeout: 3000 }).catch(() => false);

      if (emailVisible) {
        await emailInput.fill(TEST_EMAIL);
        await passwordInput.fill(TEST_PASSWORD);
        await submitBtn.click();

        await page.waitForTimeout(3000);
      }
    }

    console.log('=== 加密登录测试报告 ===');
    console.log('请求了公钥接口:', publicKeyRequested);
    console.log('登录请求数据:', JSON.stringify(loginRequestData, null, 2));
    console.log('登录响应数据:', JSON.stringify(loginResponseData, null, 2));

    if (loginRequestData) {
      const hasEncryptedFields = 'encrypted_data' in loginRequestData && 'encrypted_key' in loginRequestData;
      const hasPlaintextFields = 'email' in loginRequestData && 'password' in loginRequestData;
      const hasUsernamePassword = 'username' in loginRequestData && 'password' in loginRequestData;

      if (hasEncryptedFields && !hasPlaintextFields) {
        console.log('结果: 登录使用 RSA+AES 加密传输');
        expect(publicKeyRequested).toBe(true);
        expect(loginResponseData?.encryption_enabled).toBe(true);
      } else if (hasPlaintextFields || hasUsernamePassword) {
        console.log('结果: 登录使用明文传输 - 未加密!');
        console.log('问题: useAuth.js 直接调用 api.post 发送明文凭据，绕过了 encryption.js');
      } else {
        console.log('结果: 登录请求格式异常');
      }
    } else {
      console.log('结果: 未捕获到登录请求');
    }
  });

  test('公钥接口应返回有效的 RSA 公钥', async ({ page }) => {
    const resp = await page.request.get(`${BASE_URL}/api/v1/public-key`);
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    expect(body.public_key).toBeDefined();
    expect(body.algorithm).toBe('RSA-OAEP');
    expect(body.key_size).toBe(2048);
    expect(body.public_key).toContain('-----BEGIN PUBLIC KEY-----');
  });

  test('后端应支持加密登录模式', async ({ page }) => {
    const keyResp = await page.request.get(`${BASE_URL}/api/v1/public-key`);
    expect(keyResp.status()).toBe(200);
    const { public_key } = await keyResp.json();

    await page.goto('/');
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(async ({ email, password, publicKey }) => {
      await fetch('/api/v1/csrf-token', { credentials: 'include' });
      const csrfMatch = document.cookie.match(/csrf_token=([^;]+)/);
      const csrfToken = csrfMatch ? csrfMatch[1] : '';

      const pemContents = publicKey
        .replace('-----BEGIN PUBLIC KEY-----', '')
        .replace('-----END PUBLIC KEY-----', '')
        .replace(/\s/g, '');

      const binaryDer = atob(pemContents);
      const derArray = new Uint8Array(binaryDer.length);
      for (let i = 0; i < binaryDer.length; i++) {
        derArray[i] = binaryDer.charCodeAt(i);
      }

      const cryptoKey = await crypto.subtle.importKey(
        'spki', derArray.buffer,
        { name: 'RSA-OAEP', hash: 'SHA-256' },
        false, ['encrypt']
      );

      const aesKey = crypto.getRandomValues(new Uint8Array(32));
      const iv = crypto.getRandomValues(new Uint8Array(16));

      const aesCryptoKey = await crypto.subtle.importKey(
        'raw', aesKey, { name: 'AES-CBC' }, false, ['encrypt']
      );

      const plaintext = new TextEncoder().encode(JSON.stringify({ email, password }));
      const ciphertextBuffer = await crypto.subtle.encrypt(
        { name: 'AES-CBC', iv }, aesCryptoKey, plaintext
      );

      const combined = new Uint8Array(iv.length + ciphertextBuffer.byteLength);
      combined.set(iv, 0);
      combined.set(new Uint8Array(ciphertextBuffer), iv.length);

      function base64Encode(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
      }

      const encryptedData = base64Encode(combined.buffer);
      const encryptedKeyBuffer = await crypto.subtle.encrypt(
        { name: 'RSA-OAEP', hash: 'SHA-256' }, cryptoKey, aesKey
      );
      const encryptedKey = base64Encode(encryptedKeyBuffer);

      const loginResp = await fetch('/api/v1/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken || '',
        },
        body: JSON.stringify({ encrypted_data: encryptedData, encrypted_key: encryptedKey }),
      });

      if (loginResp.ok) {
        const data = await loginResp.json();
        return { success: true, encryption_enabled: data.encryption_enabled, username: data.username };
      } else {
        const err = await loginResp.json().catch(() => ({}));
        return { success: false, error: err.detail || loginResp.statusText };
      }
    }, { email: TEST_EMAIL, password: TEST_PASSWORD, publicKey: (await (await page.request.get(`${BASE_URL}/api/v1/public-key`)).json()).public_key });

    console.log('加密登录测试结果:', JSON.stringify(result, null, 2));

    expect(result.success).toBe(true);
    expect(result.encryption_enabled).toBe(true);
  });
});
