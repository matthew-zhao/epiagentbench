from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


class V35PublicationTopologyTests(unittest.TestCase):
    V34_CONTROL_COMMIT = "72ca992eed6c0faa5961d4063732a8a1da918301"
    V34_CONTROL_TREE = "8bf73a9753b1b0ea8d5dc2f7e230494a13fd0f47"
    V33_CLOSEOUT_COMMIT = "47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d"
    V34_CLOSEOUT_COMMIT = "038794aa1bf82440259c62afdabab44c01415978"
    V34_CLOSEOUT_TREE = "fc562ee84d81d51e7186f9186d67bea0d329f39c"
    V33_UNPUBLISHED_CONTROL_COMMIT = (
        "dac82434f2e2a73d511df418755b28003222ab3b"
    )
    V34_CLOSEOUT_REF = (
        "refs/heads/codex/v34-runtime-publication-terminal-closeout"
    )
    V35_CONTROL_REF = "refs/heads/codex/v35-control-plane"
    ACKNOWLEDGEMENT_SHA256 = (
        "d4afd8238eeb000c25a124936400102d97e327d0624b1b5059c26b0de1fd8bc0"
    )

    CONTROL_SCOPE = frozenset(
        {
            "README.md",
            "docs/PERSISTENT_RUNNER_PROTOCOL.md",
            "docs/V34_RUNBOOK.md",
            "docs/V35_DESIGN.md",
            "docs/V35_RUNBOOK.md",
            "src/epiagentbench/development_matched_panel.py",
            "src/epiagentbench/launchd_agent.py",
            "tests/test_development_matched_panel.py",
            "tests/test_persistent_launchd.py",
            "tests/test_persistent_runner_cli.py",
            "tests/test_terminal_receipt_attestation.py",
            "tests/test_v28_typed_contract_attestation.py",
            "tests/test_v35_deferred_cursor_credential.py",
            "tests/test_v35_preclaim_reconciliation.py",
            "tests/test_v35_preparation_substages.py",
            "tests/test_v35_publication_topology.py",
            "tests/test_v35_smoke_tmpdir.py",
        }
    )
    INHERITED_CLOSEOUT_SHA256 = {
        "results/development-matched-50x6-v34.superseded.json": (
            "51a29ae770e762f74a0e9ffcbc738ea82ae424adf02cd27f4e46dc6b27c9d54c"
        ),
        "tests/test_v34_supersession.py": (
            "46fb5905bffa72684311a4d42c7b2d869e4ddbabc51ea0677e592f702cedb6f3"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runbook = (cls.root / "docs" / "V35_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        cls.design = (cls.root / "docs" / "V35_DESIGN.md").read_text(
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
        self.assertEqual(len(self.CONTROL_SCOPE), 17)
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V34_CONTROL_COMMIT)
            .stdout.strip(),
            self.V33_CLOSEOUT_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V34_CONTROL_COMMIT)
            .stdout.strip(),
            self.V34_CONTROL_TREE,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%P", self.V34_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V34_CONTROL_COMMIT,
        )
        self.assertEqual(
            self._git("show", "-s", "--format=%T", self.V34_CLOSEOUT_COMMIT)
            .stdout.strip(),
            self.V34_CLOSEOUT_TREE,
        )
        for relative, expected in self.INHERITED_CLOSEOUT_SHA256.items():
            self.assertEqual(
                hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
                expected,
                relative,
            )

        v34 = json.loads(
            (
                self.root
                / "results"
                / "development-matched-50x6-v34.superseded.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            v34["schema_version"], "epiagentbench.panel_supersession.v27"
        )
        self.assertEqual(v34["control_commit"], self.V34_CONTROL_COMMIT)
        self.assertEqual(
            v34["terminal_closeout_required_parent_commit"],
            self.V34_CONTROL_COMMIT,
        )
        self.assertEqual(
            v34["replacement_panel_id"], "development-matched-50x6-v35"
        )
        for value in (
            self.V34_CLOSEOUT_COMMIT,
            self.V34_CLOSEOUT_REF,
            "epiagentbench.panel_supersession.v27",
        ):
            self.assertIn(value, self.all_flat)

    def test_v35_acknowledgement_and_provider_contract_are_exact(self) -> None:
        source_path = (
            self.root / "src" / "epiagentbench" / "development_matched_panel.py"
        )
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(source_path))
        acknowledgement: str | None = None
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name)
                and target.id == "REQUIRED_SPEND_ACKNOWLEDGEMENT"
                for target in node.targets
            ):
                candidate = ast.literal_eval(node.value)
                if not isinstance(candidate, str):
                    self.fail("V35 acknowledgement must be a string")
                acknowledgement = candidate
                break
        self.assertIsNotNone(acknowledgement)
        self.assertEqual(
            hashlib.sha256(acknowledgement.encode("utf-8")).hexdigest(),
            self.ACKNOWLEDGEMENT_SHA256,
        )
        self.assertIn(self.ACKNOWLEDGEMENT_SHA256, self.runbook)
        self.assertIn(
            '"schema_version": "epiagentbench.provider_cli_contract.v3"',
            source,
        )
        self.assertIn("epiagentbench.provider_cli_contract.v3", self.all_flat)

    def test_v35_staged_ref_has_exactly_four_ordered_one_file_receipts(self) -> None:
        self.assertIn(
            "exactly four one-file commits in order: runtime receipt, manifest, "
            "sanitized authentication receipt, and passing preflight receipt",
            self.design_flat,
        )
        for row in (
            "| Runtime-receipt ref | `refs/heads/codex/v35-runtime-preflight` |",
            "| Manifest publication ref | `refs/heads/codex/v35-runtime-preflight` |",
            "| Authentication publication ref | `refs/heads/codex/v35-runtime-preflight` |",
            "| Preflight publication ref | `refs/heads/codex/v35-runtime-preflight` |",
        ):
            self.assertIn(row, self.runbook)
        self.assertIn(
            "That same staged public-receipt ref then advances through exactly "
            "three more one-file commits",
            self.runbook_flat,
        )

    def test_v35_publication_refs_are_closed_and_mutually_exclusive(self) -> None:
        expected_refs = {
            "refs/heads/codex/v35-control-plane",
            "refs/heads/codex/v35-control-plane-publication-terminal-closeout",
            "refs/heads/codex/v35-runtime-preflight",
            "refs/heads/codex/v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v35-preflight-terminal-closeout",
            "refs/heads/codex/v35-production-results",
            "refs/heads/codex/v35-terminal-closeout",
        }
        observed_refs = set(
            re.findall(r"refs/heads/codex/v35-[a-z-]+", self.runbook)
        )
        self.assertEqual(observed_refs, expected_refs)
        self.assertIn(
            "These five terminal or outcome paths are mutually exclusive",
            self.runbook_flat,
        )
        self.assertIn(
            "is mutually exclusive with every later V35 ref",
            self.design_flat,
        )

    def test_control_publication_gate_is_one_shot_and_hook_preserving(self) -> None:
        for fragment in (
            "fresh standalone primary clone",
            "matthew-zhao",
            "boolean push permission",
            "one named `but push codex/v35-control-plane`",
            "failure or ambiguity is terminal",
            "never retried",
            "core.hooksPath` remains unset",
            "4d4892f5df8d68688d564b08a9b7ab990ee1af49f85250e94bb9e088f23c5728",
            "9bc3e13271e9bbbebdcb4543cc051e869f10c7a8219e1bff807595e52b345afc",
        ):
            self.assertIn(fragment.lower(), self.all_flat.lower())
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v35-control-plane-workspace",
            self.runbook,
        )

    def test_every_publication_has_exact_publisher_and_named_push(self) -> None:
        expected = {
            "control-plane-publication-terminal-closeout": (
                "epiagentbench-v35-control-plane-publication-terminal-closeout-workspace"
            ),
            "runtime-preflight": "epiagentbench-v35-runtime-preflight-workspace",
            "runtime-publication-terminal-closeout": (
                "epiagentbench-v35-runtime-publication-terminal-closeout-workspace"
            ),
            "preflight-terminal-closeout": (
                "epiagentbench-v35-preflight-terminal-closeout-workspace"
            ),
            "production-results": "epiagentbench-v35-production-results-workspace",
            "terminal-closeout": "epiagentbench-v35-terminal-closeout-workspace",
        }
        for branch, workspace in expected.items():
            self.assertIn(
                "/Users/matthew.zhao/Documents/Disease Surveillance/" + workspace,
                self.runbook,
            )
            self.assertIn(f"`but push codex/v35-{branch}`", self.runbook)
        self.assertIn(
            "only publication command for the control-plane phase",
            self.runbook_flat,
        )
        self.assertIn(
            "one separately authorized invocation for each of its four ordered "
            "one-file commits",
            self.runbook_flat,
        )
        self.assertIn(
            "A failed or ambiguous named push is terminal and must not be retried",
            self.runbook_flat,
        )

    def test_prepublication_gate_is_executable_and_fail_closed(self) -> None:
        begin = "# V35_PREPUBLICATION_GATE_BEGIN"
        end = "# V35_PREPUBLICATION_GATE_END"
        self.assertEqual(self.runbook.count(begin), 1)
        self.assertEqual(self.runbook.count(end), 1)
        gate = self.runbook.split(begin, 1)[1].split(end, 1)[0]
        syntax = subprocess.run(
            ["/bin/zsh", "-n"],
            input=gate,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        for fragment in (
            "V35_DESTINATION_REF='refs/heads/codex/v35-control-plane'",
            "V35_EXPECTED_REMOTE_TIP=absent",
            "remote get-url origin",
            "status --porcelain=v1",
            "auth switch --hostname github.com --user matthew-zhao",
            "api user --jq .login",
            "--jq .permissions.push",
            "--get core.hooksPath",
            ".git/hooks/pre-commit",
            ".git/hooks/post-checkout",
            "git ls-remote --refs",
            "[[ -z \"$V35_REMOTE_RECORDS\" ]]",
            "$'\\t'",
            "v35_prepublication_gate=passed",
        ):
            self.assertIn(fragment, gate)
        self.assertIn(
            "must never print a token, credential-helper response, OAuth state",
            self.runbook_flat,
        )
        self.assertIn(
            "fails closed before `but push`",
            self.runbook_flat,
        )

    def test_postpublication_pin_gate_is_executable_and_fail_closed(
        self,
    ) -> None:
        begin = "# V35_POSTPUBLICATION_PIN_GATE_BEGIN"
        end = "# V35_POSTPUBLICATION_PIN_GATE_END"
        self.assertEqual(self.runbook.count(begin), 1)
        self.assertEqual(self.runbook.count(end), 1)
        gate = self.runbook.split(begin, 1)[1].split(end, 1)[0]
        syntax = subprocess.run(
            ["/bin/zsh", "-n"],
            input=gate,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        mappings = {
            "control": (
                "refs/heads/codex/v35-control-plane",
                "epiagentbench-50x6-v35-runtime-worktree",
            ),
            "runtime_receipt": (
                "refs/heads/codex/v35-runtime-preflight",
                "epiagentbench-50x6-v35-prepare-worktree",
            ),
            "manifest": (
                "refs/heads/codex/v35-runtime-preflight",
                "epiagentbench-50x6-v35-manifest-worktree",
            ),
            "authentication_receipt": (
                "refs/heads/codex/v35-runtime-preflight",
                "epiagentbench-50x6-v35-execution-worktree",
            ),
            "passing_preflight": (
                "refs/heads/codex/v35-runtime-preflight",
                "epiagentbench-50x6-v35-production-worktree",
            ),
            "control_publication_terminal_closeout": (
                "refs/heads/codex/v35-control-plane-publication-terminal-closeout",
                "epiagentbench-50x6-v35-release-worktree",
            ),
            "runtime_publication_terminal_closeout": (
                "refs/heads/codex/v35-runtime-publication-terminal-closeout",
                "epiagentbench-50x6-v35-release-worktree",
            ),
            "preflight_terminal_closeout": (
                "refs/heads/codex/v35-preflight-terminal-closeout",
                "epiagentbench-50x6-v35-release-worktree",
            ),
            "production_results": (
                "refs/heads/codex/v35-production-results",
                "epiagentbench-50x6-v35-release-worktree",
            ),
            "terminal_closeout": (
                "refs/heads/codex/v35-terminal-closeout",
                "epiagentbench-50x6-v35-release-worktree",
            ),
        }
        for phase, (ref, checkout) in mappings.items():
            self.assertIn(f"  {phase})", gate)
            self.assertIn(f"V35_PIN_REF='{ref}'", gate)
            self.assertIn(checkout, gate)
        for fragment in (
            "V35_PIN_PHASE=control",
            "git ls-remote --refs --exit-code",
            "V35_PIN_RECORD_BEFORE=$(v35_read_pin) || exit 72",
            "V35_PIN_SHA=${V35_PIN_RECORD_BEFORE%%$'\\t'*}",
            "[[ ${#V35_PIN_SHA} -eq 40 ]] || exit 72",
            "[[ \"$V35_PIN_SHA\" != *[!0-9a-f]* ]] || exit 72",
            '"${V35_PIN_SHA}"$\'\\t\'"${V35_PIN_REF}"',
            "rev-parse --show-toplevel",
            "remote get-url --all origin",
            "status --porcelain=v1",
            "rev-parse --verify 'HEAD^{commit}'",
            "V35_PIN_RECORD_AFTER=$(v35_read_pin) || exit 72",
            '[[ "$V35_PIN_RECORD_AFTER" == "$V35_PIN_RECORD_BEFORE" ]]',
            "v35_postpublication_pin_gate=passed",
            "v35_pinned_commit=%s",
        ):
            self.assertIn(fragment, gate)
        self.assertLess(
            gate.index("V35_PIN_RECORD_BEFORE=$(v35_read_pin)"),
            gate.index("rev-parse --show-toplevel"),
        )
        self.assertLess(
            gate.index("rev-parse --verify 'HEAD^{commit}'"),
            gate.index("V35_PIN_RECORD_AFTER=$(v35_read_pin)"),
        )
        self.assertNotIn("<checkout>", self.runbook)
        self.assertIn(
            "The second independent query must be byte-for-byte identical "
            "to the first",
            self.runbook_flat,
        )

    def test_runtime_receipt_publisher_is_fresh_and_control_bound(self) -> None:
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v35-runtime-preflight-workspace",
            self.runbook,
        )
        self.assertIn(
            "rooted exactly at the independently pinned V35 control commit",
            self.runbook_flat,
        )
        self.assertIn(
            "The path and receipt destination must be absent before creation",
            self.runbook_flat,
        )

    def test_terminal_parent_and_file_scope_rules_are_exact(self) -> None:
        supersession = "results/development-matched-50x6-v35.superseded.json"
        contract_test = "tests/test_v35_supersession.py"
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
            f"as the direct child of `{self.V34_CLOSEOUT_COMMIT}`",
            self.design_flat,
        )
        self.assertIn(
            f"sole parent is `{self.V34_CLOSEOUT_COMMIT}`",
            self.design_flat,
        )
        self.assertIn(
            "may add only `results/development-matched-50x6-v35.superseded.json` "
            "and `tests/test_v35_supersession.py`",
            self.runbook_flat,
        )

    def test_future_commit_ids_remain_placeholders(self) -> None:
        expected_placeholders = {
            "<V35_CONTROL_COMMIT_40_HEX>",
            "<V35_CONTROL_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V35_RUNTIME_RECEIPT_COMMIT_40_HEX>",
            "<V35_MANIFEST_COMMIT_40_HEX>",
            "<V35_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>",
            "<V35_PREFLIGHT_RECEIPT_COMMIT_40_HEX>",
            "<V35_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V35_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V35_PRODUCTION_RESULT_COMMIT_40_HEX>",
            "<V35_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
        }
        observed = set(re.findall(r"<[A-Z0-9_]+_40_HEX>", self.runbook))
        self.assertEqual(observed, expected_placeholders)

    def test_v32_v33_and_v34_contracts_are_explicitly_rejected(self) -> None:
        for value in (
            "development-matched-50x6-v32",
            "development_matched_panel_v32",
            "development-matched-50x6-v33",
            "development_matched_panel_v33",
            "development-matched-50x6-v34",
            "development_matched_panel_v34",
            "epiagentbench.persistent_supervisor_contract.v17",
            "epiagentbench.persistent_supervisor_contract.v18",
            "epiagentbench.persistent_supervisor_contract.v19",
            "epiagentbench.persistent_supervisor_contract.v20",
        ):
            self.assertIn(value, self.all_flat)
        self.assertIn("burned", self.all_flat)
        self.assertIn("reject", self.all_flat)

    def test_committed_control_plane_has_exact_parent_scope_and_ancestry(self) -> None:
        test_path = "tests/test_v35_publication_topology.py"
        if self._git("ls-files", "--error-unmatch", test_path, check=False).returncode:
            self.skipTest("V35 control plane is not committed yet")

        control_commit = self._git(
            "log", "-1", "--format=%H", "--", test_path
        ).stdout.strip()
        self.assertEqual(
            self._git("show", "-s", "--format=%P", control_commit).stdout.strip(),
            self.V34_CLOSEOUT_COMMIT,
        )
        branch_tip = self._git("rev-parse", self.V35_CONTROL_REF).stdout.strip()
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
            "results/development-matched-50x6-v35.runtime.json",
            "results/development-matched-50x6-v35.manifest.json",
            "results/development-matched-50x6-v35.authentication.json",
            "results/development-matched-50x6-v35.preflight.json",
            "results/development-matched-50x6-v35.json",
            "results/development-matched-50x6-v35.superseded.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        ancestry = set(self._git("rev-list", control_commit).stdout.splitlines())
        self.assertNotIn(self.V33_UNPUBLISHED_CONTROL_COMMIT, ancestry)
        self.assertIn(self.V34_CLOSEOUT_COMMIT, ancestry)


if __name__ == "__main__":
    unittest.main()
