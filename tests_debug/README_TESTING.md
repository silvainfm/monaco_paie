# Testing Guide for Monaco Payroll App

## Quick Start

### Current Test Scripts

1. **test_webapp_simple.py** - HTTP-based testing (works without browser)
```bash
uv run streamlit run app.py &
uv run python test_webapp_simple.py
```

2. **test_webapp.py** - Full browser testing (requires Chrome/Chromium)
```bash
# First install browser
playwright install chromium
# Then run
uv run streamlit run app.py &
uv run python test_webapp.py
```

## Setting Up Full Testing Environment

### Install System Dependencies

```bash
# Ubuntu/Debian
apt-get update
apt-get install -y chromium-browser chromium-chromedriver

# Or for full Chrome
wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list
apt-get update
apt-get install -y google-chrome-stable
```

### Install Python Testing Packages

```bash
uv pip install pytest pytest-playwright selenium webdriver-manager beautifulsoup4 requests
```

### Install Browser for Playwright

```bash
uv run playwright install chromium
```

## Testing Approach

### 1. Unit Tests (Recommended)

Test individual components:

```python
# test_calculations.py
from services.payroll_calculations import CalculateurPaieMonaco

def test_calculate_net_salary():
    calc = CalculateurPaieMonaco()
    result = calc.calculate_net_salary(
        salaire_brut=3000,
        charges_salariales=450
    )
    assert result == 2550
```

Run:
```bash
uv run pytest tests/test_calculations.py
```

### 2. Integration Tests

Test services together:

```python
# test_payroll_system.py
from services.payroll_system import IntegratedPayrollSystem

def test_process_monthly_payroll(sample_data):
    system = IntegratedPayrollSystem()
    result = system.process_monthly_payroll(
        company_id=1,
        month=8,
        year=2025,
        data=sample_data
    )
    assert result.success
    assert len(result.employees) > 0
```

### 3. UI Tests with Streamlit Testing Framework

```python
# test_ui.py
from streamlit.testing.v1 import AppTest

def test_validation_page_loads():
    at = AppTest.from_file("app.py")
    at.run()

    # Navigate to validation page
    at.sidebar.radio[0].set_value("✅ Validation")
    at.run()

    # Check page loaded
    assert not at.exception
    assert "Validation" in at.main[0].value

def test_pdf_generation_requires_data():
    at = AppTest.from_file("app.py")
    at.run()

    # Go to PDF page without data
    at.sidebar.radio[0].set_value("📄 Génération PDF")
    at.run()

    # Should show warning
    assert any("donnée" in str(w) for w in at.warning)
```

Run:
```bash
uv run pytest tests/test_ui.py
```

### 4. Browser Automation Tests

For full end-to-end testing:

```python
# test_e2e.py
import pytest
from playwright.sync_api import Page, expect

@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()

def test_validation_page_workflow(browser, streamlit_server):
    page = browser.new_page()
    page.goto("http://localhost:8501")

    # Wait for Streamlit to load
    page.wait_for_selector("[data-testid='stApp']")

    # Select validation page
    page.click("text=Validation")

    # Check page loaded
    expect(page.locator("h1")).to_contain_text("Validation")

    # Select company
    page.click("text=Sélectionnez une entreprise")
    page.click("text=Test Company")

    # Verify employee list appears
    expect(page.locator("[data-testid='stDataFrame']")).to_be_visible()
```

## Test Data

### Create Test Fixtures

```python
# tests/conftest.py
import pytest
import polars as pl

@pytest.fixture
def sample_employee_data():
    return pl.DataFrame({
        'matricule': ['001', '002'],
        'nom': ['Dupont', 'Martin'],
        'prenom': ['Jean', 'Marie'],
        'salaire_base': [3000, 3500],
        'heures_payees': [151.67, 151.67]
    })

@pytest.fixture
def sample_company():
    return {
        'id': 1,
        'name': 'Test Company',
        'siret': '12345678901234'
    }
```

### Use Test Database

```python
# test_database.py
import duckdb
import pytest

@pytest.fixture
def test_db():
    # Create in-memory test database
    conn = duckdb.connect(':memory:')

    # Set up schema
    conn.execute("""
        CREATE TABLE payroll_data (
            company_id INTEGER,
            matricule VARCHAR,
            nom VARCHAR,
            salaire_brut DECIMAL
        )
    """)

    yield conn
    conn.close()
```

## CI/CD Integration

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh

    - name: Install dependencies
      run: uv sync

    - name: Install browsers
      run: uv run playwright install chromium

    - name: Run unit tests
      run: uv run pytest tests/unit/

    - name: Start Streamlit
      run: uv run streamlit run app.py &

    - name: Wait for app
      run: |
        timeout 30 bash -c 'until curl -s http://localhost:8501; do sleep 1; done'

    - name: Run integration tests
      run: uv run pytest tests/integration/

    - name: Run UI tests
      run: uv run pytest tests/ui/

    - name: Upload screenshots
      if: failure()
      uses: actions/upload-artifact@v3
      with:
        name: test-screenshots
        path: test_results/screenshots/
```

## Test Organization

```
monaco_paie/
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # Shared fixtures
│   ├── unit/
│   │   ├── test_calculations.py
│   │   ├── test_validators.py
│   │   └── test_helpers.py
│   ├── integration/
│   │   ├── test_payroll_system.py
│   │   ├── test_pdf_generation.py
│   │   └── test_data_import.py
│   └── ui/
│       ├── test_validation_page.py
│       ├── test_pdf_page.py
│       └── test_navigation.py
├── test_webapp.py           # Browser automation
├── test_webapp_simple.py    # HTTP testing
└── pytest.ini
```

### pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
markers =
    unit: Unit tests
    integration: Integration tests
    ui: UI tests
    slow: Slow tests
```

## Running Tests

### All Tests
```bash
uv run pytest
```

### Specific Categories
```bash
uv run pytest -m unit           # Only unit tests
uv run pytest -m integration    # Only integration tests
uv run pytest -m ui             # Only UI tests
```

### With Coverage
```bash
uv run pytest --cov=services --cov-report=html
```

### Parallel Execution
```bash
uv pip install pytest-xdist
uv run pytest -n auto
```

## Best Practices

1. **Keep tests fast** - Unit tests < 100ms, integration < 1s
2. **Use fixtures** - Avoid duplication
3. **Mock external dependencies** - Database, APIs, files
4. **Test edge cases** - Empty data, invalid input, boundaries
5. **Clear assertions** - One concept per test
6. **Descriptive names** - `test_validation_rejects_invalid_period`
7. **Independent tests** - No shared state
8. **Clean up** - Use fixtures for setup/teardown

## Debugging Failed Tests

### Run single test with output
```bash
uv run pytest tests/test_validation.py::test_specific_case -s
```

### Drop into debugger on failure
```bash
uv run pytest --pdb
```

### Increase verbosity
```bash
uv run pytest -vv
```

### Show local variables
```bash
uv run pytest -l
```

## Troubleshooting

### "ModuleNotFoundError"
```bash
uv pip install -e .  # Install package in editable mode
```

### "Browser not found"
```bash
uv run playwright install chromium
```

### "Port already in use"
```bash
lsof -ti:8501 | xargs kill -9
```

### "Connection refused"
```bash
# Check Streamlit is running
curl http://localhost:8501/_stcore/health
```

## Resources

- [Playwright Docs](https://playwright.dev/python/)
- [Streamlit Testing](https://docs.streamlit.io/develop/api-reference/app-testing)
- [Pytest Docs](https://docs.pytest.org/)
- [Testing Best Practices](https://testdriven.io/)
