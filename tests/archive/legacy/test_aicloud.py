"""
aicloud - Selenium 前端 E2E 测试

测试 aicloud 功能：
1. 侧边栏工具入口显示
2. AI 云助手弹窗打开
3. 欢迎信息显示
4. 记忆状态显示
5. 聊天功能
6. 审查设置
7. 历史记录
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
        screenshot_path = f"screenshots/aicloud_{int(time.time())}.png"
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


class TestAicloudSidebar:
    """AI云助手 - 侧边栏入口测试"""

    def test_sidebar_toolkit_exists(self, driver):
        """测试侧边栏工具集存在"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_element(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        assert toolkit_button is not None
        print("[OK] 工具集按钮存在")

    def test_aicloud_in_toolkit(self, driver):
        """测试 AI 云助手在工具集中"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        toolkit_menu = wait_for_element(driver, (By.CLASS_NAME, "toolkit-menu"))
        menu_html = toolkit_menu.get_attribute("innerHTML")

        assert "AI 云助手" in menu_html or "aicloud" in menu_html.lower()
        print("[OK] AI 云助手入口存在于工具集")

    def test_aicloud_opens_modal(self, driver):
        """测试点击 AI 云助手打开弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "aicloud"), timeout=5)
        assert modal is not None, "AI 云助手弹窗未打开"
        print("[OK] AI 云助手弹窗正常打开")


class TestAicloudWelcome:
    """AI云助手 - 欢迎信息测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_welcome_section_exists(self, driver):
        """测试欢迎区域存在"""
        welcome_section = wait_for_element(driver, (By.CLASS_NAME, "welcome-section"))
        assert welcome_section is not None
        print("[OK] 欢迎区域存在")

    def test_welcome_icon_exists(self, driver):
        """测试欢迎图标存在"""
        welcome_icon = wait_for_element(driver, (By.CLASS_NAME, "welcome-icon"))
        assert welcome_icon is not None
        print("[OK] 欢迎图标存在")

    def test_welcome_title(self, driver):
        """测试欢迎标题"""
        welcome_text = wait_for_element(driver, (By.CLASS_NAME, "welcome-text"))
        title = welcome_text.find_element(By.TAG_NAME, "h3")
        assert title.text == "AI 云助手"
        print(f"[OK] 欢迎标题: {title.text}")

    def test_welcome_description(self, driver):
        """测试欢迎描述"""
        welcome_text = wait_for_element(driver, (By.CLASS_NAME, "welcome-text"))
        description = welcome_text.find_element(By.TAG_NAME, "p")
        assert "记忆" in description.text
        print(f"[OK] 欢迎描述包含记忆功能说明")


class TestAicloudMemoryStatus:
    """AI云助手 - 记忆状态测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_memory_status_exists(self, driver):
        """测试记忆状态区域存在"""
        memory_status = wait_for_element(driver, (By.CLASS_NAME, "memory-status"))
        assert memory_status is not None
        print("[OK] 记忆状态区域存在")

    def test_memory_days_display(self, driver):
        """测试记忆天数显示"""
        status_items = driver.find_elements(By.CLASS_NAME, "status-item")
        assert len(status_items) >= 2
        print(f"[OK] 找到 {len(status_items)} 个状态项")

    def test_message_count_display(self, driver):
        """测试消息数量显示"""
        status_values = driver.find_elements(By.CLASS_NAME, "status-value")
        assert len(status_values) >= 2
        print("[OK] 消息数量显示正常")

    def test_review_status_display(self, driver):
        """测试审查状态显示"""
        review_status = driver.find_element(By.XPATH, "//span[contains(text(), '审查状态')]")
        assert review_status is not None
        print("[OK] 审查状态显示存在")


