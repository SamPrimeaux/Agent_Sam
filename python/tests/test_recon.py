"""Unit tests for repository.recon -- packet building and report validation.

No git dependency required (base_sha falls back to "unknown" outside a repo);
no model calls; no network.
"""
import json
import tempfile
import unittest
from pathlib import Path

from agentsam_sdk.repository.recon import (
    PacketError,
    ReportError,
    build_task_packet,
    from_ast_grep,
    from_matches,
    from_ripgrep,
    validate_report,
)


class TestBuildTaskPacket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "backend").mkdir()
        (self.root / "backend" / "workflows.js").write_text(
            "\n".join(f"line {i}" for i in range(1, 201)), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_builds_bounded_packet_with_content(self):
        packet = build_task_packet(
            self.root,
            question="Does this file depend on workspace_id?",
            slices=[{"path": "backend/workflows.js", "start_line": 1, "end_line": 5}],
        )
        self.assertEqual(packet["schema_version"], 1)
        self.assertEqual(len(packet["slices"]), 1)
        self.assertEqual(packet["slices"][0]["content"], "line 1\nline 2\nline 3\nline 4\nline 5")
        self.assertEqual(packet["ceilings"]["max_follow_up_reads"], 2)
        self.assertTrue(packet["task_id"].startswith("recon-"))

    def test_rejects_missing_question(self):
        with self.assertRaises(PacketError):
            build_task_packet(self.root, question="  ", slices=[{"path": "backend/workflows.js"}])

    def test_rejects_more_than_five_slices(self):
        slices = [{"path": "backend/workflows.js"} for _ in range(6)]
        with self.assertRaises(PacketError):
            build_task_packet(self.root, question="q", slices=slices)

    def test_rejects_slice_outside_repo_root(self):
        with self.assertRaises(PacketError):
            build_task_packet(self.root, question="q", slices=[{"path": "../../etc/passwd"}])

    def test_rejects_missing_file(self):
        with self.assertRaises(PacketError):
            build_task_packet(self.root, question="q", slices=[{"path": "backend/nope.js"}])


class TestFromMatches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "backend").mkdir()
        for name in ("a.js", "b.js", "c.js", "d.js", "e.js", "f.js"):
            (self.root / "backend" / name).write_text(
                "\n".join(f"line {i}" for i in range(1, 51)), encoding="utf-8"
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_chunks_more_than_five_files_into_multiple_packets(self):
        # 6 files -> ceiling is 5 per packet -> 2 packets
        matches = [
            {"path": f"backend/{name}", "line": 10, "kind": "member"}
            for name in ("a.js", "b.js", "c.js", "d.js", "e.js", "f.js")
        ]
        packets = from_matches(self.root, question="q", matches=matches, task_id_prefix="wf")
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0]["task_id"], "wf-1of2")
        self.assertEqual(packets[1]["task_id"], "wf-2of2")
        total_slices = sum(len(p["slices"]) for p in packets)
        self.assertEqual(total_slices, 6)
        for p in packets:
            self.assertLessEqual(len(p["slices"]), 5)

    def test_groups_multiple_hits_in_one_file_into_one_windowed_slice(self):
        matches = [
            {"path": "backend/a.js", "line": 5, "kind": "sql_string"},
            {"path": "backend/a.js", "line": 20, "kind": "sql_string"},
        ]
        packets = from_matches(self.root, question="q", matches=matches, context_lines=2)
        slice_ = packets[0]["slices"][0]
        self.assertEqual(slice_["start_line"], 3)
        self.assertEqual(slice_["end_line"], 22)
        self.assertEqual(slice_["hit_count"], 2)
        self.assertEqual(slice_["kind"], "sql_string")

    def test_rejects_empty_matches(self):
        with self.assertRaises(PacketError):
            from_matches(self.root, question="q", matches=[])


class TestFromRipgrep(unittest.TestCase):
    def test_parses_ndjson_match_lines_only(self):
        # Real `rg --json` shape: begin/match/end/summary records per file.
        ndjson = "\n".join([
            json.dumps({"type": "begin", "data": {"path": {"text": "backend/http/workflows/scope.js"}}}),
            json.dumps({
                "type": "match",
                "data": {
                    "path": {"text": "backend/http/workflows/scope.js"},
                    "line_number": 66,
                    "lines": {"text": "  body.workspace_id\n"},
                },
            }),
            json.dumps({"type": "end", "data": {"path": {"text": "backend/http/workflows/scope.js"}}}),
            json.dumps({"type": "summary", "data": {}}),
        ])
        hits = from_ripgrep(ndjson)
        self.assertEqual(hits, [{"path": "backend/http/workflows/scope.js", "line": 66}])

    def test_accepts_a_list_of_lines_too(self):
        lines = [json.dumps({"type": "match", "data": {"path": {"text": "a.js"}, "line_number": 1}})]
        self.assertEqual(from_ripgrep(lines), [{"path": "a.js", "line": 1}])

    def test_empty_input_yields_no_hits(self):
        self.assertEqual(from_ripgrep(""), [])

    def test_rejects_malformed_json_line(self):
        with self.assertRaises(PacketError):
            from_ripgrep("not json")


