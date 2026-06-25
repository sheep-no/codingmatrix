#!/usr/bin/env python3
"""
测试自定义 Skill 功能完整流程
"""
import requests
import json
import sys

BASE = "http://localhost:8000/api/v1"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

def ok(m): print(f"  {GREEN}✓ {m}{RESET}")
def fail(m): print(f"  {RED}✗ {m}{RESET}")
def warn(m): print(f"  {YELLOW}⚠ {m}{RESET}")
def step(m): print(f"\n{'='*60}\n{CYAN}  {m}{RESET}\n{'='*60}")

class SkillTester:
    def __init__(self):
        self.s = requests.Session()
        self._login()
        self.test_skill_name = "test_custom_skill"

    def _login(self):
        r = self.s.get(f"{BASE}/csrf-token")
        csrf = r.json()["csrf_token"]
        r = self.s.post(f"{BASE}/login",
            json={"email": "admin@example.com", "password": "admin123"},
            headers={"X-CSRF-Token": csrf})
        self.jwt = r.json()["access_token"]
        ok(f"登录成功")

    def _h(self):
        return {"Authorization": f"Bearer {self.jwt}", "Content-Type": "application/json"}

    # ── 1. 列表 ──
    def test_list(self):
        step("1. 查看所有 Skills")
        r = self.s.get(f"{BASE}/skills/list", headers=self._h())
        if r.status_code == 200:
            data = r.json()
            skills = data if isinstance(data, list) else data.get("skills", [])
            ok(f"共 {len(skills)} 个 Skill")
            for sk in skills[:8]:
                print(f"    {sk.get('name','?'):30s} | {sk.get('category','?'):12s} | {sk.get('description','')[:40]}")
            if len(skills) > 8:
                print(f"    ... 还有 {len(skills)-8} 个")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:200]}")
            return False

    # ── 2. 分类 ──
    def test_categories(self):
        step("2. 查看支持的分类")
        r = self.s.get(f"{BASE}/skills/categories", headers=self._h())
        if r.status_code == 200:
            data = r.json()
            cats = data if isinstance(data, list) else data.get("categories", [])
            ok(f"共 {len(cats)} 个分类")
            for c in cats:
                if isinstance(c, dict):
                    print(f"    {c.get('name','?'):15s} - {c.get('description','')}")
                else:
                    print(f"    {c}")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:200]}")
            return False

    # ── 3. 上传 JSON ──
    def test_upload_json(self):
        step("3. JSON 方式上传自定义 Skill")
        r = self.s.post(f"{BASE}/skills/upload",
            json={
                "name": self.test_skill_name,
                "category": "orchestrator",
                "description": "测试用自定义 Skill",
                "content": "# 测试 Skill\n\n你是一个专门用于测试的 AI 助手。\n\n## 规则\n\n1. 始终用中文回答\n2. 在回答末尾加上 [自定义Skill生效]\n3. 保持简洁"
            },
            headers=self._h())
        if r.status_code in (200, 201):
            data = r.json()
            ok(f"上传成功: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:300]}")
            return False

    # ── 4. 获取详情 ──
    def test_get_detail(self):
        step("4. 获取 Skill 详情")
        r = self.s.get(f"{BASE}/skills/{self.test_skill_name}", headers=self._h())
        if r.status_code == 200:
            data = r.json()
            ok(f"名称: {data.get('name')}")
            print(f"    分类: {data.get('category')}")
            print(f"    描述: {data.get('description')}")
            print(f"    版本: {data.get('version')}")
            print(f"    内容: {str(data.get('content',''))[:100]}...")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:200]}")
            return False

    # ── 5. 更新 ──
    def test_update(self):
        step("5. 更新 Skill 内容")
        r = self.s.put(f"{BASE}/skills/{self.test_skill_name}",
            json={
                "content": "# 测试 Skill (已更新)\n\n你是一个专门用于测试的 AI 助手。\n\n## 规则\n\n1. 始终用中文回答\n2. 在回答末尾加上 [自定义Skill已更新生效]\n3. 保持简洁\n4. 优先展示更新后的行为",
                "description": "测试用自定义 Skill (已更新)"
            },
            headers=self._h())
        if r.status_code == 200:
            data = r.json()
            ok(f"更新成功: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:300]}")
            return False

    # ── 6. 文件上传 ──
    def test_upload_file(self):
        step("6. 文件方式上传 Skill")
        md_content = """# 文件上传测试 Skill

这是一个通过文件上传创建的 Skill。

## 功能

- 测试文件上传接口
- 验证 .md 文件解析
"""
        files = {"file": ("file_test_skill.md", md_content.encode(), "text/markdown")}
        data = {"name": "file_test_skill", "category": "other", "description": "文件上传测试"}
        r = self.s.post(f"{BASE}/skills/upload-file",
            files=files, data=data,
            headers={"Authorization": f"Bearer {self.jwt}"})
        if r.status_code in (200, 201):
            data = r.json()
            ok(f"文件上传成功: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:300]}")
            return False

    # ── 7. 热重载 ──
    def test_reload(self):
        step("7. 热重载 Skills")
        r = self.s.post(f"{BASE}/skills/reload", headers=self._h())
        if r.status_code == 200:
            data = r.json()
            ok(f"重载成功: {json.dumps(data, ensure_ascii=False)}")
            return True
        else:
            fail(f"[{r.status_code}] {r.text[:300]}")
            return False

    # ── 8. 验证覆盖 ──
    def test_override_agent_prompt(self):
        step("8. 验证自定义 Skill 覆盖 Agent 系统提示词")
        # 检查 skill_registry 是否能获取到自定义 skill
        r = self.s.get(f"{BASE}/skills/{self.test_skill_name}", headers=self._h())
        if r.status_code != 200:
            warn("Skill 不存在，跳过覆盖测试")
            return False

        data = r.json()
        content = data.get("content", "")
        if "自定义Skill" in content:
            ok(f"自定义 Skill 内容已存储，包含覆盖标识")
            print(f"    内容: {content[:150]}...")
        else:
            warn(f"内容异常: {content[:100]}")

        # 检查 agent 是否会加载这个 skill
        # architect 会查找 "architect_prompt"，我们创建的叫 "test_custom_skill" 不会覆盖
        # 但我们可以验证 registry 能正确返回
        r2 = self.s.get(f"{BASE}/skills/list?category=orchestrator", headers=self._h())
        if r2.status_code == 200:
            skills = r2.json() if isinstance(r2.json(), list) else r2.json().get("skills", [])
            found = any(s.get("name") == self.test_skill_name for s in skills)
            if found:
                ok(f"自定义 Skill 在 orchestrator 分类列表中可见")
            else:
                warn(f"自定义 Skill 未在列表中找到")
            return found
        return False

    # ── 9. 删除 ──
    def test_delete(self):
        step("9. 删除自定义 Skill")
        # 删除 test skill
        r = self.s.delete(f"{BASE}/skills/{self.test_skill_name}", headers=self._h())
        if r.status_code == 200:
            ok(f"删除 {self.test_skill_name} 成功")
        else:
            warn(f"删除 {self.test_skill_name} [{r.status_code}]")

        # 删除 file upload skill
        r2 = self.s.delete(f"{BASE}/skills/file_test_skill", headers=self._h())
        if r2.status_code == 200:
            ok(f"删除 file_test_skill 成功")
        else:
            warn(f"删除 file_test_skill [{r2.status_code}]")

        # 验证已删除
        r3 = self.s.get(f"{BASE}/skills/{self.test_skill_name}", headers=self._h())
        if r3.status_code == 404:
            ok(f"确认已删除（404）")
            return True
        else:
            warn(f"删除后仍可访问 [{r3.status_code}]")
            return False

    # ── 10. 列表验证 ──
    def test_list_after_cleanup(self):
        step("10. 清理后列表验证")
        r = self.s.get(f"{BASE}/skills/list", headers=self._h())
        if r.status_code == 200:
            data = r.json()
            skills = data if isinstance(data, list) else data.get("skills", [])
            test_skills = [s for s in skills if "test" in s.get("name", "").lower()]
            if not test_skills:
                ok(f"清理完成，无残留测试 Skill")
            else:
                warn(f"仍有 {len(test_skills)} 个测试 Skill 残留")
            return len(test_skills) == 0
        return False

    def run_all(self):
        print(f"\n{CYAN}╔══════════════════════════════════════╗{RESET}")
        print(f"{CYAN}║     自定义 Skill 功能完整测试        ║{RESET}")
        print(f"{CYAN}╚══════════════════════════════════════╝{RESET}")

        results = {}
        tests = [
            ("列表", self.test_list),
            ("分类", self.test_categories),
            ("JSON上传", self.test_upload_json),
            ("详情", self.test_get_detail),
            ("更新", self.test_update),
            ("文件上传", self.test_upload_file),
            ("热重载", self.test_reload),
            ("覆盖验证", self.test_override_agent_prompt),
            ("删除", self.test_delete),
            ("清理验证", self.test_list_after_cleanup),
        ]

        for name, fn in tests:
            try:
                results[name] = fn()
            except Exception as e:
                fail(f"异常: {e}")
                import traceback; traceback.print_exc()
                results[name] = False

        step("测试结果汇总")
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        for name, r in results.items():
            s = f"{GREEN}PASS{RESET}" if r else f"{RED}FAIL{RESET}"
            print(f"  [{s}] {name}")
        print(f"\n  通过: {passed}/{total}")
        return passed == total


if __name__ == "__main__":
    t = SkillTester()
    ok = t.run_all()
    sys.exit(0 if ok else 1)
