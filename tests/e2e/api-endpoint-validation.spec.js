/**
 * API 端点验证测试
 * 检查前后端API路径是否一致
 */

import { test, expect } from '@playwright/test';

const BACKEND_BASE = 'http://localhost:8000';

// 前端调用的API路径列表（从 src/utils/api/*.js 中提取）
const frontendApis = {
  project: [
    '/api/v1/agent/generate',
    '/api/v1/agent/orchestrate/stream',
    '/api/v1/agent/session/{session_id}/action',
    '/api/v1/agent/sessions/{session_id}',
    '/api/v1/agent/session/{session_id}/decision',
    '/api/v1/agent/saved',
    '/api/v1/agent/saved/{project_id}',
    '/api/v1/agent/save',
    '/api/v1/agent/generate/files',
    '/api/v1/agent/generate/read',
    '/api/v1/agent/generate/file',
    '/api/v1/agent/modify',
    '/api/v1/agent/analyze_complexity',
    '/api/v1/agent/orchestrate',
    '/api/v1/agent/evaluate',
  ],
  agent: [
    '/api/v1/agent/snapshots/{session_id}',
    '/api/v1/agent/rollback/{session_id}',
    '/api/v1/agent/snapshot/diff',
    '/api/v1/agent/knowledge',
    '/api/v1/agent/knowledge/search',
    '/api/v1/agent/requirement-association',
    '/api/v1/agent/requirement-association/confirm',
    '/api/v1/agent/requirement-association/helpfulness',
    '/api/v1/agent/requirement-association/stats',
    '/api/v1/agent/performance',
    '/api/v1/agent/performance/trends',
    '/api/v1/agent/performance/export',
    '/api/v1/agent/learning/stats',
    '/api/v1/agent/learning/common-errors/{file_type}',
    '/api/v1/agent/concurrent-limits/recommended',
    '/api/v1/agent/concurrent-limits',
    '/api/v1/agent/concurrent-limits/history',
    '/api/v1/agent/cache/stats',
    '/api/v1/agent/cache/clear',
  ],
  admin: [
    '/api/v2/admin/users',
    '/api/v2/admin/users/{user_id}',
    '/api/v2/admin/services',
    '/api/v2/admin/services/{service_name}',
    '/api/v2/admin/config',
    '/api/v2/admin/logs',
  ],
  user: [
    '/api/v2/Controller/GetCurrentUser',
    '/api/v2/Controller/Logout',
  ],
  resource: [
    '/api/v2/Controller/ListAllServices',
    '/api/v2/Controller/GetServiceStatus',
    '/api/v2/Controller/StartService',
    '/api/v2/Controller/StopService',
    '/api/v2/Controller/RestartService',
  ],
  girlai: [
    '/api/v2/Controller/AiChat',
    '/api/v2/Controller/AudioChat',
    '/api/v2/Controller/UploadImage',
    '/api/v2/Controller/GetAvatarList',
  ],
  nginx: [
    '/api/v2/Controller/GetNginxConfig',
    '/api/v2/Controller/UpdateNginxConfig',
    '/api/v2/Controller/ReloadNginx',
  ],
};

