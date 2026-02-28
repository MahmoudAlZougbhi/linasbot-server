# Testing Patterns

**Analysis Date:** 2026-01-19

## Test Framework

**Backend (Python):**
- No formal test framework configured
- Manual test scripts in project root
- Test endpoints via `routes/testing_routes.py`

**Dashboard (JavaScript):**
- Jest via react-scripts
- @testing-library/react 13.4.0
- @testing-library/jest-dom 5.17.0
- @testing-library/user-event 13.5.0

**Run Commands:**
```bash
# Dashboard tests
cd dashboard && npm test                # Run Jest tests
cd dashboard && npm test -- --coverage  # With coverage

# Backend manual tests
python test_montymobile.py              # MontyMobile API test
python test_live_chat_simple.py         # Live chat test
python test_appointment_api.py          # Appointment API test
```

## Test File Organization

**Backend:**
- Location: Manual test scripts in project root
- No `tests/` directory with automated tests
- Pattern: `test_*.py` scripts for manual execution

**Dashboard:**
- Location: Test files would be alongside source (not detected)
- Pattern: `*.test.js` or `*.spec.js` (Create React App convention)
- Currently: No custom test files detected in `dashboard/src/`

**Structure:**
```
linaslaserbot-2.7.22/
├── test_montymobile.py        # Manual: MontyMobile API testing
├── test_live_chat_simple.py   # Manual: Live chat flow testing
├── test_appointment_api.py    # Manual: Appointment scheduling test
├── test_live_conversation.py  # Manual: Full conversation test
├── routes/testing_routes.py   # API: Test endpoints
├── dashboard/src/pages/Testing.js  # UI: Interactive test dashboard
└── tests/                     # Empty/minimal directory
```

## Test Structure

**Backend Test Scripts:**
```python
# Pattern observed in test files:
import httpx
import asyncio

async def test_something():
    """Test description"""
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        print(f"Response: {response.status_code}")
        print(response.json())

if __name__ == "__main__":
    asyncio.run(test_something())
```

**Dashboard Test Pattern (Jest):**
```javascript
// Standard Create React App pattern (not implemented):
import { render, screen } from '@testing-library/react';
import Component from './Component';

describe('Component', () => {
  it('renders correctly', () => {
    render(<Component />);
    expect(screen.getByText('Expected text')).toBeInTheDocument();
  });
});
```

## Testing UI (Dashboard)

**Interactive Testing Page:**
- Location: `dashboard/src/pages/Testing.js` (71KB)
- Purpose: Interactive API testing from dashboard
- Features:
  - Send test messages to WhatsApp
  - Test bot responses
  - View conversation logs
  - Test different message types

**API Test Endpoints:**
- Location: `routes/testing_routes.py` (16KB)
- Purpose: Backend endpoints for testing features
- Endpoints: Various test and debug routes

## Mocking

**Not extensively used:**
- No mock factories or fixtures detected
- Test scripts make real API calls
- Dashboard testing uses actual backend

**Recommendations for future:**
```python
# Python: Use unittest.mock or pytest-mock
from unittest.mock import patch, MagicMock

# JavaScript: Use Jest mocks
jest.mock('./api', () => ({
  fetchData: jest.fn()
}));
```

## Fixtures and Factories

**Test Data:**
- Manual test data in test scripts
- No shared fixtures directory
- Example data inline in test files

**Example from test_montymobile.py:**
```python
TEST_PHONE = "96170XXXXXX"
TEST_MESSAGE = "Hello, this is a test message"
```

## Coverage

**Requirements:**
- No coverage targets set
- No CI integration
- Coverage available via Jest for dashboard

**Configuration:**
- Dashboard: Built-in via react-scripts
- Backend: Not configured (would need pytest-cov)

**View Coverage:**
```bash
cd dashboard && npm test -- --coverage
```

## Test Types

**Manual Integration Tests:**
- API endpoint tests (test_*.py scripts)
- Full conversation flow tests
- WhatsApp provider tests

**Interactive UI Tests:**
- Dashboard Testing page
- Manual verification via bot conversations

**Unit Tests:**
- Not implemented for backend
- Not implemented for dashboard (beyond CRA defaults)

**E2E Tests:**
- Not implemented
- Could use Playwright/Cypress for dashboard

## Common Patterns

**Async Testing (Python):**
```python
import asyncio

async def test_async_function():
    result = await some_async_call()
    assert result is not None

if __name__ == "__main__":
    asyncio.run(test_async_function())
```

**API Testing:**
```python
async with httpx.AsyncClient() as client:
    response = await client.post(
        "http://localhost:8003/api/endpoint",
        json={"key": "value"}
    )
    assert response.status_code == 200
```

**WhatsApp Provider Testing:**
```python
# From test_montymobile.py
async def test_send_message():
    adapter = WhatsAppFactory.get_adapter("montymobile")
    result = await adapter.send_text_message(phone, message)
    print(f"Send result: {result}")
```

## Test Gaps

**Critical Missing Tests:**
- Unit tests for `chat_response_service.py`
- Unit tests for handlers
- Integration tests for webhook flow
- Dashboard component tests

**Recommended Testing Strategy:**
1. Add pytest for Python unit tests
2. Add mocking for external services
3. Implement dashboard component tests
4. Add CI pipeline with test execution

---

*Testing analysis: 2026-01-19*
*Update when test patterns change*
