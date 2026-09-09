"""Unit tests for repository.recon -- packet building and report validation.

No git dependency required (base_sha falls back to "unknown" outside a repo);
no model calls; no network.
"""
import tempfile
import unittest
from pathlib import Path

from agentsam_sdk.repository.recon import (
    PacketError,
    ReportError,
    build_task_packet,
    from_matches,
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