class TestAicloudChat:
    """AI云助手 - 聊天功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_chat_section_exists(self, driver):
        """测试聊天区域存在"""
        chat_section = wait_for_element(driver, (By.CLASS_NAME, "chat-section"))
        assert chat_section is not None
        print("[OK] 聊天区域存在")

    def test_chat_messages_container_exists(self, driver):
        """测试消息容器存在"""
        messages_container = wait_for_element(driver, (By.CLASS_NAME, "chat-messages"))
        assert messages_container is not None
        print("[OK] 消息容器存在")

    def test_empty_messages_display(self, driver):
        """测试空消息状态显示"""
        empty_messages = wait_for_element(driver, (By.CLASS_NAME, "empty-messages"))
        assert empty_messages is not None
        print("[OK] 空消息状态正确显示")

    def test_input_section_exists(self, driver):
        """测试输入区域存在"""
        input_section = wait_for_element(driver, (By.CLASS_NAME, "input-section"))
        assert input_section is not None
        print("[OK] 输入区域存在")

    def test_message_input_exists(self, driver):
        """测试消息输入框存在"""
        message_input = wait_for_element(driver, (By.CLASS_NAME, "message-input"))
        assert message_input is not None
        print("[OK] 消息输入框存在")

    def test_message_input_placeholder(self, driver):
        """测试输入框占位符"""
        message_input = wait_for_element(driver, (By.CLASS_NAME, "message-input"))
        placeholder = message_input.get_attribute("placeholder")
        assert placeholder is not None and len(placeholder) > 0
        print(f"[OK] 输入框占位符: {placeholder}")

    def test_send_button_exists(self, driver):
        """测试发送按钮存在"""
        send_button = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '发送')]"))
        assert send_button is not None
        print("[OK] 发送按钮存在")


class TestAicloudReview:
    """AI云助手 - 审查设置测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_toggle_review_button_exists(self, driver):
        """测试切换审查按钮存在"""
        toggle_button = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '审查')]"))
        assert toggle_button is not None
        print("[OK] 审查设置按钮存在")

    def test_toggle_review_functionality(self, driver):
        """测试切换审查功能"""
        toggle_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(text(), '审查')]"))
        initial_text = toggle_button.text

        toggle_button.click()
        time.sleep(0.5)

        new_text = toggle_button.text
        assert initial_text != new_text or "关闭" in initial_text or "开启" in new_text
        print("[OK] 审查设置可切换")


class TestAicloudHistory:
    """AI云助手 - 历史记录测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_history_button_exists(self, driver):
        """测试历史按钮存在"""
        history_button = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '历史')]"))
        assert history_button is not None
        print("[OK] 历史按钮存在")

    def test_export_button_exists(self, driver):
        """测试导出按钮存在"""
        export_button = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '导出')]"))
        assert export_button is not None
        print("[OK] 导出按钮存在")

    def test_history_panel_toggle(self, driver):
        """测试历史面板切换"""
        history_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(text(), '历史')]"))
        history_button.click()
        time.sleep(0.5)

        history_panel = driver.find_elements(By.CLASS_NAME, "history-panel")
        assert len(history_panel) > 0
        print("[OK] 历史面板可切换显示")


class TestAicloudClearMemory:
    """AI云助手 - 清除记忆测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 云助手弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        yield

    def test_clear_memory_button_exists(self, driver):
        """测试清除记忆按钮存在"""
        clear_button = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '清除记忆')]"))
        assert clear_button is not None
        print("[OK] 清除记忆按钮存在")


class TestAicloudResponsive:
    """AI云助手 - 响应式测试"""

    def test_modal_on_small_screen(self, driver):
        """测试小屏幕下的弹窗"""
        driver.set_window_size(375, 812)
        time.sleep(1)

        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        aicloud_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 云助手')]"))
        aicloud_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "aicloud"), timeout=5)
        assert modal is not None

        driver.set_window_size(1920, 1080)
        print("[OK] 响应式弹窗测试通过")


if __name__ == "__main__":
    os.makedirs("screenshots", exist_ok=True)

    pytest.main([
        __file__,
        "-v",
        "-s",
        f"--html=reports/report_aicloud_{time.strftime('%Y%m%d_%H%M%S')}.html",
        "--self-contained-html",
        "--tb=short"
    ])
