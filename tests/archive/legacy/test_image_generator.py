"""
ImageGenerator + Prompt画廊 - Selenium 前端 E2E 测试

测试 AI 绘画和 Prompt 画廊功能：
1. 侧边栏工具入口显示
2. AI 绘画弹窗打开
3. 文生图/图生图模式切换
4. 提示词输入
5. 风格预设选择
6. 分辨率/迭代步数配置
7. 图片生成功能
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
        screenshot_path = f"screenshots/image_generator_{int(time.time())}.png"
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


class TestImageGeneratorSidebar:
    """AI绘画 - 侧边栏入口测试"""

    def test_sidebar_toolkit_exists(self, driver):
        """测试侧边栏工具集存在"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_element(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        assert toolkit_button is not None
        print("[OK] 工具集按钮存在")

    def test_image_generator_in_toolkit(self, driver):
        """测试 AI 绘画在工具集中"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        toolkit_menu = wait_for_element(driver, (By.CLASS_NAME, "toolkit-menu"))
        menu_html = toolkit_menu.get_attribute("innerHTML")

        assert "AI 绘画" in menu_html or "imageGenerator" in menu_html
        print("[OK] AI 绘画入口存在于工具集")

    def test_image_generator_opens_modal(self, driver):
        """测试点击 AI 绘画打开弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "image-generator"), timeout=5)
        assert modal is not None, "AI 绘画弹窗未打开"
        print("[OK] AI 绘画弹窗正常打开")


class TestImageGeneratorMode:
    """AI绘画 - 模式切换测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_mode_switch_exists(self, driver):
        """测试模式切换按钮存在"""
        mode_switch = wait_for_element(driver, (By.CLASS_NAME, "mode-switch"))
        assert mode_switch is not None
        print("[OK] 模式切换区域存在")

    def test_text2img_mode_active_by_default(self, driver):
        """测试默认模式为文生图"""
        text2img_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '文生图')]"))
        assert "active" in text2img_btn.get_attribute("class")
        print("[OK] 默认模式为文生图")

    def test_switch_to_img2img_mode(self, driver):
        """测试切换到图生图模式"""
        img2img_btn = wait_for_clickable(driver, (By.XPATH, "//button[contains(text(), '图生图')]"))
        img2img_btn.click()
        time.sleep(0.5)

        reference_section = wait_for_element(driver, (By.XPATH, "//section[contains(@class, 'form-section')]//label[contains(text(), '参考图片')]"))
        assert reference_section is not None
        print("[OK] 图生图模式切换成功，显示参考图片上传区域")


class TestImageGeneratorPrompt:
    """AI绘画 - 提示词输入测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_prompt_input_exists(self, driver):
        """测试提示词输入框存在"""
        prompt_input = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        assert prompt_input is not None
        print("[OK] 提示词输入框存在")

    def test_prompt_input_placeholder(self, driver):
        """测试提示词输入框占位符"""
        prompt_input = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        placeholder = prompt_input.get_attribute("placeholder")
        assert placeholder is not None and len(placeholder) > 0
        print(f"[OK] 提示词占位符: {placeholder}")

    def test_prompt_input_typing(self, driver):
        """测试提示词可输入"""
        prompt_input = wait_for_element(driver, (By.XPATH, "//textarea[contains(@class, 'form-textarea')]"))
        prompt_input.clear()
        test_text = "一只可爱的猫咪在草地上玩耍"
        prompt_input.send_keys(test_text)

        actual_value = prompt_input.get_attribute("value")
        assert test_text in actual_value
        print("[OK] 提示词可正常输入")

    def test_char_count_display(self, driver):
        """测试字符计数显示"""
        char_count = wait_for_element(driver, (By.CLASS_NAME, "char-count"))
        assert char_count is not None
        print(f"[OK] 字符计数显示: {char_count.text}")


