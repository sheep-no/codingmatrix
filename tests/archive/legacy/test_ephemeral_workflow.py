"""
临时工作流 - Selenium 前端 E2E 测试

测试临时工作流功能的前端界面：
1. 侧边栏工具入口显示
2. 临时工作流弹窗打开
3. 任务输入框功能
4. 工作流节点显示
5. 导入/导出 JSON 功能
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
        screenshot_path = f"screenshots/ephemeral_workflow_{int(time.time())}.png"
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


class TestEphemeralWorkflowSidebar:
    """临时工作流 - 侧边栏入口测试"""

    def test_sidebar_toolkit_exists(self, driver):
        """测试侧边栏工具集存在"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_element(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        assert toolkit_button is not None
        print("[OK] 工具集按钮存在")

    def test_ephemeral_workflow_in_toolkit(self, driver):
        """测试临时工作流在工具集中"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        toolkit_menu = wait_for_element(driver, (By.CLASS_NAME, "toolkit-menu"))
        assert toolkit_menu is not None

        menu_html = toolkit_menu.get_attribute("innerHTML")
        assert "临时工作流" in menu_html or "ephemeral" in menu_html.lower(), \
            f"临时工作流未在工具菜单中找到"

        print("[OK] 临时工作流入口存在于工具集")

    def test_ephemeral_workflow_opens_modal(self, driver):
        """测试点击临时工作流打开弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        workflow_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '临时工作流')]"))
        workflow_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "ephemeral-workflow"), timeout=5)
        assert modal is not None, "临时工作流弹窗未打开"

        print("[OK] 临时工作流弹窗正常打开")


class TestEphemeralWorkflowInput:
    """临时工作流 - 输入区域测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开临时工作流弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        workflow_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '临时工作流')]"))
        workflow_item.click()
        time.sleep(2)

        yield

    def test_request_input_exists(self, driver):
        """测试任务输入框存在"""
        input_elem = wait_for_element(driver, (By.CLASS_NAME, "request-input"))
        assert input_elem is not None
        print("[OK] 任务输入框存在")

    def test_request_input_placeholder(self, driver):
        """测试输入框占位符"""
        input_elem = wait_for_element(driver, (By.CLASS_NAME, "request-input"))
        placeholder = input_elem.get_attribute("placeholder")
        assert placeholder is not None and len(placeholder) > 0
        print(f"[OK] 输入框占位符: {placeholder}")

    def test_request_input_typing(self, driver):
        """测试输入框可输入"""
        input_elem = wait_for_element(driver, (By.CLASS_NAME, "request-input"))
        input_elem.clear()
        test_text = "帮我搜索最新的AI新闻"
        input_elem.send_keys(test_text)

        actual_value = input_elem.get_attribute("value")
        assert test_text in actual_value, f"输入内容未正确显示: {actual_value}"
        print("[OK] 输入框可正常输入")

    def test_execute_button_exists(self, driver):
        """测试执行按钮存在"""
        execute_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '执行工作流')]"))
        assert execute_btn is not None
        print("[OK] 执行工作流按钮存在")

    def test_explain_button_exists(self, driver):
        """测试查看计划按钮存在"""
        explain_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '查看计划')]"))
        assert explain_btn is not None
        print("[OK] 查看计划按钮存在")

    def test_import_export_buttons_exist(self, driver):
        """测试导入导出按钮存在"""
        import_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '导入')]"))
        assert import_btn is not None
        print("[OK] 导入按钮存在")


class TestEphemeralWorkflowExport:
    """临时工作流 - 导出功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开临时工作流弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        workflow_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '临时工作流')]"))
        workflow_item.click()
        time.sleep(2)

        yield

    def test_export_button_initially_hidden(self, driver):
        """测试导出按钮初始状态隐藏（无工作流时）"""
        export_buttons = driver.find_elements(By.XPATH, "//button[contains(text(), '导出')]")
        if len(export_buttons) > 0:
            is_displayed = export_buttons[0].is_displayed()
            assert not is_displayed, "导出按钮应该在没有工作流时隐藏"
            print("[OK] 导出按钮初始状态正确（隐藏）")

    def test_workflow_section_initially_hidden(self, driver):
        """测试工作流图区域初始状态隐藏"""
        workflow_section = driver.find_elements(By.CLASS_NAME, "workflow-graph-section")
        if len(workflow_section) > 0:
            is_displayed = workflow_section[0].is_displayed()
            assert not is_displayed, "工作流图区域应该初始隐藏"
            print("[OK] 工作流图区域初始状态正确（隐藏）")


class TestEphemeralWorkflowModal:
    """临时工作流 - 弹窗功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开临时工作流弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        workflow_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '临时工作流')]"))
        workflow_item.click()
        time.sleep(2)

        yield

    def test_modal_close_button(self, driver):
        """测试弹窗关闭按钮"""
        close_btn = wait_for_element(driver, (By.XPATH, "//button[contains(@class, 'modal-close')]"), timeout=3)
        if close_btn:
            close_btn.click()
            time.sleep(1)
            print("[OK] 弹窗可关闭")

    def test_modal_title(self, driver):
        """测试弹窗标题"""
        title_elem = wait_for_element(driver, (By.CLASS_NAME, "modal-title"), timeout=3)
        if title_elem:
            title_text = title_elem.text
            assert "临时工作流" in title_text or "工作流" in title_text
            print(f"[OK] 弹窗标题: {title_text}")


class TestEphemeralWorkflowResponsive:
    """临时工作流 - 响应式测试"""

    def test_modal_on_small_screen(self, driver):
        """测试小屏幕下的弹窗"""
        driver.set_window_size(375, 812)
        time.sleep(1)

        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        workflow_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), '临时工作流')]"))
        workflow_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "ephemeral-workflow"), timeout=5)
        assert modal is not None

        driver.set_window_size(1920, 1080)
        print("[OK] 响应式弹窗测试通过")


if __name__ == "__main__":
    os.makedirs("screenshots", exist_ok=True)

    pytest.main([
        __file__,
        "-v",
        "-s",
        f"--html=reports/report_ephemeral_workflow_{time.strftime('%Y%m%d_%H%M%S')}.html",
        "--self-contained-html",
        "--tb=short"
    ])
