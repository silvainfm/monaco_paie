"""
Test script for Monaco Payroll App - Validation and PDF Generation pages
"""
import time
import os
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from datetime import datetime


class StreamlitAppTester:
    def __init__(self, base_url="http://localhost:8501"):
        self.base_url = base_url
        self.driver = None
        self.results = []
        self.screenshots_dir = Path("test_results/screenshots")
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def setup_driver(self):
        """Setup Chrome driver in headless mode"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")

        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
            self.log_result("Setup", "SUCCESS", "Chrome driver initialized")
        except Exception as e:
            self.log_result("Setup", "FAILED", f"Failed to initialize driver: {str(e)}")
            raise

    def teardown_driver(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()

    def log_result(self, test_name, status, message):
        """Log test result"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result = {
            "timestamp": timestamp,
            "test": test_name,
            "status": status,
            "message": message
        }
        self.results.append(result)
        print(f"[{timestamp}] {test_name}: {status} - {message}")

    def take_screenshot(self, name):
        """Take screenshot"""
        if self.driver:
            filepath = self.screenshots_dir / f"{name}_{int(time.time())}.png"
            self.driver.save_screenshot(str(filepath))
            self.log_result("Screenshot", "INFO", f"Saved: {filepath}")
            return filepath
        return None

    def wait_for_streamlit_load(self, timeout=30):
        """Wait for Streamlit to fully load"""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(2)  # Additional wait for dynamic content
            return True
        except TimeoutException:
            return False

    def test_app_loads(self):
        """Test 1: Check if app loads"""
        test_name = "App Load"
        try:
            self.driver.get(self.base_url)
            if self.wait_for_streamlit_load():
                self.take_screenshot("01_app_loaded")

                # Check for common Streamlit elements
                page_source = self.driver.page_source
                if "streamlit" in page_source.lower() or "st-" in page_source:
                    self.log_result(test_name, "SUCCESS", "App loaded successfully")
                    return True
                else:
                    self.log_result(test_name, "WARNING", "App loaded but Streamlit elements not found")
                    return False
            else:
                self.log_result(test_name, "FAILED", "Timeout waiting for app to load")
                return False
        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            self.take_screenshot("01_app_load_error")
            return False

    def find_radio_option(self, text):
        """Find and click radio button option by text"""
        try:
            # Streamlit radio buttons are typically in label elements
            labels = self.driver.find_elements(By.TAG_NAME, "label")
            for label in labels:
                if text in label.text:
                    label.click()
                    time.sleep(1)
                    return True
            return False
        except Exception as e:
            print(f"Error finding radio option: {e}")
            return False

    def test_navigation_to_validation(self):
        """Test 2: Navigate to Validation page"""
        test_name = "Navigate to Validation"
        try:
            # Look for validation menu item
            if self.find_radio_option("Validation"):
                time.sleep(2)
                self.take_screenshot("02_validation_page")

                # Check if we're on validation page
                page_source = self.driver.page_source
                if "Validation" in page_source and ("Modification" in page_source or "Paies" in page_source):
                    self.log_result(test_name, "SUCCESS", "Navigated to Validation page")
                    return True
                else:
                    self.log_result(test_name, "WARNING", "Navigation unclear")
                    return False
            else:
                self.log_result(test_name, "FAILED", "Could not find Validation menu option")
                return False
        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            self.take_screenshot("02_validation_error")
            return False

    def test_validation_page_elements(self):
        """Test 3: Check Validation page elements"""
        test_name = "Validation Page Elements"
        try:
            page_source = self.driver.page_source

            # Check for key elements
            checks = {
                "Header": "Validation" in page_source,
                "Company selection": "entreprise" in page_source.lower() or "company" in page_source.lower(),
                "Period selection": "période" in page_source.lower() or "period" in page_source.lower(),
            }

            passed = sum(checks.values())
            total = len(checks)

            if passed == total:
                self.log_result(test_name, "SUCCESS", f"All {total} elements found")
                return True
            elif passed > 0:
                self.log_result(test_name, "PARTIAL", f"{passed}/{total} elements found: {checks}")
                return False
            else:
                self.log_result(test_name, "FAILED", "No expected elements found")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_navigation_to_pdf_generation(self):
        """Test 4: Navigate to PDF Generation page"""
        test_name = "Navigate to PDF Generation"
        try:
            # Look for PDF generation menu item
            if self.find_radio_option("PDF") or self.find_radio_option("Génération"):
                time.sleep(2)
                self.take_screenshot("03_pdf_generation_page")

                # Check if we're on PDF generation page
                page_source = self.driver.page_source
                if "PDF" in page_source and ("Génération" in page_source or "Generation" in page_source):
                    self.log_result(test_name, "SUCCESS", "Navigated to PDF Generation page")
                    return True
                else:
                    self.log_result(test_name, "WARNING", "Navigation unclear")
                    return False
            else:
                self.log_result(test_name, "FAILED", "Could not find PDF Generation menu option")
                return False
        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            self.take_screenshot("03_pdf_generation_error")
            return False

    def test_pdf_generation_page_elements(self):
        """Test 5: Check PDF Generation page elements"""
        test_name = "PDF Generation Page Elements"
        try:
            page_source = self.driver.page_source

            # Check for key elements
            checks = {
                "Header": "PDF" in page_source and "Génération" in page_source,
                "Company/Period check": "entreprise" in page_source.lower() or "période" in page_source.lower(),
                "PDF related content": "pdf" in page_source.lower(),
            }

            passed = sum(checks.values())
            total = len(checks)

            if passed == total:
                self.log_result(test_name, "SUCCESS", f"All {total} elements found")
                return True
            elif passed > 0:
                self.log_result(test_name, "PARTIAL", f"{passed}/{total} elements found: {checks}")
                return False
            else:
                self.log_result(test_name, "FAILED", "No expected elements found")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_page_responsiveness(self):
        """Test 6: Check if pages are responsive"""
        test_name = "Page Responsiveness"
        try:
            # Check for Streamlit connection status
            page_source = self.driver.page_source

            # Check for error messages
            error_indicators = ["error", "exception", "failed", "échec"]
            has_errors = any(indicator in page_source.lower() for indicator in error_indicators)

            # Check for loading indicators stuck
            loading_indicators = ["spinner", "loading"]
            is_loading = any(indicator in page_source.lower() for indicator in loading_indicators)

            if has_errors:
                self.log_result(test_name, "WARNING", "Error indicators found on page")
                self.take_screenshot("04_page_errors")
                return False
            elif is_loading:
                self.log_result(test_name, "WARNING", "Page still loading")
                return False
            else:
                self.log_result(test_name, "SUCCESS", "Page responsive, no errors")
                return True

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("Monaco Payroll App - Webapp Testing")
        print("=" * 80)
        print()

        try:
            self.setup_driver()

            # Run tests in sequence
            tests = [
                self.test_app_loads,
                self.test_navigation_to_validation,
                self.test_validation_page_elements,
                self.test_navigation_to_pdf_generation,
                self.test_pdf_generation_page_elements,
                self.test_page_responsiveness,
            ]

            for test in tests:
                test()
                time.sleep(1)

        except Exception as e:
            self.log_result("Test Suite", "FAILED", f"Fatal error: {str(e)}")
        finally:
            self.teardown_driver()
            self.print_summary()

    def print_summary(self):
        """Print test summary"""
        print()
        print("=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)

        success = sum(1 for r in self.results if r["status"] == "SUCCESS")
        failed = sum(1 for r in self.results if r["status"] == "FAILED")
        warning = sum(1 for r in self.results if r["status"] in ["WARNING", "PARTIAL"])
        total = len([r for r in self.results if r["status"] in ["SUCCESS", "FAILED", "PARTIAL", "WARNING"]])

        print(f"\nTotal Tests: {total}")
        print(f"✓ Passed: {success}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Warnings: {warning}")
        print()

        print("Detailed Results:")
        print("-" * 80)
        for result in self.results:
            status_symbol = {
                "SUCCESS": "✓",
                "FAILED": "✗",
                "WARNING": "⚠",
                "PARTIAL": "◐",
                "INFO": "ℹ"
            }.get(result["status"], "?")

            print(f"{status_symbol} [{result['test']}] {result['status']}: {result['message']}")

        print()
        print(f"Screenshots saved to: {self.screenshots_dir}")
        print("=" * 80)


if __name__ == "__main__":
    # Check if Streamlit is running
    import socket

    def check_port(host="localhost", port=8501):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0

    if not check_port():
        print("ERROR: Streamlit app not running on port 8501")
        print("Please start the app first: uv run streamlit run app.py")
        exit(1)

    # Run tests
    tester = StreamlitAppTester()
    tester.run_all_tests()