// 后端实际路由（从 app/api/v1/ai_agent/*.py 和 app/api/v2/*.py 中提取）
const backendRoutes = {
  '/api/v1/agent/generate': 'POST',
  '/api/v1/agent/generate/download/{project_path}': 'GET',
  '/api/v1/agent/generate/files': 'GET',
  '/api/v1/agent/generate/read': 'GET',
  '/api/v1/agent/generate/file': 'DELETE',
  '/api/v1/agent/save': 'POST',
  '/api/v1/agent/saved': 'GET',
  '/api/v1/agent/session/{session_id}/action': 'POST',
  '/api/v1/agent/sessions/{session_id}': 'DELETE',
  '/api/v1/agent/session/{session_id}/decision': 'POST',
  '/api/v1/agent/saved/{project_id}': 'GET,DELETE',
  '/api/v1/agent/snapshots/{session_id}': 'GET',
  '/api/v1/agent/rollback/{session_id}': 'POST',
  '/api/v1/agent/learning/common-errors/{file_type}': 'GET',
  '/api/v2/admin/users/{user_id}': 'DELETE',
  '/api/v2/admin/services/{service_name}': 'DELETE',
  '/api/v1/agent/modify': 'POST',
  '/api/v1/agent/orchestrate': 'POST',
  '/api/v1/agent/orchestrate/stream': 'POST',
  '/api/v1/agent/analyze_complexity': 'POST',
  '/api/v1/agent/session/{session_id}/action': 'POST',
  '/api/v1/agent/sessions/{session_id}': 'DELETE',
  '/api/v1/agent/session/{session_id}/decision': 'POST',
  '/api/v1/agent/evaluate': 'POST',
  '/api/v1/agent/snapshots/{session_id}': 'GET',
  '/api/v1/agent/rollback/{session_id}': 'POST',
  '/api/v1/agent/snapshot/diff': 'GET',
  '/api/v1/agent/knowledge': 'POST,GET',
  '/api/v1/agent/knowledge/search': 'GET',
  '/api/v1/agent/requirement-association': 'POST',
  '/api/v1/agent/requirement-association/confirm': 'POST',
  '/api/v1/agent/requirement-association/helpfulness': 'POST',
  '/api/v1/agent/requirement-association/stats': 'GET',
  '/api/v1/agent/performance': 'GET',
  '/api/v1/agent/performance/trends': 'GET',
  '/api/v1/agent/performance/export': 'POST',
  '/api/v1/agent/learning/stats': 'GET',
  '/api/v1/agent/learning/common-errors/{file_type}': 'GET',
  '/api/v1/agent/concurrent-limits/recommended': 'GET',
  '/api/v1/agent/concurrent-limits': 'PUT',
  '/api/v1/agent/concurrent-limits/history': 'GET',
  '/api/v1/agent/cache/stats': 'GET',
  '/api/v1/agent/cache/clear': 'POST',
  '/api/v2/admin/users': 'GET,POST',
  '/api/v2/admin/users/{user_id}': 'DELETE',
  '/api/v2/admin/services': 'GET,POST',
  '/api/v2/admin/services/{service_name}': 'DELETE',
  '/api/v2/admin/config': 'GET,PUT',
  '/api/v2/admin/logs': 'GET',
  '/api/v2/Controller/GetCurrentUser': 'GET',
  '/api/v2/Controller/Logout': 'POST',
  '/api/v2/Controller/ListAllServices': 'GET',
  '/api/v2/Controller/GetServiceStatus': 'GET',
  '/api/v2/Controller/StartService': 'POST',
  '/api/v2/Controller/StopService': 'POST',
  '/api/v2/Controller/RestartService': 'POST',
  '/api/v2/Controller/AiChat': 'POST',
  '/api/v2/Controller/AudioChat': 'POST',
  '/api/v2/Controller/UploadImage': 'POST',
  '/api/v2/Controller/GetAvatarList': 'GET',
  '/api/v2/Controller/GetNginxConfig': 'GET',
  '/api/v2/Controller/UpdateNginxConfig': 'POST',
  '/api/v2/Controller/ReloadNginx': 'POST',
};

