# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Application Evaluator - A system for collecting AI program applications from Confluence, automatically evaluating them using LLM, and enabling web-based review by evaluators. Built for a global semiconductor company's internal AI adoption program.

**Korean codebase**: Comments, prompts, and UI text are in Korean. Database schema and code use English.

## Development Commands

### Initial Setup (Required on first clone)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment (edit with actual values)
cp .env.example .env

# Initialize database (CRITICAL - run once after clone)
python init_db.py
```

**Note**: `init_db.py` creates `data/app.db`, initializes schema, creates default admin account (username: `admin`, password: `admin123!`), and optionally generates test data.

### Running the Application

```bash
# Development server with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Access at: http://localhost:8000

### Testing

```bash
# Test rate limiter
python test_rate_limiter.py

# Database reset (WARNING: deletes all data)
rm data/app.db
python init_db.py
```

## Architecture Overview

### Core Data Flow

1. **Data Ingestion**: `ConfluenceParser` fetches application pages from Confluence, parses HTML tables into structured data
2. **AI Classification**: `AIClassifier` categorizes applications into AI technology types (LLM, RAG, ML, DL, AI Agent, etc.) via keyword matching
3. **AI Evaluation**: `LLMEvaluator` sends structured prompts to LLM API to grade applications (S/A/B/C/D) across 8 criteria
4. **User Review**: Evaluators view and grade applications through web interface, filtered by department permissions
5. **Export**: Results exported to CSV for downstream analysis

### Critical Architectural Patterns

**Rate Limiting**: Both `ConfluenceParser` and `LLMEvaluator` use `RateLimiter` with sliding window algorithm to prevent API throttling. Confluence: 10 calls/min, LLM: 20 calls/min.

**Permission System**:
- Admin: Access all applications, can sync Confluence, manage users/departments
- Reviewer: Access only their department's applications, can evaluate
- Implemented via `get_current_user` dependency and role checks in routers

**Evaluation History**: `EvaluationHistory` tracks all AI and user evaluations separately. Applications store current evaluation state in denormalized fields (`ai_grade`, `user_grade`) for query performance.

**HTML Parsing Strategy**: Confluence HTML uses complex table structures. Parser looks for header cells (e.g., "과제명", "Pain point") then extracts content from adjacent/next-row cells. See `confluence_parser.py:parse_application_page()`.

### Database Design

**SQLite with SQLAlchemy ORM**. Key relationships:

- `Application` -> `Department` (many-to-one): Applications belong to business departments
- `Application` -> `User` (evaluator, many-to-one): Tracks who performed user evaluation
- `Application` -> `EvaluationHistory` (one-to-many): Audit trail of all evaluations
- `User` -> `Department` (many-to-one): Users assigned to departments for permission filtering

**JSON Fields**: `Application` stores flexible data in JSON columns:
- `pre_survey`: Survey responses as key-value pairs
- `tech_capabilities`: Array of participant skills with proficiency levels
- `ai_categories`: Ordered list of classified AI technology categories
- `ai_evaluation_detail`: Per-criterion LLM evaluation results with grades and reasoning

### LLM Integration

Uses LangChain with OpenAI-compatible API. Custom headers required:
- `x-dep-ticket`: Credential key
- `Send-System-Name`: System identifier
- `User-ID`: User identifier
- `Prompt-Msg-Id` / `Completion-Msg-Id`: UUIDs for tracing

Prompt engineering approach:
1. System prompt establishes role (AI expert at semiconductor company) and principles (no hallucination, fact-based analysis)
2. Includes department context for business-aware evaluation
3. Structures application data in clear markdown sections
4. Defines each evaluation criterion with detailed guide
5. Requests JSON response with specific schema for parsing

Temperature set to 0.1 for consistency across evaluations.

### Frontend Architecture

**Jinja2 templates** with vanilla JavaScript (no framework). Templates inherit from `base.html` which includes:
- Bootstrap CSS for layout
- JWT token management in localStorage
- Navigation with role-based menu items
- Logout functionality

Key templates:
- `login.html`: Authentication entry point
- `dashboard.html`: Statistics summary with charts
- `applications/list.html`: Filterable application table
- `applications/detail.html`: Single application view with evaluation form
- `admin/*.html`: Administrative CRUD interfaces

## Working with This Codebase

### Adding New Evaluation Criteria

1. Add criterion to `EvaluationCriteria` table via admin UI or init script
2. Update LLM prompt template in `llm_evaluator.py:build_evaluation_prompt()` to include new criterion
3. Update grading logic in `llm_evaluator.py:evaluate_application()` to parse new criterion from LLM response
4. Update UI in `applications/detail.html` to display new criterion

### Modifying Confluence Parser

HTML structure varies by Confluence version. If parsing fails:
1. Check `parse_error_log` field in `Application` table for specific errors
2. Add debug logging to `confluence_parser.py:parse_application_page()`
3. Test parser with `parse_application_page(html_content)` directly
4. Common issues: header cell text mismatch, table nesting changes, encoding problems

### Extending Permission System

Current roles: `admin`, `reviewer`. To add new role:
1. Add role to `User.role` enum validation
2. Create permission dependency (e.g., `get_current_manager`) in `auth.py`
3. Apply dependency to protected routes in routers
4. Update frontend templates to show/hide UI elements based on role

### Performance Considerations

- Confluence sync is slow (rate-limited to 10 calls/min). Budget ~6 seconds per application page.
- LLM evaluation is expensive. Batch processing preferred. UI shows progress.
- SQLite adequate for <10k applications. Consider PostgreSQL migration if scaling beyond.
- No caching layer currently. LLM re-evaluation re-scores from scratch.

## Configuration

**Environment Variables** (`.env`):

Critical settings:
- `CONFLUENCE_*`: API credentials and parent page ID to sync from
- `LLM_API_*`: LLM endpoint, API keys, model name
- `SECRET_KEY`: JWT signing key (must be 32+ characters)
- `DATABASE_URL`: SQLite path or PostgreSQL connection string

Debug mode: Set `DEBUG=True` for SQLAlchemy SQL logging and auto-reload.

## Common Issues

**"Database not found"**: Run `python init_db.py` to create `data/app.db`.

**LLM returns malformed JSON**: Check prompt schema matches parsing logic. Add retry with tenacity decorator if intermittent.

**Confluence 429 errors**: Rate limiter handles this with exponential backoff. If persistent, reduce `max_calls` in `ConfluenceParser.__init__`.

**Permission denied errors**: Verify user's `department_id` matches application's `department_id`. Admins bypass department filter.

**Parsing errors**: Confluence HTML inconsistencies. Check `Application.parse_error_log` for details. May need to update header cell text matching in parser.
