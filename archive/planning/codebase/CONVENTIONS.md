# Coding Conventions

**Analysis Date:** 2026-01-19

## Naming Patterns

**Files:**
- snake_case.py for all Python files (e.g., `chat_response_service.py`)
- PascalCase.js for React components (e.g., `LiveChat.js`)
- lowercase.json/jsonl for data files
- *_api.py for API modules, *_service.py for services, *_handlers.py for handlers

**Functions:**
- snake_case for Python functions (e.g., `handle_message`, `generate_response`)
- camelCase for JavaScript functions (e.g., `fetchBotStatus`, `handleClick`)
- Async functions: `async def` in Python, `async function` or arrow functions in JS

**Variables:**
- snake_case for Python variables
- camelCase for JavaScript variables
- UPPER_SNAKE_CASE for constants (e.g., `MAX_CONTEXT_MESSAGES`, `OPENAI_API_KEY`)

**Types:**
- PascalCase for React components (e.g., `Dashboard`, `ProtectedRoute`)
- Pydantic models in PascalCase (e.g., `MessageModel`)

## Code Style

**Formatting (Python):**
- No explicit formatter config detected
- 4-space indentation (Python default)
- Single quotes and double quotes mixed (prefer double for strings)
- UTF-8 encoding header: `# -*- coding: utf-8 -*-`

**Formatting (JavaScript):**
- No Prettier config detected
- 2-space indentation (React standard)
- Single quotes for strings
- Semicolons required

**Linting:**
- ESLint via react-app preset (dashboard)
- No Python linter config detected (consider adding pylint/flake8)

## Import Organization

**Python Order:**
1. Standard library imports (`os`, `json`, `datetime`)
2. Third-party imports (`fastapi`, `httpx`, `openai`)
3. Local imports (`from config import`, `from handlers import`)
4. Type imports last (if using typing)

**JavaScript Order:**
1. React and core libraries (`react`, `react-router-dom`)
2. Third-party libraries (`axios`, `framer-motion`)
3. Local components (`./components/`, `./pages/`)
4. Hooks and contexts (`./hooks/`, `./contexts/`)
5. Utilities and constants (`./utils/`)

**Grouping:**
- Blank line between groups
- No strict alphabetical sorting observed

## Error Handling

**Python Patterns:**
- Try/except at handler level
- Log errors with print statements
- Return graceful responses to avoid webhook retries

```python
try:
    result = await some_operation()
except Exception as e:
    print(f"Error: {e}")
    return {"status": "error", "message": str(e)}
```

**JavaScript Patterns:**
- Try/catch for async operations
- Toast notifications for user-facing errors
- Silent handling for non-critical errors (e.g., initial API fetch)

```javascript
try {
  await apiCall();
} catch (error) {
  toast.error('Something went wrong');
}
```

## Logging

**Framework:**
- Python: print statements (no structured logging library)
- JavaScript: console.log (development only)

**Patterns:**
- Emoji prefixes for status: ✅ success, ❌ error, ℹ️ info, 🤖 bot
- Arabic comments in some files (multilingual codebase)
- Log at service boundaries and on errors

**Example:**
```python
print("✅ تم تحميل قائمة الأسعار من data/price_list.txt")
print(f"❌ خطأ في تحميل data/price_list.txt: {e}")
```

## Comments

**When to Comment:**
- Explain complex business logic
- Document API endpoints and parameters
- Note deprecated code or temporary workarounds
- Arabic and English comments both used

**Docstrings:**
- Triple-quoted docstrings for modules and key functions
- Brief description of purpose

```python
"""
Main entry point for Lina's Laser AI Bot
Loads all modular components and starts the FastAPI server.
"""
```

**TODO Comments:**
- Format: `TODO:` or `# TODO:`
- Found in third-party adapter templates
- No issue linking convention

## Function Design

**Size:**
- Large functions observed (chat_response_service.py is 62KB)
- Extract helpers for complex logic (not always followed)

**Parameters:**
- Python: positional and keyword arguments
- JavaScript: destructured props for React components
- Use default values for optional parameters

**Return Values:**
- Python: dictionaries for API responses, explicit None for failures
- JavaScript: Promises for async, objects for state

## Module Design

**Python Exports:**
- Import specific functions/classes (not `from module import *`)
- `__init__.py` for package initialization

**JavaScript Exports:**
- Default export for React components
- Named exports for utilities and hooks
- Index files for barrel exports (contexts)

**React Patterns:**
- Functional components with hooks
- Context for global state (Auth, Permissions)
- Custom hooks for API calls (`useApi`)

## API Design

**Endpoints:**
- RESTful patterns: GET for reads, POST for actions
- Path parameters for resources: `/api/qa/{id}`
- Query parameters for filtering

**Response Format:**
```python
{
    "status": "success" | "error",
    "data": {...},
    "message": "Optional message"
}
```

**Dashboard API calls:**
- Axios for HTTP requests
- Base URL configured via proxy (development)
- Error handling with try/catch and toast

---

*Convention analysis: 2026-01-19*
*Update when patterns change*
