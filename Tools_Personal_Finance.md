# Plugin Tool: `personal_finance`

## Functional Requirements

### Credit Cards

Store and manage credit card accounts with the following fields:

- **Card name / issuer** — e.g. "Chase Sapphire", "Amex Gold"
- **Credit limit** — maximum balance allowed (currency)
- **APR** — annual percentage rate for interest calculations
- **Minimum payment** — required minimum payment each billing cycle
- **Statement cut date** — day of month the billing cycle closes
- **Payment due date** — day of month payment is due
- **Current balance / amount owed** — current outstanding amount (currency)

### Loans

Store and manage loan accounts with the following fields:

- **Name / reason** — label for the loan (e.g. "Car loan", "Personal loan for medical")
- **Original loan amount** — total amount borrowed (currency)
- **Current balance** — remaining amount owed (currency)
- **APR** — annual percentage rate
- **Monthly payment amount** — fixed payment per period (currency)
- **Payment due date** — day of month payment is due
- **Start date** — when the loan originated

### Income (Transactions)

Record income entries per month with:

- **Amount** — currency
- **Source label** — e.g. "Salary", "Freelance", "Rental", "Bonus"
- **Month / Year** — the period this income applies to
- **Recurring flag** — if `true`, the entry auto-projects into subsequent months until explicitly stopped

### Expenses (Transactions)

Record expense entries with:

- **Amount** — currency
- **Description** — short free-text label
- **Date** — specific date the expense occurred
- **Category** — one of the following fixed enum values:
  - `Housing` — rent, mortgage, HOA fees
  - `Food & Groceries` — supermarket, restaurants, delivery
  - `Transport` — gas, car payment, transit, rideshare
  - `Utilities` — electric, water, internet, phone
  - `Health` — medical, pharmacy, gym
  - `Entertainment` — streaming, events, hobbies
  - `Debt Payment` — credit card payments, loan payments
  - `Other` — anything that doesn't fit above

### Duplicate Detection

When adding a transaction (income or expense), check for potential duplicates based on: same `user_id` + same `amount` + same `date` + same `description` (case-insensitive).

- **Flag**: report the conflict to the user with both the existing and incoming entry
- **Suggest merge**: prompt the user to confirm which entry to keep or to proceed as a new entry
- Do **not** auto-delete — always require user confirmation

### Reports

All reports are scoped to the **current calendar month** by default.

- **Burn rate** — percentage of monthly income already spent on expenses
- **Daily budget** — remaining spendable income for the month divided by remaining days in the month

---

## Technical Requirements

### Database

Add a **PostgreSQL** service as a separate backing store (alongside existing Redis):

- All tables include a `user_id` column to scope rows per user
- `user_id` is passed explicitly as a tool argument by the LLM — no auth layer required
- Tables:
  - `credit_cards (id, user_id, name, credit_limit, apr, min_payment, cut_date, due_date, balance, created_at, updated_at)`
  - `loans (id, user_id, name, original_amount, balance, apr, monthly_payment, due_date, start_date, created_at, updated_at)`
  - `income (id, user_id, amount, source, month, year, recurring, created_at)`
  - `expenses (id, user_id, amount, description, date, category, created_at)`

### Docker Compose

Add a `postgres` service to `docker-compose.yml`:

- Use official `postgres:16` image
- Expose port `5432`
- Persist data via a named volume
- Pass connection string to the backend via env var `POSTGRES_URL`
- Run DB migrations on startup (Alembic or plain SQL init script)

### Plugin Structure

Implement as a `ToolPlugin` subclass under `tools/plugins/personal_finance/`:

- Separate sub-tools for each entity: `add_credit_card`, `add_loan`, `add_income`, `add_expense`, `get_report`, `list_conflicts`
- Register all sub-tools in `tools/plugins/__init__.py` via `ALL_PLUGINS`
- Use an async PostgreSQL client (e.g. `asyncpg` or `SQLAlchemy` async) injected via `KernelServices` or a dedicated service

### Dependencies

Add to `backend/3rdparty/requirements.txt`:

- `asyncpg` or `psycopg[binary]` (async PostgreSQL driver)
- `SQLAlchemy[asyncio]` (if using ORM)
- `alembic` (migrations)
