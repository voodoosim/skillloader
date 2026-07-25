#!/usr/bin/env python3
"""Run the committed Gate 6 routing fixture against live Claude Code.

The runner compares two isolated `claude -p` invocations per task:

* eager: all fixture skill documents are included in a full system-prompt
  override; the run is denied every tool, so it must answer directly.
* skillloader: only the SkillLoader MCP server is registered (via
  --strict-mcp-config), and the model may call only its two tools
  (mcp__skillloader__search_skills, mcp__skillloader__load_skill).

Unlike the Codex counterpart (scripts/run_gate6_codex.py), Claude Code
2.1.212 defers MCP tool schemas behind a built-in `ToolSearch` tool: the
model must call ToolSearch to resolve a tool's schema before it can invoke
it. This is Claude-Code-specific harness behavior with no Codex analogue,
so ToolSearch calls are recorded and reported separately rather than
folded into the search/load scoring used by the Codex runner.

Isolation is achieved with `--setting-sources ""` (skip project/user
settings.json, hooks, and CLAUDE.md-driven system-prompt assembly) plus
`--disable-slash-commands` (skip all locally installed skills) plus
`--strict-mcp-config` (only the MCP server passed via --mcp-config is
registered). `--bare` was tested and rejected: it also skips keychain
reads, so the CLI cannot authenticate through the existing subscription
login. This isolation was verified empirically (see
docs/BENCHMARK.md) by inspecting the `system/init` event's `tools`,
`skills`, and `mcp_servers` fields and confirming no SessionStart hook
output appears in the transcript; it was not verified against every
possible local hook/plugin combination, so treat `environment.json`'s
recorded `system_init` field as the source of truth for what a given
run actually saw, not this docstring.

Anthropic's own token-usage accounting (input_tokens /
cache_creation_input_tokens / cache_read_input_tokens / output_tokens) is
structurally different from Codex's (input_tokens / cached_input_tokens /
output_tokens / reasoning_output_tokens). This script does not attempt to
reconcile the two into one number; it reports Claude Code's native fields
and compares eager vs skillloader within Claude Code only. Do not compare
totals from this script against scripts/run_gate6_codex.py's totals as if
they used the same accounting.

Every invocation is capped with --max-budget-usd to bound runaway cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
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
TOKEN_ENCODING = "cl100k_base"
MAX_SKILLS = 2
DEFAULT_MODEL = "sonnet"
DEFAULT_MAX_BUDGET_USD = "2.00"
SKILLLOADER_TOOLS = ("mcp__skillloader__search_skills", "mcp__skillloader__load_skill")
REQUIRED_USAGE_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
CHILD_ENV_ALLOWLIST = (
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
JSON object required by the output schema. Do not use any tool other than the ones
explicitly named in this prompt."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="new directory in which to write evidence and the summary",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="run only the named task; repeat to select multiple tasks",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help="claude -p --model value"
    )
    parser.add_argument(
        "--max-budget-usd",
        default=DEFAULT_MAX_BUDGET_USD,
        help="per-invocation --max-budget-usd cap passed to claude",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
        help="timeout for each claude invocation",
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
        r"\bsk-(?:ant-)?(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b",
        "<REDACTED_TOKEN>",
        redacted,
    )
    redacted = re.sub(
        r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b",
        "<REDACTED_TOKEN>",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(\b(?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+)[A-Za-z0-9._~+/-]{12,}",
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
    for variable, placeholder in (("HOME", "<HOME>"), ("TMPDIR", "<TMPDIR>")):
        path = os.environ.get(variable)
        if path and path != "/":
            redacted = redacted.replace(path, placeholder)
    redacted = re.sub(
        r"/tmp/skillloader-gate6-cc-[^/\"'\s]+",
        "<TEMP_WORKDIR>",
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
        if previous == "--system-prompt":
            value = "<SYSTEM_PROMPT>"
        elif previous == "--json-schema":
            value = "<OUTPUT_SCHEMA>"
        elif previous == "--mcp-config":
            value = re.sub(r'"command":"[^"]*"', '"command":"<TEMP_BINARY>"', value)
            value = re.sub(
                r'"SKILLLOADER_ROOTS":"[^"]*"',
                '"SKILLLOADER_ROOTS":"<FIXTURE_CATALOG_ROOT>"',
                value,
            )
            value = re.sub(
                r'"XDG_CACHE_HOME":"[^"]*"',
                '"XDG_CACHE_HOME":"<TEMP_CACHE>"',
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


def build_input_metadata() -> dict[str, Any]:
    pathspec = ("*.go", "go.mod", "go.sum")
    dirty = command_output(
        "git", "status", "--porcelain", "--untracked-files=all", "--", *pathspec
    )
    if dirty:
        raise SystemExit(
            "Go build inputs differ from HEAD; refusing to create evidence"
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
    return {"git_clean": True, "files": files, "sha256": combined.hexdigest()}


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
    sections = [
        f'<skill logical_name="{skill["name"]}">\n{skill["content"]}</skill>'
        for skill in skills
    ]
    return "<skill_catalog>\n" + "\n".join(sections) + "\n</skill_catalog>"


def eager_system_prompt(catalog: str) -> str:
    return (
        f"{COMMON_POLICY}\n\n"
        "All available skill documents are included below. You have been given no tools "
        "for this task. Select directly from these documents.\n\n"
        f"{catalog}"
    )


def skillloader_system_prompt() -> str:
    return (
        f"{COMMON_POLICY}\n\n"
        "Call search_skills exactly once with the complete Query and limit 5. "
        "Use only its returned logical names. If no returned skill is relevant, do not "
        "call load_skill. Otherwise call load_skill exactly once for every selected skill "
        "and use the complete returned document."
    )


def task_prompt(query: str) -> str:
    return f"Query: {query}"


def claude_arguments(
    mode: str,
    prompt: str,
    system_prompt: str,
    model: str,
    max_budget_usd: str,
    binary: Path | None,
    catalog_root: Path | None,
    mcp_cache: Path | None,
) -> list[str]:
    args = [
        "claude",
        "-p",
        prompt,
        "--setting-sources",
        "",
        "--disable-slash-commands",
        "--model",
        model,
        "--system-prompt",
        system_prompt,
        "--json-schema",
        json.dumps(OUTPUT_SCHEMA, ensure_ascii=False),
        "--output-format",
        "stream-json",
        "--verbose",
        "--permission-mode",
        "default",
        "--max-budget-usd",
        max_budget_usd,
    ]
    if mode == "eager":
        args += ["--allowedTools", ""]
    elif mode == "skillloader":
        assert binary is not None and catalog_root is not None and mcp_cache is not None
        mcp_config = {
            "mcpServers": {
                "skillloader": {
                    "type": "stdio",
                    "command": str(binary),
                    "env": {
                        "SKILLLOADER_ROOTS": str(catalog_root),
                        "XDG_CACHE_HOME": str(mcp_cache),
                    },
                }
            }
        }
        args += [
            "--mcp-config",
            json.dumps(mcp_config, ensure_ascii=False),
            "--strict-mcp-config",
            "--allowedTools",
            ",".join(SKILLLOADER_TOOLS),
        ]
    else:
        raise ValueError(f"unknown mode: {mode}")
    return args


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


def system_init_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event
    return None


def result_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("type") == "result":
            return event
    return None


def final_response(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    final = result_event(events)
    if final is None:
        return None
    text = final.get("result")
    if not isinstance(text, str):
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) and "selected_names" in value else None


def assistant_tool_uses(
    events: list[dict[str, Any]],
) -> list[tuple[int, dict[str, Any]]]:
    calls: list[tuple[int, dict[str, Any]]] = []
    for index, event in enumerate(events):
        if event.get("type") != "assistant":
            continue
        for item in event.get("message", {}).get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "tool_use":
                calls.append((index, item))
    return calls


def tool_results_by_use_id(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("type") != "user":
            continue
        for item in event.get("message", {}).get("content", []) or []:
            if isinstance(item, dict) and item.get("type") == "tool_result":
                use_id = item.get("tool_use_id")
                if isinstance(use_id, str):
                    results[use_id] = {
                        "content": item.get("content"),
                        "structured": event.get("tool_use_result"),
                    }
    return results


def mcp_calls(events: list[dict[str, Any]], tool_name: str) -> list[dict[str, Any]]:
    """Pair tool_use items named mcp__skillloader__<tool_name> with their results."""
    full_name = f"mcp__skillloader__{tool_name}"
    results = tool_results_by_use_id(events)
    calls: list[dict[str, Any]] = []
    for index, item in assistant_tool_uses(events):
        if item.get("name") != full_name:
            continue
        use_id = item.get("id")
        result = results.get(use_id) if isinstance(use_id, str) else None
        structured = None
        if result is not None:
            raw_tool_use_result = result.get("structured")
            if isinstance(raw_tool_use_result, dict):
                structured = raw_tool_use_result.get("structuredContent")
            if not isinstance(structured, dict):
                content = result.get("content")
                if isinstance(content, str):
                    try:
                        structured = json.loads(content)
                    except json.JSONDecodeError:
                        structured = None
        calls.append(
            {
                "event_index": index,
                "id": use_id,
                "arguments": item.get("input"),
                "result": structured,
                "result_present": result is not None,
            }
        )
    return calls


def toolsearch_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls = []
    for index, item in assistant_tool_uses(events):
        if item.get("name") == "ToolSearch":
            calls.append({"event_index": index, "arguments": item.get("input")})
    return calls


def non_skillloader_tool_uses(
    events: list[dict[str, Any]], mode: str
) -> list[dict[str, Any]]:
    # StructuredOutput is a synthetic tool call the CLI emits itself to enforce
    # --json-schema; it is not a model-chosen action in either mode.
    allowed = {"StructuredOutput"}
    if mode == "skillloader":
        allowed |= {"ToolSearch"}
        allowed |= {
            f"mcp__skillloader__{tool}" for tool in ("search_skills", "load_skill")
        }
    unexpected = []
    for index, item in assistant_tool_uses(events):
        name = item.get("name")
        if name not in allowed:
            unexpected.append({"event_index": index, "name": name})
    return unexpected


def canonical_tokens(encoding: Any, value: Any) -> int:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return len(encoding.encode(serialized))


def search_names(calls: list[dict[str, Any]]) -> list[str]:
    if not calls:
        return []
    result = calls[0].get("result") or {}
    matches = result.get("matches") if isinstance(result, dict) else None
    if not isinstance(matches, list):
        return []
    return [item.get("name", "") for item in matches if isinstance(item, dict)]


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


def score_run(
    mode: str,
    task: dict[str, Any],
    events: list[dict[str, Any]],
    response: dict[str, Any] | None,
    instructions: dict[str, str],
) -> dict[str, Any]:
    searches = mcp_calls(events, "search_skills")
    loads = mcp_calls(events, "load_skill")
    reported = response.get("selected_names", []) if response else []
    reported_names = [name for name in reported if isinstance(name, str)]
    loaded_names = [
        call.get("arguments", {}).get("name", "")
        for call in loads
        if isinstance(call.get("arguments"), dict)
    ]
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
    required_names_list: list[str] = (
        required_names if isinstance(required_names, list) else []
    )
    required_names_valid = (
        isinstance(required_names, list)
        and all(isinstance(name, str) for name in required_names_list)
        and len(required_names_list)
        == len(set(required_names_list))
        == int(task["load_count"])
    )
    required_skill_set_correct = (
        required_names_valid
        and len(selected_names) == len(required_names_list)
        and set(selected_names) == set(required_names_list)
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

    unexpected_tools = non_skillloader_tool_uses(events, mode)
    tool_sequence_ok = not unexpected_tools
    reported_matches_calls = True
    top_five_recall: bool | None = None
    names_from_search: list[str] = []
    top_one_correct = selection_top_one_correct

    if mode == "skillloader":
        names_from_search = search_names(searches)
        search_indexes = [call["event_index"] for call in searches]
        load_indexes = [call["event_index"] for call in loads]
        search_completed_before_loads = bool(search_indexes) and all(
            index > search_indexes[0] for index in load_indexes
        )
        loads_belong_to_search = all(name in names_from_search for name in loaded_names)
        search_arguments = searches[0].get("arguments") if len(searches) == 1 else None
        search_arguments_ok = (
            isinstance(search_arguments, dict)
            and search_arguments.get("query") == task["query"]
            and search_arguments.get("limit") == 5
        )
        results_present = all(call["result_present"] for call in searches + loads)
        tool_sequence_ok = all(
            [
                len(searches) == 1,
                search_completed_before_loads,
                loads_belong_to_search,
                search_arguments_ok,
                results_present,
                not unexpected_tools,
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

    routing_failure = response is None or not tool_sequence_ok
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
    return {
        "observed": {
            "reported_names": reported_names,
            "selected_names": selected_names,
            "loaded_names": loaded_names,
            "search_names": names_from_search,
            "search_call_count": len(searches),
            "load_call_count": len(loads),
            "toolsearch_call_count": len(toolsearch_calls(events)),
            "unexpected_tools": unexpected_tools,
            "required_names": required_names_list if required_names_valid else [],
        },
        "score": {
            "top_one_correct": top_one_correct,
            "selection_top_one_correct": selection_top_one_correct,
            "top_five_recall": top_five_recall,
            "no_load_correct": no_load_correct,
            "incorrect_load": incorrect_load,
            "load_count_correct": load_count_correct,
            "selected_instructions_exact": instructions_exact,
            "required_skill_set_correct": required_skill_set_correct,
            "reported_names_match_calls": reported_matches_calls,
            "response_shape_ok": response_shape_ok,
            "tool_sequence_ok": tool_sequence_ok,
            "routing_failure": routing_failure,
            "task_success": task_success,
        },
    }


def sanitize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return redact_evidence_value(events)


def usage_from(events: list[dict[str, Any]]) -> dict[str, Any]:
    final = result_event(events)
    if final is None:
        return {}
    usage = final.get("usage")
    return dict(usage) if isinstance(usage, dict) else {}


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
    return result


def execution_failure(record: dict[str, Any]) -> str | None:
    run_id = record.get("run_id", "unknown run")
    if record.get("timed_out"):
        return f"{run_id}: invocation timed out"
    if record.get("exit_code") != 0:
        return f"{run_id}: nonzero exit code {record.get('exit_code')!r}"
    final = record.get("result_event")
    if not isinstance(final, dict) or final.get("is_error"):
        return f"{run_id}: claude reported an error result"
    if record.get("final_response") is None:
        return f"{run_id}: missing structured final response"
    try:
        validated_usage(record)
    except ValueError as error:
        return str(error)
    return None


def percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(100 * numerator / denominator, 2)


def run_claude(
    mode: str,
    task: dict[str, Any],
    prompt: str,
    system_prompt: str,
    model: str,
    max_budget_usd: str,
    binary: Path | None,
    catalog_root: Path | None,
    mcp_cache: Path | None,
    run_cwd: Path,
    timeout_seconds: int,
    encoding: Any,
    instructions: dict[str, str],
    environment: dict[str, str],
) -> dict[str, Any]:
    args = claude_arguments(
        mode,
        prompt,
        system_prompt,
        model,
        max_budget_usd,
        binary,
        catalog_root,
        mcp_cache,
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
        stdout, stderr = completed.stdout, completed.stderr
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
    outcome = score_run(mode, task, parsed_events, response, instructions)
    init_event = system_init_event(parsed_events)
    final = result_event(parsed_events)
    sanitized_events = sanitize_events(parsed_events)
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
        "system_prompt_sha256": sha256_bytes(system_prompt.encode("utf-8")),
        "argv_without_prompt": redact_argv([a for a in args if a != prompt]),
        "stdout_non_json": [redact_evidence_text(line) for line in non_json_stdout],
        "stderr": redact_evidence_text(stderr),
        "events": sanitized_events,
        "system_init": redact_evidence_value(init_event) if init_event else None,
        "result_event": redact_evidence_value(final) if final else None,
        "final_response": final_response(sanitized_events),
        "usage": usage_from(parsed_events),
        "total_cost_usd": (final or {}).get("total_cost_usd"),
        "payload_token_estimates": {
            "prompt_cl100k": len(encoding.encode(prompt)),
        },
        "observed": redact_evidence_value(outcome["observed"]),
        "score": outcome["score"],
        "task": task,
    }


def static_token_estimates(encoding: Any, catalog: str) -> dict[str, Any]:
    return {
        "method": f"tiktoken {TOKEN_ENCODING} (offline estimate; not Anthropic's tokenizer)",
        "eager_catalog_block_cl100k": len(encoding.encode(catalog)),
        "common_policy_cl100k": len(encoding.encode(COMMON_POLICY)),
        "eager_system_prompt_cl100k": len(
            encoding.encode(eager_system_prompt(catalog))
        ),
        "skillloader_system_prompt_cl100k": len(
            encoding.encode(skillloader_system_prompt())
        ),
    }


def summarize(records: list[dict[str, Any]], static: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(records),
        "task_completion_success": "not measured; fixture evaluates routing and exact final-instruction extraction",
        "static_token_estimates": static,
        "usage_accounting_note": (
            "Claude Code usage fields (input_tokens/cache_creation_input_tokens/"
            "cache_read_input_tokens/output_tokens) are not the same accounting model "
            "as Codex's (input_tokens/cached_input_tokens/output_tokens/"
            "reasoning_output_tokens). Do not compare totals across the two runners."
        ),
        "modes": {},
    }
    for mode in ("eager", "skillloader"):
        selected = [record for record in records if record["mode"] == mode]
        load_tasks = [record for record in selected if record["task"]["expected_top"]]
        no_load_tasks = [record for record in selected if record["task"]["no_load"]]
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
        total_prompt_tokens = (
            usage_totals["input_tokens"]
            + usage_totals["cache_creation_input_tokens"]
            + usage_totals["cache_read_input_tokens"]
        )
        quality = {
            "top_one_correct": sum(r["score"]["top_one_correct"] for r in load_tasks),
            "top_one_total": len(load_tasks),
            "top_one_percent": percentage(
                sum(r["score"]["top_one_correct"] for r in load_tasks), len(load_tasks)
            ),
            "top_five_recall_correct": sum(
                r["score"]["top_five_recall"] is True for r in top_five
            ),
            "top_five_recall_total": len(top_five),
            "top_five_recall_percent": percentage(
                sum(r["score"]["top_five_recall"] is True for r in top_five),
                len(top_five),
            ),
            "no_load_correct": sum(
                r["score"]["no_load_correct"] for r in no_load_tasks
            ),
            "no_load_total": len(no_load_tasks),
            "no_load_percent": percentage(
                sum(r["score"]["no_load_correct"] for r in no_load_tasks),
                len(no_load_tasks),
            ),
            "incorrect_load_runs": sum(r["score"]["incorrect_load"] for r in selected),
            "load_count_correct": sum(
                r["score"]["load_count_correct"] for r in selected
            ),
            "load_count_total": len(selected),
            "exact_selected_instruction_runs": sum(
                r["score"]["selected_instructions_exact"] is True
                for r in instruction_runs
            ),
            "exact_selected_instruction_run_total": len(instruction_runs),
            "required_skill_set_correct": sum(
                r["score"]["required_skill_set_correct"] for r in load_tasks
            ),
            "routing_failures": sum(r["score"]["routing_failure"] for r in selected),
            "task_successes": sum(r["score"]["task_success"] for r in selected),
            "task_success_total": len(selected),
        }
        summary["modes"][mode] = {
            "run_count": len(selected),
            "completed_exit_zero": sum(r["exit_code"] == 0 for r in selected),
            "duration_ms_total": sum(r["duration_ms"] for r in selected),
            "total_cost_usd": round(
                sum(r.get("total_cost_usd") or 0 for r in selected), 6
            ),
            "usage_totals_client_reported": usage_totals,
            "total_prompt_tokens_client_reported": total_prompt_tokens,
            "toolsearch_call_count_total": sum(
                r["observed"]["toolsearch_call_count"] for r in selected
            ),
            "quality": quality,
        }

    eager_prompt_tokens = summary["modes"]["eager"][
        "total_prompt_tokens_client_reported"
    ]
    loader_prompt_tokens = summary["modes"]["skillloader"][
        "total_prompt_tokens_client_reported"
    ]
    eager_cost = summary["modes"]["eager"]["total_cost_usd"]
    loader_cost = summary["modes"]["skillloader"]["total_cost_usd"]
    summary["comparisons"] = {
        "total_prompt_token_reduction_percent_client_reported": (
            round(100 * (1 - loader_prompt_tokens / eager_prompt_tokens), 2)
            if eager_prompt_tokens
            else None
        ),
        "total_cost_usd_reduction_percent": (
            round(100 * (1 - loader_cost / eager_cost), 2) if eager_cost else None
        ),
        "toolsearch_overhead_note": (
            "skillloader mode pays an extra ToolSearch round trip per resolved MCP tool "
            "name; this has no Codex analogue and is not present in eager mode."
        ),
    }
    return summary


def main() -> int:
    args = parse_args()
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
    for task in tasks:
        append_jsonl(output_dir / "tasks.jsonl", task)

    claude_environment = safe_child_environment()

    with tempfile.TemporaryDirectory(prefix="skillloader-gate6-cc-") as temp_name:
        temp_dir = Path(temp_name)
        binary = temp_dir / "skillloader"
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
        run_cwd = temp_dir / "run-cwd"
        run_cwd.mkdir()
        mcp_cache = temp_dir / "mcp-cache"
        static = static_token_estimates(encoding, catalog)
        environment = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_commit": command_output("git", "rev-parse", "HEAD"),
            "git_branch": command_output("git", "branch", "--show-current"),
            "claude_code_version": command_output("claude", "--version"),
            "model": args.model,
            "max_budget_usd_per_invocation": args.max_budget_usd,
            "go_version": command_output("go", "version"),
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "task_fixture": str(TASKS_PATH.relative_to(REPO)),
            "task_fixture_sha256": sha256_bytes(fixture_bytes),
            "catalog_root": str(CATALOG_ROOT.relative_to(REPO)),
            "catalog_size": len(skills),
            "catalog_sha256": catalog_hash,
            "catalog_skill_names": [skill["name"] for skill in skills],
            "runner": {"execution_sha256": sha256_bytes(Path(__file__).read_bytes())},
            "build_source": build_source,
            "binary_sha256": sha256_bytes(binary.read_bytes()),
            "isolation": {
                "setting_sources": "",
                "disable_slash_commands": True,
                "strict_mcp_config": True,
                "bare_mode_used": False,
                "bare_mode_rejected_reason": (
                    "--bare also skips keychain reads, breaking subscription auth"
                ),
                "working_directory": "temporary directory outside repository",
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
                system_prompt = (
                    eager_system_prompt(catalog)
                    if mode == "eager"
                    else skillloader_system_prompt()
                )
                prompt = task_prompt(task["query"])
                print(f"[{run_number}/{total_runs}] {task['id']} {mode}", flush=True)
                record = run_claude(
                    mode=mode,
                    task=task,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    model=args.model,
                    max_budget_usd=args.max_budget_usd,
                    binary=binary if mode == "skillloader" else None,
                    catalog_root=CATALOG_ROOT if mode == "skillloader" else None,
                    mcp_cache=mcp_cache if mode == "skillloader" else None,
                    run_cwd=run_cwd,
                    timeout_seconds=args.timeout_seconds,
                    encoding=encoding,
                    instructions=instructions,
                    environment=claude_environment,
                )
                records.append(record)
                append_jsonl(output_dir / f"{mode}.jsonl", record)
                print(
                    f"  exit={record['exit_code']} selected={record['observed']['selected_names']} "
                    f"success={record['score']['task_success']} "
                    f"cost=${record.get('total_cost_usd')}",
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
