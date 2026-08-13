from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest


class V48PublicationTopologyTests(unittest.TestCase):
    V47_CLOSEOUT_COMMIT = "31928645baff6182852c9c88a393b6fcaa6be557"
    V47_CLOSEOUT_PARENT = "e8946a10997863412d4a2ec0113b72e066a73550"
    V47_CLOSEOUT_TREE = "e21dacbbfc859206a15c7dbbbb9feaf214ca78d5"
    V33_UNPUBLISHED_CONTROL_COMMIT = "dac82434f2e2a73d511df418755b28003222ab3b"
    V47_CLOSEOUT_REF = (
        "refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout"
    )
    V48_CONTROL_REF = "refs/heads/codex/v48-control-plane"
    ACKNOWLEDGEMENT_SHA256 = (
        "2521ee29ff8baaef2bdab86477e13ed7a384784aba62a76e27b9edac30bdea0f"
    )

    CONTROL_SCOPE = frozenset(
        {
            "README.md",
            "docs/PERSISTENT_RUNNER_PROTOCOL.md",
            "docs/V35_RUNBOOK.md",
            "docs/V48_DESIGN.md",
            "docs/V48_RUNBOOK.md",
            "src/epiagentbench/development_matched_panel.py",
            "src/epiagentbench/launchd_agent.py",
            "tests/test_development_matched_panel.py",
            "tests/test_persistent_launchd.py",
            "tests/test_persistent_runner_cli.py",
            "tests/test_terminal_receipt_attestation.py",
            "tests/test_v28_typed_contract_attestation.py",
            "tests/test_v48_deferred_cursor_credential.py",
            "tests/test_v48_preclaim_reconciliation.py",
            "tests/test_v48_preparation_substages.py",
            "tests/test_v48_publication_topology.py",
            "tests/test_v48_smoke_tmpdir.py",
        }
    )
    INHERITED_CLOSEOUT_SHA256 = {
        "results/development-matched-50x6-v35.superseded.json": (
            "843654f16c0bf7a2c461d229ff71a1f3bdf5e36a90ebc8da019d34f8dcf88cf0"
        ),
        "tests/test_v35_supersession.py": (
            "68c45bc342152249e48a2e529b0908e2b8ea287779e7709025a80d5334477042"
        ),
        "results/development-matched-50x6-v40.superseded.json": (
            "76f533598108bda5996fbabcf7e220d36ffc3675648db744a4dc4cad44dae611"
        ),
        "tests/test_v40_supersession.py": (
            "4ce9b0fdebfcc3e78aefd7cb3146ab44e0d3079eac04d343b9d71c756b840419"
        ),
        "results/development-matched-50x6-v46.superseded.json": (
            "b751588e905d133ea99c08d42668b50f9d658a1e622c5a6560611c19e052d7bc"
        ),
        "tests/test_v46_supersession.py": (
            "2622fdc4fca24ead7e1dfd510055991117c1872bea9757889262b6b001ce6406"
        ),
        "results/development-matched-50x6-v47.superseded.json": (
            "69950caf5327cee3523154ea8194f2f8b9b79321cc9f0bf529c876f04bd1c75a"
        ),
        "tests/test_v47_supersession.py": (
            "70a0f447ff7b4affbbfc2001c58c7492ff0249c97cb8023a46ba65ecbc793ab1"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runbook = (cls.root / "docs" / "V48_RUNBOOK.md").read_text(encoding="utf-8")
        cls.design = (cls.root / "docs" / "V48_DESIGN.md").read_text(encoding="utf-8")
        cls.runbook_flat = re.sub(r"\s+", " ", cls.runbook)
        cls.design_flat = re.sub(r"\s+", " ", cls.design)
        cls.all_text = cls.runbook + "\n" + cls.design
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
        for relative, expected in self.INHERITED_CLOSEOUT_SHA256.items():
            self.assertEqual(
                hashlib.sha256((self.root / relative).read_bytes()).hexdigest(),
                expected,
                relative,
            )

        v47 = json.loads(
            (
                self.root / "results" / "development-matched-50x6-v47.superseded.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(v47["schema_version"], "epiagentbench.panel_supersession.v31")
        self.assertEqual(
            v47["terminal_closeout_required_parent_commit"],
            self.V47_CLOSEOUT_PARENT,
        )
        self.assertEqual(v47["replacement_panel_id"], "development-matched-50x6-v48")
        self.assertEqual(v47["terminal_closeout_required_ref"], self.V47_CLOSEOUT_REF)
        for value in (
            self.V47_CLOSEOUT_COMMIT,
            self.V47_CLOSEOUT_PARENT,
            self.V47_CLOSEOUT_TREE,
            self.V47_CLOSEOUT_REF,
            "epiagentbench.panel_supersession.v31",
        ):
            self.assertIn(value, self.all_flat)

    def test_v48_acknowledgement_and_provider_contract_are_exact(self) -> None:
        source_path = (
            self.root / "src" / "epiagentbench" / "development_matched_panel.py"
        )
        source = source_path.read_text(encoding="utf-8")
        module = ast.parse(source, filename=str(source_path))
        values: dict[str, object] = {}
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                    "REQUIRED_SPEND_ACKNOWLEDGEMENT",
                    "_PREPARATION_RUNTIME_SMOKE_GOLDEN_SHA256",
                }:
                    values[target.id] = ast.literal_eval(node.value)
        acknowledgement = values["REQUIRED_SPEND_ACKNOWLEDGEMENT"]
        self.assertIsInstance(acknowledgement, str)
        self.assertEqual(
            hashlib.sha256(acknowledgement.encode("utf-8")).hexdigest(),
            self.ACKNOWLEDGEMENT_SHA256,
        )
        self.assertIn(acknowledgement, self.runbook)
        self.assertIn(self.ACKNOWLEDGEMENT_SHA256, self.runbook)
        smoke = values["_PREPARATION_RUNTIME_SMOKE_GOLDEN_SHA256"]
        self.assertIsInstance(smoke, str)
        self.assertEqual(
            smoke,
            "sha256:e91a8e76e32048c3bbc63c02ee2a1279fc53a6af078130a7d3baaa91ac8a3d5f",
        )
        self.assertIn(smoke, self.all_text)
        self.assertIn(
            '"schema_version": "epiagentbench.provider_cli_contract.v3"',
            source,
        )
        self.assertIn("epiagentbench.provider_cli_contract.v3", self.all_flat)

    def test_v48_staged_ref_has_exactly_four_ordered_one_file_receipts(self) -> None:
        self.assertIn(
            "exactly four one-file commits in order: runtime receipt, manifest, "
            "sanitized authentication receipt, and passing preflight receipt",
            self.design_flat,
        )
        for row in (
            "| Runtime-receipt ref | `refs/heads/codex/v48-runtime-preflight` |",
            "| Manifest publication ref | `refs/heads/codex/v48-runtime-preflight` |",
            "| Authentication publication ref | `refs/heads/codex/v48-runtime-preflight` |",
            "| Preflight publication ref | `refs/heads/codex/v48-runtime-preflight` |",
        ):
            self.assertIn(row, self.runbook)
        self.assertIn(
            "That same staged public-receipt ref then advances through exactly "
            "three more one-file commits",
            self.runbook_flat,
        )

    def test_v48_publication_refs_are_closed_and_mutually_exclusive(self) -> None:
        expected_refs = {
            "refs/heads/codex/v48-control-plane",
            "refs/heads/codex/v48-control-plane-publication-terminal-closeout",
            "refs/heads/codex/v48-runtime-preflight",
            "refs/heads/codex/v48-runtime-publication-terminal-closeout",
            "refs/heads/codex/v48-preflight-terminal-closeout",
            "refs/heads/codex/v48-production-results",
            "refs/heads/codex/v48-terminal-closeout",
        }
        observed_refs = set(
            re.findall(r"refs/heads/codex/v48-[a-z0-9-]+", self.runbook)
        )
        observed_refs.discard(self.V47_CLOSEOUT_REF)
        self.assertEqual(observed_refs, expected_refs)
        self.assertIn(
            "These five terminal or outcome paths are mutually exclusive",
            self.runbook_flat,
        )
        self.assertIn(
            "is mutually exclusive with every later V48 ref",
            self.design_flat,
        )

    def test_control_publication_gate_is_one_shot_and_hook_preserving(self) -> None:
        for fragment in (
            "fresh standalone primary clone",
            "matthew-zhao",
            "boolean push permission",
            "one named `but push codex/v48-control-plane`",
            "failure or ambiguity is terminal",
            "never retried",
            "core.hooksPath` remains unset",
            "4d4892f5df8d68688d564b08a9b7ab990ee1af49f85250e94bb9e088f23c5728",
            "9bc3e13271e9bbbebdcb4543cc051e869f10c7a8219e1bff807595e52b345afc",
        ):
            self.assertIn(fragment.lower(), self.all_flat.lower())
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v48-control-plane-workspace",
            self.runbook,
        )

    def test_every_publication_has_exact_publisher_and_named_push(self) -> None:
        expected = {
            "control-plane-publication-terminal-closeout": (
                "epiagentbench-v48-control-plane-publication-terminal-closeout-workspace"
            ),
            "runtime-preflight": "epiagentbench-v48-runtime-preflight-workspace",
            "runtime-publication-terminal-closeout": (
                "epiagentbench-v48-runtime-publication-terminal-closeout-workspace"
            ),
            "preflight-terminal-closeout": (
                "epiagentbench-v48-preflight-terminal-closeout-workspace"
            ),
            "production-results": "epiagentbench-v48-production-results-workspace",
            "terminal-closeout": "epiagentbench-v48-terminal-closeout-workspace",
        }
        for branch, workspace in expected.items():
            self.assertIn(
                "/Users/matthew.zhao/Documents/Disease Surveillance/" + workspace,
                self.runbook,
            )
            self.assertIn(f"`but push codex/v48-{branch}`", self.runbook)
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
        begin = "# V48_PREPUBLICATION_GATE_BEGIN"
        end = "# V48_PREPUBLICATION_GATE_END"
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
            "V48_DESTINATION_REF='refs/heads/codex/v48-control-plane'",
            "V48_EXPECTED_REMOTE_TIP=absent",
            "remote get-url origin",
            "status --porcelain=v1",
            "auth switch --hostname github.com --user matthew-zhao",
            "api user --jq .login",
            "--jq .permissions.push",
            "--get core.hooksPath",
            ".git/hooks/pre-commit",
            ".git/hooks/post-checkout",
            "git ls-remote --refs",
            '[[ -z "$V48_REMOTE_RECORDS" ]]',
            "$'\\t'",
            "v48_prepublication_gate=passed",
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
        begin = "# V48_POSTPUBLICATION_PIN_GATE_BEGIN"
        end = "# V48_POSTPUBLICATION_PIN_GATE_END"
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
                "refs/heads/codex/v48-control-plane",
                "epiagentbench-50x6-v48-runtime-worktree",
            ),
            "runtime_receipt": (
                "refs/heads/codex/v48-runtime-preflight",
                "epiagentbench-50x6-v48-prepare-worktree",
            ),
            "manifest": (
                "refs/heads/codex/v48-runtime-preflight",
                "epiagentbench-50x6-v48-manifest-worktree",
            ),
            "authentication_receipt": (
                "refs/heads/codex/v48-runtime-preflight",
                "epiagentbench-50x6-v48-execution-worktree",
            ),
            "passing_preflight": (
                "refs/heads/codex/v48-runtime-preflight",
                "epiagentbench-50x6-v48-production-worktree",
            ),
            "control_publication_terminal_closeout": (
                "refs/heads/codex/v48-control-plane-publication-terminal-closeout",
                "epiagentbench-50x6-v48-release-worktree",
            ),
            "runtime_publication_terminal_closeout": (
                "refs/heads/codex/v48-runtime-publication-terminal-closeout",
                "epiagentbench-50x6-v48-release-worktree",
            ),
            "preflight_terminal_closeout": (
                "refs/heads/codex/v48-preflight-terminal-closeout",
                "epiagentbench-50x6-v48-release-worktree",
            ),
            "production_results": (
                "refs/heads/codex/v48-production-results",
                "epiagentbench-50x6-v48-release-worktree",
            ),
            "terminal_closeout": (
                "refs/heads/codex/v48-terminal-closeout",
                "epiagentbench-50x6-v48-release-worktree",
            ),
        }
        for phase, (ref, checkout) in mappings.items():
            self.assertIn(f"  {phase})", gate)
            self.assertIn(f"V48_PIN_REF='{ref}'", gate)
            self.assertIn(checkout, gate)
        for fragment in (
            "V48_PIN_PHASE=control",
            "git ls-remote --refs --exit-code",
            "V48_PIN_RECORD_BEFORE=$(v48_read_pin) || exit 72",
            "V48_PIN_SHA=${V48_PIN_RECORD_BEFORE%%$'\\t'*}",
            "[[ ${#V48_PIN_SHA} -eq 40 ]] || exit 72",
            '[[ "$V48_PIN_SHA" != *[!0-9a-f]* ]] || exit 72',
            '"${V48_PIN_SHA}"$\'\\t\'"${V48_PIN_REF}"',
            "rev-parse --show-toplevel",
            "remote get-url --all origin",
            "status --porcelain=v1",
            "rev-parse --verify 'HEAD^{commit}'",
            "V48_PIN_RECORD_AFTER=$(v48_read_pin) || exit 72",
            '[[ "$V48_PIN_RECORD_AFTER" == "$V48_PIN_RECORD_BEFORE" ]]',
            "v48_postpublication_pin_gate=passed",
            "v48_pinned_commit=%s",
        ):
            self.assertIn(fragment, gate)
        self.assertLess(
            gate.index("V48_PIN_RECORD_BEFORE=$(v48_read_pin)"),
            gate.index("rev-parse --show-toplevel"),
        )
        self.assertLess(
            gate.index("rev-parse --verify 'HEAD^{commit}'"),
            gate.index("V48_PIN_RECORD_AFTER=$(v48_read_pin)"),
        )
        self.assertNotIn("<checkout>", self.runbook)
        self.assertIn(
            "The second independent query must be byte-for-byte identical to the first",
            self.runbook_flat,
        )

    def test_runtime_receipt_publisher_is_fresh_and_control_bound(self) -> None:
        self.assertIn(
            "/Users/matthew.zhao/Documents/Disease Surveillance/"
            "epiagentbench-v48-runtime-preflight-workspace",
            self.runbook,
        )
        self.assertIn(
            "rooted exactly at the independently pinned V48 control commit",
            self.runbook_flat,
        )
        self.assertIn(
            "The path and receipt destination must be absent before creation",
            self.runbook_flat,
        )

    def test_terminal_parent_and_file_scope_rules_are_exact(self) -> None:
        supersession = "results/development-matched-50x6-v48.superseded.json"
        contract_test = "tests/test_v48_supersession.py"
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
            f"as the direct child of `{self.V47_CLOSEOUT_COMMIT}`",
            self.design_flat,
        )
        self.assertIn(
            f"sole parent is `{self.V47_CLOSEOUT_COMMIT}`",
            self.design_flat,
        )
        self.assertIn(
            "may add only `results/development-matched-50x6-v48.superseded.json` "
            "and `tests/test_v48_supersession.py`",
            self.runbook_flat,
        )

    def test_future_commit_ids_remain_placeholders(self) -> None:
        expected_placeholders = {
            "<V48_CONTROL_COMMIT_40_HEX>",
            "<V48_CONTROL_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V48_RUNTIME_RECEIPT_COMMIT_40_HEX>",
            "<V48_MANIFEST_COMMIT_40_HEX>",
            "<V48_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>",
            "<V48_PREFLIGHT_RECEIPT_COMMIT_40_HEX>",
            "<V48_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V48_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
            "<V48_PRODUCTION_RESULT_COMMIT_40_HEX>",
            "<V48_TERMINAL_CLOSEOUT_COMMIT_40_HEX>",
        }
        observed = set(re.findall(r"<[A-Z0-9_]+_40_HEX>", self.runbook))
        self.assertEqual(observed, expected_placeholders)

    def test_predecessor_panel_contracts_are_explicitly_rejected(self) -> None:
        for value in (
            "development-matched-50x6-v35",
            "development_matched_panel_v35",
            "development-matched-50x6-v40",
            "development_matched_panel_v40",
            "development-matched-50x6-v46",
            "development_matched_panel_v46",
            "development-matched-50x6-v47",
            "development_matched_panel_v47",
            "epiagentbench.persistent_supervisor_contract.v20",
            "epiagentbench.persistent_supervisor_contract.v21",
            "epiagentbench.persistent_supervisor_contract.v22",
            "epiagentbench.persistent_supervisor_contract.v23",
        ):
            self.assertIn(value, self.all_flat)
        self.assertIn("non-reusable", self.all_flat)
        self.assertIn("reject", self.all_flat)

    def test_committed_control_plane_has_exact_parent_scope_and_ancestry(self) -> None:
        test_path = "tests/test_v48_publication_topology.py"
        if self._git("ls-files", "--error-unmatch", test_path, check=False).returncode:
            self.skipTest("V48 control plane is not committed yet")

        self.assertEqual(
            self._git(
                "show", "-s", "--format=%P", self.V47_CLOSEOUT_COMMIT
            ).stdout.strip(),
            self.V47_CLOSEOUT_PARENT,
        )
        self.assertEqual(
            self._git(
                "show", "-s", "--format=%T", self.V47_CLOSEOUT_COMMIT
            ).stdout.strip(),
            self.V47_CLOSEOUT_TREE,
        )
        control_commit = self._git(
            "log", "-1", "--format=%H", "--", test_path
        ).stdout.strip()
        self.assertEqual(
            self._git("show", "-s", "--format=%P", control_commit).stdout.strip(),
            self.V47_CLOSEOUT_COMMIT,
        )
        branch_tip = self._git("rev-parse", self.V48_CONTROL_REF).stdout.strip()
        self.assertEqual(control_commit, branch_tip)

        changed_paths = frozenset(
            self._git(
                "diff-tree", "--no-commit-id", "--name-only", "-r", control_commit
            ).stdout.splitlines()
        )
        self.assertEqual(changed_paths, self.CONTROL_SCOPE)

        tree_paths = frozenset(
            self._git(
                "ls-tree", "-r", "--name-only", control_commit
            ).stdout.splitlines()
        )
        for forbidden_path in (
            "results/development-matched-50x6-v48.runtime.json",
            "results/development-matched-50x6-v48.manifest.json",
            "results/development-matched-50x6-v48.authentication.json",
            "results/development-matched-50x6-v48.preflight.json",
            "results/development-matched-50x6-v48.json",
            "results/development-matched-50x6-v48.superseded.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        ancestry = set(self._git("rev-list", control_commit).stdout.splitlines())
        self.assertNotIn(self.V33_UNPUBLISHED_CONTROL_COMMIT, ancestry)
        self.assertIn(self.V47_CLOSEOUT_COMMIT, ancestry)


if __name__ == "__main__":
    unittest.main()
