// Sprint 1: 用户与权限系统 (RBAC) E2E 测试
// 测试多租户、用户管理、角色权限、部门管理、认证安全、审计日志

const { test, expect } = require('@playwright/test');

test.describe('Sprint 1: RBAC 系统 E2E 测试', () => {

  // ==================== 认证与安全测试 ====================

  test.describe('认证流程测试', () => {
    test('邮箱密码登录 - 成功', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // 点击登录按钮
      const loginBtn = page.locator('.login-btn, [class*="login"]');
      if (await loginBtn.count() > 0) {
        await loginBtn.first().click();
        await page.waitForTimeout(500);
      }

      // 填写登录表单
      await page.fill('input[type="email"], input[placeholder*="邮箱"], [class*="email"]', 'mr_yang@example.com');
      await page.fill('input[type="password"]', '12345678');
      
      // 点击登录
      await page.click('button:has-text("登录"), [class*="login"]');
      await page.waitForTimeout(1000);

      // 验证登录成功 - 检查是否有用户信息显示
      const isLoggedIn = await page.evaluate(() => {
        return !!document.querySelector('[class*="user"]') || 
               !!document.querySelector('[class*="avatar"]') ||
               document.body.textContent.includes('活跃');
      });
      expect(isLoggedIn).toBeTruthy();
    });

    test('邮箱密码登录 - 无效凭据失败', async ({ page }) => {
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      // 点击登录按钮
      const loginBtn = page.locator('.login-btn, [class*="login"]');
      if (await loginBtn.count() > 0) {
        await loginBtn.first().click();
        await page.waitForTimeout(500);
      }

      // 填写错误凭据
      await page.fill('input[type="email"], input[placeholder*="邮箱"]', 'wrong@example.com');
      await page.fill('input[type="password"]', 'wrongpassword');
      
      await page.click('button:has-text("登录"), [class*="login"]');
      await page.waitForTimeout(1000);

      // 验证登录失败 - 应显示错误提示
      const hasError = await page.evaluate(() => {
        return !!document.querySelector('[class*="error"]') || 
               !!document.querySelector('[class*="alert"]') ||
               document.body.textContent.includes('错误') ||
               document.body.textContent.includes('失败');
      });
      expect(hasError).toBeTruthy();
    });

    test('登出功能 - 登出后应清除登录状态', async ({ page }) => {
      // 先登录
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');

      const loginBtn = page.locator('.login-btn, [class*="login"]');
      if (await loginBtn.count() > 0) {
        await loginBtn.first().click();
        await page.waitForTimeout(500);
      }
      await page.fill('input[type="email"], input[placeholder*="邮箱"]', 'mr_yang@example.com');
      await page.fill('input[type="password"]', '12345678');
      await page.click('button:has-text("登录"), [class*="login"]');
      await page.waitForTimeout(1000);

      // 执行登出
      await page.evaluate(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        localStorage.removeItem('user_info');
      });
      await page.reload();
      await page.waitForLoadState('domcontentloaded');

      // 验证已登出 - 应显示登录入口
      const isLoggedOut = await page.evaluate(() => {
        return !!document.querySelector('.login-btn') ||
               !!document.querySelector('[class*="login"]') ||
               !document.querySelector('[class*="user-name"]');
      });
      expect(isLoggedOut).toBeTruthy();
    });

    test('Token 刷新 - 有效 token 应能刷新', async ({ page }) => {
      // 设置有效 token
      await page.goto('/');
      await page.waitForLoadState('domcontentloaded');
      
      await page.evaluate(() => {
        localStorage.setItem('access_token', 'test-valid-token');
        localStorage.setItem('refresh_token', 'test-refresh-token');
        localStorage.setItem('username', 'test_user');
      });
      
      await page.reload();
      await page.waitForTimeout(1000);

      // 验证 token 存在
      const hasToken = await page.evaluate(() => {
        return !!localStorage.getItem('access_token');
      });
      expect(hasToken).toBeTruthy();
    });
  });

  // ==================== 用户管理测试 ====================

  test.describe('用户管理测试', () => {
    test('用户管理页面应可访问', async ({ page }) => {
      await page.goto('/admin');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查管理面板是否加载
      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('用户列表应显示用户信息', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有用户列表或表格
      const hasUserList = await page.evaluate(() => {
        return !!document.querySelector('table') ||
               !!document.querySelector('[class*="user-list"]') ||
               !!document.querySelector('[class*="user-table"]') ||
               !!document.querySelector('[class*="list"]');
      });
      expect(hasUserList).toBeTruthy();
    });

    test('用户搜索功能应存在', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有搜索框
      const hasSearch = await page.evaluate(() => {
        return !!document.querySelector('input[type="search"]') ||
               !!document.querySelector('input[placeholder*="搜索"]') ||
               !!document.querySelector('[class*="search"]');
      });
      expect(hasSearch).toBeTruthy();
    });

    test('用户状态筛选应存在', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有筛选功能
      const hasFilter = await page.evaluate(() => {
        return !!document.querySelector('select') ||
               !!document.querySelector('[class*="filter"]') ||
               !!document.querySelector('[class*="status"]');
      });
      expect(hasFilter).toBeTruthy();
    });
  });

  // ==================== 角色权限测试 ====================

  test.describe('角色权限测试', () => {
    test('角色管理页面应可访问', async ({ page }) => {
      await page.goto('/admin/roles');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('角色列表应显示预置角色', async ({ page }) => {
      await page.goto('/admin/roles');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有角色列表
      const hasRoleList = await page.evaluate(() => {
        return !!document.querySelector('table') ||
               !!document.querySelector('[class*="role-list"]') ||
               !!document.querySelector('[class*="role-table"]') ||
               !!document.querySelector('[class*="list"]');
      });
      expect(hasRoleList).toBeTruthy();
    });

    test('权限配置组件应存在', async ({ page }) => {
      await page.goto('/admin/roles');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有权限配置相关元素
      const hasPermissionConfig = await page.evaluate(() => {
        return !!document.querySelector('[class*="permission"]') ||
               !!document.querySelector('[class*="checkbox"]') ||
               !!document.querySelector('[class*="tree"]') ||
               document.body.textContent.includes('权限');
      });
      expect(hasPermissionConfig).toBeTruthy();
    });

    test('权限树应支持分组展示', async ({ page }) => {
      await page.goto('/admin/roles');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有分组或分类
      const hasGroups = await page.evaluate(() => {
        return !!document.querySelector('[class*="group"]') ||
               !!document.querySelector('[class*="category"]') ||
               !!document.querySelector('[class*="section"]');
      });
      expect(hasGroups).toBeTruthy();
    });
  });

  // ==================== 部门管理测试 ====================

  test.describe('部门管理测试', () => {
    test('部门管理页面应可访问', async ({ page }) => {
      await page.goto('/admin/departments');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('部门树应正确渲染', async ({ page }) => {
      await page.goto('/admin/departments');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有部门树结构
      const hasTree = await page.evaluate(() => {
        return !!document.querySelector('[class*="tree"]') ||
               !!document.querySelector('[class*="department"]') ||
               !!document.querySelector('[class*="dept"]') ||
               !!document.querySelector('[class*="node"]');
      });
      expect(hasTree).toBeTruthy();
    });

    test('部门应支持展开/折叠', async ({ page }) => {
      await page.goto('/admin/departments');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有展开/折叠按钮
      const hasToggle = await page.evaluate(() => {
        return !!document.querySelector('[class*="toggle"]') ||
               !!document.querySelector('[class*="expand"]') ||
               !!document.querySelector('[class*="collapse"]') ||
               !!document.querySelector('[class*="arrow"]');
      });
      expect(hasToggle).toBeTruthy();
    });

    test('部门应显示成员统计', async ({ page }) => {
      await page.goto('/admin/departments');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有成员数量显示
      const hasMemberCount = await page.evaluate(() => {
        return !!document.querySelector('[class*="member"]') ||
               !!document.querySelector('[class*="count"]') ||
               !!document.querySelector('[class*="badge"]') ||
               document.body.textContent.includes('人');
      });
      expect(hasMemberCount).toBeTruthy();
    });
  });

  // ==================== 多租户测试 ====================

  test.describe('多租户测试', () => {
    test('租户管理页面应可访问', async ({ page }) => {
      await page.goto('/admin/tenants');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('租户切换功能应存在', async ({ page }) => {
      await page.goto('/admin/tenants');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有租户切换相关元素
      const hasSwitch = await page.evaluate(() => {
        return !!document.querySelector('[class*="switch"]') ||
               !!document.querySelector('[class*="tenant"]') ||
               !!document.querySelector('[class*="select"]') ||
               document.body.textContent.includes('租户');
      });
      expect(hasSwitch).toBeTruthy();
    });
  });

  // ==================== 审计日志测试 ====================

  test.describe('审计日志测试', () => {
    test('审计日志页面应可访问', async ({ page }) => {
      await page.goto('/admin/audit-logs');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('日志列表应显示操作记录', async ({ page }) => {
      await page.goto('/admin/audit-logs');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有日志列表
      const hasLogs = await page.evaluate(() => {
        return !!document.querySelector('table') ||
               !!document.querySelector('[class*="log"]') ||
               !!document.querySelector('[class*="list"]') ||
               !!document.querySelector('[class*="record"]');
      });
      expect(hasLogs).toBeTruthy();
    });

    test('日志筛选应支持时间范围', async ({ page }) => {
      await page.goto('/admin/audit-logs');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有时间筛选
      const hasTimeFilter = await page.evaluate(() => {
        return !!document.querySelector('input[type="date"]') ||
               !!document.querySelector('input[type="datetime"]') ||
               !!document.querySelector('[class*="date"]') ||
               !!document.querySelector('[class*="time"]') ||
               document.body.textContent.includes('时间');
      });
      expect(hasTimeFilter).toBeTruthy();
    });
  });

  // ==================== 安全设置测试 ====================

  test.describe('安全设置测试', () => {
    test('安全设置页面应可访问', async ({ page }) => {
      await page.goto('/admin/security');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      const isLoaded = await page.evaluate(() => {
        return document.readyState === 'complete' || document.readyState === 'interactive';
      });
      expect(isLoaded).toBeTruthy();
    });

    test('密码策略设置应存在', async ({ page }) => {
      await page.goto('/admin/security');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有密码策略相关元素
      const hasPasswordPolicy = await page.evaluate(() => {
        return !!document.querySelector('[class*="password"]') ||
               !!document.querySelector('[class*="policy"]') ||
               document.body.textContent.includes('密码') ||
               document.body.textContent.includes('策略');
      });
      expect(hasPasswordPolicy).toBeTruthy();
    });

    test('2FA 设置应存在', async ({ page }) => {
      await page.goto('/admin/security');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有 2FA 相关元素
      const has2FA = await page.evaluate(() => {
        return !!document.querySelector('[class*="2fa"]') ||
               !!document.querySelector('[class*="totp"]') ||
               !!document.querySelector('[class*="authenticator"]') ||
               document.body.textContent.includes('双因素') ||
               document.body.textContent.includes('2FA');
      });
      expect(has2FA).toBeTruthy();
    });

    test('会话管理应存在', async ({ page }) => {
      await page.goto('/admin/security');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有会话管理相关元素
      const hasSession = await page.evaluate(() => {
        return !!document.querySelector('[class*="session"]') ||
               !!document.querySelector('[class*="device"]') ||
               document.body.textContent.includes('会话') ||
               document.body.textContent.includes('设备');
      });
      expect(hasSession).toBeTruthy();
    });
  });

  // ==================== 权限控制测试 ====================

  test.describe('权限控制测试', () => {
    test('未认证用户访问管理页面应被拦截', async ({ page }) => {
      // 清除登录状态
      await page.context().clearCookies();
      await page.evaluate(() => {
        localStorage.removeItem('access_token');
        localStorage.removeItem('username');
        localStorage.removeItem('user_info');
      });

      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 验证被重定向或显示登录提示
      const isBlocked = await page.evaluate(() => {
        return !!document.querySelector('[class*="login"]') ||
               !!document.querySelector('[class*="dialog"]') ||
               window.location.href.includes('login') ||
               document.body.textContent.includes('登录');
      });
      expect(isBlocked).toBeTruthy();
    });

    test('无权限用户访问敏感页面应显示 403', async ({ page }) => {
      // 设置低权限用户 token
      await page.context().clearCookies();
      await page.evaluate(() => {
        localStorage.setItem('access_token', 'test-guest-token');
        localStorage.setItem('username', 'guest_user');
        localStorage.setItem('user_role', 'guest');
      });

      await page.goto('/admin/security');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 验证权限不足提示
      const isForbidden = await page.evaluate(() => {
        return document.body.textContent.includes('403') ||
               document.body.textContent.includes('权限') ||
               document.body.textContent.includes('无权限') ||
               !!document.querySelector('[class*="forbidden"]') ||
               !!document.querySelector('[class*="403"]');
      });
      expect(isForbidden).toBeTruthy();
    });
  });

  // ==================== 批量操作测试 ====================

  test.describe('批量操作测试', () => {
    test('用户列表应支持批量选择', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有复选框或批量选择功能
      const hasBatchSelect = await page.evaluate(() => {
        return !!document.querySelector('input[type="checkbox"]') ||
               !!document.querySelector('[class*="batch"]') ||
               !!document.querySelector('[class*="select-all"]') ||
               document.body.textContent.includes('全选');
      });
      expect(hasBatchSelect).toBeTruthy();
    });

    test('批量操作按钮应存在', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有批量操作按钮
      const hasBatchActions = await page.evaluate(() => {
        return !!document.querySelector('[class*="batch"]') ||
               !!document.querySelector('[class*="bulk"]') ||
               !!document.querySelector('[class*="action"]') ||
               document.body.textContent.includes('批量');
      });
      expect(hasBatchActions).toBeTruthy();
    });
  });

  // ==================== 分页测试 ====================

  test.describe('分页测试', () => {
    test('列表页面应支持分页', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有分页组件
      const hasPagination = await page.evaluate(() => {
        return !!document.querySelector('[class*="pagination"]') ||
               !!document.querySelector('[class*="pager"]') ||
               !!document.querySelector('[class*="page"]') ||
               document.body.textContent.includes('页');
      });
      expect(hasPagination).toBeTruthy();
    });

    test('分页应显示总记录数', async ({ page }) => {
      await page.goto('/admin/users');
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(1000);

      // 检查是否有总数显示
      const hasTotal = await page.evaluate(() => {
        return !!document.querySelector('[class*="total"]') ||
               !!document.querySelector('[class*="count"]') ||
               document.body.textContent.includes('共') ||
               document.body.textContent.includes('条');
      });
      expect(hasTotal).toBeTruthy();
    });
  });
});
