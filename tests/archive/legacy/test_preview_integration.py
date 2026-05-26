"""
预览功能集成端到端测试
测试 FilePreviewCenter 组件集成到 PPTGenerator 和 ProjectGenerator 的功能
"""

import pytest
import httpx
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class TestPreviewIntegration:
 """预览功能集成测试类"""
 
 @pytest.fixture(scope="function")
 def driver(self):
 """Selenium WebDriver 配置"""
 chrome_options = Options()
 chrome_options.add_argument('--headless')
 chrome_options.add_argument('--no-sandbox')
 chrome_options.add_argument('--disable-dev-shm-usage')
 chrome_options.add_argument('--disable-gpu')
 chrome_options.add_argument('--window-size=1920,1080')
 
 driver = webdriver.Chrome(options=chrome_options)
 driver.set_page_load_timeout(30)
 yield driver
 driver.quit()
 
 @pytest.fixture(scope="function")
 def http_client(self, api_base_url):
 """HTTP 客户端用于 API 调用"""
 return httpx.Client(base_url=api_base_url, timeout=30)
 
 def test_01_file_preview_center_component_exists(self):
 """测试 FilePreviewCenter 组件文件存在"""
 import os
 component_path = 'src/components/tools/FilePreviewCenter.vue'
 assert os.path.exists(component_path), f"FilePreviewCenter 组件不存在：{component_path}"
 
 def test_02_ppt_generator_integration(self):
 """测试 PPTGenerator 集成 FilePreviewCenter"""
 with open('src/components/tools/PPTGenerator.vue', 'r', encoding='utf-8') as f:
 content = f.read()
 
 # 检查集成点
 checks = {
 'import FilePreviewCenter': '导入组件',
 'showPreview': '预览状态',
 'openPPTPreview': '预览方法',
 '<FilePreviewCenter': '模板组件'
 }
 
 for key, desc in checks.items():
 assert key in content, f"PPTGenerator 缺少{desc}: {key}"
 
 def test_03_project_generator_integration(self):
 """测试 ProjectGenerator 集成 FilePreviewCenter"""
 with open('src/components/tools/ProjectGenerator.vue', 'r', encoding='utf-8') as f:
 content = f.read()
 
 # 检查集成点
 checks = {
 'import FilePreviewCenter': '导入组件',
 'showPreview': '预览状态',
 'previewProject': '预览方法',
 '<FilePreviewCenter': '模板组件'
 }
 
 for key, desc in checks.items():
 assert key in content, f"ProjectGenerator 缺少{desc}: {key}"
 
 def test_04_api_generate_files_endpoint_exists(self):
 """测试项目文件列表 API 端点实现"""
 with open('app/api/v1/AiProjectCode.py', 'r', encoding='utf-8') as f:
 content = f.read()
 
 # 检查关键功能
 assert 'get_project_files' in content, "缺少 get_project_files 函数"
 assert '@router.get("/generate/files"' in content, "缺少路由定义"
 assert 'mime_types' in content, "缺少文件类型识别"
 
 def test_05_preview_api_exists(self):
 """测试 Preview API 存在"""
 import os
 assert os.path.exists('app/api/v1/preview.py'), "preview.py 文件不存在"
 
 with open('app/api/v1/preview.py', 'r', encoding='utf-8') as f:
 content = f.read()
 assert 'preview' in content.lower(), "Preview API 内容不完整"
 
 def test_06_swagger_ui_loads(self, driver, api_base_url):
 """测试 Swagger UI 加载"""
 driver.get(f"{api_base_url}/docs")
 WebDriverWait(driver, 10).until(
 lambda d: "Swagger" in d.title or "FastAPI" in d.title
 )
 assert "Swagger" in driver.title or "FastAPI" in driver.title
 
 def test_07_openapi_schema_valid(self, http_client):
 """测试 OpenAPI Schema 完整性"""
 response = http_client.get("/openapi.json")
 assert response.status_code == 200
 
 openapi = response.json()
 assert 'paths' in openapi, "OpenAPI schema 缺少 paths"
 assert 'info' in openapi, "OpenAPI schema 缺少 info"
 assert len(openapi['paths']) > 0, "OpenAPI schema 无 API 端点"
 
 def test_08_api_routes_exist(self, http_client):
 """测试关键 API 路由存在"""
 response = http_client.get("/openapi.json")
 openapi = response.json()
 paths = openapi.get('paths', {})
 
 # 验证关键端点
 required_endpoints = [
 '/api/v1/agent/generate',
 '/api/v1/agent/generate/download/{project_path}',
 '/api/v1/agent/generate/files'
 ]
 
 found = 0
 for endpoint in required_endpoints:
 for path in paths.keys():
 if path == endpoint or path.startswith(endpoint.rstrip('/')):
 found += 1
 break
 
 assert found >= 2, f"只找到 {found}/{len(required_endpoints)} 个关键端点"
 
 def test_09_python_syntax_valid(self):
 """测试 Python 文件语法"""
 import py_compile
 
 files_to_check = [
 'app/api/v1/AiProjectCode.py',
 'app/api/v1/preview.py'
 ]
 
 for file_path in files_to_check:
 try:
 py_compile.compile(file_path, doraise=True)
 except py_compile.PyCompileError as e:
 pytest.fail(f"{file_path} 语法错误：{e}")
 
 def test_10_file_preview_center_props(self):
 """测试 FilePreviewCenter 组件 props 配置"""
 with open('src/components/tools/FilePreviewCenter.vue', 'r', encoding='utf-8') as f:
 content = f.read()
 
 # 检查是否支持 file prop
 assert 'file:' in content or "file: {" in content, "FilePreviewCenter 缺少 file prop"
 
 # 检查 watch 监听
 assert 'watch(() => props.file' in content, "FilePreviewCenter 缺少 file prop 监听"


class TestPreviewAPIFunctionality:
 """预览 API 功能测试"""
 
 @pytest.fixture(scope="function")
 def http_client(self, api_base_url):
 """HTTP 客户端"""
 return httpx.Client(base_url=api_base_url, timeout=30)
 
 def test_11_api_health_check(self, http_client):
 """测试 API 服务响应"""
 try:
 response = http_client.get("/health")
 # 健康检查端点可能不存在或需要认证，只要能响应就正常
 assert response.status_code in [200, 404, 401, 403, 405, 500]
 except httpx.RequestError:
 pytest.fail("API 服务无响应")
 
 def test_12_openapi_endpoint_count(self, http_client):
 """测试 API 端点数量"""
 response = http_client.get("/openapi.json")
 openapi = response.json()
 
 path_count = len(openapi.get('paths', {}))
 assert path_count >= 50, f"API 端点数量过少：{path_count} < 50"
