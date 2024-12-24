from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PIL import Image
import numpy as np
from scipy import ndimage
import requests
import ddddocr
import logging
import json
import time
from typing import Dict, Any, Optional, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 加载配置
def load_config() -> Dict[str, Any]:
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "url": "https://www.serv00.com/offer/create_new_account",
            "max_retries": 3,
            "timeout": 10,
            "wait_time": 1
        }

CONFIG = load_config()

class CaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr()

    @staticmethod
    def remove_noise_median(image):
        """去除图像噪点"""
        img_gray = image.convert('L')
        img_array = np.array(img_gray)
        denoised = ndimage.median_filter(img_array, 3)
        return Image.fromarray(denoised)

    def solve_captcha(self, driver: webdriver.Firefox) -> str:
        """解析验证码并填入表单"""
        try:
            captcha = WebDriverWait(driver, CONFIG['timeout']).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='id_captcha_1']/../img"))
            )
            captcha_url = captcha.get_attribute('src')
            
            # 配置代理
            proxies = None
            if CONFIG.get('proxy', {}).get('enabled', False):
                proxy_http = CONFIG['proxy']['http']
                proxies = {
                    'http': proxy_http,
                    'https': proxy_http
                }
            
            response = requests.get(captcha_url, proxies=proxies)
            captcha_data = response.content

            captcha_text = self.ocr.classification(captcha_data)
            captcha_text = captcha_text.upper()

            input_captcha = driver.find_element(By.ID, "id_captcha_1")
            input_captcha.clear()
            input_captcha.send_keys(captcha_text)
            
            logger.info(f"验证码识别结果: {captcha_text}")
            return captcha_text
            
        except Exception as e:
            logger.error(f"验证码处理失败: {str(e)}")
            raise

