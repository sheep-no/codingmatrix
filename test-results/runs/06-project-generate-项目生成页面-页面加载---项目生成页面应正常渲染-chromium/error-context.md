# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 06-project-generate.spec.js >> 项目生成页面 >> 页面加载 - 项目生成页面应正常渲染
- Location: tests/e2e/06-project-generate.spec.js:13:7

# Error details

```
Error: Channel closed
```

```
Error: locator.click: Target page, context or browser has been closed
Call log:
  - waiting for locator('button[class*="btn-login"], button:has-text("登录")').first()
    - locator resolved to <button class="login-btn">…</button>
  - attempting click action
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div data-v-762c07c8="" class="login-modal">…</div> intercepts pointer events
    - retrying click action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and stable
      - element is visible, enabled and stable
      - scrolling into view if needed
      - done scrolling
      - <div data-v-762c07c8="" class="login-modal">…</div> intercepts pointer events
    - retrying click action
      - waiting 100ms
    24 × waiting for element to be visible, enabled and stable
       - element is visible, enabled and stable
       - scrolling into view if needed
       - done scrolling
       - <div data-v-762c07c8="" class="login-modal">…</div> intercepts pointer events
     - retrying click action
       - waiting 500ms

```

```
Error: browserContext.close: Target page, context or browser has been closed
```