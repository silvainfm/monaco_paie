"""
Simple HTTP-based test for Monaco Payroll App
Tests validation and PDF generation pages
"""
import requests
import time
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path


class SimpleAppTester:
    def __init__(self, base_url="http://localhost:8501"):
        self.base_url = base_url
        self.results = []
        self.session = requests.Session()

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
        status_symbol = {
            "SUCCESS": "✓",
            "FAILED": "✗",
            "WARNING": "⚠",
            "PARTIAL": "◐",
            "INFO": "ℹ"
        }.get(status, "?")
        print(f"[{timestamp}] {status_symbol} {test_name}: {status} - {message}")

    def test_app_accessible(self):
        """Test 1: Check if app is accessible"""
        test_name = "App Accessibility"
        try:
            response = self.session.get(self.base_url, timeout=10)
            if response.status_code == 200:
                self.log_result(test_name, "SUCCESS", f"App accessible (HTTP {response.status_code})")
                return True
            else:
                self.log_result(test_name, "FAILED", f"HTTP {response.status_code}")
                return False
        except Exception as e:
            self.log_result(test_name, "FAILED", f"Connection error: {str(e)}")
            return False

    def test_app_content(self):
        """Test 2: Check app contains expected content"""
        test_name = "App Content Check"
        try:
            response = self.session.get(self.base_url, timeout=10)
            content = response.text.lower()

            # Check for key application elements
            checks = {
                "Streamlit framework": "streamlit" in content,
                "Application title/header": any(word in content for word in ["monaco", "paie", "payroll"]),
                "Navigation elements": any(word in content for word in ["menu", "navigation", "sidebar"]),
            }

            passed = sum(checks.values())
            total = len(checks)

            if passed == total:
                self.log_result(test_name, "SUCCESS", f"All {total} content checks passed")
                return True
            elif passed > 0:
                details = ", ".join([f"{k}: {'✓' if v else '✗'}" for k, v in checks.items()])
                self.log_result(test_name, "PARTIAL", f"{passed}/{total} checks passed ({details})")
                return False
            else:
                self.log_result(test_name, "FAILED", "No expected content found")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_validation_page_references(self):
        """Test 3: Check for validation page references"""
        test_name = "Validation Page References"
        try:
            response = self.session.get(self.base_url, timeout=10)
            content = response.text

            # Search for validation-related content
            validation_terms = ["validation", "modification", "paies", "édition", "validate"]
            found_terms = [term for term in validation_terms if term in content.lower()]

            if len(found_terms) >= 2:
                self.log_result(
                    test_name,
                    "SUCCESS",
                    f"Found {len(found_terms)} validation-related terms: {', '.join(found_terms[:3])}"
                )
                return True
            elif found_terms:
                self.log_result(
                    test_name,
                    "PARTIAL",
                    f"Found {len(found_terms)} term(s): {', '.join(found_terms)}"
                )
                return False
            else:
                self.log_result(test_name, "FAILED", "No validation references found")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_pdf_generation_references(self):
        """Test 4: Check for PDF generation page references"""
        test_name = "PDF Generation References"
        try:
            response = self.session.get(self.base_url, timeout=10)
            content = response.text

            # Search for PDF-related content
            pdf_terms = ["pdf", "génération", "generation", "bulletin", "payslip"]
            found_terms = [term for term in pdf_terms if term in content.lower()]

            if len(found_terms) >= 2:
                self.log_result(
                    test_name,
                    "SUCCESS",
                    f"Found {len(found_terms)} PDF-related terms: {', '.join(found_terms[:3])}"
                )
                return True
            elif found_terms:
                self.log_result(
                    test_name,
                    "PARTIAL",
                    f"Found {len(found_terms)} term(s): {', '.join(found_terms)}"
                )
                return False
            else:
                self.log_result(test_name, "FAILED", "No PDF generation references found")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_required_pages_structure(self):
        """Test 5: Check for required pages in navigation"""
        test_name = "Required Pages Structure"
        try:
            response = self.session.get(self.base_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for page navigation elements
            page_text = soup.get_text()

            required_pages = {
                "Dashboard": "tableau de bord" in page_text.lower() or "dashboard" in page_text.lower(),
                "Import": "import" in page_text.lower(),
                "Validation": "validation" in page_text.lower(),
                "PDF Generation": "génération" in page_text.lower() and "pdf" in page_text.lower(),
            }

            found = sum(required_pages.values())
            total = len(required_pages)

            if found >= 3:  # At least 3 of 4 pages found
                details = ", ".join([f"{k}: {'✓' if v else '✗'}" for k, v in required_pages.items()])
                self.log_result(test_name, "SUCCESS", f"{found}/{total} pages found ({details})")
                return True
            elif found > 0:
                details = ", ".join([f"{k}: {'✓' if v else '✗'}" for k, v in required_pages.items()])
                self.log_result(test_name, "PARTIAL", f"{found}/{total} pages found ({details})")
                return False
            else:
                self.log_result(test_name, "FAILED", "No expected pages found in navigation")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_app_health(self):
        """Test 6: Check app health endpoint"""
        test_name = "App Health Check"
        try:
            # Streamlit has a _stcore/health endpoint
            health_url = f"{self.base_url}/_stcore/health"
            response = self.session.get(health_url, timeout=5)

            if response.status_code == 200:
                self.log_result(test_name, "SUCCESS", "Health endpoint OK")
                return True
            else:
                self.log_result(test_name, "WARNING", f"Health endpoint returned {response.status_code}")
                return False
        except Exception as e:
            self.log_result(test_name, "WARNING", f"Health endpoint unavailable: {str(e)}")
            return False

    def test_streamlit_specific_elements(self):
        """Test 7: Check for Streamlit-specific elements"""
        test_name = "Streamlit Elements"
        try:
            response = self.session.get(self.base_url, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Look for Streamlit-specific classes/IDs
            streamlit_elements = {
                "Streamlit root": soup.find(id="root") is not None or soup.find(attrs={"data-testid": True}),
                "Streamlit scripts": any("streamlit" in str(script) for script in soup.find_all("script")),
                "Streamlit styles": any("streamlit" in str(link.get("href", "")) for link in soup.find_all("link")),
            }

            found = sum(streamlit_elements.values())
            total = len(streamlit_elements)

            if found >= 2:
                self.log_result(test_name, "SUCCESS", f"{found}/{total} Streamlit elements found")
                return True
            elif found > 0:
                self.log_result(test_name, "PARTIAL", f"{found}/{total} Streamlit elements found")
                return False
            else:
                self.log_result(test_name, "FAILED", "No Streamlit elements detected")
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def test_javascript_errors(self):
        """Test 8: Check for obvious errors in page"""
        test_name = "Error Detection"
        try:
            response = self.session.get(self.base_url, timeout=10)
            content = response.text.lower()

            # Look for common error indicators
            error_patterns = ["error", "exception", "traceback", "fatal", "failed to"]
            found_errors = [pattern for pattern in error_patterns if pattern in content]

            # Filter out false positives (e.g., "error handling" is OK)
            suspicious_errors = [e for e in found_errors if content.count(e) > 2]

            if not suspicious_errors:
                self.log_result(test_name, "SUCCESS", "No obvious errors detected")
                return True
            else:
                self.log_result(
                    test_name,
                    "WARNING",
                    f"Possible errors detected: {', '.join(suspicious_errors)}"
                )
                return False

        except Exception as e:
            self.log_result(test_name, "FAILED", f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("Monaco Payroll App - Simple HTTP Testing")
        print("Testing Validation and PDF Generation Pages")
        print("=" * 80)
        print()

        tests = [
            self.test_app_accessible,
            self.test_app_content,
            self.test_validation_page_references,
            self.test_pdf_generation_references,
            self.test_required_pages_structure,
            self.test_app_health,
            self.test_streamlit_specific_elements,
            self.test_javascript_errors,
        ]

        for test in tests:
            test()
            time.sleep(0.5)

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
        total = len(self.results)

        print(f"\nTotal Tests: {total}")
        print(f"✓ Passed: {success}")
        print(f"✗ Failed: {failed}")
        print(f"⚠ Warnings: {warning}")

        if success == total:
            print("\n🎉 All tests passed!")
        elif failed == 0:
            print("\n✅ All tests completed (some warnings)")
        else:
            print(f"\n⚠️ {failed} test(s) failed")

        print("=" * 80)

        # Return exit code
        return 0 if failed == 0 else 1


if __name__ == "__main__":
    import socket

    def check_port(host="localhost", port=8501):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0

    if not check_port():
        print("ERROR: Streamlit app not running on port 8501")
        print("Please start: uv run streamlit run app.py")
        exit(1)

    tester = SimpleAppTester()
    exit_code = tester.run_all_tests()
    exit(exit_code)
