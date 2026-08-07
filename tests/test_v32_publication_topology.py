from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest


class V32PublicationTopologyTests(unittest.TestCase):
    V31_CONTROL_COMMIT = "6efe0fa93e9c72946b48c22ab27a7fe6b41c199c"
    V31_LOCAL_RUNTIME_COMMIT = "4bb1cc37bceb8b8c723db4307eea595b28cc5bb4"
    V31_CLOSEOUT_REF = (
        "refs/heads/codex/v31-runtime-publication-terminal-closeout"
    )
    V32_CONTROL_REF = "refs/heads/codex/v32-control-plane"

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runbook = (cls.root / "docs" / "V32_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.design = (cls.root / "docs" / "V32_DESIGN.md").read_text(
            encoding="utf-8"
        )
        cls.v31_runbook = (
            cls.root / "docs" / "V31_RUNBOOK.md"
        ).read_text(encoding="utf-8")
        cls.runbook_flat = re.sub(r"\s+", " ", cls.runbook)
        cls.design_flat = re.sub(r"\s+", " ", cls.design)
        cls.all_flat = cls.runbook_flat + " " + cls.design_flat
        cls.v31_supersession = json.loads(
            (
                cls.root
                / "results"
                / "development-matched-50x6-v31.superseded.json"
            ).read_text(encoding="utf-8")
        )

    def test_v31_closeout_contract_excludes_the_unpublished_runtime(self) -> None:
        for document in (self.runbook, self.design, self.v31_runbook):
            self.assertIn(self.V31_CLOSEOUT_REF, document)
            self.assertIn(self.V31_CONTROL_COMMIT, document)
            self.assertIn(
                "results/development-matched-50x6-v31.superseded.json",
                document,
            )
            self.assertIn("tests/test_v31_supersession.py", document)
        self.assertEqual(
            self.v31_supersession["terminal_closeout_required_parent_commit"],
            self.V31_CONTROL_COMMIT,
        )
        self.assertIs(
            self.v31_supersession[
                "terminal_closeout_runtime_receipt_file_in_tree_permitted"
            ],
            False,
        )
        self.assertIs(
            self.v31_supersession[
                "terminal_closeout_unpublished_runtime_receipt_in_ancestry_permitted"
            ],
            False,
        )

    def test_v32_staged_ref_has_exactly_four_ordered_one_file_receipts(self) -> None:
        self.assertIn(
            "exactly four one-file commits in order: runtime receipt, manifest, "
            "sanitized authentication receipt, and passing preflight receipt",
            self.design_flat,
        )
        expected_rows = (
            "| Runtime-receipt ref | `refs/heads/codex/v32-runtime-preflight` |",
            "| Manifest publication ref | `refs/heads/codex/v32-runtime-preflight` |",
            (
                "| Authentication publication ref | "
                "`refs/heads/codex/v32-runtime-preflight` |"
            ),
            "| Preflight publication ref | `refs/heads/codex/v32-runtime-preflight` |",
        )
        for row in expected_rows:
            self.assertIn(row, self.runbook)
        self.assertIn(
            "That same staged public-receipt ref then advances through exactly "
            "three more one-file commits",
            self.runbook_flat,
        )

    def test_v32_publication_refs_are_closed_and_mutually_exclusive(self) -> None:
        expected_refs = {
            "refs/heads/codex/v32-control-plane",
            "refs/heads/codex/v32-runtime-preflight",
            "refs/heads/codex/v32-runtime-publication-terminal-closeout",
            "refs/heads/codex/v32-preflight-terminal-closeout",
            "refs/heads/codex/v32-production-results",
            "refs/heads/codex/v32-terminal-closeout",
        }
        observed_refs = set(
            re.findall(r"refs/heads/codex/v32-[a-z-]+", self.runbook)
        )
        self.assertEqual(observed_refs, expected_refs)
        self.assertIn(
            "These four terminal paths are mutually exclusive",
            self.runbook_flat,
        )
        self.assertIn(
            "The early terminal, preflight terminal, production success, and "
            "production terminal refs are mutually exclusive",
            self.design_flat,
        )

    def test_terminal_parent_rules_never_accept_local_or_provisional_state(
        self,
    ) -> None:
        self.assertIn(
            "whose sole parent is the last commit already independently pinned "
            "from the fixed origin",
            self.runbook_flat,
        )
        self.assertIn(
            "whose sole parent is the independently pinned "
            "authentication-receipt commit",
            self.runbook_flat,
        )
        self.assertIn(
            "whose sole parent is the passing preflight commit",
            self.runbook_flat,
        )
        self.assertIn(
            "A local branch, candidate, provisional object ID, publication "
            "output, or failed-to-pin remote value is never a parent or pin",
            self.runbook_flat,
        )
        self.assertIn(
            "Never fill a commit placeholder from local or provisional state",
            self.runbook,
        )

    def test_terminal_refs_have_exact_frozen_public_file_scopes(self) -> None:
        supersession = "results/development-matched-50x6-v32.superseded.json"
        preflight = "results/development-matched-50x6-v32.preflight.json"
        result = "results/development-matched-50x6-v32.json"
        contract_test = "tests/test_v32_supersession.py"
        for path in (supersession, preflight, result, contract_test):
            self.assertIn(path, self.runbook)

        self.assertIn(
            f"The early closeout adds only `{supersession}` and "
            f"`{contract_test}`",
            self.runbook_flat,
        )
        self.assertIn(
            f"That closeout adds only `{supersession}`, `{contract_test}`, "
            "and—only when the supervisor durably produced it—the canonical "
            f"trace-free closed preflight receipt at `{preflight}`",
            self.runbook_flat,
        )
        self.assertIn(
            "a failure before any preflight receipt has a two-file closeout; "
            "a failure with an existing closed preflight receipt has a "
            "three-file closeout",
            self.runbook_flat,
        )
        self.assertIn(
            f"Successful production publishes only the closed canonical "
            f"result `{result}`",
            self.runbook_flat,
        )
        self.assertIn(
            f"may add only the trace-free terminal result `{result}`, "
            f"`{supersession}`, and `{contract_test}`",
            self.runbook_flat,
        )

    def test_all_future_commit_ids_remain_explicit_placeholders(self) -> None:
        expected_placeholders = {
            "<V31_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V32_CONTROL_COMMIT_40_HEX>",
            "<V32_RUNTIME_RECEIPT_COMMIT_40_HEX>",
            "<V32_MANIFEST_COMMIT_40_HEX>",
            "<V32_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>",
            "<V32_PREFLIGHT_RECEIPT_COMMIT_40_HEX>",
            "<V32_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V32_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V32_PRODUCTION_RESULT_COMMIT_40_HEX>",
            "<V32_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
        }
        observed_placeholders = set(
            re.findall(r"<[A-Z0-9_]+_40_HEX>", self.runbook)
        )
        self.assertEqual(observed_placeholders, expected_placeholders)
        exact_commit_ids = set(
            re.findall(
                r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])",
                self.runbook + "\n" + self.design,
            )
        )
        self.assertEqual(exact_commit_ids, {self.V31_CONTROL_COMMIT})

    def test_no_retry_and_independent_pin_rules_are_explicit(self) -> None:
        for fragment in (
            "must not retry, repair, regenerate, republish, or advance",
            "Each commit pin is obtained independently from the fixed HTTPS origin",
            (
                "never from a local branch name or a value copied from the "
                "publication command"
            ),
            "each destination is absent before first use",
            "each operation is attempted at most once",
            "never resumed or repaired",
        ):
            self.assertIn(fragment.lower(), self.all_flat.lower())

    def test_committed_v32_control_plane_has_the_approved_parent_and_scope(
        self,
    ) -> None:
        test_path = "tests/test_v32_publication_topology.py"
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", test_path],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if tracked.returncode != 0:
            self.skipTest("V32 control plane is not committed yet")

        control_commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", test_path],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        control_ref = subprocess.run(
            ["git", "rev-parse", self.V32_CONTROL_REF],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        closeout_ref = subprocess.run(
            ["git", "rev-parse", self.V31_CLOSEOUT_REF],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(control_commit, control_ref)
        parents = subprocess.run(
            ["git", "show", "-s", "--format=%P", control_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(parents, closeout_ref)

        changed_paths = subprocess.run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                control_commit,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertTrue(changed_paths)
        for path in changed_paths:
            self.assertTrue(
                path == "README.md"
                or path.startswith(("docs/", "src/", "tests/")),
                path,
            )
        self.assertNotIn(
            "results/development-matched-50x6-v31.superseded.json",
            changed_paths,
        )
        self.assertNotIn("tests/test_v31_supersession.py", changed_paths)

        tree_paths = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", control_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v31.runtime.json",
            "results/development-matched-50x6-v32.runtime.json",
            "results/development-matched-50x6-v32.manifest.json",
            "results/development-matched-50x6-v32.authentication.json",
            "results/development-matched-50x6-v32.preflight.json",
            "results/development-matched-50x6-v32.json",
            "results/development-matched-50x6-v32.superseded.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        unpublished_is_ancestor = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                self.V31_LOCAL_RUNTIME_COMMIT,
                control_commit,
            ],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(unpublished_is_ancestor.returncode, 1)


if __name__ == "__main__":
    unittest.main()