test.describe('API端点验证', () => {
  test('检查前端API路径是否与后端匹配', async () => {
    const mismatches = [];
    
    // 检查所有前端API路径
    for (const [category, apis] of Object.entries(frontendApis)) {
      for (const frontendApi of apis) {
        // 查找匹配的后端路由
        const backendMatch = Object.keys(backendRoutes).find(route => {
          // 规范化路径参数比较
          const normalizedRoute = route.replace(/\{[^}]+\}/g, '{param}');
          const normalizedTestPath = frontendApi.replace(/\{[^}]+\}/g, '{param}');
          return normalizedRoute === normalizedTestPath;
        });
        
        if (!backendMatch) {
          mismatches.push({
            frontendPath: frontendApi,
            category,
            issue: '后端无匹配路由'
          });
        } else {
          console.log(`✓ ${frontendApi} -> ${backendMatch}`);
        }
      }
    }
    
    if (mismatches.length > 0) {
      console.log('\n发现路径不匹配:');
      mismatches.forEach(m => {
        console.log(`  [${m.category}] ${m.frontendPath} - ${m.issue}`);
      });
      
      test.info().annotations.push({
        type: 'api-mismatches',
        description: JSON.stringify(mismatches, null, 2)
      });
    }
    
    console.log(`\n总计: ${Object.values(frontendApis).flat().length} 个前端API`);
    console.log(`匹配: ${Object.values(frontendApis).flat().length - mismatches.length} 个`);
    console.log(`不匹配: ${mismatches.length} 个`);
    
    // 所有路径都应该匹配
    expect(mismatches.length).toBe(0);
  });
  
  test('检查后端路由是否都有前端调用', async ({ request }) => {
    const unusedBackendRoutes = [];
    
    // 检查所有后端路由是否被前端使用
    for (const [backendRoute, methods] of Object.entries(backendRoutes)) {
      const normalizedBackendRoute = backendRoute.replace(/\{[^}]+\}/g, '{param}');
      
      const frontendMatch = Object.values(frontendApis).flat().find(frontendApi => {
        const normalizedFrontendApi = frontendApi.replace(/\{[^}]+\}/g, '{param}');
        return normalizedFrontendApi === normalizedBackendRoute;
      });
      
      if (!frontendMatch) {
        unusedBackendRoutes.push({
          route: backendRoute,
          methods,
          issue: '前端未使用此路由'
        });
      }
    }
    
    if (unusedBackendRoutes.length > 0) {
      console.log('\n发现后端路由未被前端使用:');
      unusedBackendRoutes.forEach(r => {
        console.log(`  ${r.route} (${r.methods}) - ${r.issue}`);
      });
      
      test.info().annotations.push({
        type: 'unused-backend-routes',
        description: JSON.stringify(unusedBackendRoutes, null, 2)
      });
    }
    
    console.log(`\n后端路由总计: ${Object.keys(backendRoutes).length} 个`);
    console.log(`被前端使用: ${Object.keys(backendRoutes).length - unusedBackendRoutes.length} 个`);
    console.log(`未被使用: ${unusedBackendRoutes.length} 个`);
    
    // 可以有一些未被使用的后端路由（内部API）
    // 但应该少于20%
    expect(unusedBackendRoutes.length).toBeLessThan(Object.keys(backendRoutes).length * 0.2);
  });
  
  test('验证关键API端点可访问性', async ({ request }) => {
    const endpointStatus = [];
    
    // 测试关键端点（使用正确的方法）
    const criticalEndpoints = [
      { path: '/api/v1/agent/saved', method: 'GET' },
      { path: '/api/v1/agent/orchestrate/stream', method: 'POST' }, // POST方法
      { path: '/api/v2/Controller/admin/stats', method: 'GET' },
    ];
    
    for (const endpoint of criticalEndpoints) {
      try {
        let response;
        if (endpoint.method === 'GET') {
          response = await request.get(`${BACKEND_BASE}${endpoint.path}`, {
            headers: { 'Accept': 'application/json' },
            timeout: 5000
          });
        } else if (endpoint.method === 'POST') {
          response = await request.post(`${BACKEND_BASE}${endpoint.path}`, {
            headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
            data: {},
            timeout: 5000
          });
        }
        
        endpointStatus.push({
          endpoint: endpoint.path,
          method: endpoint.method,
          status: response.status(),
          available: response.ok() || response.status() === 401 || response.status() === 422 // 401需要认证，422缺少参数
        });
      } catch (error) {
        endpointStatus.push({
          endpoint: endpoint.path,
          method: endpoint.method,
          error: error.message,
          available: false
        });
      }
    }
    
    console.log('\n关键端点状态:');
    endpointStatus.forEach(e => {
      const statusText = e.available ? '✓' : '✗';
      console.log(`  ${statusText} ${e.method} ${e.endpoint} - ${e.status || e.error}`);
    });
    
    // 所有关键端点都应该存在（返回非404）
    const notFound = endpointStatus.filter(e => e.status === 404);
    expect(notFound.length).toBe(0);
  });
});
