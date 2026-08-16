# Prompt 3: AWS RDS PostgreSQL + WebSocket Progress Tracking

Build on top of the existing FastAPI backend. Add AWS RDS (PostgreSQL) for storing users and analysis history, and FastAPI WebSocket for live progress updates.

## What to build

### Database (AWS RDS for PostgreSQL)

- Connect to an AWS RDS PostgreSQL instance (or Aurora PostgreSQL-Compatible) using `asyncpg` or `psycopg2`.
- Store the database connection string in `.env` (`DATABASE_URL`).
- Create two tables on startup:
  - `users` — id, email, password_hash, created_at
  - `analyses` — id, user_id, resource_group, resources_scanned (int), issues_found (int), estimated_savings (text), analysis_result (jsonb), status, created_at
- After AI analysis completes, store the full result in the `analyses` table.
- Add a `GET /api/history` endpoint that returns past analyses for the authenticated user.

### WebSocket Progress

- Add a WebSocket endpoint `ws://localhost:8000/ws/progress/{analysis_id}`.
- During the `POST /api/analyze` flow, push progress messages through the WebSocket at each stage:
  - `"Fetching resource groups..."`
  - `"Scanning resources in <rg>..."`
  - `"Analyzing costs with AI..."`
  - `"Storing results..."`
  - `"Analysis complete"`
- The frontend will connect to this WebSocket to show live progress.

### Update .env.example

Add `DATABASE_URL` to `.env.example`.

- If RDS is provisioned inside a VPC (the common case), note that the backend (or a bastion/tunnel) needs network access to the DB's security group — add a comment in `.env.example` reminding the developer to allow inbound access from their runtime environment (local dev, ECS/EC2, etc.) on port 5432.
- Optionally support IAM database authentication (`aws rds generate-db-auth-token`) as an alternative to a static password in `DATABASE_URL`, if the project wants to avoid storing DB credentials directly.

## Project structure update

```
backend/
├── main.py          (updated — history endpoint, WebSocket, DB init)
├── aws_scanner.py   (no change)
├── ai_analyzer.py   (no change)
├── db.py            (new — DB connection, table creation, queries)
├── requirements.txt (updated — add asyncpg/psycopg2, websockets)
├── .env.example     (updated — add DATABASE_URL)
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers steps ④ and ⑥ of the request flow.
