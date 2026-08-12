# Technology Stack

**Analysis Date:** 2026-01-19

## Languages

**Primary:**
- Python 3.11 - Backend API, bot logic, services (`.python-version`)
- JavaScript (ES6+) - React dashboard frontend

**Secondary:**
- JSON - Configuration files, data storage
- CSS/TailwindCSS - Dashboard styling

## Runtime

**Environment:**
- Python 3.11 (specified in `.python-version`)
- Node.js - For React dashboard (Create React App)

**Package Manager:**
- pip - Python dependencies (`requirements.txt`)
- npm - JavaScript dependencies (`dashboard/package.json`)
- Lockfile: `dashboard/package-lock.json` present

## Frameworks

**Core:**
- FastAPI 0.104.1 - Python web framework for API (`requirements.txt`)
- React 18.2.0 - Dashboard UI (`dashboard/package.json`)
- React Router DOM 6.8.0 - Client-side routing

**Testing:**
- Jest (via react-scripts) - Dashboard unit tests
- @testing-library/react 13.4.0 - React component testing
- Manual Python test scripts - Backend integration tests

**Build/Dev:**
- Uvicorn 0.24.0 - ASGI server for FastAPI
- react-scripts 5.0.1 - Create React App build tooling
- TailwindCSS 3.3.0 - Utility-first CSS framework
- PostCSS 8.4.31 - CSS processing
- Autoprefixer 10.4.16 - CSS vendor prefixes

## Key Dependencies

**Critical:**
- openai 1.3.0 - AI chat responses (`requirements.txt`)
- firebase-admin 6.1.0 - Firestore database access
- httpx 0.25.1 - Async HTTP client for WhatsApp APIs
- pydub 0.25.1 - Audio processing for voice messages

**Infrastructure:**
- google-cloud-firestore 2.11.1 - Firestore client
- python-dotenv 1.0.0 - Environment variable loading
- apscheduler 3.10.4 - Task scheduling

**Dashboard:**
- axios 1.6.0 - HTTP client for API calls
- recharts 2.8.0 - Analytics charts
- framer-motion 10.16.0 - Animations
- react-hot-toast 2.4.1 - Toast notifications
- @heroicons/react 2.0.18 - Icon library
- date-fns 2.30.0 - Date formatting

## Configuration

**Environment:**
- `.env` files for secrets (`.env`, `.env.example`)
- Key configs: `OPENAI_API_KEY`, `MONTYMOBILE_*`, `FIRESTORE_SERVICE_ACCOUNT_KEY_PATH`
- Dashboard proxy configured to backend port 8003

**Build:**
- `dashboard/package.json` - React build scripts
- TailwindCSS configured via PostCSS
- ESLint via react-app preset

**Data Files:**
- `data/knowledge_base.txt` - Bot knowledge
- `data/style_guide.txt` - Response style
- `data/price_list.txt` - Pricing info
- `data/qa_database.json` - Q&A pairs

## Platform Requirements

**Development:**
- macOS/Linux/Windows (any platform with Python 3.11 and Node.js)
- FFMPEG required for voice message processing (path in `FFMPEG_PATH`)
- Firebase service account JSON file required

**Production:**
- Backend: uvicorn or gunicorn (included in requirements)
- Dashboard: Static build served from backend or separate hosting
- Port 8003 default for backend API
- prometheus-client 0.19.0 available for monitoring

---

*Stack analysis: 2026-01-19*
*Update after major dependency changes*
