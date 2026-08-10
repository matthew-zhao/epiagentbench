from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


class V34PublicationTopologyTests(unittest.TestCase):
    V32_CONTROL_COMMIT = "c6cd10e795944e08e76a6de249689d1a5538099b"
    V32_CLOSEOUT_COMMIT = "f26d8f7e50748883142f3452ee11daf43595e421"
    V32_CLOSEOUT_TREE = "2daa94031f3d34cf5b4283928c3523af7ee758c4"
    V33_CLOSEOUT_COMMIT = "47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d"
    V33_CLOSEOUT_TREE = "f92c4d1a505598eb80118fa51b703d902ad6ace5"
    V33_UNPUBLISHED_CONTROL_COMMIT = (
        "dac82434f2e2a73d511df418755b28003222ab3b"
    )
    V33_CLOSEOUT_REF = (
        "refs/heads/codex/v33-control-plane-publication-terminal-closeout"
    )
    V34_CONTROL_REF = "refs/heads/codex/v34-control-plane"

    CONTROL_SCOPE = frozenset(
        {
            "README.md",
            "docs/PERSISTENT_RUNNER_PROTOCOL.md",
            "docs/V32_RUNBOOK.md",
            "docs/V34_DESIGN.md",
            "docs/V34_RUNBOOK.md",
            "src/epiagentbench/development_matched_panel.py",
            "src/epiagentbench/launchd_agent.py",
            "tests/test_development_matched_panel.py",
            "tests/test_persistent_launchd.py",
            "tests/test_persistent_runner_cli.py",
            "tests/test_terminal_receipt_attestation.py",
            "tests/test_v28_typed_contract_attestation.py",
            "tests/test_v31_supersession.py",
            "tests/test_v32_publication_topology.py",
            "tests/test_v34_deferred_cursor_credential.py",
            "tests/test_v34_preclaim_reconciliation.py",
            "tests/test_v34_preparation_substages.py",
            "tests/test_v34_publication_topology.py",
            "tests/test_v34_smoke_tmpdir.py",
        }
    )
    INHERITED_CLOSEOUT_SHA256 = {
        "results/development-matched-50x6-v32.superseded.json": (
            "63698df2197842ae3a6c8b59be3d89679a7273cd5a8000d13f826ae246a5cdb7"
        ),
        "tests/test_v32_supersession.py": (
            "bca340269fb87f45af27ece44f3bc3252f819e3e6e13e89ff0f4adf8d4ef289d"
        ),
        "results/development-matched-50x6-v33.superseded.json": (
            "9edf0b6415f7cada2546c0c9fe56942055db37e023a7c4c86cb8a9230cf439e6"
        ),
        "tests/test_v33_supersession.py": (
            "7aa5054b00039204fd87301b418e26ef4c81e1a233bab4e70f353836862b2ae3"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runbook = (cls.root / "docs" / "V34_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.design = (cls.root / "docs" / "V34_DESIGN.md").read_text(
            encoding="utf-8"
        )
        cls.runbook_flat = re.sub(r"\s+", " ", cls.runbook)
        cls.design_flat = re.sub(r"\s+", " ", cls.design)
        cls.all_flat = cls.runbook_flat + " " + cls.design_flat

    @classmethod
    def _git(cls, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cls.root,
            check=check,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def test_public_predecessors_and_closeout_bytes_are_exact(self) -> None:
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V32_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V32_CONTROL_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V32_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V32_CLOSEOUT_TREE,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V33_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V32_CLOSEOUT_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V33_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V33_CLOSEOUT_TREE,
        )
        for relative, expected in self.INHERITED_CLOSEOUT_SHA256.items():
            self.assertEqual(
                hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
                expected,
                relative,
            )

        v32 = json.loads(
            (
                self.root
                / "results"
                / "development-matched-50x6-v32.superseded.json"
            ).read_text(encoding="utf-8")
        )
        v33 = json.loads(
            (
                self.root
                / "results"
                / "development-matched-50x6-v33.superseded.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(v32["schema_version"], "epiagentbench.panel_supersession.v25")
        self.assertEqual(v33["schema_version"], "epiagentbench.panel_supersession.v26")
        self.assertEqual(v33["terminal_closeout_required_parent_commit"], self.V32_CLOSEOUT_COMMIT)

    def test_v34_staged_ref_has_exactly_four_ordered_one_file_receipts(self) -> None:
        self.assertIn(
            "exactly four one-file commits in order: runtime receipt, manifest, "
            "sanitized authentication receipt, and passing preflight receipt",
            self.design_flat,
        )
        for row in (
            "| Runtime-receipt ref | `refs/heads/codex/v34-runtime-preflight` |",
            "| Manifest publication ref | `refs/heads/codex/v34-runtime-preflight` |",
            "| Authentication publication ref | `refs/heads/codex/v34-runtime-preflight` |",
            "| Preflight publication ref | `refs/heads/codex/v34-runtime-preflight` |",
        ):
            self.assertIn(row, self.runbook)
        self.assertIn(
            "That same staged public-receipt ref then advances through exactly "
            "three more one-file commits",
            self.runbook_flat,
        )

    def test_v34_publication_refs_are_closed_and_mutually_exclusive(self) -> None:
        expected_refs = {
            "refs/heads/codex/v34-control-plane",
            "refs/heads/codex/v34-control-plane-publication-terminal-closeout",
            "refs/heads/codex/v34-runtime-preflight",
            "refs/heads/codex/v34-runtime-publication-terminal-closeout",
            "refs/heads/codex/v34-preflight-terminal-closeout",
            "refs/heads/codex/v34-production-results",
            "refs/heads/codex/v34-terminal-closeout",
        }
        observed_refs = set(
            re.findall(r"refs/heads/codex/v34-[a-z-]+", self.runbook)
        )
        self.assertEqual(observed_refs, expected_refs)
        self.assertIn(
            "These five terminal or outcome paths are mutually exclusive",
            self.runbook_flat,
        )
        self.assertIn(
            "is mutually exclusive with every later V34 ref",
            self.design_flat,
        )

    def test_control_publication_gate_is_one_shot_and_hook_preserving(self) -> None:
        for fragment in (
            "fresh standalone primary clone",
            "matthew-zhao",
            "boolean push permission",
            "one named `but push codex/v34-control-plane`",
            "failure or ambiguity is terminal",
            "never retried",
            "core.hooksPath` remains unset",
            "4d4892f5df8d68688d564b08a9b7ab990ee1af49f85250e94bb9e088f23c5728",
            "9bc3e13271e9bbbebdcb4543cc051e869f10c7a8219e1bff807595e52b345afc",
        ):
            self.assertIn(fragment.lower(), self.all_flat.lower())
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v34-control-plane-workspace",
            self.runbook,
        )

    def test_runtime_receipt_publisher_is_fresh_and_control_bound(self) -> None:
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v34-runtime-preflight-workspace",
            self.runbook,
        )
        self.assertIn(
            "rooted exactly at the independently pinned V34 control commit",
            self.runbook_flat,
        )
        self.assertIn(
            "The path and receipt destination must be absent before creation",
            self.runbook_flat,
        )

    def test_terminal_parent_and_file_scope_rules_are_exact(self) -> None:
        supersession = "results/development-matched-50x6-v34.superseded.json"
        contract_test = "tests/test_v34_supersession.py"
        for path in (supersession, contract_test):
            self.assertIn(path, self.runbook)
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
            "may add only `results/development-matched-50x6-v34.superseded.json` "
            "and `tests/test_v34_supersession.py`",
            self.runbook_flat,
        )

    def test_future_commit_ids_remain_placeholders(self) -> None:
        expected_placeholders = {
            "<V34_CONTROL_COMMIT_40_HEX>",
            "<V34_CONTROL_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V34_RUNTIME_RECEIPT_COMMIT_40_HEX>",
            "<V34_MANIFEST_COMMIT_40_HEX>",
            "<V34_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>",
            "<V34_PREFLIGHT_RECEIPT_COMMIT_40_HEX>",
            "<V34_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V34_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V34_PRODUCTION_RESULT_COMMIT_40_HEX>",
            "<V34_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
        }
        observed = set(re.findall(r"<[A-Z0-9_]+_40_HEX>", self.runbook))
        self.assertEqual(observed, expected_placeholders)

    def test_burned_v32_and_v33_contracts_are_explicitly_rejected(self) -> None:
        for value in (
            "development-matched-50x6-v32",
            "development_matched_panel_v32",
            "development-matched-50x6-v33",
            "development_matched_panel_v33",
            "epiagentbench.persistent_supervisor_contract.v17",
            "epiagentbench.persistent_supervisor_contract.v18",
            "epiagentbench.persistent_supervisor_contract.v19",
        ):
            self.assertIn(value, self.all_flat)
        self.assertIn("burned", self.all_flat)
        self.assertIn("reject", self.all_flat)

    def test_committed_control_plane_has_exact_parent_scope_and_ancestry(self) -> None:
        test_path = "tests/test_v34_publication_topology.py"
        if self._git("ls-files", "--error-unmatch", test_path, check=False).returncode:
            self.skipTest("V34 control plane is not committed yet")

        control_commit = self._git(
            "log", "-1", "--format=%H", "--", test_path
        ).stdout.strip()
        self.assertEqual(
            self._git("show", "-s", "--format=%P", control_commit).stdout.strip(),
            self.V33_CLOSEOUT_COMMIT,
        )
        branch_tip = self._git("rev-parse", self.V34_CONTROL_REF).stdout.strip()
        self.assertEqual(control_commit, branch_tip)

        changed_paths = frozenset(
            self._git(
                "diff-tree", "--no-commit-id", "--name-only", "-r", control_commit
            ).stdout.splitlines()
        )
        self.assertEqual(changed_paths, self.CONTROL_SCOPE)

        tree_paths = frozenset(
            self._git("ls-tree", "-r", "--name-only", control_commit).stdout.splitlines()
        )
        for forbidden_path in (
            "docs/V33_DESIGN.md",
            "docs/V33_RUNBOOK.md",
            "tests/test_v33_deferred_cursor_credential.py",
            "tests/test_v33_preclaim_reconciliation.py",
            "tests/test_v33_preparation_substages.py",
            "tests/test_v33_publication_topology.py",
            "tests/test_v33_smoke_tmpdir.py",
            "results/development-matched-50x6-v34.runtime.json",
            "results/development-matched-50x6-v34.manifest.json",
            "results/development-matched-50x6-v34.authentication.json",
            "results/development-matched-50x6-v34.preflight.json",
            "results/development-matched-50x6-v34.json",
            "results/development-matched-50x6-v34.superseded.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        ancestry = set(self._git("rev-list", control_commit).stdout.splitlines())
        self.assertNotIn(self.V33_UNPUBLISHED_CONTROL_COMMIT, ancestry)


if __name__ == "__main__":
    unittest.main()
