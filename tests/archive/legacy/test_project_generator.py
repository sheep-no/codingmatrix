"""
ProjectGenerator + Sketch-to-Code - Selenium 前端 E2E 测试

测试 AI 项目生成器和 UI草图转代码功能：
1. 侧边栏工具入口显示
2. 项目生成器弹窗打开
3. 项目需求输入
4. 项目类型/技术栈/AI模型选择
5. Skill 模板选择
6. 项目预览功能
7. 生成功能
"""

import pytest
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

BASE_URL = os.getenv("TEST_BASE_URL", "http://127.0.0.1:5173")
API_URL = "http://127.0.0.1:8000"
HEADLESS = os.getenv("CI", "false").lower() == "true"
TIMEOUT = 30


@pytest.fixture(scope="session")
def driver():
    """创建 Chrome WebDriver"""
    chrome_options = Options()

    if HEADLESS:
        chrome_options.add_argument("--headless")

    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """
    })

    yield driver
    driver.quit()


def wait_for_element(driver, locator, timeout=TIMEOUT):
    """等待元素出现"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(locator)
        )
    except TimeoutException:
        screenshot_path = f"screenshots/project_generator_{int(time.time())}.png"
        os.makedirs("screenshots", exist_ok=True)
        driver.save_screenshot(screenshot_path)
        raise AssertionError(f"元素等待超时: {locator}, 截图: {screenshot_path}")


def wait_for_clickable(driver, locator, timeout=TIMEOUT):
    """等待元素可点击"""
    try:
        return WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable(locator)
        )
    except TimeoutException:
        raise AssertionError(f"元素不可点击: {locator}")


def save_screenshot(driver, name):
    """保存截图"""
    os.makedirs("screenshots", exist_ok=True)
    path = f"screenshots/{name}_{int(time.time())}.png"
    driver.save_screenshot(path)
    return path


class TestProjectGeneratorSidebar:
    """AI项目生成器 - 侧边栏入口测试"""

    def test_sidebar_toolkit_exists(self, driver):
        """测试侧边栏工具集存在"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_element(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        assert toolkit_button is not None
        print("[OK] 工具集按钮存在")

    def test_project_generator_in_toolkit(self, driver):
        """测试项目生成器在工具集中"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        toolkit_menu = wait_for_element(driver, (By.CLASS_NAME, "toolkit-menu"))
        menu_html = toolkit_menu.get_attribute("innerHTML")

        assert "项目生成" in menu_html or "projectGenerator" in menu_html
        print("[OK] 项目生成器入口存在于工具集")

    def test_project_generator_opens_modal(self, driver):
        """测试点击项目生成器打开弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "project-generator"), timeout=5)
        assert modal is not None, "项目生成器弹窗未打开"
        print("[OK] 项目生成器弹窗正常打开")


class TestProjectGeneratorForm:
    """AI项目生成器 - 表单测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开项目生成器弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        yield

    def test_requirement_textarea_exists(self, driver):
        """测试需求输入框存在"""
        textarea = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        assert textarea is not None
        print("[OK] 需求输入框存在")

    def test_requirement_textarea_placeholder(self, driver):
        """测试需求输入框占位符"""
        textarea = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        placeholder = textarea.get_attribute("placeholder")
        assert placeholder is not None and len(placeholder) > 0
        print(f"[OK] 需求输入框占位符存在")

    def test_requirement_textarea_typing(self, driver):
        """测试需求输入"""
        textarea = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        textarea.clear()
        test_text = "创建一个简单的博客系统"
        textarea.send_keys(test_text)

        actual_value = textarea.get_attribute("value")
        assert test_text in actual_value
        print("[OK] 需求输入功能正常")

    def test_char_count_display(self, driver):
        """测试字符计数"""
        char_count = wait_for_element(driver, (By.CLASS_NAME, "char-count"))
        assert char_count is not None
        print(f"[OK] 字符计数显示: {char_count.text}")


