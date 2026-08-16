"""AWS resource scanning via the AWS CLI.

Shells out to `aws` (resource-groups + resourcegroupstaggingapi) instead of
using boto3 so the backend only depends on the CLI being installed and
configured on the host, matching the Azure CLI approach used elsewhere in
this project.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional

AWS_ARN_LIST_BATCH_SIZE = 100  # resourcegroupstaggingapi limit per call


class AWSScannerError(Exception):
    """Base class for all AWS scanner errors."""


class AWSCLINotInstalledError(AWSScannerError):
    def __init__(self) -> None:
        super().__init__(
            "AWS CLI not found. Install it from "
            "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        )


class AWSNotConfiguredError(AWSScannerError):
    def __init__(self) -> None:
        super().__init__(
            "AWS CLI is not configured. Run `aws configure` (or set "
            "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY) and try again."
        )


class AWSCredentialsExpiredError(AWSScannerError):
    def __init__(self) -> None:
        super().__init__(
            "AWS credentials are expired or invalid. Refresh your credentials "
            "(e.g. `aws sso login`) and try again."
        )


class InvalidResourceGroupError(AWSScannerError):
    def __init__(self, group_name: str) -> None:
        super().__init__(f"Resource group '{group_name}' was not found.")


class AWSCLICommandError(AWSScannerError):
    """Fallback for AWS CLI failures that don't match a known category."""


def _run_aws_cli(args: List[str]) -> Any:
    """Run an AWS CLI command and return its parsed JSON output.

    Raises a specific AWSScannerError subclass for known failure modes.
    """
    if shutil.which("aws") is None:
        raise AWSCLINotInstalledError()

    try:
        result = subprocess.run(
            ["aws", *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise AWSCLINotInstalledError() from exc
    except subprocess.TimeoutExpired as exc:
        raise AWSCLICommandError("AWS CLI command timed out.") from exc

    if result.returncode != 0:
        _raise_for_stderr(result.stderr, args)

    stdout = result.stdout.strip()
    if not stdout:
        return {}

    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AWSCLICommandError(f"Could not parse AWS CLI output: {exc}") from exc


def _raise_for_stderr(stderr: str, args: List[str]) -> None:
    lower = stderr.lower()

    if "unable to locate credentials" in lower or "could not be found" in lower and "profile" in lower:
        raise AWSNotConfiguredError()

    if any(
        marker in lower
        for marker in (
            "expiredtoken",
            "requestexpired",
            "invalidclienttokenid",
            "the security token included in the request is invalid",
            "signaturedoesnotmatch",
        )
    ):
        raise AWSCredentialsExpiredError()

    if "notfoundexception" in lower or "resource group not found" in lower or "does not exist" in lower:
        group_name = _extract_group_name(args)
        raise InvalidResourceGroupError(group_name or "unknown")

    raise AWSCLICommandError(stderr.strip() or "AWS CLI command failed.")


def _extract_group_name(args: List[str]) -> Optional[str]:
    for flag in ("--group-name", "--group"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1]
    return None


def list_resource_groups() -> List[Dict[str, Any]]:
    """Return all AWS Resource Groups as [{name, arn, description}, ...]."""
    data = _run_aws_cli(["resource-groups", "list-groups", "--output", "json"])
    groups = data.get("Groups") or data.get("GroupIdentifiers") or []

    return [
        {
            "name": group.get("Name") or group.get("GroupName"),
            "arn": group.get("GroupArn") or group.get("Arn"),
            "description": group.get("Description"),
        }
        for group in groups
    ]


def _list_group_resource_arns(group_name: str) -> List[str]:
    data = _run_aws_cli(
        [
            "resource-groups",
            "list-group-resources",
            "--group-name",
            group_name,
            "--output",
            "json",
        ]
    )
    resource_identities = data.get("ResourceIdentifiers") or []
    return [
        identity["ResourceArn"]
        for identity in resource_identities
        if identity.get("ResourceArn")
    ]


def _get_tags_for_arns(arns: List[str]) -> Dict[str, Dict[str, str]]:
    """Fetch tags for a list of ARNs via resourcegroupstaggingapi, batched."""
    tags_by_arn: Dict[str, Dict[str, str]] = {}

    for i in range(0, len(arns), AWS_ARN_LIST_BATCH_SIZE):
        batch = arns[i : i + AWS_ARN_LIST_BATCH_SIZE]
        data = _run_aws_cli(
            [
                "resourcegroupstaggingapi",
                "get-resources",
                "--resource-arn-list",
                *batch,
                "--output",
                "json",
            ]
        )
        for mapping in data.get("ResourceTagMappingList") or []:
            arn = mapping.get("ResourceARN")
            if not arn:
                continue
            tags_by_arn[arn] = {
                tag["Key"]: tag.get("Value", "") for tag in mapping.get("Tags") or []
            }

    return tags_by_arn


def _parse_arn(arn: str) -> Dict[str, Optional[str]]:
    """Parse an ARN into its components.

    Format: arn:partition:service:region:account-id:resource
    where `resource` may be `type/id`, `type:id`, or just `id`.
    """
    parts = arn.split(":", 5)
    if len(parts) < 6:
        return {
            "resource_type": "unknown",
            "name": arn,
            "resource_id": arn,
            "region": None,
        }

    _, _, service, region, _account_id, resource = parts

    resource_type = service
    resource_id = resource

    if "/" in resource:
        resource_type, resource_id = resource.split("/", 1)
    elif ":" in resource:
        resource_type, resource_id = resource.split(":", 1)

    name = resource_id.rsplit("/", 1)[-1]

    return {
        "resource_type": resource_type or service,
        "name": name,
        "resource_id": resource_id,
        "region": region or None,
    }


def get_resources_in_group(group_name: str) -> List[Dict[str, Any]]:
    """Fetch all resources in a resource group, with type/name/region/tags."""
    arns = _list_group_resource_arns(group_name)
    if not arns:
        return []

    tags_by_arn = _get_tags_for_arns(arns)

    resources = []
    for arn in arns:
        parsed = _parse_arn(arn)
        resources.append(
            {
                "arn": arn,
                "resource_type": parsed["resource_type"],
                "name": parsed["name"],
                "resource_id": parsed["resource_id"],
                "region": parsed["region"],
                "tags": tags_by_arn.get(arn, {}),
            }
        )

    return resources
