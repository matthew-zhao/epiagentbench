from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest


class V32PublicationTopologyTests(unittest.TestCase):
    V31_CLOSEOUT_COMMIT = "9c354164347f2b09a7656171ef5cbc7480111c6e"
    V32_CONTROL_COMMIT = "c6cd10e795944e08e76a6de249689d1a5538099b"
    V32_CONTROL_TREE = "e8336b16bdb6384a64eecb583377cc664e2adf4e"
    V32_LOCAL_RUNTIME_COMMIT = "1ffd2f2903cb7a8327ff0ef7a0f10870e1a27e3b"
    V32_CLOSEOUT_COMMIT = "f26d8f7e50748883142f3452ee11daf43595e421"
    V32_CLOSEOUT_TREE = "2daa94031f3d34cf5b4283928c3523af7ee758c4"
    V32_CLOSEOUT_SCOPE = {
        "results/development-matched-50x6-v32.superseded.json",
        "tests/test_v32_supersession.py",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runbook = (cls.root / "docs" / "V32_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.supersession = json.loads(
            (
                cls.root
                / "results"
                / "development-matched-50x6-v32.superseded.json"
            ).read_text(encoding="utf-8")
        )

    @classmethod
    def _git(cls, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=cls.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def test_control_commit_has_exact_public_parent_and_tree(self) -> None:
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V32_CONTROL_COMMIT),
            self.V31_CLOSEOUT_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V32_CONTROL_COMMIT),
            self.V32_CONTROL_TREE,
        )

    def test_terminal_closeout_has_exact_parent_tree_and_two_file_delta(
        self,
    ) -> None:
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V32_CLOSEOUT_COMMIT),
            self.V32_CONTROL_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V32_CLOSEOUT_COMMIT),
            self.V32_CLOSEOUT_TREE,
        )
        changed = set(
            self._git(
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                self.V32_CLOSEOUT_COMMIT,
            ).splitlines()
        )
        self.assertEqual(changed, self.V32_CLOSEOUT_SCOPE)

    def test_unpublished_runtime_is_absent_without_requiring_its_object(
        self,
    ) -> None:
        ancestry = set(self._git("rev-list", self.V32_CLOSEOUT_COMMIT).splitlines())
        self.assertNotIn(self.V32_LOCAL_RUNTIME_COMMIT, ancestry)
        tree = set(
            self._git(
                "ls-tree", "-r", "--name-only", self.V32_CLOSEOUT_COMMIT
            ).splitlines()
        )
        for forbidden in (
            "results/development-matched-50x6-v32.runtime.json",
            "results/development-matched-50x6-v32.manifest.json",
            "results/development-matched-50x6-v32.authentication.json",
            "results/development-matched-50x6-v32.preflight.json",
            "results/development-matched-50x6-v32.json",
        ):
            self.assertNotIn(forbidden, tree)

    def test_supersession_records_zero_call_terminal_publication(self) -> None:
        self.assertEqual(
            self.supersession["schema_version"],
            "epiagentbench.panel_supersession.v25",
        )
        self.assertEqual(
            self.supersession["status"],
            "failed_zero_model_runtime_receipt_publication",
        )
        self.assertEqual(self.supersession["gitbutler_publication_attempts"], 1)
        self.assertIs(self.supersession["remote_ref_mutation_observed"], False)
        self.assertIs(self.supersession["publication_retry_permitted"], False)
        self.assertIs(self.supersession["resumption_permitted"], False)
        self.assertEqual(self.supersession["authentication_processes_started"], 0)
        self.assertEqual(self.supersession["provider_processes_started"], 0)
        self.assertEqual(self.supersession["model_calls_started"], 0)

    def test_runbook_is_terminal_and_points_only_forward_to_v34(self) -> None:
        self.assertIn(
            "V32 IS TERMINAL AND NON-RESUMABLE. DO NOT EXECUTE ANY CEREMONY BELOW.",
            self.runbook,
        )
        self.assertIn(self.V32_CLOSEOUT_COMMIT, self.runbook)
        self.assertIn("47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d", self.runbook)
        self.assertIn("[V34 runbook](V34_RUNBOOK.md)", self.runbook)
        self.assertIn("authorize no retry, repair, reuse", self.runbook)


if __name__ == "__main__":
    unittest.main()
