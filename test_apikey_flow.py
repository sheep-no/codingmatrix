#!/usr/bin/env python3
"""
测试用户 API Key 上传接入模型 + 指定不添加降级模型的完整流程
"""
import requests
import json
import base64
import sys
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

BASE_URL = "http://localhost:8000"
API_PREFIX = f"{BASE_URL}/api/v1"

TEST_API_KEY = "sk-hvrcuxxqjhkdsaysyqeulrvsjieknsdqablvxhuhesiuinny"
TEST_PROVIDER = "siliconflow"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

def log(msg, color=CYAN):
    print(f"{color}{msg}{RESET}")
def ok(msg):
    print(f"  {GREEN}✓ {msg}{RESET}")
def fail(msg):
    print(f"  {RED}✗ {msg}{RESET}")
def warn(msg):
    print(f"  {YELLOW}⚠ {msg}{RESET}")
def step(msg):
    print(f"\n{'='*60}")
    log(f"  {msg}")
    print(f"{'='*60}")


class ApiKeyTester:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.jwt = None
        self._login()

    def _login(self):
        resp = self.session.get(f"{API_PREFIX}/csrf-token")
        csrf = resp.json()["csrf_token"]
        resp = self.session.post(
            f"{API_PREFIX}/login",
            json={"email": "admin@example.com", "password": "admin123"},
            headers={"X-CSRF-Token": csrf}
        )
        self.jwt = resp.json()["access_token"]
        ok(f"登录成功")

    def _headers(self):
        return {"Authorization": f"Bearer {self.jwt}", "Content-Type": "application/json"}

    def _encrypt_key(self, api_key: str) -> str:
        resp = self.session.get(f"{API_PREFIX}/agent/apikey/public-key")
        pub_pem = resp.json()["public_key"].encode()
        public_key = serialization.load_pem_public_key(pub_pem)
        encrypted = public_key.encrypt(
            api_key.encode(),
            padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        return base64.b64encode(encrypted).decode()

    def test_upload_key(self):
        step("测试 1: 上传 API Key（RSA 加密 → Redis 存储）")
        encrypted = self._encrypt_key(TEST_API_KEY)
        ok(f"RSA 加密完成，密文长度: {len(encrypted)} 字符")
        
        resp = self.session.post(
            f"{API_PREFIX}/agent/apikey",
            json={"encrypted_key": encrypted, "provider": TEST_PROVIDER, "ttl": 604800, "remark": "测试 SiliconFlow Key"},
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("token")
            ok(f"Key 上传成功！Token: {self.token}")
            return True
        else:
            fail(f"上传失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_list_keys(self):
        step("测试 2: 查看用户 API Key 列表")
        resp = self.session.get(f"{API_PREFIX}/agent/apikeys", headers=self._headers())
        if resp.status_code == 200:
            keys = resp.json()  # 直接返回 list
            ok(f"共 {len(keys)} 个 Key")
            for k in keys:
                log(f"    Token: {k.get('token', 'N/A')[:12]}... | "
                    f"Provider: {k.get('provider')} | "
                    f"Status: {k.get('status')} | "
                    f"Enabled: {k.get('enabled')}")
            return True
        else:
            fail(f"查询失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_key_connection(self):
        step("测试 3: 测试 API Key 连接是否有效")
        resp = self.session.post(
            f"{API_PREFIX}/agent/apikey/test",
            json={"token": self.token},
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"Key 连接测试: success={data.get('success')} | message={data.get('message')}")
            return True
        else:
            fail(f"测试失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_call_model(self):
        step("测试 4: 使用用户 Key 调用模型（通过虚拟姬端点）")
        resp = self.session.post(
            f"{API_PREFIX}/GirlAi",
            json={"prompt": "你好，请用一句话介绍自己", "character_id": "gentle"},
            headers=self._headers(),
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"模型调用成功！模型: {data.get('model', 'N/A')}")
            log(f"    响应: {str(data.get('message', ''))[:150]}")
            log(f"    Tokens: {data.get('tokens_used', 'N/A')}")
            return True
        else:
            fail(f"调用失败 [{resp.status_code}]: {resp.text[:200]}")
            return False

    def test_get_fallback_preference(self):
        step("测试 5: 查看当前降级配置")
        resp = self.session.get(
            f"{API_PREFIX}/agent/apikey/{self.token}/fallback-preference",
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"当前降级配置: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"查询失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_disable_fallback(self):
        step("测试 6: 设置降级策略为 disabled（不添加降级模型）")
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/fallback-preference",
            json={"fallback_preference": "disabled"},
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"降级策略已设为 disabled")
            log(f"    响应: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"设置失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_call_with_fallback_disabled(self):
        step("测试 7: 禁用降级后调用模型（验证无降级回退）")
        # 验证配置
        resp = self.session.get(
            f"{API_PREFIX}/agent/apikey/{self.token}/fallback-preference",
            headers=self._headers()
        )
        if resp.status_code == 200:
            pref = resp.json().get("fallback_preference")
            ok(f"降级策略确认为: {pref}")
        
        # 调用模型
        resp = self.session.post(
            f"{API_PREFIX}/GirlAi",
            json={"prompt": "请用一句话回答：1+1等于几？", "character_id": "lively"},
            headers=self._headers(),
            timeout=60
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"禁用降级后调用成功！")
            log(f"    响应: {str(data.get('message', ''))[:150]}")
            log(f"    模型: {data.get('model', 'N/A')}")
            return True
        else:
            fail(f"调用失败 [{resp.status_code}]: {resp.text[:200]}")
            return False

    def test_custom_fallback(self):
        step("测试 8: 设置自定义降级链")
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/fallback-preference",
            json={
                "fallback_preference": "custom",
                "custom_fallback_chain": ["Qwen/Qwen3-8B", "THUDM/GLM-Z1-9B-0414"]
            },
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"自定义降级链设置成功")
            log(f"    降级链: {data.get('custom_fallback_chain')}")
            return True
        else:
            fail(f"设置失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_restore_default_fallback(self):
        step("测试 9: 恢复默认降级策略（use_admin_default）")
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/fallback-preference",
            json={"fallback_preference": "use_admin_default"},
            headers=self._headers()
        )
        if resp.status_code == 200:
            ok(f"已恢复默认降级策略")
            return True
        else:
            fail(f"恢复失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_toggle_key(self):
        step("测试 10: 启用/禁用 API Key 切换")
        # 禁用（query param）
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/enabled?enabled=false",
            headers=self._headers()
        )
        if resp.status_code == 200:
            ok("Key 已禁用")
        else:
            fail(f"禁用失败 [{resp.status_code}]: {resp.text}")
            return False
        
        # 启用
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/enabled?enabled=true",
            headers=self._headers()
        )
        if resp.status_code == 200:
            ok("Key 已重新启用")
            return True
        else:
            fail(f"启用失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_update_context_lengths(self):
        step("测试 11: 更新模型上下文长度配置")
        resp = self.session.put(
            f"{API_PREFIX}/agent/apikey/{self.token}/context-lengths",
            json={"context_lengths": {"Qwen/Qwen3-8B": 32768, "THUDM/GLM-Z1-9B-0414": 16384}},
            headers=self._headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            ok(f"上下文长度配置更新成功: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"更新失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_batch_export(self):
        step("测试 12: 批量导出 Key 元数据")
        resp = self.session.get(f"{API_PREFIX}/agent/apikey/batch/export", headers=self._headers())
        if resp.status_code == 200:
            data = resp.json()
            ok(f"导出成功: format={data.get('format')} | count={data.get('count')}")
            return True
        else:
            fail(f"导出失败 [{resp.status_code}]: {resp.text}")
            return False

    def test_delete_key(self):
        step("测试 13: 删除 API Key（清理测试数据）")
        if not self.token:
            warn("没有可删除的 Token，跳过")
            return True
        resp = self.session.delete(
            f"{API_PREFIX}/agent/apikey/{self.token}",
            headers=self._headers()
        )
        if resp.status_code == 200:
            ok(f"Key 已删除: {self.token}")
            self.token = None
            return True
        else:
            fail(f"删除失败 [{resp.status_code}]: {resp.text}")
            return False

    def run_all(self):
        log("\n╔══════════════════════════════════════════════════╗")
        log("║  用户 API Key 上传接入模型 + 禁用降级 全流程测试  ║")
        log("╚══════════════════════════════════════════════════╝\n")
        
        results = {}
        tests = [
            ("上传 API Key", self.test_upload_key),
            ("查看 Key 列表", self.test_list_keys),
            ("测试 Key 连接", self.test_key_connection),
            ("调用模型", self.test_call_model),
            ("查看降级配置", self.test_get_fallback_preference),
            ("禁用降级模型", self.test_disable_fallback),
            ("禁用降级后调用", self.test_call_with_fallback_disabled),
            ("自定义降级链", self.test_custom_fallback),
            ("恢复默认降级", self.test_restore_default_fallback),
            ("启用/禁用 Key", self.test_toggle_key),
            ("更新上下文长度", self.test_update_context_lengths),
            ("批量导出", self.test_batch_export),
            ("删除 Key", self.test_delete_key),
        ]
        
        for name, test_fn in tests:
            try:
                results[name] = test_fn()
            except Exception as e:
                fail(f"异常: {e}")
                import traceback; traceback.print_exc()
                results[name] = False
        
        step("测试结果汇总")
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        for name, result in results.items():
            status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
            print(f"  [{status}] {name}")
        print(f"\n  通过: {passed}/{total}")
        if passed == total:
            log(f"\n  {GREEN}所有测试通过！{RESET}")
        else:
            log(f"\n  {RED}{total - passed} 个测试失败{RESET}")
        return passed == total


if __name__ == "__main__":
    tester = ApiKeyTester()
    success = tester.run_all()
    sys.exit(0 if success else 1)