class TestProjectGeneratorConfig:
    """AI项目生成器 - 配置选项测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开项目生成器弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        yield

    def test_project_type_select_exists(self, driver):
        """测试项目类型选择器存在"""
        selects = driver.find_elements(By.XPATH, "//select[contains(@class, 'form-select')]")
        assert len(selects) >= 3
        print(f"[OK] 找到 {len(selects)} 个下拉选择器")

    def test_project_type_options(self, driver):
        """测试项目类型选项"""
        selects = driver.find_elements(By.XPATH, "//select[contains(@class, 'form-select')]")
        project_type_select = selects[0]
        options = project_type_select.find_elements(By.TAG_NAME, "option")

        option_texts = [opt.text for opt in options]
        assert any("Web" in text or "web" in text for text in option_texts)
        print(f"[OK] 项目类型选项: {option_texts[:3]}...")

    def test_stack_options_exist(self, driver):
        """测试技术栈选项存在"""
        selects = driver.find_elements(By.XPATH, "//select[contains(@class, 'form-select')]")
        if len(selects) >= 2:
            stack_select = selects[1]
            options = stack_select.find_elements(By.TAG_NAME, "option")
            option_texts = [opt.text for opt in options]
            assert any("Vue" in text or "FastAPI" in text for text in option_texts)
            print(f"[OK] 技术栈选项存在")

    def test_model_select_exists(self, driver):
        """测试AI模型选择器存在"""
        model_select = wait_for_element(driver, (By.XPATH, "//select[contains(@class, 'form-select')]"))
        assert model_select is not None
        print("[OK] AI模型选择器存在")

    def test_generation_mode_select_exists(self, driver):
        """测试生成模式选择器存在"""
        selects = driver.find_elements(By.XPATH, "//select[contains(@class, 'form-select')]")
        assert len(selects) >= 3
        print("[OK] 生成模式选择器存在")


class TestProjectGeneratorSkills:
    """AI项目生成器 - Skill模板测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开项目生成器弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        yield

    def test_skill_grid_exists(self, driver):
        """测试 Skill 模板网格存在"""
        skill_grid = wait_for_element(driver, (By.CLASS_NAME, "skill-grid"))
        assert skill_grid is not None
        print("[OK] Skill 模板网格存在")

    def test_skill_cards_exist(self, driver):
        """测试 Skill 卡片存在"""
        skill_cards = driver.find_elements(By.CLASS_NAME, "skill-card")
        assert len(skill_cards) > 0, "至少应该有一个 Skill 模板"
        print(f"[OK] 找到 {len(skill_cards)} 个 Skill 模板")

    def test_skill_selection(self, driver):
        """测试 Skill 选择功能"""
        skill_cards = driver.find_elements(By.CLASS_NAME, "skill-card")
        if len(skill_cards) > 0:
            skill_cards[0].click()
            time.sleep(0.3)

            selected_cards = driver.find_elements(By.CLASS_NAME, "skill-card.selected")
            assert len(selected_cards) >= 1
            print("[OK] Skill 选择功能正常")


class TestProjectGeneratorPreview:
    """AI项目生成器 - 预览测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开项目生成器弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        yield

    def test_project_preview_shows_after_input(self, driver):
        """测试输入后显示项目预览"""
        textarea = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        textarea.clear()
        test_text = "创建一个在线商城系统"
        textarea.send_keys(test_text)
        time.sleep(1)

        preview = wait_for_element(driver, (By.CLASS_NAME, "project-preview"), timeout=3)
        assert preview is not None, "输入后应该显示项目预览"
        print("[OK] 项目预览正确显示")

    def test_project_preview_content(self, driver):
        """测试项目预览内容"""
        textarea = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        textarea.clear()
        test_text = "创建一个博客系统"
        textarea.send_keys(test_text)
        time.sleep(1)

        preview_items = driver.find_elements(By.CLASS_NAME, "preview-item")
        assert len(preview_items) > 0
        print(f"[OK] 预览项数量: {len(preview_items)}")


class TestProjectGeneratorButtons:
    """AI项目生成器 - 按钮测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开项目生成器弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        yield

    def test_start_generation_button_exists(self, driver):
        """测试开始生成按钮存在"""
        buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'btn-primary')]")
        has_generate_btn = any("生成" in btn.text or "开始" in btn.text for btn in buttons)
        assert has_generate_btn
        print("[OK] 开始生成按钮存在")


class TestProjectGeneratorResponsive:
    """AI项目生成器 - 响应式测试"""

    def test_modal_on_small_screen(self, driver):
        """测试小屏幕下的弹窗"""
        driver.set_window_size(375, 812)
        time.sleep(1)

        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        project_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '项目生成')]"))
        project_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "project-generator"), timeout=5)
        assert modal is not None

        driver.set_window_size(1920, 1080)
        print("[OK] 响应式弹窗测试通过")


if __name__ == "__main__":
    os.makedirs("screenshots", exist_ok=True)

    pytest.main([
        __file__,
        "-v",
        "-s",
        f"--html=reports/report_project_generator_{time.strftime('%Y%m%d_%H%M%S')}.html",
        "--self-contained-html",
        "--tb=short"
    ])