class TestFromAstGrep(unittest.TestCase):
    def test_parses_compact_json_array_with_caller_supplied_kind(self):
        # Real `sg -p '...' --json=compact` shape.
        raw = json.dumps([
            {
                "text": "body.workspace_id",
                "range": {"start": {"line": 66, "column": 76}, "end": {"line": 66, "column": 93}},
                "file": "backend/http/workflows/scope.js",
            },
            {
                "text": "ctx.workspaceId",
                "range": {"start": {"line": 12, "column": 4}, "end": {"line": 12, "column": 19}},
                "file": "backend/workflows/handlers/tool.js",
            },
        ])
        hits = from_ast_grep(raw, kind="member")
        self.assertEqual(hits, [
            {"path": "backend/http/workflows/scope.js", "line": 66, "kind": "member"},
            {"path": "backend/workflows/handlers/tool.js", "line": 12, "kind": "member"},
        ])

    def test_kind_is_optional(self):
        raw = json.dumps([{"range": {"start": {"line": 1}}, "file": "a.js"}])
        self.assertEqual(from_ast_grep(raw), [{"path": "a.js", "line": 1}])

    def test_empty_array_yields_no_hits(self):
        self.assertEqual(from_ast_grep("[]"), [])

    def test_rejects_invalid_json(self):
        with self.assertRaises(PacketError):
            from_ast_grep("not json")

    def test_adapters_compose_into_from_matches(self):
        # The actual workflow: run several classified sg queries + one rg sweep,
        # concatenate, then chunk into packets -- same shape as the iMac smoke test.
        member_hits = from_ast_grep(
            json.dumps([{"range": {"start": {"line": 5}}, "file": "backend/a.js"}]), kind="member"
        )
        sql_hits = from_ast_grep(
            json.dumps([{"range": {"start": {"line": 20}}, "file": "backend/b.js"}]), kind="sql_string"
        )
        rg_hits = from_ripgrep(json.dumps({
            "type": "match", "data": {"path": {"text": "backend/c.js"}, "line_number": 8},
        }))
        combined = member_hits + sql_hits + rg_hits
        self.assertEqual(len(combined), 3)
        self.assertEqual({h["path"] for h in combined}, {"backend/a.js", "backend/b.js", "backend/c.js"})
        self.assertEqual(combined[2].get("kind"), None)  # rg hit carries no kind


class TestValidateReport(unittest.TestCase):
    def setUp(self):
        self.packet = {
            "task_id": "recon-abc123",
            "slices": [{"path": "backend/workflows.js"}],
        }

    def test_accepts_answered_report_citing_known_file(self):
        report = {
            "schema_version": 1,
            "task_id": "recon-abc123",
            "status": "answered",
            "findings": [
                {
                    "severity": "high",
                    "file": "backend/workflows.js",
                    "finding": "still queries workspace_id",
                }
            ],
        }
        self.assertEqual(validate_report(report, self.packet), report)

    def test_accepts_needs_context_with_reason(self):
        report = {
            "schema_version": 1,
            "task_id": "recon-abc123",
            "status": "needs_context",
            "reason": "definition of ensureWorkflowRun() not supplied",
        }
        self.assertEqual(validate_report(report, self.packet)["status"], "needs_context")

    def test_rejects_needs_context_without_reason(self):
        report = {"schema_version": 1, "task_id": "recon-abc123", "status": "needs_context"}
        with self.assertRaises(ReportError):
            validate_report(report, self.packet)

    def test_rejects_finding_that_cites_a_file_outside_the_packet(self):
        report = {
            "schema_version": 1,
            "task_id": "recon-abc123",
            "status": "answered",
            "findings": [
                {"severity": "high", "file": "backend/other.js", "finding": "made up"}
            ],
        }
        with self.assertRaises(ReportError):
            validate_report(report, self.packet)

    def test_rejects_task_id_mismatch(self):
        report = {"schema_version": 1, "task_id": "recon-different", "status": "needs_context", "reason": "x"}
        with self.assertRaises(ReportError):
            validate_report(report, self.packet)

    def test_rejects_invalid_severity(self):
        report = {
            "schema_version": 1,
            "task_id": "recon-abc123",
            "status": "answered",
            "findings": [
                {"severity": "critical", "file": "backend/workflows.js", "finding": "x"}
            ],
        }
        with self.assertRaises(ReportError):
            validate_report(report, self.packet)


if __name__ == "__main__":
    unittest.main()
