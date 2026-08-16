"""AI-powered cost analysis of scanned AWS resources via the OpenAI API."""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

MODEL = "gpt-4o"

SYSTEM_PROMPT = """You are a cloud cost optimization expert analyzing a list of AWS \
resources (with type, name, region, resource id, and tags) pulled from a single \
AWS Resource Group.

Look for:
- Over-provisioned resources (e.g. oversized EC2 instances, RDS instances, EBS volumes)
- Unused or idle resources (e.g. unattached EBS volumes, unassociated Elastic IPs, \
idle load balancers, stopped-but-not-terminated instances)
- Misconfigurations (e.g. no lifecycle policy on S3 buckets, missing auto-scaling, \
gp2 volumes that should be gp3)
- Wrong pricing tiers / missing reserved instances or savings plans
- Any other cost optimization opportunity visible from the resource metadata and tags

Respond with ONLY a JSON object (no markdown, no commentary) matching this exact schema:
{
  "summary": "<2-4 sentence overview of the findings>",
  "issues": [
    {
      "resource_name": "<name>",
      "resource_id": "<resource id>",
      "resource_type": "<type>",
      "issue_type": "over-provisioned" | "unused" | "misconfigured" | "other",
      "issue": "<description of the problem>",
      "severity": "high" | "medium" | "low",
      "estimated_monthly_savings_usd": <number>,
      "fix_command": "<an AWS CLI command the user can run to fix or investigate this>"
    }
  ],
  "total_estimated_monthly_savings_usd": <number>
}

If a dollar estimate can't be determined precisely, give a reasonable best-effort estimate \
rather than omitting the field. If no issues are found, return an empty "issues" array."""


class AIAnalyzerError(Exception):
    """Base class for AI analyzer errors."""


class OpenAIKeyMissingError(AIAnalyzerError):
    def __init__(self) -> None:
        super().__init__(
            "OPENAI_API_KEY is not set. Add it to backend/.env (see .env.example)."
        )


class OpenAIRequestError(AIAnalyzerError):
    """Raised when the OpenAI API call fails or returns an unusable response."""


def _build_user_prompt(resources: List[Dict[str, Any]]) -> str:
    return (
        "Analyze the following AWS resources for cost issues:\n\n"
        f"{json.dumps(resources, indent=2)}\n\n"
        "Return the JSON object described in the system prompt. Reference each "
        "issue's resource_name/resource_id from the data above."
    )


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise OpenAIKeyMissingError()
    return OpenAI(api_key=api_key)


def analyze_resources(resources: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Send scanned resources to OpenAI and return a structured cost analysis."""
    if not resources:
        return {
            "summary": "No resources found in this resource group.",
            "issues": [],
            "total_estimated_monthly_savings_usd": 0,
        }

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_prompt(resources)},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    except AuthenticationError as exc:
        raise OpenAIKeyMissingError() from exc
    except RateLimitError as exc:
        raise OpenAIRequestError(
            "OpenAI rate limit or quota exceeded. Try again shortly."
        ) from exc
    except APIConnectionError as exc:
        raise OpenAIRequestError("Could not reach the OpenAI API.") from exc
    except APIStatusError as exc:
        raise OpenAIRequestError(f"OpenAI API error: {exc.message}") from exc
    except OpenAIError as exc:
        raise OpenAIRequestError(str(exc)) from exc

    content = response.choices[0].message.content
    try:
        analysis = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        raise OpenAIRequestError("Could not parse the AI response as JSON.") from exc

    analysis.setdefault("summary", "")
    analysis.setdefault("issues", [])
    analysis.setdefault("total_estimated_monthly_savings_usd", 0)
    return analysis
