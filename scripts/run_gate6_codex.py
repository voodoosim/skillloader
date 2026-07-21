#!/usr/bin/env python3
"""Run the committed Gate 6 routing fixture against live Codex.

The runner compares two isolated Codex CLI configurations:

* eager: all fixture skill documents are included in developer instructions;
* skillloader: only the SkillLoader MCP server is configured, and Codex must
  search before loading zero, one, or two selected documents.

It records redacted Codex JSONL events, client-reported usage, offline cl100k_base
estimates for the catalog/tool payload layers, and deterministic routing scores.
The runner does not directly read or copy authentication files and does not
modify Codex configuration. Codex uses the existing login through its CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tiktoken


REPO = Path(__file__).resolve().parents[1]
TASKS_PATH = REPO / "bench" / "tasks" / "task-fixture-v1.json"
CATALOG_ROOT = REPO / "testdata" / "parity" / "home" / ".codex" / "skills"
REQUIREMENTS_PATH = REPO / "requirements-gate6.txt"
MODEL = "gpt-5.6-sol"
TOKEN_ENCODING = "cl100k_base"
MAX_SKILLS = 2
REQUIRED_USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
CHILD_ENV_ALLOWLIST = (
    "CODEX_HOME",
    "HOME",
    "LANG",
    "LC_ALL",
    "LOGNAME",
    "PATH",
    "SHELL",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TERM",
    "TMPDIR",
    "TZ",
    "USER",
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["selected_names", "no_load", "applied_instructions", "decision"],
    "properties": {
        "selected_names": {
            "type": "array",
            "maxItems": MAX_SKILLS,
            "items": {"type": "string"},
        },
        "no_load": {"type": "boolean"},
        "applied_instructions": {
            "type": "array",
            "maxItems": MAX_SKILLS,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "instruction"],
                "properties": {
                    "name": {"type": "string"},
                    "instruction": {"type": "string"},
                },
            },
        },
        "decision": {"type": "string"},
    },
}

COMMON_POLICY = """You are participating in a deterministic SkillLoader routing evaluation.
Use only the supplied synthetic catalog information. Treat the query as a routing request,
not as permission to perform the described work. Choose no skill when none is relevant.
Choose the narrowest applicable skill; choose a second skill only for a separate required
workflow or safety gate. Never select more than two skills. In applied_instructions, copy
the final instruction sentence from every selected skill document exactly. Return only the
JSON object required by the output schema."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--output-dir",
        type=Path,
        help="new directory in which to write redacted and summarized evidence",
    )
    destination.add_argument(
        "--rescore-dir",
        type=Path,
        help="recompute scores and summary from an existing evidence directory",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="run only the named task; repeat to select multiple tasks",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="timeout for each Codex invocation",
    )
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for value in values:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    temporary.replace(path)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_child_environment() -> dict[str, str]:
    environment = {
        key: os.environ[key] for key in CHILD_ENV_ALLOWLIST if key in os.environ
    }
    environment["NO_COLOR"] = "1"
    return environment


def redact_evidence_text(value: str) -> str:
    redacted = re.sub(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
        "<REDACTED_PRIVATE_KEY>",
        value,
        flags=re.DOTALL,
    )
    redacted = re.sub(
        r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b",
        "<REDACTED_TOKEN>",
        redacted,
    )
    redacted = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
        r"[A-Za-z0-9_-]{10,}\b",
        "<REDACTED_TOKEN>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(\b(?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+)"
        r"[A-Za-z0-9._~+/-]{12,}",
        r"\1<REDACTED_TOKEN>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|password)(\s*[:=]\s*)"
        r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[^\s,;}\]]+)",
        r"\1\2<REDACTED_SECRET>",
        redacted,
    )
    redacted = redacted.replace(str(REPO), "<REPO>")
    for variable, placeholder in (
        ("CODEX_HOME", "<CODEX_HOME>"),
        ("HOME", "<HOME>"),
        ("TMPDIR", "<TMPDIR>"),
    ):
        path = os.environ.get(variable)
        if path and path != "/":
            redacted = redacted.replace(path, placeholder)
    redacted = re.sub(
        r"/tmp/skillloader-gate6-[^/\"'\s]+",
        "<TEMP_WORKDIR>",
        redacted,
    )
    redacted = re.sub(
        r"\bfile:///(?:[^/\s\"'<>]+/)*[^/\s\"'<>]+",
        "file://<ABS_PATH>",
        redacted,
    )
    redacted = re.sub(
        r"(?<=:)/(?:[^/\s\"'<>]+/)*[^/\s\"'<>]+",
        "<ABS_PATH>",
        redacted,
    )
    return re.sub(
        r"(?<![:/\w<>])/(?:[^/\s\"'<>]+/)*[^/\s\"'<>]+",
        "<ABS_PATH>",
        redacted,
    )


