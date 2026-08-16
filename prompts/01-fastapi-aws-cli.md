# Prompt 1: FastAPI Backend + AWS CLI

Create a Python FastAPI backend in a `backend/` folder for the AI Cloud Cost Detective project.

## What to build

- A FastAPI server with a `POST /api/analyze` endpoint that accepts `{ "resource_group": "<name>" }`.
- A `GET /api/resource-groups` endpoint that returns the list of AWS Resource Groups.
- Use Python's `subprocess` module to run AWS CLI commands:
  - `aws resource-groups list-groups` to list all resource groups.
  - `aws resource-groups list-group-resources --group-name <name> --output json` to fetch all resources in the selected group.
  - `aws resourcegroupstaggingapi get-resources --resource-arn-list <arn>` (or equivalent) to pull tags for each resource.
- Parse the AWS CLI JSON output and return a structured response with resource type, name (parsed from ARN), region, resource identifier/ID, and tags.
- Add error handling for:
  - AWS CLI not installed
  - Not configured (no credentials / `aws configure` not run)
  - Expired or invalid credentials
  - Invalid resource group name
- Enable CORS for `http://localhost:5173`.
- Include a `requirements.txt` with `fastapi`, `uvicorn`.

## Project structure

```
backend/
├── main.py
├── aws_scanner.py
├── requirements.txt
```

Refer to `Architecture.MD` and `RequestFlow.MD`. This covers step ③ of the request flow.

## Notes / Open Decisions

1. **Resource Groups in AWS** are less universally used than in Azure — many AWS environments organize resources by tags, accounts, or VPCs instead. `aws_scanner.py` may need a fallback path using `aws resourcegroupstaggingapi get-resources --tag-filters Key=...` if resources aren't already organized into AWS Resource Groups.
2. **No direct SKU equivalent** — AWS resource list/describe calls don't expose a uniform SKU-like field the way Azure does. Getting instance-type-level detail (e.g., `t3.medium` for EC2) requires additional per-service `describe-*` calls (e.g., `aws ec2 describe-instances`). SKU is omitted from the structured response above; add back with per-service describe calls if needed.
