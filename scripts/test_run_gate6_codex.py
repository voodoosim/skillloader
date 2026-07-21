#!/usr/bin/env python3
"""Focused regression tests for the Gate 6 evidence runner."""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_gate6_codex as gate6


def mcp_event(
    event_type: str, item_id: str, tool: str, **values: object
) -> dict[str, object]:
    item: dict[str, object] = {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "skillloader",
        "tool": tool,
        "status": "completed" if event_type == "item.completed" else "in_progress",
    }
    item.update(values)
    return {"type": event_type, "item": item}


class Gate6RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task = {
            "id": "exact-name-01",
            "expected_top": "api-guardian",
            "required_names": ["api-guardian"],
            "alternatives": [],
            "load_count": 1,
            "no_load": False,
            "query": "api",
        }
        self.response = {
            "selected_names": ["api-guardian"],
            "no_load": False,
            "applied_instructions": [
                {"name": "api-guardian", "instruction": "Apply API checks."}
            ],
            "decision": "selected",
        }
        self.instructions = {"api-guardian": "Apply API checks."}
        self.documents = {
            "api-guardian": "# API Guardian\n\nApply API checks.\n",
        }
        search_result = {
            "structured_content": {
                "catalog_revision": "sha256:test",
                "query": "api",
                "limit": 5,
                "matches": [
                    {
                        "name": "api-guardian",
                        "description": "Review APIs.",
                        "source": "test",
                        "score": 10,
                        "tags": ["api"],
                    }
                ],
            }
        }
        self.search_start = mcp_event(
            "item.started",
            "search",
            "search_skills",
            arguments={"query": "api", "limit": 5},
        )
        self.search_complete = mcp_event(
            "item.completed",
            "search",
            "search_skills",
            arguments={"query": "api", "limit": 5},
            result=search_result,
        )
        self.load_start = mcp_event(
            "item.started", "load", "load_skill", arguments={"name": "api-guardian"}
        )
        self.load_complete = mcp_event(
            "item.completed",
            "load",
            "load_skill",
            arguments={"name": "api-guardian"},
            result={
                "structured_content": {
                    "skill": {
                        "name": "api-guardian",
                        "content": self.documents["api-guardian"],
                        "content_sha256": gate6.sha256_bytes(
                            self.documents["api-guardian"].encode("utf-8")
                        ),
                    }
                }
            },
        )

    def score(self, events: list[dict[str, object]]) -> dict[str, object]:
        _, score = gate6.score_run(
            "skillloader",
            self.task,
            events,
            self.response,
            self.instructions,
            self.documents,
        )
        return score

    def test_valid_search_then_load_succeeds(self) -> None:
        score = self.score(
            [
                self.search_start,
                self.search_complete,
                self.load_start,
                self.load_complete,
            ]
        )
        self.assertTrue(score["task_success"])
        self.assertTrue(score["tool_sequence_ok"])

    def test_invalid_loaded_document_fails(self) -> None:
        valid_events = [
            self.search_start,
            self.search_complete,
            self.load_start,
            self.load_complete,
        ]
        variants = {
            "missing skill": None,
            "wrong name": {
                "name": "test-designer",
                "content": self.documents["api-guardian"],
                "content_sha256": gate6.sha256_bytes(
                    self.documents["api-guardian"].encode("utf-8")
                ),
            },
            "wrong content": {
                "name": "api-guardian",
                "content": "tampered",
                "content_sha256": gate6.sha256_bytes(b"tampered"),
            },
            "wrong hash": {
                "name": "api-guardian",
                "content": self.documents["api-guardian"],
                "content_sha256": "wrong",
            },
        }
        for label, skill in variants.items():
            with self.subTest(label=label):
                events = copy.deepcopy(valid_events)
                events[3]["item"]["result"]["structured_content"]["skill"] = skill  # type: ignore[index]
                observed, score = gate6.score_run(
                    "skillloader",
                    self.task,
                    events,
                    self.response,
                    self.instructions,
                    self.documents,
                )
                self.assertFalse(observed["load_results_valid"])
                self.assertFalse(score["selected_instructions_exact"])
                self.assertFalse(score["task_success"])

    def test_response_requires_complete_output_schema(self) -> None:
        invalid_responses = []
        missing_decision = copy.deepcopy(self.response)
        del missing_decision["decision"]
        invalid_responses.append(missing_decision)
        wrong_decision_type = copy.deepcopy(self.response)
        wrong_decision_type["decision"] = 1
        invalid_responses.append(wrong_decision_type)
        extra_response_field = copy.deepcopy(self.response)
        extra_response_field["extra"] = True
        invalid_responses.append(extra_response_field)
        extra_applied_field = copy.deepcopy(self.response)
        extra_applied_field["applied_instructions"][0]["extra"] = True
        invalid_responses.append(extra_applied_field)
        events = [
            self.search_start,
            self.search_complete,
            self.load_start,
            self.load_complete,
        ]
        for response in invalid_responses:
            with self.subTest(response=response):
                _, score = gate6.score_run(
                    "skillloader",
                    self.task,
                    events,
                    response,
                    self.instructions,
                    self.documents,
                )
                self.assertFalse(score["response_shape_ok"])
                self.assertFalse(score["task_success"])

    def test_parallel_load_completion_order_is_not_significant(self) -> None:
        second_document = "# Test Designer\n\nDesign tests.\n"
        task = {
            **self.task,
            "load_count": 2,
            "alternatives": ["test-designer"],
            "required_names": ["api-guardian", "test-designer"],
        }
        response = {
            "selected_names": ["api-guardian", "test-designer"],
            "no_load": False,
            "applied_instructions": [
                {"name": "api-guardian", "instruction": "Apply API checks."},
                {"name": "test-designer", "instruction": "Design tests."},
            ],
            "decision": "both",
        }
        search_complete = copy.deepcopy(self.search_complete)
        search_complete["item"]["result"]["structured_content"]["matches"].append(  # type: ignore[index]
            {
                "name": "test-designer",
                "description": "Design tests.",
                "source": "test",
                "score": 5,
                "tags": ["testing"],
            }
        )
        second_start = mcp_event(
            "item.started",
            "load-two",
            "load_skill",
            arguments={"name": "test-designer"},
        )
        second_complete = mcp_event(
            "item.completed",
            "load-two",
            "load_skill",
            arguments={"name": "test-designer"},
            result={
                "structured_content": {
                    "skill": {
                        "name": "test-designer",
                        "content": second_document,
                        "content_sha256": gate6.sha256_bytes(
                            second_document.encode("utf-8")
                        ),
                    }
                }
            },
        )
        events = [
            self.search_start,
            search_complete,
            self.load_start,
            second_start,
            second_complete,
            self.load_complete,
        ]
        _, score = gate6.score_run(
            "skillloader",
            task,
            events,
            response,
            {**self.instructions, "test-designer": "Design tests."},
            {**self.documents, "test-designer": second_document},
        )
        self.assertTrue(score["tool_sequence_ok"])
        self.assertTrue(score["task_success"])

    def test_load_before_search_completion_fails(self) -> None:
        score = self.score(
            [
                self.search_start,
                self.load_start,
                self.load_complete,
                self.search_complete,
            ]
        )
        self.assertFalse(score["task_success"])
        self.assertFalse(score["tool_sequence_ok"])

    def test_completion_before_matching_start_fails(self) -> None:
        score = self.score(
            [
                self.search_complete,
                self.search_start,
                self.load_complete,
                self.load_start,
            ]
        )
        self.assertFalse(score["tool_sequence_ok"])
        self.assertFalse(score["task_success"])

    def test_load_absent_from_search_results_fails(self) -> None:
        events = copy.deepcopy(
            [
                self.search_start,
                self.search_complete,
                self.load_start,
                self.load_complete,
            ]
        )
        events[1]["item"]["result"]["structured_content"]["matches"] = []  # type: ignore[index]
        score = self.score(events)
        self.assertFalse(score["task_success"])
        self.assertFalse(score["tool_sequence_ok"])

    def test_wrong_search_arguments_fail(self) -> None:
        events = copy.deepcopy(
            [
                self.search_start,
                self.search_complete,
                self.load_start,
                self.load_complete,
            ]
        )
        events[0]["item"]["arguments"] = {"query": "wrong", "limit": 1}  # type: ignore[index]
        events[1]["item"]["arguments"] = {"query": "wrong", "limit": 1}  # type: ignore[index]
        score = self.score(events)
        self.assertFalse(score["task_success"])
        self.assertFalse(score["tool_sequence_ok"])

    def test_query_label_is_accepted_as_complete_query(self) -> None:
        events = copy.deepcopy(
            [
                self.search_start,
                self.search_complete,
                self.load_start,
                self.load_complete,
            ]
        )
        labeled_query = gate6.task_prompt(self.task["query"])
        events[0]["item"]["arguments"] = {"query": labeled_query, "limit": 5}  # type: ignore[index]
        events[1]["item"]["arguments"] = {"query": labeled_query, "limit": 5}  # type: ignore[index]
        events[1]["item"]["result"]["structured_content"]["query"] = labeled_query  # type: ignore[index]
        score = self.score(events)
        self.assertTrue(score["tool_sequence_ok"])
        self.assertTrue(score["task_success"])

    def test_structured_mcp_error_fails_routing(self) -> None:
        events = copy.deepcopy(
            [
                self.search_start,
                self.search_complete,
                self.load_start,
                self.load_complete,
            ]
        )
        events[1]["item"]["result"]["structured_content"]["error"] = {  # type: ignore[index]
            "code": "CATALOG_ERROR",
            "message": "redacted",
            "retryable": False,
        }
        observed, score = gate6.score_run(
            "skillloader",
            self.task,
            events,
            self.response,
            self.instructions,
            self.documents,
        )
        self.assertEqual(observed["tool_errors"][0]["code"], "CATALOG_ERROR")
        self.assertFalse(score["tool_sequence_ok"])
        self.assertFalse(score["task_success"])

    def test_missing_or_malformed_search_result_fails_routing(self) -> None:
        variants = {
            "missing result": None,
            "missing matches": {
                "structured_content": {
                    "catalog_revision": "sha256:test",
                    "query": "api",
                    "limit": 5,
                }
            },
            "invalid match": {
                "structured_content": {
                    "catalog_revision": "sha256:test",
                    "query": "api",
                    "limit": 5,
                    "matches": [{"name": "api-guardian"}],
                }
            },
        }
        for label, result in variants.items():
            with self.subTest(label=label):
                search_complete = copy.deepcopy(self.search_complete)
                search_complete["item"]["result"] = result
                score = self.score([self.search_start, search_complete])
                self.assertFalse(score["tool_sequence_ok"])
                self.assertFalse(score["task_success"])

    def test_unexpected_command_fails_and_payload_is_redacted(self) -> None:
        events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "command",
                    "type": "command_execution",
                    "status": "completed",
                    "command": "read /home/alice/private.txt",
                    "aggregated_output": "private user payload",
                },
            }
        ]
        _, score = gate6.score_run(
            "eager",
            self.task,
            events,
            self.response,
            self.instructions,
            self.documents,
        )
        sanitized = gate6.sanitize_events(events, "eager")
        self.assertFalse(score["tool_sequence_ok"])
        self.assertFalse(score["task_success"])
        self.assertTrue(sanitized[0]["item"]["payload_redacted"])
        self.assertNotIn("command", sanitized[0]["item"])
        self.assertNotIn("aggregated_output", sanitized[0]["item"])

    def test_duplicate_selected_skill_does_not_satisfy_two_loads(self) -> None:
        task = {
            **self.task,
            "load_count": 2,
            "alternatives": ["test-designer"],
            "required_names": ["api-guardian", "test-designer"],
        }
        response = copy.deepcopy(self.response)
        response["selected_names"] = ["api-guardian", "api-guardian"]
        _, score = gate6.score_run(
            "eager", task, [], response, self.instructions, self.documents
        )
        self.assertFalse(score["load_count_correct"])
        self.assertFalse(score["selected_instructions_exact"])
        self.assertFalse(score["task_success"])

    def test_contradictory_no_load_field_fails(self) -> None:
        task = {
            **self.task,
            "expected_top": None,
            "required_names": [],
            "load_count": 0,
            "no_load": True,
        }
        response = {
            "selected_names": [],
            "no_load": False,
            "applied_instructions": [],
            "decision": "none",
        }
        _, score = gate6.score_run(
            "eager", task, [], response, self.instructions, self.documents
        )
        self.assertFalse(score["response_shape_ok"])
        self.assertFalse(score["no_load_correct"])
        self.assertFalse(score["task_success"])

    def test_no_load_rejects_applied_instructions(self) -> None:
        task = {
            **self.task,
            "expected_top": None,
            "required_names": [],
            "load_count": 0,
            "no_load": True,
        }
        response = {
            "selected_names": [],
            "no_load": True,
            "applied_instructions": [
                {"name": "api-guardian", "instruction": "Apply API checks."}
            ],
            "decision": "none",
        }
        _, score = gate6.score_run(
            "eager", task, [], response, self.instructions, self.documents
        )
        self.assertFalse(score["required_instruction_set_applied"])
        self.assertFalse(score["task_success"])

    def test_required_multi_skill_set_must_match_exactly(self) -> None:
        task = {
            **self.task,
            "required_names": ["api-guardian", "docker-builder"],
            "alternatives": ["contract-auditor", "docker-builder"],
            "load_count": 2,
        }
        response = {
            "selected_names": ["api-guardian", "contract-auditor"],
            "no_load": False,
            "applied_instructions": [
                {"name": "api-guardian", "instruction": "Apply API checks."},
                {"name": "contract-auditor", "instruction": "Audit contracts."},
            ],
            "decision": "wrong second skill",
        }
        _, score = gate6.score_run(
            "eager",
            task,
            [],
            response,
            {**self.instructions, "contract-auditor": "Audit contracts."},
            self.documents,
        )
        self.assertFalse(score["required_skill_set_correct"])
        self.assertFalse(score["required_instruction_set_applied"])
        self.assertFalse(score["task_success"])

    def test_required_multi_skill_set_is_not_an_incorrect_load(self) -> None:
        task = {
            **self.task,
            "required_names": ["api-guardian", "docker-builder"],
            "alternatives": [],
            "load_count": 2,
        }
        response = {
            "selected_names": ["api-guardian", "docker-builder"],
            "no_load": False,
            "applied_instructions": [
                {"name": "api-guardian", "instruction": "Apply API checks."},
                {"name": "docker-builder", "instruction": "Build containers."},
            ],
            "decision": "required pair",
        }
        _, score = gate6.score_run(
            "eager",
            task,
            [],
            response,
            {**self.instructions, "docker-builder": "Build containers."},
            self.documents,
        )
        self.assertTrue(score["required_skill_set_correct"])
        self.assertFalse(score["incorrect_load"])
        self.assertTrue(score["task_success"])

    def test_incorrect_skill_does_not_apply_required_instruction_set(self) -> None:
        response = {
            "selected_names": ["invented-skill"],
            "no_load": False,
            "applied_instructions": [
                {"name": "invented-skill", "instruction": "Wrong instruction."}
            ],
            "decision": "wrong",
        }
        instructions = {**self.instructions, "invented-skill": "Wrong instruction."}
        _, score = gate6.score_run(
            "eager", self.task, [], response, instructions, self.documents
        )
        self.assertTrue(score["incorrect_load"])
        self.assertFalse(score["required_instruction_set_applied"])
        self.assertFalse(score["task_success"])

    def test_child_environment_excludes_secret_variables(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PATH": "/usr/bin",
                "HOME": "/tmp/example-home",
                "OPENAI_API_KEY": "secret",
                "AWS_SECRET_ACCESS_KEY": "secret",
                "SKILLLOADER_ROOTS": "/private/root",
            },
            clear=True,
        ):
            environment = gate6.safe_child_environment()
        self.assertEqual(environment["PATH"], "/usr/bin")
        self.assertEqual(environment["HOME"], "/tmp/example-home")
        self.assertEqual(environment["NO_COLOR"], "1")
        self.assertNotIn("OPENAI_API_KEY", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("SKILLLOADER_ROOTS", environment)

    def test_isolated_codex_home_links_only_auth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source_home = root / "source"
            source_home.mkdir()
            source_auth = source_home / "auth.json"
            source_auth.write_text("opaque", encoding="utf-8")
            (source_home / "AGENTS.md").write_text("must not copy", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"CODEX_HOME": str(source_home), "HOME": str(root), "PATH": "/bin"},
                clear=True,
            ):
                codex_home, environment = gate6.prepare_isolated_codex_home(
                    root / "run"
                )
            self.assertTrue((codex_home / "auth.json").is_symlink())
            self.assertEqual((codex_home / "auth.json").resolve(), source_auth)
            self.assertFalse((codex_home / "AGENTS.md").exists())
            self.assertEqual(environment["CODEX_HOME"], str(codex_home))

    def test_prompt_preflight_rejects_agent_instructions(self) -> None:
        result = SimpleNamespace(
            stdout=json.dumps(
                [
                    {
                        "role": "user",
                        "content": "# AGENTS.md instructions\n<INSTRUCTIONS>",
                    }
                ]
            )
        )
        with patch.object(gate6.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(SystemExit, "AGENTS.md instructions"):
                gate6.effective_prompt_metadata("developer", "prompt", Path("/tmp"), {})

    def test_summary_rejects_missing_usage(self) -> None:
        record = {
            "run_id": "missing-usage:eager",
            "mode": "eager",
            "task": self.task,
            "score": {
                "selected_instructions_exact": True,
                "top_five_recall": None,
            },
            "usage": {},
        }
        static = {
            "eager_developer_instructions_cl100k": 10,
            "skillloader_developer_instructions_cl100k": 2,
            "mcp_tool_schemas_cl100k": 2,
            "eager_catalog_block_cl100k": 8,
        }
        with self.assertRaisesRegex(ValueError, "missing usage counters"):
            gate6.summarize([record], static)

    def test_execution_failure_reports_missing_usage(self) -> None:
        failure = gate6.execution_failure(
            {
                "run_id": "missing-usage:eager",
                "timed_out": False,
                "exit_code": 0,
                "final_response": self.response,
                "usage": {},
            }
        )
        self.assertIsNotNone(failure)
        self.assertIn("missing usage counters", failure)

    def test_evidence_paths_are_redacted(self) -> None:
        arguments = [
            "codex",
            "-c",
            'mcp_servers.skillloader.command="/tmp/skillloader-gate6-abcd/skillloader"',
            "-c",
            'mcp_servers.skillloader.env={SKILLLOADER_ROOTS="'
            + str(gate6.CATALOG_ROOT)
            + '",XDG_CACHE_HOME="/tmp/skillloader-gate6-abcd/mcp-cache"}',
            "--output-schema",
            str(gate6.REPO / "schema.json"),
            "-C",
            "/tmp/skillloader-gate6-abcd",
        ]
        redacted = " ".join(gate6.redact_argv(arguments))
        self.assertNotIn(str(gate6.REPO), redacted)
        self.assertNotIn("/tmp/skillloader-gate6-", redacted)
        self.assertIn("<TEMP_BINARY>", redacted)
        self.assertIn("<FIXTURE_CATALOG_ROOT>", redacted)
        self.assertEqual(
            gate6.redact_evidence_text("failed at /home/alice/private/file.txt"),
            "failed at <ABS_PATH>",
        )
        self.assertEqual(
            gate6.redact_evidence_text("file:///home/alice/private/file.txt"),
            "file://<ABS_PATH>",
        )
        self.assertEqual(
            gate6.redact_evidence_text("failed:/home/alice/private/file.txt"),
            "failed:<ABS_PATH>",
        )
        self.assertEqual(
            gate6.redact_evidence_text("</skill> </skill_catalog>"),
            "</skill> </skill_catalog>",
        )

    def test_evidence_credentials_are_redacted(self) -> None:
        private_key = (
            "-----BEGIN PRIVATE KEY-----\nprivate-material\n-----END PRIVATE KEY-----"
        )
        values = {
            "openai": "sk-" + "A" * 32,
            "bearer": "Bearer " + "b" * 24,
            "jwt": "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12,
            "assignment": "api_key=super-secret-value",
            "private_key": private_key,
        }
        for label, secret in values.items():
            with self.subTest(label=label):
                redacted = gate6.redact_evidence_text(f"error: {secret}")
                self.assertNotIn(secret, redacted)
                self.assertIn("<REDACTED_", redacted)

        events = [
            {
                "type": "item.completed",
                "item": {
                    "id": "message",
                    "type": "agent_message",
                    "text": values["openai"],
                },
            }
        ]
        self.assertNotIn(values["openai"], str(gate6.sanitize_events(events, "eager")))

    def test_run_scores_raw_events_before_redacting_evidence(self) -> None:
        name = "path-skill"
        instruction = "Use /usr/bin/tool."
        task = {
            "id": "path-skill-01",
            "query": "use path skill",
            "expected_top": name,
            "required_names": [name],
            "alternatives": [],
            "no_load": False,
            "load_count": 1,
        }
        response = {
            "selected_names": [name],
            "no_load": False,
            "applied_instructions": [{"name": name, "instruction": instruction}],
            "decision": "selected",
        }
        stdout = "\n".join(
            [
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "message",
                            "type": "agent_message",
                            "text": json.dumps(response),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 1,
                            "cached_input_tokens": 0,
                            "output_tokens": 1,
                            "reasoning_output_tokens": 0,
                        },
                    }
                ),
            ]
        )
        completed = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        encoding = SimpleNamespace(encode=lambda value: list(value))
        with (
            patch.object(gate6, "effective_prompt_metadata", return_value={}),
            patch.object(gate6.subprocess, "run", return_value=completed),
        ):
            record = gate6.run_codex(
                mode="eager",
                task=task,
                prompt="Query: use path skill",
                developer_instructions="fixture",
                binary=Path("/tmp/skillloader"),
                catalog_root=Path("/tmp/catalog"),
                schema_path=Path("/tmp/schema.json"),
                run_cwd=Path("/tmp"),
                timeout_seconds=1,
                encoding=encoding,
                instructions={name: instruction},
                documents={name: instruction},
                environment={},
            )
        self.assertTrue(record["score"]["selected_instructions_exact"])
        self.assertTrue(record["event_payload_redacted"])
        self.assertEqual(
            record["final_response"]["applied_instructions"][0]["instruction"],
            "Use <ABS_PATH>",
        )

    def test_run_redacts_derived_tool_errors(self) -> None:
        response = {
            "selected_names": [],
            "no_load": True,
            "applied_instructions": [],
            "decision": "none",
        }
        stdout = "\n".join(
            [
                json.dumps(
                    mcp_event(
                        "item.completed",
                        "search",
                        "search_skills",
                        arguments={"query": "api", "limit": 5},
                        error={"message": "failed at /home/alice/private.txt"},
                    )
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "message",
                            "type": "agent_message",
                            "text": json.dumps(response),
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 1,
                            "cached_input_tokens": 0,
                            "output_tokens": 1,
                            "reasoning_output_tokens": 0,
                        },
                    }
                ),
            ]
        )
        completed = SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        encoding = SimpleNamespace(encode=lambda value: list(value))
        with (
            patch.object(gate6, "effective_prompt_metadata", return_value={}),
            patch.object(gate6.subprocess, "run", return_value=completed),
        ):
            record = gate6.run_codex(
                mode="skillloader",
                task={
                    **self.task,
                    "expected_top": None,
                    "required_names": [],
                    "load_count": 0,
                    "no_load": True,
                },
                prompt="Query: api",
                developer_instructions="fixture",
                binary=Path("/tmp/skillloader"),
                catalog_root=Path("/tmp/catalog"),
                schema_path=Path("/tmp/schema.json"),
                run_cwd=Path("/tmp"),
                timeout_seconds=1,
                encoding=encoding,
                instructions={},
                documents={},
                environment={},
            )
        self.assertNotIn("/home/alice", str(record["observed"]))
        self.assertIn("<ABS_PATH>", str(record["observed"]))

    def test_temporary_build_environment_uses_writable_temp_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            temp_dir = Path(temp_name)
            environment = gate6.temporary_build_environment(temp_dir)
            self.assertEqual(environment["GOCACHE"], str(temp_dir / "go-build-cache"))
            self.assertEqual(environment["GOTMPDIR"], str(temp_dir / "go-tmp"))
            self.assertTrue((temp_dir / "go-tmp").is_dir())

    def test_dirty_go_build_inputs_are_rejected(self) -> None:
        with patch.object(gate6, "command_output", return_value=" M main.go"):
            with self.assertRaisesRegex(SystemExit, "differ from HEAD"):
                gate6.build_input_metadata()

    def test_catalog_can_be_loaded_from_snapshot_root(self) -> None:
        _, expected_hash, _ = gate6.load_catalog()
        with tempfile.TemporaryDirectory() as temp_name:
            snapshot = Path(temp_name) / "catalog"
            shutil.copytree(gate6.CATALOG_ROOT, snapshot)
            skills, snapshot_hash, _ = gate6.load_catalog(snapshot)
        self.assertEqual(len(skills), 10)
        self.assertEqual(snapshot_hash, expected_hash)

    def test_rescore_rejects_catalog_hash_mismatch_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name)
            fixture_bytes = gate6.TASKS_PATH.read_bytes()
            fixture = json.loads(fixture_bytes)
            environment = {
                "task_fixture": str(gate6.TASKS_PATH.relative_to(gate6.REPO)),
                "task_fixture_sha256": gate6.sha256_bytes(fixture_bytes),
                "catalog_sha256": "deliberately-wrong",
            }
            path = directory / "environment.json"
            path.write_text(json.dumps(environment), encoding="utf-8")
            (directory / "output-schema.json").write_text(
                json.dumps(gate6.OUTPUT_SCHEMA), encoding="utf-8"
            )
            (directory / "tasks.jsonl").write_text(
                json.dumps(fixture["tasks"][0]) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SystemExit, "catalog hash mismatch"):
                gate6.rescore_existing(directory)

    def test_rescore_rejects_unpaired_records(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name) / "evidence"
            shutil.copytree(source, directory)
            path = directory / "skillloader.jsonl"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "do not match tasks.jsonl"):
                gate6.rescore_existing(directory)

    def test_rescore_rebuilds_derived_fields_from_events(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name) / "evidence"
            shutil.copytree(source, directory)
            eager_path = directory / "eager.jsonl"
            records = gate6.read_jsonl(eager_path)
            records[0]["final_response"] = {"selected_names": ["tampered"]}
            records[0]["usage"] = {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "reasoning_output_tokens": 0,
            }
            records[0]["payload_token_estimates"] = {
                "prompt_cl100k": 999,
                "search_results_cl100k": 999,
                "load_results_cl100k": 999,
            }
            gate6.write_jsonl(eager_path, records)

            gate6.rescore_existing(directory)

            rescored = gate6.read_jsonl(eager_path)[0]
            self.assertEqual(
                rescored["final_response"], gate6.final_response(rescored["events"])
            )
            self.assertEqual(rescored["usage"], gate6.usage_from(rescored["events"]))
            self.assertNotEqual(
                rescored["payload_token_estimates"]["prompt_cl100k"], 999
            )
            developer_config = next(
                argument
                for argument in rescored["argv_without_prompt"]
                if argument.startswith("developer_instructions=")
            )
            self.assertIn("</skill>", developer_config)
            self.assertNotIn("<<ABS_PATH>>", developer_config)

    def test_rescore_records_prior_scoring_fixture_hash(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            directory = root / "evidence"
            shutil.copytree(source, directory)
            environment_before = gate6.read_json(directory / "environment.json")
            prior_hash = environment_before["runner"]["scoring_fixture_sha256"]

            fixture = json.loads(gate6.TASKS_PATH.read_text(encoding="utf-8"))
            fixture["tasks"][0]["alternatives"] = ["contract-auditor"]
            fixture_path = root / "bench" / "tasks" / "task-fixture-v1.json"
            fixture_path.parent.mkdir(parents=True)
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
            current_hash = gate6.sha256_bytes(fixture_path.read_bytes())

            with (
                patch.object(gate6, "REPO", root),
                patch.object(gate6, "TASKS_PATH", fixture_path),
            ):
                gate6.rescore_existing(directory)

            environment_after = gate6.read_json(directory / "environment.json")
            runner = environment_after["runner"]
            self.assertEqual(runner["scoring_fixture_sha256"], current_hash)
            self.assertIn(prior_hash, runner["prior_scoring_fixture_sha256"])

    def test_rescore_summary_uses_current_scoring_task(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            directory = root / "evidence"
            shutil.copytree(source, directory)
            fixture = json.loads(gate6.TASKS_PATH.read_text(encoding="utf-8"))
            task = next(task for task in fixture["tasks"] if task["id"] == "korean-02")
            task.update(
                expected_top=None,
                required_names=[],
                alternatives=[],
                no_load=True,
                load_count=0,
            )
            fixture_path = root / "bench" / "tasks" / "task-fixture-v1.json"
            fixture_path.parent.mkdir(parents=True)
            fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

            with (
                patch.object(gate6, "REPO", root),
                patch.object(gate6, "TASKS_PATH", fixture_path),
            ):
                gate6.rescore_existing(directory)

            summary = gate6.read_json(directory / "summary.json")
            self.assertEqual(summary["modes"]["eager"]["quality"]["no_load_total"], 3)
            self.assertEqual(
                summary["modes"]["skillloader"]["quality"]["no_load_total"], 3
            )

    def test_rescore_rejects_output_schema_tampering(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name) / "evidence"
            shutil.copytree(source, directory)
            schema_path = directory / "output-schema.json"
            schema = gate6.read_json(schema_path)
            schema["required"] = []
            schema_path.write_text(json.dumps(schema), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "output schema mismatch"):
                gate6.rescore_existing(directory)

    def test_rescore_rejects_invocation_argument_tampering(self) -> None:
        source = (
            gate6.REPO / "bench" / "results" / "2026-07-21-codex-0.144.6-gate6-isolated"
        )
        with tempfile.TemporaryDirectory() as temp_name:
            directory = Path(temp_name) / "evidence"
            shutil.copytree(source, directory)
            path = directory / "eager.jsonl"
            records = gate6.read_jsonl(path)
            model_index = records[0]["argv_without_prompt"].index("-m") + 1
            records[0]["argv_without_prompt"][model_index] = "different-model"
            gate6.write_jsonl(path, records)
            with self.assertRaisesRegex(SystemExit, "invocation arguments mismatch"):
                gate6.rescore_existing(directory)


if __name__ == "__main__":
    unittest.main()