class AccountRegistration:
    def __init__(self):
        self.captcha_solver = CaptchaSolver()
        self.driver = None

    def setup_driver(self):
        """配置并初始化WebDriver"""
        options = Options()
        if CONFIG.get('headless', True):  # 默认启用无头模式
            options.add_argument('--headless')
            logger.info("启用无头模式")
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        
        # 配置代理
        if CONFIG.get('proxy', {}).get('enabled', False):
            proxy_http = CONFIG['proxy']['http']
            if proxy_http:
                # 使用Firefox的代理设置
                options.set_preference('network.proxy.type', 1)
                options.set_preference('network.proxy.http', proxy_http.split('://')[1].split(':')[0])
                options.set_preference('network.proxy.http_port', int(proxy_http.split(':')[-1]))
                options.set_preference('network.proxy.ssl', proxy_http.split('://')[1].split(':')[0])
                options.set_preference('network.proxy.ssl_port', int(proxy_http.split(':')[-1]))
                # 设置所有协议使用相同的代理
                options.set_preference('network.proxy.share_proxy_settings', True)
                # 设置不使用代理的域名
                options.set_preference('network.proxy.no_proxies_on', 'localhost,127.0.0.1')
        # 添加更多无头模式优化
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--no-first-run')
        options.add_argument('--no-zygote')
        options.add_argument('--single-process')
        options.add_argument('--disable-infobars')
        
        service = Service('/root/Serv00-Reg/geckodriver')
        # service = Service(CONFIG.get('geckodriver_path', '/usr/local/bin/geckodriver'))
        self.driver = webdriver.Firefox(service=service, options=options)
        self.driver.implicitly_wait(CONFIG['wait_time'])
        # 设置窗口大小以确保元素可见性
        self.driver.set_window_size(1920, 1080)

    def random_sleep(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """随机等待一段时间"""
        sleep_time = min_seconds + (max_seconds - min_seconds) * np.random.random()
        time.sleep(sleep_time)

    def simulate_human_input(self, element, text: str):
        """模拟人工输入"""
        for char in text:
            element.send_keys(char)
            time.sleep(0.05 + np.random.random() * 0.1)  # 随机输入延迟

    def fill_form_field(self, field_id: str, value: str):
        """填写表单字段"""
        try:
            element = WebDriverWait(self.driver, CONFIG['timeout']).until(
                EC.presence_of_element_located((By.ID, field_id))
            )
            element.clear()
            self.simulate_human_input(element, value)
            self.random_sleep(0.5, 1.5)  # 字段间随机等待
        except TimeoutException:
            logger.error(f"无法找到字段: {field_id}")
            raise

    def wait_for_url_change(self, original_url: str, timeout: int = 120) -> Tuple[bool, Optional[str]]:
        """等待URL变化或检查错误消息"""
        start_time = time.time()
        retry_count = 0
        
        while time.time() - start_time < timeout:
            # 检查URL变化
            current_url = self.driver.current_url
            if current_url != original_url:
                logger.info(f"URL已更改: {current_url}")
                time.sleep(2)  # 等待2秒确认
                return True, None
            
            # 检查错误消息
            try:
                error_messages = self.driver.find_elements(By.CSS_SELECTOR, "[class*='error_message']")
                if error_messages:
                    error_text = error_messages[0].text
                    if "CAPTCHA" in error_text and retry_count < CONFIG['max_retries']:
                        logger.info(f"验证码错误，正在重试... (第 {retry_count + 1} 次)")
                        
                        # 随机等待后重试
                        self.random_sleep(2, 4)
                        
                        # 重新获取并填写验证码
                        self.captcha_solver.solve_captcha(self.driver)
                        
                        # 随机等待后提交
                        self.random_sleep(1, 3)
                        submit_button = self.driver.find_element(
                            By.XPATH, "/html/body/section/div/div[2]/div[2]/form/p[9]"
                        )
                        submit_button.click()
                        
                        retry_count += 1
                    else:
                        logger.error(f"表单提交错误: {error_text}")
                        return False, error_text
            except Exception as e:
                logger.warning(f"检查错误消息时发生异常: {str(e)}")
            
            time.sleep(0.5)  # 每0.5秒检查一次
        
        logger.error("等待URL变化超时")
        return False, "注册超时，URL未发生变化"

    def register_account(self, first_name: str, last_name: str, username: str, email: str) -> Tuple[bool, Optional[str]]:
        """
        注册账号主函数
        返回: (是否成功, 错误信息)
        """
        error_msg = None
        try:
            self.setup_driver()
            self.driver.set_page_load_timeout(CONFIG['timeout'])  # 设置页面加载超时
            self.driver.get(CONFIG['url'])
            logger.info(f"网页标题: {self.driver.title}")

            # 模拟人工填写表单
            form_fields = {
                'id_first_name': first_name,
                'id_last_name': last_name,
                'id_username': username,
                'id_email': email,
                'id_question': 'free'
            }
            
            for field_id, value in form_fields.items():
                self.fill_form_field(field_id, value)
                self.random_sleep()  # 字段间随机等待

            # 处理checkbox
            checkbox = self.driver.find_element(By.ID, "id_tos")
            if not checkbox.is_selected():
                checkbox.click()
                self.random_sleep()

            # 处理验证码
            try:
                self.captcha_solver.solve_captcha(self.driver)
            except Exception as e:
                error_msg = f"验证码处理失败: {str(e)}"
                return False, error_msg

            # 随机等待后提交
            self.random_sleep(1, 3)
            submit_button = self.driver.find_element(
                By.XPATH, "/html/body/section/div/div[2]/div[2]/form/p[9]"
            )
            submit_button.click()

            # 记录当前URL并等待结果
            original_url = self.driver.current_url
            success, error_msg = self.wait_for_url_change(original_url)
            return success, error_msg

        except TimeoutException as e:
            error_msg = "页面加载超时"
            logger.error(error_msg)
            return False, error_msg
        except NoSuchElementException as e:
            error_msg = f"找不到元素: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"注册过程发生错误: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
        finally:
            if self.driver:
                self.driver.quit()

if __name__ == "__main__":
    registration = AccountRegistration()
    success, error = registration.register_account(
        "Zhi", 
        "Yang", 
        "cbzy-011-0aca", 
        "zhi.yang@sjsu.edu"
    )
    if success:
        logger.info("注册成功")
    else:
        logger.error(f"注册失败: {error}")