def redact_evidence_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_evidence_text(value)
    if isinstance(value, list):
        return [redact_evidence_value(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_evidence_value(item) for key, item in value.items()}
    return value


def redact_argv(args: list[str]) -> list[str]:
    redacted: list[str] = []
    previous = ""
    for argument in args:
        value = redact_evidence_text(argument)
        if previous == "--output-schema":
            value = "<OUTPUT_SCHEMA>"
        elif previous == "-C":
            value = "<TEMP_WORKDIR>"
        elif value.startswith("mcp_servers.skillloader.command="):
            value = 'mcp_servers.skillloader.command="<TEMP_BINARY>"'
        elif value.startswith("mcp_servers.skillloader.env="):
            value = re.sub(
                r'SKILLLOADER_ROOTS="[^"]*"',
                'SKILLLOADER_ROOTS="<FIXTURE_CATALOG_ROOT>"',
                value,
            )
            value = re.sub(
                r'XDG_CACHE_HOME="[^"]*"',
                'XDG_CACHE_HOME="<TEMP_CACHE>"',
                value,
            )
        redacted.append(value)
        previous = argument
    return redacted


def command_output(*args: str, environment: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=REPO,
        env=environment or safe_child_environment(),
        check=True,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip() or completed.stderr.strip()


def prepare_isolated_codex_home(temp_dir: Path) -> tuple[Path, dict[str, str]]:
    source_home = Path(
        os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
    ).expanduser()
    source_auth = source_home / "auth.json"
    if not source_auth.is_file():
        raise SystemExit("Codex auth file is unavailable; refusing an unisolated run")
    client_home = temp_dir / "client-home"
    codex_home = client_home / ".codex"
    temp_home = client_home / "tmp"
    codex_home.mkdir(parents=True)
    temp_home.mkdir()
    (codex_home / "auth.json").symlink_to(source_auth)
    environment = safe_child_environment()
    environment["HOME"] = str(client_home)
    environment["CODEX_HOME"] = str(codex_home)
    environment["TMPDIR"] = str(temp_home)
    return codex_home, environment


def effective_prompt_metadata(
    developer_instructions: str,
    prompt: str,
    run_cwd: Path,
    environment: dict[str, str],
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "codex",
            "-c",
            "developer_instructions="
            + json.dumps(developer_instructions, ensure_ascii=False),
            "debug",
            "prompt-input",
            prompt,
        ],
        cwd=run_cwd,
        env=environment,
        check=True,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=True,
    )
    try:
        prompt_input = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SystemExit(
            "Codex prompt-input preflight returned invalid JSON"
        ) from error
    canonical = json.dumps(
        prompt_input, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if "# AGENTS.md instructions" in canonical:
        raise SystemExit(
            "Codex prompt contains AGENTS.md instructions; refusing benchmark"
        )
    return {
        "sha256": sha256_bytes(canonical.encode("utf-8")),
        "agent_instructions_present": False,
    }


def build_input_metadata() -> dict[str, Any]:
    pathspec = ("*.go", "go.mod", "go.sum")
    dirty = command_output(
        "git", "status", "--porcelain", "--untracked-files=all", "--", *pathspec
    )
    if dirty:
        raise SystemExit(
            "Go build inputs differ from HEAD; refusing to create product evidence"
        )
    listed = command_output("git", "ls-files", "--", *pathspec).splitlines()
    files = sorted(path for path in listed if path)
    if not files:
        raise SystemExit("no tracked Go build inputs found")
    combined = hashlib.sha256()
    for relative in files:
        combined.update(relative.encode("utf-8"))
        combined.update(b"\0")
        combined.update((REPO / relative).read_bytes())
        combined.update(b"\0")
    return {
        "git_clean": True,
        "files": files,
        "sha256": combined.hexdigest(),
    }


def temporary_build_environment(temp_dir: Path) -> dict[str, str]:
    go_temp = temp_dir / "go-tmp"
    go_temp.mkdir()
    environment = safe_child_environment()
    environment["GOCACHE"] = str(temp_dir / "go-build-cache")
    environment["GOTMPDIR"] = str(go_temp)
    return environment


def load_catalog(
    root: Path = CATALOG_ROOT,
) -> tuple[list[dict[str, str]], str, dict[str, str]]:
    skills: list[dict[str, str]] = []
    combined = hashlib.sha256()
    instructions: dict[str, str] = {}
    for path in sorted(root.glob("*/SKILL.md")):
        content = path.read_text(encoding="utf-8")
        name = path.parent.name
        skills.append({"name": name, "content": content})
        combined.update(name.encode("utf-8"))
        combined.update(b"\0")
        combined.update(content.encode("utf-8"))
        combined.update(b"\0")
        body_lines = [line.strip() for line in content.split("---", 2)[-1].splitlines()]
        sentences = [line for line in body_lines if line and not line.startswith("#")]
        if not sentences:
            raise SystemExit(f"fixture skill lacks an instruction: {path}")
        instructions[name] = sentences[-1]
    if not skills:
        raise SystemExit(f"no fixture skills found under {root}")
    return skills, combined.hexdigest(), instructions


def catalog_block(skills: list[dict[str, str]]) -> str:
    sections = []
    for skill in skills:
        sections.append(
            f'<skill logical_name="{skill["name"]}">\n{skill["content"]}</skill>'
        )
    return "<skill_catalog>\n" + "\n".join(sections) + "\n</skill_catalog>"


def eager_developer_instructions(catalog: str) -> str:
    return (
        f"{COMMON_POLICY}\n\n"
        "All available skill documents are included below. Do not call any tool. "
        "Select directly from these documents.\n\n"
        f"{catalog}"
    )


def skillloader_developer_instructions() -> str:
    return (
        f"{COMMON_POLICY}\n\n"
        "Call search_skills exactly once with the complete Query and limit 5. "
        "Use only its returned logical names. If no returned skill is relevant, do not "
        "call load_skill. Otherwise call load_skill exactly once for every selected skill "
        "and use the complete returned document. Do not call shell or any other tool."
    )


def task_prompt(query: str) -> str:
    return f"Query: {query}"


def list_mcp_tools(binary: Path, catalog_root: Path) -> list[dict[str, Any]]:
    environment = safe_child_environment()
    environment["SKILLLOADER_ROOTS"] = str(catalog_root)
    environment["XDG_CACHE_HOME"] = str(binary.parent / "cache")
    process = subprocess.Popen(
        [str(binary)],
        cwd=REPO,
        env=environment,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if process.stdin is None or process.stdout is None or process.stderr is None:
        raise SystemExit("failed to open SkillLoader stdio pipes")
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "gate6-evidence", "version": "1"},
        },
    }
    process.stdin.write(json.dumps(initialize) + "\n")
    process.stdin.flush()
    initialized = json.loads(process.stdout.readline())
    if initialized.get("id") != 1 or "result" not in initialized:
        raise SystemExit(f"SkillLoader initialize failed: {initialized}")
    process.stdin.write(
        json.dumps(
            {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        )
        + "\n"
    )
    process.stdin.write(
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    process.stdin.flush()
    listed = json.loads(process.stdout.readline())
    process.stdin.close()
    process.wait(timeout=30)
    if listed is None or "result" not in listed:
        stderr = process.stderr.read()
        raise SystemExit(f"SkillLoader tools/list response missing: {listed}; {stderr}")
    tools = listed["result"].get("tools", [])
    names = sorted(tool.get("name") for tool in tools)
    if names != ["load_skill", "search_skills"]:
        raise SystemExit(f"unexpected MCP tools: {names}")
    return tools


def parse_jsonl(stdout: str) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    other: list[str] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            other.append(line)
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            other.append(line)
    return events, other


def final_response(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        item = event.get("item", {})
        if event.get("type") != "item.completed" or item.get("type") != "agent_message":
            continue
        try:
            value = json.loads(item.get("text", ""))
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "selected_names" in value:
            return value
    return None


def completed_tool_calls(
    events: list[dict[str, Any]], tool: str
) -> list[dict[str, Any]]:
    calls = []
    for event in events:
        item = event.get("item", {})
        if (
            event.get("type") == "item.completed"
            and item.get("type") == "mcp_tool_call"
            and item.get("server") == "skillloader"
            and item.get("tool") == tool
        ):
            calls.append(item)
    return calls


def tool_call_events(
    events: list[dict[str, Any]], event_type: str, tool: str
) -> list[tuple[int, dict[str, Any]]]:
    calls: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(events):
        item = event.get("item", {})
        if (
            event.get("type") == event_type
            and item.get("type") == "mcp_tool_call"
            and item.get("server") == "skillloader"
            and item.get("tool") == tool
        ):
            calls.append((index, item))
    return calls


def usage_from(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "turn.completed" and isinstance(
            event.get("usage"), dict
        ):
            return dict(event["usage"])
    return {}


def canonical_tokens(encoding: Any, value: Any) -> int:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return len(encoding.encode(serialized))


def tool_payload_tokens(encoding: Any, calls: list[dict[str, Any]]) -> int:
    total = 0
    for call in calls:
        result = call.get("result")
        if result is not None:
            total += canonical_tokens(encoding, result)
    return total


def search_names(calls: list[dict[str, Any]]) -> list[str]:
    if not calls:
        return []
    result = calls[0].get("result") or {}
    structured = result.get("structured_content") or {}
    return [item.get("name", "") for item in structured.get("matches", [])]


def tool_call_error(call: dict[str, Any]) -> Any | None:
    if call.get("status") != "completed":
        return call.get("error") or {"code": "INCOMPLETE_TOOL_CALL"}
    if call.get("error") is not None:
        return call["error"]
    result = call.get("result") or {}
    structured = result.get("structured_content") or {}
    return structured.get("error")


def item_is_allowed(item: dict[str, Any], mode: str) -> bool:
    item_type = item.get("type")
    if item_type in (None, "agent_message", "reasoning"):
        return True
    return (
        mode == "skillloader"
        and item_type == "mcp_tool_call"
        and item.get("server") == "skillloader"
        and item.get("tool") in ("search_skills", "load_skill")
    )


def unexpected_action_events(
    events: list[dict[str, Any]], mode: str
) -> list[dict[str, Any]]:
    unexpected: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") not in ("item.started", "item.completed"):
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item_is_allowed(item, mode):
            continue
        unexpected.append(
            {
                "event_type": event.get("type"),
                "id": item.get("id"),
                "item_type": item.get("type"),
                "server": item.get("server"),
                "tool": item.get("tool"),
            }
        )
    return unexpected


def sanitize_events(events: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    sanitized = redact_evidence_value(events)
    for event in sanitized:
        if event.get("type") not in ("item.started", "item.completed"):
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item_is_allowed(item, mode):
            continue
        event["item"] = {
            key: item.get(key)
            for key in ("id", "type", "status", "server", "tool")
            if item.get(key) is not None
        }
        event["item"]["payload_redacted"] = True
    return sanitized


def instruction_score(
    response: dict[str, Any] | None,
    selected_names: list[str],
    instructions: dict[str, str],
) -> bool:
    if response is None:
        return False
    if len(selected_names) != len(set(selected_names)):
        return False
    if any(name not in instructions for name in selected_names):
        return False
    applied = response.get("applied_instructions")
    if not isinstance(applied, list):
        return False
    actual: dict[str, str] = {}
    for item in applied:
        if not isinstance(item, dict):
            return False
        name = item.get("name")
        instruction = item.get("instruction")
        if not isinstance(name, str) or not isinstance(instruction, str):
            return False
        if name in actual:
            return False
        actual[name] = instruction.strip()
    expected = {name: instructions.get(name, "").strip() for name in selected_names}
    return actual == expected


def response_matches_schema(response: dict[str, Any] | None) -> bool:
    if not isinstance(response, dict) or set(response) != set(
        OUTPUT_SCHEMA["required"]
    ):
        return False
    selected = response.get("selected_names")
    applied = response.get("applied_instructions")
    if (
        not isinstance(selected, list)
        or len(selected) > MAX_SKILLS
        or not all(isinstance(name, str) for name in selected)
        or not isinstance(response.get("no_load"), bool)
        or not isinstance(applied, list)
        or len(applied) > MAX_SKILLS
        or not isinstance(response.get("decision"), str)
    ):
        return False
    return all(
        isinstance(item, dict)
        and set(item) == {"name", "instruction"}
        and isinstance(item.get("name"), str)
        and isinstance(item.get("instruction"), str)
        for item in applied
    )


def load_result_is_valid(call: dict[str, Any], documents: dict[str, str]) -> bool:
    arguments = call.get("arguments")
    result = call.get("result")
    if not isinstance(arguments, dict) or not isinstance(result, dict):
        return False
    requested_name = arguments.get("name")
    structured = result.get("structured_content")
    if not isinstance(requested_name, str) or not isinstance(structured, dict):
        return False
    skill = structured.get("skill")
    expected_content = documents.get(requested_name)
    if not isinstance(skill, dict) or expected_content is None:
        return False
    return (
        skill.get("name") == requested_name
        and skill.get("content") == expected_content
        and skill.get("content_sha256")
        == sha256_bytes(expected_content.encode("utf-8"))
    )


def search_result_is_valid(call: dict[str, Any]) -> bool:
    arguments = call.get("arguments")
    result = call.get("result")
    if not isinstance(arguments, dict) or not isinstance(result, dict):
        return False
    query = arguments.get("query")
    limit = arguments.get("limit")
    structured = result.get("structured_content")
    if (
        not isinstance(query, str)
        or not isinstance(limit, int)
        or not isinstance(structured, dict)
        or structured.get("query") != query
        or structured.get("limit") != limit
        or not isinstance(structured.get("catalog_revision"), str)
    ):
        return False
    matches = structured.get("matches")
    if not isinstance(matches, list) or len(matches) > limit:
        return False
    names: list[str] = []
    for match in matches:
        if not isinstance(match, dict):
            return False
        name = match.get("name")
        tags = match.get("tags")
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(match.get("description"), str)
            or not isinstance(match.get("source"), str)
            or not isinstance(match.get("score"), int)
            or not (
                tags is None
                or isinstance(tags, list)
                and all(isinstance(tag, str) for tag in tags)
            )
        ):
            return False
        names.append(name)
    return len(names) == len(set(names))


def matching_call_ids(
    starts: list[tuple[int, dict[str, Any]]],
    completions: list[tuple[int, dict[str, Any]]],
) -> bool:
    started_ids = [item.get("id") for _, item in starts]
    completed_ids = [item.get("id") for _, item in completions]
    identities_match = (
        all(isinstance(item_id, str) and item_id for item_id in started_ids)
        and all(isinstance(item_id, str) and item_id for item_id in completed_ids)
        and len(started_ids) == len(set(started_ids))
        and len(completed_ids) == len(set(completed_ids))
        and set(started_ids) == set(completed_ids)
    )
    if not identities_match:
        return False
    started_at = {item["id"]: index for index, item in starts}
    completed_at = {item["id"]: index for index, item in completions}
    return all(started_at[item_id] < completed_at[item_id] for item_id in started_at)


def score_run(
    mode: str,
    task: dict[str, Any],
    events: list[dict[str, Any]],
    response: dict[str, Any] | None,
    instructions: dict[str, str],
    documents: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    searches = completed_tool_calls(events, "search_skills")
    loads = completed_tool_calls(events, "load_skill")
    reported = response.get("selected_names", []) if response else []
    reported_names = [name for name in reported if isinstance(name, str)]
    loaded_names = [call.get("arguments", {}).get("name", "") for call in loads]
    selected_names = reported_names
    reported_no_load = response.get("no_load") if response else None
    response_shape_ok = response_matches_schema(response) and reported_no_load == (
        not selected_names
    )

    required_names = task.get("required_names")
    allowed = set(task.get("alternatives", []))
    if isinstance(required_names, list):
        allowed.update(name for name in required_names if isinstance(name, str))
    if task.get("expected_top"):
        allowed.add(task["expected_top"])
    no_load_observed = not selected_names
    expected_top = task.get("expected_top")
    required_names_valid = (
        isinstance(required_names, list)
        and all(isinstance(name, str) for name in required_names)
        and len(required_names) == len(set(required_names)) == int(task["load_count"])
    )
    required_skill_set_correct = (
        required_names_valid
        and len(selected_names) == len(required_names)
        and set(selected_names) == set(required_names)
    )
    selection_top_one_correct = (
        no_load_observed
        if task.get("no_load")
        else bool(selected_names) and selected_names[0] == expected_top
    )
    incorrect_load = any(
        name not in allowed for name in set(selected_names + loaded_names)
    )
    counted_loads = selected_names if mode == "eager" else loaded_names
    load_count_correct = (
        len(counted_loads) == len(set(counted_loads)) == int(task["load_count"])
    )
    no_load_correct = response_shape_ok and no_load_observed == bool(task["no_load"])
    applied = instruction_score(response, selected_names, instructions)
    instructions_exact: bool | None = applied if selected_names else None
    load_results_valid = mode == "eager" or all(
        load_result_is_valid(call, documents) for call in loads
    )
    search_results_valid = mode == "eager" or all(
        search_result_is_valid(call) for call in searches
    )
    if instructions_exact is not None:
        instructions_exact = instructions_exact and load_results_valid

    unexpected_actions = unexpected_action_events(events, mode)
    tool_errors = [
        error
        for error in (tool_call_error(call) for call in searches + loads)
        if error is not None
    ]
    tool_sequence_ok = not unexpected_actions
    reported_matches_calls = True
    top_five_recall: bool | None = None
    names_from_search: list[str] = []
    top_one_correct = selection_top_one_correct
    if mode == "skillloader":
        names_from_search = search_names(searches)
        search_starts = tool_call_events(events, "item.started", "search_skills")
        search_completions = tool_call_events(events, "item.completed", "search_skills")
        load_starts = tool_call_events(events, "item.started", "load_skill")
        load_completions = tool_call_events(events, "item.completed", "load_skill")
        search_completed_before_loads = bool(search_completions) and all(
            index > search_completions[0][0] for index, _ in load_starts
        )
        loads_belong_to_search = all(name in names_from_search for name in loaded_names)
        search_arguments = (
            searches[0].get("arguments", {}) if len(searches) == 1 else {}
        )
        search_arguments_ok = search_arguments in (
            {"query": task["query"], "limit": 5},
            {"query": task_prompt(task["query"]), "limit": 5},
        )
        tool_sequence_ok = all(
            [
                len(searches) == len(search_starts) == len(search_completions) == 1,
                matching_call_ids(search_starts, search_completions),
                len(loads) == len(load_starts) == len(load_completions),
                matching_call_ids(load_starts, load_completions),
                search_completed_before_loads,
                loads_belong_to_search,
                search_results_valid,
                load_results_valid,
                search_arguments_ok,
                not tool_errors,
                not unexpected_actions,
            ]
        )
        reported_matches_calls = sorted(reported_names) == sorted(loaded_names)
        no_load_correct = no_load_correct and (
            (not loaded_names) == bool(task["no_load"])
        )
        if expected_top:
            top_five_recall = expected_top in names_from_search[:5]
            top_one_correct = (
                bool(names_from_search) and names_from_search[0] == expected_top
            )

    routing_failure = response is None or bool(tool_errors) or not tool_sequence_ok
    task_success = all(
        [
            selection_top_one_correct,
            no_load_correct,
            not incorrect_load,
            load_count_correct,
            applied,
            required_skill_set_correct,
            response_shape_ok,
            not routing_failure,
            reported_matches_calls,
        ]
    )

    observed = {
        "reported_names": reported_names,
        "selected_names": selected_names,
        "loaded_names": loaded_names,
        "search_names": names_from_search,
        "search_call_count": len(searches),
        "load_call_count": len(loads),
        "tool_errors": tool_errors,
        "unexpected_actions": unexpected_actions,
        "load_results_valid": load_results_valid,
        "search_results_valid": search_results_valid,
        "required_names": required_names if required_names_valid else [],
    }
    score = {
        "top_one_correct": top_one_correct,
        "selection_top_one_correct": selection_top_one_correct,
        "top_five_recall": top_five_recall,
        "no_load_correct": no_load_correct,
        "incorrect_load": incorrect_load,
        "load_count_correct": load_count_correct,
        "selected_instructions_exact": instructions_exact,
        "required_instruction_set_applied": (
            instructions_exact is True
            and required_skill_set_correct
            and reported_matches_calls
            if int(task["load_count"]) > 0
            else no_load_correct
            and response_shape_ok
            and applied
            and required_skill_set_correct
        ),
        "required_skill_set_correct": required_skill_set_correct,
        "reported_names_match_calls": reported_matches_calls,
        "response_shape_ok": response_shape_ok,
        "tool_sequence_ok": tool_sequence_ok,
        "routing_failure": routing_failure,
        "task_success": task_success,
    }
    return observed, score


def codex_arguments(
    mode: str,
    prompt: str,
    developer_instructions: str,
    binary: Path,
    catalog_root: Path,
    schema_path: Path,
    run_cwd: Path,
) -> list[str]:
    mcp_cache = run_cwd / "mcp-cache"
    args = [
        "codex",
        "-a",
        "never",
        "-s",
        "read-only",
        "-m",
        MODEL,
        "-c",
        "developer_instructions="
        + json.dumps(developer_instructions, ensure_ascii=False),
    ]
    if mode == "skillloader":
        args.extend(
            [
                "-c",
                f'mcp_servers.skillloader.command="{binary}"',
                "-c",
                "mcp_servers.skillloader.env="
                f'{{SKILLLOADER_ROOTS="{catalog_root}",'
                f'XDG_CACHE_HOME="{mcp_cache}"}}',
                "-c",
                'mcp_servers.skillloader.enabled_tools=["search_skills","load_skill"]',
                "-c",
                'mcp_servers.skillloader.default_tools_approval_mode="approve"',
                "-c",
                'mcp_servers.skillloader.tools.search_skills.approval_mode="approve"',
                "-c",
                'mcp_servers.skillloader.tools.load_skill.approval_mode="approve"',
            ]
        )
    args.extend(
        [
            "exec",
            "--strict-config",
            "--ignore-user-config",
            "--ephemeral",
            "--json",
            "--color",
            "never",
            "--skip-git-repo-check",
            "--output-schema",
            str(schema_path),
            "-C",
            str(run_cwd),
            prompt,
        ]
    )
    return args


def expected_redacted_argv(
    mode: str, prompt: str, developer_instructions: str
) -> list[str]:
    placeholder_root = Path("/tmp/skillloader-gate6-expected")
    return redact_argv(
        codex_arguments(
            mode,
            prompt,
            developer_instructions,
            placeholder_root / "skillloader",
            placeholder_root / "catalog",
            placeholder_root / "output-schema.json",
            placeholder_root,
        )[:-1]
    )


def run_codex(
    mode: str,
    task: dict[str, Any],
    prompt: str,
    developer_instructions: str,
    binary: Path,
    catalog_root: Path,
    schema_path: Path,
    run_cwd: Path,
    timeout_seconds: int,
    encoding: Any,
    instructions: dict[str, str],
    documents: dict[str, str],
    environment: dict[str, str],
) -> dict[str, Any]:
    args = codex_arguments(
        mode,
        prompt,
        developer_instructions,
        binary,
        catalog_root,
        schema_path,
        run_cwd,
    )
    prompt_input = effective_prompt_metadata(
        developer_instructions, prompt, run_cwd, environment
    )
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            args,
            cwd=run_cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = 124
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
    duration_ms = round((time.monotonic() - started) * 1000)
    parsed_events, non_json_stdout = parse_jsonl(stdout)
    response = final_response(parsed_events)
    searches = completed_tool_calls(parsed_events, "search_skills")
    loads = completed_tool_calls(parsed_events, "load_skill")
    observed, score = score_run(
        mode, task, parsed_events, response, instructions, documents
    )
    events = sanitize_events(parsed_events, mode)
    return {
        "schema_version": 1,
        "run_id": f"{task['id']}:{mode}",
        "task_id": task["id"],
        "mode": mode,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "prompt": prompt,
        "developer_instructions": developer_instructions,
        "effective_prompt": prompt_input,
        "argv_without_prompt": redact_argv(args[:-1]),
        "stdout_non_json": [redact_evidence_text(line) for line in non_json_stdout],
        "stderr": redact_evidence_text(stderr),
        "events": events,
        "event_payload_redacted": events != parsed_events,
        "final_response": final_response(events),
        "usage": usage_from(parsed_events),
        "payload_token_estimates": {
            "prompt_cl100k": len(encoding.encode(prompt)),
            "search_results_cl100k": tool_payload_tokens(encoding, searches),
            "load_results_cl100k": tool_payload_tokens(encoding, loads),
        },
        "observed": redact_evidence_value(observed),
        "score": score,
    }


def percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(100 * numerator / denominator, 2)


def validated_usage(record: dict[str, Any]) -> dict[str, int]:
    usage = record.get("usage")
    run_id = record.get("run_id", "unknown run")
    if not isinstance(usage, dict):
        raise ValueError(f"{run_id}: missing client-reported usage")
    missing = [key for key in REQUIRED_USAGE_KEYS if key not in usage]
    if missing:
        raise ValueError(f"{run_id}: missing usage counters: {missing}")
    result: dict[str, int] = {}
    for key in REQUIRED_USAGE_KEYS:
        value = usage[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{run_id}: invalid usage counter {key}: {value!r}")
        result[key] = value
    if result["cached_input_tokens"] > result["input_tokens"]:
        raise ValueError(f"{run_id}: cached input exceeds total input")
    return result


def execution_failure(record: dict[str, Any]) -> str | None:
    run_id = record.get("run_id", "unknown run")
    if record.get("timed_out"):
        return f"{run_id}: invocation timed out"
    if record.get("exit_code") != 0:
        return f"{run_id}: nonzero exit code {record.get('exit_code')!r}"
    if record.get("final_response") is None:
        return f"{run_id}: missing structured final response"
    try:
        validated_usage(record)
    except ValueError as error:
        return str(error)
    return None


def static_token_estimates(
    encoding: Any, catalog: str, tools: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "method": f"tiktoken {importlib.metadata.version('tiktoken')} {TOKEN_ENCODING}",
        "eager_catalog_block_cl100k": len(encoding.encode(catalog)),
        "mcp_tool_schemas_cl100k": canonical_tokens(encoding, tools),
        "common_policy_cl100k": len(encoding.encode(COMMON_POLICY)),
        "eager_developer_instructions_cl100k": len(
            encoding.encode(eager_developer_instructions(catalog))
        ),
        "skillloader_developer_instructions_cl100k": len(
            encoding.encode(skillloader_developer_instructions())
        ),
    }


def summarize(records: list[dict[str, Any]], static: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(records),
        "task_completion_success": "not measured; fixture evaluates routing and exact final-instruction extraction",
        "static_token_estimates": static,
        "modes": {},
    }
    for mode in ("eager", "skillloader"):
        selected = [record for record in records if record["mode"] == mode]
        load_tasks = [
            record
            for record in selected
            if record.get("scoring_task", record["task"])["expected_top"]
        ]
        no_load_tasks = [
            record
            for record in selected
            if record.get("scoring_task", record["task"])["no_load"]
        ]
        instruction_runs = [
            record
            for record in selected
            if record["score"]["selected_instructions_exact"] is not None
        ]
        top_five = [
            record
            for record in load_tasks
            if record["score"]["top_five_recall"] is not None
        ]
        validated_usages = [validated_usage(record) for record in selected]
        usage_totals = {
            key: sum(usage[key] for usage in validated_usages)
            for key in REQUIRED_USAGE_KEYS
        }
        quality = {
            "top_one_correct": sum(
                record["score"]["top_one_correct"] for record in load_tasks
            ),
            "top_one_total": len(load_tasks),
            "selection_top_one_correct": sum(
                record["score"]["selection_top_one_correct"] for record in load_tasks
            ),
            "selection_top_one_total": len(load_tasks),
            "selection_top_one_percent": percentage(
                sum(
                    record["score"]["selection_top_one_correct"]
                    for record in load_tasks
                ),
                len(load_tasks),
            ),
            "top_one_percent": percentage(
                sum(record["score"]["top_one_correct"] for record in load_tasks),
                len(load_tasks),
            ),
            "top_five_recall_correct": sum(
                record["score"]["top_five_recall"] is True for record in top_five
            ),
            "top_five_recall_total": len(top_five),
            "top_five_recall_percent": percentage(
                sum(record["score"]["top_five_recall"] is True for record in top_five),
                len(top_five),
            ),
            "no_load_correct": sum(
                record["score"]["no_load_correct"] for record in no_load_tasks
            ),
            "no_load_total": len(no_load_tasks),
            "no_load_percent": percentage(
                sum(record["score"]["no_load_correct"] for record in no_load_tasks),
                len(no_load_tasks),
            ),
            "incorrect_load_runs": sum(
                record["score"]["incorrect_load"] for record in selected
            ),
            "incorrect_load_percent": percentage(
                sum(record["score"]["incorrect_load"] for record in selected),
                len(selected),
            ),
            "load_count_correct": sum(
                record["score"]["load_count_correct"] for record in selected
            ),
            "load_count_total": len(selected),
            "exact_selected_instruction_runs": sum(
                record["score"]["selected_instructions_exact"] is True
                for record in instruction_runs
            ),
            "exact_selected_instruction_run_total": len(instruction_runs),
            "required_instruction_set_applied": sum(
                record["score"]["required_instruction_set_applied"]
                for record in load_tasks
            ),
            "required_instruction_set_total": len(load_tasks),
            "routing_failures": sum(
                record["score"]["routing_failure"] for record in selected
            ),
            "task_successes": sum(
                record["score"]["task_success"] for record in selected
            ),
            "task_success_total": len(selected),
        }
        payload_totals = {
            key: sum(record["payload_token_estimates"][key] for record in selected)
            for key in ("prompt_cl100k", "search_results_cl100k", "load_results_cl100k")
        }
        summary["modes"][mode] = {
            "run_count": len(selected),
            "completed_exit_zero": sum(record["exit_code"] == 0 for record in selected),
            "duration_ms_total": sum(record["duration_ms"] for record in selected),
            "usage_totals_client_reported": usage_totals,
            "payload_token_estimate_totals": payload_totals,
            "quality": quality,
        }

    eager_input = summary["modes"]["eager"]["usage_totals_client_reported"][
        "input_tokens"
    ]
    loader_input = summary["modes"]["skillloader"]["usage_totals_client_reported"][
        "input_tokens"
    ]
    eager_cached = summary["modes"]["eager"]["usage_totals_client_reported"][
        "cached_input_tokens"
    ]
    loader_cached = summary["modes"]["skillloader"]["usage_totals_client_reported"][
        "cached_input_tokens"
    ]
    eager_uncached = eager_input - eager_cached
    loader_uncached = loader_input - loader_cached
    eager_duration = summary["modes"]["eager"]["duration_ms_total"]
    loader_duration = summary["modes"]["skillloader"]["duration_ms_total"]
    eager_static = static["eager_developer_instructions_cl100k"]
    loader_static = (
        static["skillloader_developer_instructions_cl100k"]
        + static["mcp_tool_schemas_cl100k"]
    )
    summary["comparisons"] = {
        "total_input_token_reduction_percent_client_reported": (
            round(100 * (1 - loader_input / eager_input), 2) if eager_input else None
        ),
        "catalog_overhead_reduction_percent_cl100k_estimate": round(
            100
            * (
                1
                - static["mcp_tool_schemas_cl100k"]
                / static["eager_catalog_block_cl100k"]
            ),
            2,
        ),
        "initial_static_overhead": {
            "eager_cl100k_estimate": eager_static,
            "skillloader_cl100k_estimate": loader_static,
            "reduction_percent_cl100k_estimate": round(
                100 * (1 - loader_static / eager_static), 2
            ),
        },
        "uncached_input_tokens_client_reported": {
            "eager": eager_uncached,
            "skillloader": loader_uncached,
            "reduction_percent": (
                round(100 * (1 - loader_uncached / eager_uncached), 2)
                if eager_uncached
                else None
            ),
        },
        "duration": {
            "eager_total_ms": eager_duration,
            "skillloader_total_ms": loader_duration,
            "reduction_percent": (
                round(100 * (1 - loader_duration / eager_duration), 2)
                if eager_duration
                else None
            ),
        },
        "total_input_note": "Codex turn usage aggregates all model calls, including cached input tokens.",
        "catalog_overhead_note": "Offline cl100k_base estimate over the exact eager catalog block and canonical MCP tools/list schemas; not provider billing tokens.",
    }
    return summary


def rescore_existing(directory: Path) -> int:
    directory = directory.resolve()
    environment = read_json(directory / "environment.json")
    recorded_output_schema = read_json(directory / "output-schema.json")
    if recorded_output_schema != OUTPUT_SCHEMA:
        raise SystemExit("recorded output schema mismatch; refusing to rescore")
    expected_fixture_path = str(TASKS_PATH.relative_to(REPO))
    if environment.get("task_fixture") != expected_fixture_path:
        raise SystemExit("unexpected task fixture path; refusing to rescore")
    fixture_bytes = TASKS_PATH.read_bytes()
    scoring_fixture_hash = sha256_bytes(fixture_bytes)
    fixture = json.loads(fixture_bytes)
    fixture_tasks = {task["id"]: task for task in fixture["tasks"]}
    recorded_tasks = read_jsonl(directory / "tasks.jsonl")
    task_ids = [task.get("id") for task in recorded_tasks]
    if not task_ids or len(task_ids) != len(set(task_ids)):
        raise SystemExit("missing or duplicate recorded task ids; refusing to rescore")
    execution_fixture_matches = (
        environment.get("task_fixture_sha256") == scoring_fixture_hash
    )
    expected_recorded_tasks = [fixture_tasks.get(task_id) for task_id in task_ids]
    if not execution_fixture_matches:
        expected_recorded_tasks = [
            {"id": task.get("id"), "query": task.get("query")}
            if isinstance(task, dict)
            else task
            for task in expected_recorded_tasks
        ]
        recorded_tasks_for_comparison = [
            {"id": task.get("id"), "query": task.get("query")}
            if isinstance(task, dict)
            else task
            for task in recorded_tasks
        ]
    else:
        recorded_tasks_for_comparison = recorded_tasks
    if expected_recorded_tasks != recorded_tasks_for_comparison:
        raise SystemExit("recorded tasks differ from the fixture; refusing to rescore")
    runner_metadata = environment.setdefault("runner", {})
    recorded_scoring_hash = runner_metadata.get("scoring_fixture_sha256")
    if recorded_scoring_hash not in (None, scoring_fixture_hash):
        scoring_history = runner_metadata.setdefault("prior_scoring_fixture_sha256", [])
        if recorded_scoring_hash not in scoring_history:
            scoring_history.append(recorded_scoring_hash)

    skills, catalog_hash, instructions = load_catalog()
    catalog = catalog_block(skills)
    recorded_catalog_hash = environment.get("catalog_sha256")
    if recorded_catalog_hash != catalog_hash:
        raise SystemExit(
            "catalog hash mismatch; refusing to rescore historical evidence "
            f"(recorded {recorded_catalog_hash!r}, current {catalog_hash!r})"
        )
    encoding = tiktoken.get_encoding(TOKEN_ENCODING)
    tools = environment.get("mcp_tools")
    if not isinstance(tools, list) or not all(isinstance(tool, dict) for tool in tools):
        raise SystemExit("missing recorded MCP tool schemas; refusing to rescore")
    static = static_token_estimates(encoding, catalog, tools)
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for mode in ("eager", "skillloader"):
        path = directory / f"{mode}.jsonl"
        mode_records = read_jsonl(path)
        mode_task_ids = [record.get("task_id") for record in mode_records]
        if mode_task_ids != task_ids:
            raise SystemExit(
                f"{mode} records do not match tasks.jsonl; refusing to rescore"
            )
        for record, task in zip(mode_records, recorded_tasks):
            if (
                record.get("mode") != mode
                or record.get("run_id") != f"{task['id']}:{mode}"
                or record.get("task") != task
            ):
                raise SystemExit(f"invalid {mode} record identity; refusing to rescore")
        by_mode[mode] = mode_records

    records: list[dict[str, Any]] = []
    for mode in ("eager", "skillloader"):
        mode_records = by_mode[mode]
        for record in mode_records:
            scoring_task = fixture_tasks[record["task_id"]]
            expected_prompt = task_prompt(scoring_task["query"])
            expected_developer_instructions = (
                eager_developer_instructions(catalog)
                if mode == "eager"
                else skillloader_developer_instructions()
            )
            if record.get("prompt") != expected_prompt:
                raise SystemExit(
                    f"{record['run_id']}: prompt mismatch; refusing to rescore"
                )
            if record.get("developer_instructions") != expected_developer_instructions:
                raise SystemExit(
                    f"{record['run_id']}: developer instructions mismatch; "
                    "refusing to rescore"
                )
            events = record.get("events")
            if not isinstance(events, list) or not all(
                isinstance(event, dict) for event in events
            ):
                raise SystemExit(
                    f"{record['run_id']}: invalid events; refusing to rescore"
                )
            if record.get("event_payload_redacted") is True:
                raise SystemExit(
                    f"{record['run_id']}: redacted event payload cannot be rescored"
                )
            raw_events = events
            response = final_response(raw_events)
            searches = completed_tool_calls(raw_events, "search_skills")
            loads = completed_tool_calls(raw_events, "load_skill")
            events = sanitize_events(raw_events, mode)
            record["events"] = events
            record["event_payload_redacted"] = events != raw_events
            record["final_response"] = final_response(events)
            record["usage"] = usage_from(raw_events)
            record["payload_token_estimates"] = {
                "prompt_cl100k": len(encoding.encode(expected_prompt)),
                "search_results_cl100k": tool_payload_tokens(encoding, searches),
                "load_results_cl100k": tool_payload_tokens(encoding, loads),
            }
            argv = record.get("argv_without_prompt")
            if not isinstance(argv, list) or not all(
                isinstance(arg, str) for arg in argv
            ):
                raise SystemExit(
                    f"{record['run_id']}: invalid argv; refusing to rescore"
                )
            expected_argv = expected_redacted_argv(
                mode, expected_prompt, expected_developer_instructions
            )
            actual_argv = redact_argv(argv)
            legacy_argv = list(expected_argv)
            if mode == "skillloader":
                legacy_argv = [
                    'mcp_servers.skillloader.env={SKILLLOADER_ROOTS="<FIXTURE_CATALOG_ROOT>"}'
                    if argument.startswith("mcp_servers.skillloader.env=")
                    else argument
                    for argument in legacy_argv
                ]
            legacy_allowed = runner_metadata.get("argv_schema_version") is None
            if actual_argv != expected_argv and not (
                legacy_allowed and actual_argv == legacy_argv
            ):
                raise SystemExit(
                    f"{record['run_id']}: invocation arguments mismatch; refusing to rescore"
                )
            record["argv_without_prompt"] = expected_argv
            stdout_non_json = record.get("stdout_non_json")
            if not isinstance(stdout_non_json, list) or not all(
                isinstance(line, str) for line in stdout_non_json
            ):
                raise SystemExit(
                    f"{record['run_id']}: invalid non-JSON stdout; refusing to rescore"
                )
            record["stdout_non_json"] = [
                redact_evidence_text(line) for line in stdout_non_json
            ]
            stderr = record.get("stderr")
            if not isinstance(stderr, str):
                raise SystemExit(
                    f"{record['run_id']}: invalid stderr; refusing to rescore"
                )
            record["stderr"] = redact_evidence_text(stderr)
            observed, score = score_run(
                mode=mode,
                task=scoring_task,
                events=raw_events,
                response=response,
                instructions=instructions,
                documents={skill["name"]: skill["content"] for skill in skills},
            )
            record["observed"] = redact_evidence_value(observed)
            record["score"] = score
            record["scoring_task"] = scoring_task
            failure = execution_failure(record)
            if failure is not None:
                raise SystemExit(f"{failure}; refusing to rescore")
        records.extend(mode_records)
    summary = summarize(records, static)
    environment["static_token_estimates"] = static
    runner_metadata["scoring_fixture_sha256"] = scoring_fixture_hash
    runner_metadata["argv_schema_version"] = 2
    runner_metadata["last_rescore_sha256"] = sha256_bytes(Path(__file__).read_bytes())
    runner_metadata["last_rescored_at"] = datetime.now(timezone.utc).isoformat()
    for mode, mode_records in by_mode.items():
        write_jsonl(directory / f"{mode}.jsonl", mode_records)
    write_json(directory / "environment.json", environment)
    write_json(directory / "summary.json", summary)
    print(json.dumps(summary["comparisons"], ensure_ascii=False, sort_keys=True))
    return 0


def main() -> int:
    args = parse_args()
    if args.rescore_dir is not None:
        return rescore_existing(args.rescore_dir)
    output_dir = args.output_dir.resolve()

    fixture_bytes = TASKS_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)
    if fixture.get("schema_version") != 1:
        raise SystemExit("unsupported task fixture schema")
    tasks = fixture["tasks"]
    if args.task_id:
        wanted = set(args.task_id)
        tasks = [task for task in tasks if task["id"] in wanted]
        missing = sorted(wanted - {task["id"] for task in tasks})
        if missing:
            raise SystemExit(f"unknown task ids: {missing}")
    if not tasks:
        raise SystemExit("no tasks selected")

    skills, catalog_hash, instructions = load_catalog()
    catalog = catalog_block(skills)
    encoding = tiktoken.get_encoding(TOKEN_ENCODING)
    build_source = build_input_metadata()
    output_dir.mkdir(parents=True, exist_ok=False)
    schema_path = output_dir / "output-schema.json"
    write_json(schema_path, OUTPUT_SCHEMA)
    for task in tasks:
        append_jsonl(output_dir / "tasks.jsonl", task)

    with tempfile.TemporaryDirectory(prefix="skillloader-gate6-") as temp_name:
        temp_dir = Path(temp_name)
        _, codex_environment = prepare_isolated_codex_home(temp_dir)
        binary = temp_dir / "skillloader"
        snapshot_root = temp_dir / "catalog"
        shutil.copytree(CATALOG_ROOT, snapshot_root)
        _, snapshot_hash, _ = load_catalog(snapshot_root)
        if snapshot_hash != catalog_hash:
            raise SystemExit("fixture catalog changed while creating its snapshot")
        subprocess.run(
            ["go", "build", "-o", str(binary), "."],
            cwd=REPO,
            env=temporary_build_environment(temp_dir),
            check=True,
            stdin=subprocess.DEVNULL,
        )
        if build_input_metadata() != build_source:
            raise SystemExit(
                "Go build inputs changed while building the evidence binary"
            )
        tools = list_mcp_tools(binary, snapshot_root)
        static = static_token_estimates(encoding, catalog, tools)
        environment = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": command_output("git", "rev-parse", "HEAD"),
            "git_branch": command_output("git", "branch", "--show-current"),
            "codex_version": command_output("codex", "--version"),
            "codex_auth_status": command_output(
                "codex", "login", "status", environment=codex_environment
            ),
            "model": MODEL,
            "model_provider": "openai via ChatGPT login",
            "temperature": "client default; CLI exposes no value in this run",
            "go_version": command_output("go", "version"),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "task_fixture": str(TASKS_PATH.relative_to(REPO)),
            "task_fixture_sha256": sha256_bytes(fixture_bytes),
            "catalog_root": str(CATALOG_ROOT.relative_to(REPO)),
            "catalog_size": len(skills),
            "catalog_sha256": catalog_hash,
            "catalog_skill_names": [skill["name"] for skill in skills],
            "runner": {
                "execution_sha256": sha256_bytes(Path(__file__).read_bytes()),
                "scoring_fixture_sha256": sha256_bytes(fixture_bytes),
                "requirements": str(REQUIREMENTS_PATH.relative_to(REPO)),
                "requirements_sha256": sha256_bytes(REQUIREMENTS_PATH.read_bytes()),
            },
            "build_source": build_source,
            "binary_sha256": sha256_bytes(binary.read_bytes()),
            "mcp_tools": tools,
            "isolation": {
                "ignore_user_config": True,
                "ephemeral": True,
                "sandbox": "read-only",
                "approval_policy": "never",
                "mcp_tool_approval_mode": "approve",
                "working_directory": "temporary directory outside repository",
                "user_config_modified": False,
                "global_agent_instructions": False,
                "isolated_codex_home": True,
                "ephemeral_auth_symlink": True,
                "runner_credentials_read_or_copied": False,
            },
            "run_order": "paired by task; eager first for even indexes, skillloader first for odd indexes",
            "static_token_estimates": static,
        }
        write_json(output_dir / "environment.json", environment)

        records: list[dict[str, Any]] = []
        total_runs = len(tasks) * 2
        run_number = 0
        for index, task in enumerate(tasks):
            modes = (
                ("eager", "skillloader") if index % 2 == 0 else ("skillloader", "eager")
            )
            for mode in modes:
                run_number += 1
                developer_instructions = (
                    eager_developer_instructions(catalog)
                    if mode == "eager"
                    else skillloader_developer_instructions()
                )
                prompt = task_prompt(task["query"])
                print(
                    f"[{run_number}/{total_runs}] {task['id']} {mode}",
                    flush=True,
                )
                record = run_codex(
                    mode=mode,
                    task=task,
                    prompt=prompt,
                    developer_instructions=developer_instructions,
                    binary=binary,
                    catalog_root=snapshot_root,
                    schema_path=schema_path,
                    run_cwd=temp_dir,
                    timeout_seconds=args.timeout_seconds,
                    encoding=encoding,
                    instructions=instructions,
                    documents={skill["name"]: skill["content"] for skill in skills},
                    environment=codex_environment,
                )
                record["task"] = task
                record["scoring_task"] = task
                records.append(record)
                append_jsonl(output_dir / f"{mode}.jsonl", record)
                print(
                    f"  exit={record['exit_code']} selected={record['observed']['selected_names']} "
                    f"success={record['score']['task_success']} input={record['usage'].get('input_tokens')}",
                    flush=True,
                )

    execution_failures = [
        failure
        for record in records
        if (failure := execution_failure(record)) is not None
    ]
    if execution_failures:
        write_json(output_dir / "execution-failures.json", execution_failures)
        print(f"execution failures: {execution_failures}", file=sys.stderr)
        return 1
    summary = summarize(records, static)
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary["comparisons"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
