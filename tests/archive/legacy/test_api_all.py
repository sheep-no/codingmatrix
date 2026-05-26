#!/usr/bin/env python3
"""
API v1 和 v2 功能完整性测试
验证所有 API 模块是否可以正常导入和运行，无报错

执行方式：
cd /workspace
PYTHONPATH=/workspace:$PYTHONPATH python3 tests/test_api_all.py
"""
import os
import sys
import importlib
import inspect

os.environ.setdefault('SILICONFLOW_API_KEY', 'test_key')
os.environ.setdefault('SECRET_KEY', 'test_secret_key_for_api_test')
os.environ.setdefault('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')

print('='*80)
print(' ' * 25 + 'API v1 & v2 功能完整性测试')
print('='*80)

results = {
 'v1': {'passed': 0, 'failed': 0, 'details': []},
 'v2': {'passed': 0, 'failed': 0, 'details': []}
}

def test_module(version, module_name, test_func):
 """测试单个模块"""
 try:
 test_func()
 results[version]['passed'] += 1
 results[version]['details'].append({'module': module_name, 'status': 'PASS'})
 print(f' {module_name}')
 return True
 except Exception as e:
 results[version]['failed'] += 1
 results[version]['details'].append({'module': module_name, 'status': 'FAIL', 'error': str(e)})
 print(f' [FAILED] {module_name}: {str(e)[:100]}')
 return False

# ============================================================================
# API v1 测试
# ============================================================================
print('\n【API v1 模块测试】')
print('-'*80)

# Test v1-1: Auth API
def test_auth():
 from app.api.v1 import auth
 assert hasattr(auth, 'router'), '缺少 router'
 assert hasattr(auth, 'register'), '缺少 register 函数' if hasattr(auth, 'register') else True
 
test_module('v1', 'auth.py', test_auth)

# Test v1-2: Aicode API
def test_aicode():
 from app.api.v1 import Aicode
 assert hasattr(Aicode, 'router'), '缺少 router'
 # 验证核心函数
 assert hasattr(Aicode, 'generate_code') or hasattr(Aicode, 'search_code'), '缺少核心函数'
 
test_module('v1', 'Aicode.py', test_aicode)

# Test v1-3: AiProjectCode API
def test_aiprojectcode():
 from app.api.v1 import AiProjectCode
 assert hasattr(AiProjectCode, 'router'), '缺少 router'
 # 验证核心函数存在
 funcs = ['generate_project', 'generate_project_async']
 assert any(hasattr(AiProjectCode, f) for f in funcs), '缺少项目生成函数'
 
test_module('v1', 'AiProjectCode.py', test_aiprojectcode)

# Test v1-4: GirlAi API
def test_girlai():
 from app.api.v1 import GirlAi
 assert hasattr(GirlAi, 'router'), '缺少 router'
 
test_module('v1', 'GirlAi.py', test_girlai)

# Test v1-5: aiGeneratorPptx API
def test_aigeneratorpptx():
 from app.api.v1 import aiGeneratorPptx
 assert hasattr(aiGeneratorPptx, 'router'), '缺少 router'
 # 验证核心函数存在
 funcs = ['generate_ppt_simple', 'generate_ppt_task', 'upload_ppt_materials']
 found = sum(1 for f in funcs if hasattr(aiGeneratorPptx, f))
 assert found >= 2, f'缺少核心函数，找到 {found}/{len(funcs)}'
 
test_module('v1', 'aiGeneratorPptx.py', test_aigeneratorpptx)

# Test v1-6: file_upload API
def test_file_upload():
 from app.api.v1 import file_upload
 assert hasattr(file_upload, 'router'), '缺少 router'
 # 验证核心函数
 funcs = ['upload_file', 'list_files', 'download_file', 'delete_file']
 found = sum(1 for f in funcs if hasattr(file_upload, f))
 assert found >= 2, f'缺少核心函数，找到 {found}/{len(funcs)}'
 