class TestImageGeneratorStyle:
    """AI绘画 - 风格预设测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_style_grid_exists(self, driver):
        """测试风格选择网格存在"""
        style_grid = wait_for_element(driver, (By.CLASS_NAME, "style-grid"))
        assert style_grid is not None
        print("[OK] 风格选择网格存在")

    def test_style_cards_exist(self, driver):
        """测试风格卡片存在"""
        style_cards = driver.find_elements(By.CLASS_NAME, "style-card")
        assert len(style_cards) > 0, "至少应该有一个风格选项"
        print(f"[OK] 找到 {len(style_cards)} 个风格选项")

    def test_style_selection(self, driver):
        """测试风格选择功能"""
        style_cards = driver.find_elements(By.CLASS_NAME, "style-card")
        if len(style_cards) > 1:
            style_cards[1].click()
            time.sleep(0.3)

            selected_cards = driver.find_elements(By.CLASS_NAME, "style-card.selected")
            assert len(selected_cards) >= 1
            print("[OK] 风格选择功能正常")


class TestImageGeneratorConfig:
    """AI绘画 - 配置选项测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_resolution_select_exists(self, driver):
        """测试分辨率选择存在"""
        resolution_select = wait_for_element(driver, (By.XPATH, "//select[contains(@class, 'form-select')]"))
        assert resolution_select is not None
        print("[OK] 分辨率选择器存在")

    def test_resolution_options(self, driver):
        """测试分辨率选项"""
        resolution_select = wait_for_element(driver, (By.XPATH, "//select[contains(@class, 'form-select')]"))
        options = resolution_select.find_elements(By.TAG_NAME, "option")
        option_texts = [opt.text for opt in options]

        assert any("512" in text for text in option_texts), "应该有 512 分辨率选项"
        assert any("1024" in text for text in option_texts), "应该有 1024 分辨率选项"
        print(f"[OK] 分辨率选项: {option_texts}")

    def test_steps_slider_exists(self, driver):
        """测试迭代步数滑块存在"""
        steps_slider = wait_for_element(driver, (By.XPATH, "//input[@type='range' and contains(@class, 'form-slider')]"))
        assert steps_slider is not None
        print("[OK] 迭代步数滑块存在")

    def test_cfg_scale_input_exists(self, driver):
        """测试引导系数输入框存在"""
        cfg_inputs = driver.find_elements(By.XPATH, "//input[contains(@class, 'form-input') and @type='number']")
        assert len(cfg_inputs) > 0
        print("[OK] 引导系数输入框存在")

    def test_batch_size_input_exists(self, driver):
        """测试数量输入框存在"""
        batch_inputs = driver.find_elements(By.XPATH, "//input[contains(@class, 'form-input') and @type='number']")
        assert len(batch_inputs) >= 2
        print("[OK] 数量输入框存在")


class TestImageGeneratorGallery:
    """AI绘画 - 画廊测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_preview_panel_exists(self, driver):
        """测试预览面板存在"""
        preview_panel = wait_for_element(driver, (By.CLASS_NAME, "preview-panel"))
        assert preview_panel is not None
        print("[OK] 预览面板存在")

    def test_preview_header_exists(self, driver):
        """测试预览标题存在"""
        preview_header = wait_for_element(driver, (By.CLASS_NAME, "preview-header"))
        assert preview_header is not None
        print("[OK] 预览标题存在")

    def test_empty_gallery_display(self, driver):
        """测试空画廊显示"""
        empty_gallery = wait_for_element(driver, (By.CLASS_NAME, "empty-gallery"))
        assert empty_gallery is not None
        print("[OK] 空画廊状态显示正确")


class TestImageGeneratorGenerate:
    """AI绘画 - 生成功能测试"""

    @pytest.fixture(autouse=True)
    def setup(self, driver):
        """打开 AI 绘画弹窗"""
        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        yield

    def test_generate_button_exists(self, driver):
        """测试生成按钮存在"""
        generate_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '生成图片')]"))
        assert generate_btn is not None
        print("[OK] 生成图片按钮存在")

    def test_cancel_button_exists(self, driver):
        """测试取消按钮存在"""
        cancel_btn = wait_for_element(driver, (By.XPATH, "//button[contains(text(), '取消')]"))
        assert cancel_btn is not None
        print("[OK] 取消按钮存在")


class TestImageGeneratorResponsive:
    """AI绘画 - 响应式测试"""

    def test_modal_on_small_screen(self, driver):
        """测试小屏幕下的弹窗"""
        driver.set_window_size(375, 812)
        time.sleep(1)

        driver.get(BASE_URL)
        time.sleep(2)

        toolkit_button = wait_for_clickable(driver, (By.XPATH, "//button[contains(@class, 'btn-toolkit')]"))
        toolkit_button.click()
        time.sleep(1)

        image_item = wait_for_clickable(driver, (By.XPATH, "//span[contains(text(), 'AI 绘画')]"))
        image_item.click()
        time.sleep(2)

        modal = wait_for_element(driver, (By.CLASS_NAME, "image-generator"), timeout=5)
        assert modal is not None

        driver.set_window_size(1920, 1080)
        print("[OK] 响应式弹窗测试通过")


if __name__ == "__main__":
    os.makedirs("screenshots", exist_ok=True)

    pytest.main([
        __file__,
        "-v",
        "-s",
        f"--html=reports/report_image_generator_{time.strftime('%Y%m%d_%H%M%S')}.html",
        "--self-contained-html",
        "--tb=short"
    ])