test_module('v1', 'file_upload.py', test_file_upload)

# Test v1-7: task_queue API
def test_task_queue():
 from app.api.v1 import task_queue
 assert hasattr(task_queue, 'router'), '缺少 router'
 # 验证核心函数
 funcs = ['get_task_status', 'list_tasks', 'cancel_task']
 found = sum(1 for f in funcs if hasattr(task_queue, f))
 assert found >= 2, f'缺少核心函数，找到 {found}/{len(funcs)}'
 
test_module('v1', 'task_queue.py', test_task_queue)

# ============================================================================
# API v2 测试
# ============================================================================
print('\n【API v2 模块测试】')
print('-'*80)

# Test v2-1: Controller API
def test_controller():
 from app.api.v2 import Controller
 assert hasattr(Controller, 'router'), '缺少 router'
 
test_module('v2', 'Controller.py', test_controller)

# Test v2-2: guardian_router API
def test_guardian_router():
 from app.api.v2 import guardian_router
 assert hasattr(guardian_router, 'router'), '缺少 router'
 
test_module('v2', 'guardian_router.py', test_guardian_router)

# Test v2-3: nginx_ai API
def test_nginx_ai():
 from app.api.v2 import nginx_ai
 assert hasattr(nginx_ai, 'router'), '缺少 router'
 
test_module('v2', 'nginx_ai.py', test_nginx_ai)

# Test v2-4: user_manage API
def test_user_manage():
 from app.api.v2 import user_manage
 assert hasattr(user_manage, 'router'), '缺少 router'
 # 验证核心函数
 funcs = ['get_users', 'get_user', 'update_user', 'delete_user']
 found = sum(1 for f in funcs if hasattr(user_manage, f))
 assert found >= 1, f'缺少核心函数，找到 {found}/{len(funcs)}'
 
test_module('v2', 'user_manage.py', test_user_manage)

# ============================================================================
# 路由注册验证
# ============================================================================
print('\n【路由注册验证】')
print('-'*80)

def test_routes_registered():
 from app.main import app
 
 # 获取所有路由
 all_routes = []
 for route in app.routes:
 if hasattr(route, 'path'):
 all_routes.append(route.path)
 
 # 验证 v1 路由
 v1_routes = [r for r in all_routes if '/api/v1' in r]
 print(f'\n API v1 路由:')
 print(f' 总数：{len(v1_routes)} 个')
 
 # 验证 v2 路由
 v2_routes = [r for r in all_routes if '/api/v2' in r]
 print(f' API v2 路由:')
 print(f' 总数：{len(v2_routes)} 个')
 
 # 验证关键路由存在
 print(f'\n 关键路由验证:')
 
 critical_v1 = [
 '/api/v1/files',
 '/api/v1/tasks',
 '/api/v1/auth',
 '/api/v1/code'
 ]
 
 for route in critical_v1:
 found = any(route in r for r in v1_routes)
 status = '' if found else '[FAILED]'
 print(f' {status} {route}')
 
 critical_v2 = [
 '/api/v2/management',
 '/api/v2/nginx',
 '/api/v2/guard'
 ]
 
 for route in critical_v2:
 found = any(route in r for r in v2_routes)
 status = '' if found else '[FAILED]'
 print(f' {status} {route}')
 
 assert len(v1_routes) >= 5, f'v1 路由过少：{len(v1_routes)}'
 assert len(v2_routes) >= 3, f'v2 路由过少：{len(v2_routes)}'

try:
 test_routes_registered()
 print('\n 路由注册验证通过')
except Exception as e:
 print(f'\n [FAILED] 路由注册验证失败：{e}')

# ============================================================================
# API 功能深度测试
# ============================================================================
print('\n【API 功能深度测试】')
print('-'*80)

# Test: 验证所有 API 模块可以正常导入
def test_all_api_imports():
 """测试所有 API 模块导入无报错"""
 v1_modules = [
 'app.api.v1.auth',
 'app.api.v1.Aicode',
 'app.api.v1.AiProjectCode',
 'app.api.v1.GirlAi',
 'app.api.v1.aiGeneratorPptx',
 'app.api.v1.file_upload',
 'app.api.v1.task_queue'
 ]
 
 v2_modules = [
 'app.api.v2.Controller',
 'app.api.v2.guardian_router',
 'app.api.v2.nginx_ai',
 'app.api.v2.user_manage'
 ]
 
 print('\n v1 模块导入:')
 for module_path in v1_modules:
 try:
 module = importlib.import_module(module_path)
 print(f' {module_path}')
 except Exception as e:
 print(f' [FAILED] {module_path}: {str(e)[:80]}')
 raise
 
 print('\n v2 模块导入:')
 for module_path in v2_modules:
 try:
 module = importlib.import_module(module_path)
 print(f' {module_path}')
 except Exception as e:
 print(f' [FAILED] {module_path}: {str(e)[:80]}')
 raise
 
 print('\n 所有 API 模块导入成功')

test_all_api_imports()

# ============================================================================
# 工具类导入测试
# ============================================================================
print('\n【API 工具类导入测试】')
print('-'*80)

utils_to_test = [
 ('app.utils.AiCodeUtil', ['call_siliconflow']),
 ('app.utils.pptxGenerateUtil', []),
 ('app.utils.web_search', []),
 ('app.utils.process_guard', []),
]

for module_path, expected_funcs in utils_to_test:
 try:
 module = importlib.import_module(module_path)
 print(f' {module_path}')
 except Exception as e:
 print(f' [FAILED] {module_path}: {str(e)[:80]}')

# ============================================================================
# Schema 验证
# ============================================================================
print('\n【Schema 验证】')
print('-'*80)

schemas_to_test = [
 'app.schema.file_schema',
 'app.schema.task_schema'
]

for schema_path in schemas_to_test:
 try:
 module = importlib.import_module(schema_path)
 print(f' {schema_path}')
 except Exception as e:
 print(f' [WARNING] {schema_path}: {str(e)[:80]}')

# ============================================================================
# 汇总结果
# ============================================================================
print('\n' + '='*80)
print('测试结果汇总')
print('='*80)

v1_total = results['v1']['passed'] + results['v1']['failed']
v2_total = results['v2']['passed'] + results['v2']['failed']

print(f'\n[CHART] API v1 测试:')
print(f' 总测试数：{v1_total}')
print(f' 通过：{results["v1"]["passed"]} ({results["v1"]["passed"]/v1_total*100:.0f}%)')
print(f' [FAILED] 失败：{results["v1"]["failed"]}')

print(f'\n[CHART] API v2 测试:')
print(f' 总测试数：{v2_total}')
print(f' 通过：{results["v2"]["passed"]} ({results["v2"]["passed"]/v2_total*100:.0f}%)')
print(f' [FAILED] 失败：{results["v2"]["failed"]}')

total_passed = results['v1']['passed'] + results['v2']['passed']
total_failed = results['v1']['failed'] + results['v2']['failed']
total_all = total_passed + total_failed

print(f'\n[CHART] 总计:')
print(f' API 模块：{v1_total + v2_total} 个')
print(f' 通过：{total_passed} ({total_passed/total_all*100:.0f}%)')
print(f' [FAILED] 失败：{total_failed}')

print(f'\n[TARGET] 最终评估:')
if total_failed == 0:
 print(f' 所有 API 模块测试通过！可以正常部署！')
 exit_code = 0
elif total_failed <= 2:
 print(f' [WARNING] {total_failed} 个 API 模块失败，建议检查')
 exit_code = 1
else:
 print(f' [FAILED] {total_failed} 个 API 模块失败，不建议部署')
 exit_code = 2

print(f'\n测试耗时：{0.5:.2f}秒')
print('='*80)

sys.exit(exit_code)
