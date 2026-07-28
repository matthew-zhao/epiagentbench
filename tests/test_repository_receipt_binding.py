from __future__ import annotations

from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched


_AUTHENTICATION_KEY = b"repository binding test key".ljust(32, b"!")
_CONTENT_SHA256 = "sha256:" + "a" * 64


class RepositoryReceiptBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        workspace = Path(__file__).resolve().parents[1]
        self.temporary = TemporaryDirectory(
            prefix=".epiagentbench-receipt-binding-", dir=workspace
        )
        self.parent = Path(self.temporary.name)
        os.chmod(self.parent, 0o700)
        self.root = self.parent / "checkout"
        self.root.mkdir(mode=0o700)
        self.state_directory = self.parent / "private-state"
        self.state_directory.mkdir(mode=0o700)
        self.private_path = self.state_directory / "panel.private.json"
        self.key_path = self.state_directory / "authentication.key"
        self.key_path.write_bytes(_AUTHENTICATION_KEY)
        os.chmod(self.key_path, 0o600)
        self.claude_storage = self.parent / "claude-storage"
        self.claude_storage.mkdir(mode=0o700)
        self.codex_storage = self.parent / "codex-storage"
        self.codex_storage.mkdir(mode=0o700)
        self.public_path = self.root / "results" / "manifest.json"
        self.receipt_path = matched._authentication_receipt_path(
            self.public_path
        )
        self.receipt = {
            "schema_version": "test.authentication.receipt.v1",
            "receipt_sha256": _CONTENT_SHA256,
            "status": "passed",
        }
        self._write_json(self.public_path, {"test": "manifest"})
        self._write_json(self.receipt_path, self.receipt)
        self._git("init", "-q")
        self._git("config", "user.name", "EpiAgentBench Test")
        self._git("config", "user.email", "test@example.invalid")
        self._git("add", "results/manifest.json")
        self._git(
            "add",
            str(self.receipt_path.relative_to(self.root)),
        )
        self._git("commit", "-q", "-m", "publish receipt")
        self.published_commit = self._git("rev-parse", "HEAD")
        self.binding = matched._repository_receipt_binding(
            root=self.root,
            path=self.receipt_path,
            artifact_kind="authentication",
            content_sha256=_CONTENT_SHA256,
            payload=self.receipt,
            published_commit=self.published_commit,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _git(self, *arguments: str, root: Path | None = None) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=self.root if root is None else root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            self.fail(
                f"temporary git command failed: {arguments!r}: "
                f"{process.stderr.strip()}"
            )
        return process.stdout.strip()

    def test_binding_survives_checkout_relocation_and_clean_descendant(self):
        relocated = self.parent / "relocated-checkout"
        self.root.rename(relocated)
        self.root = relocated
        self.public_path = self.root / "results" / "manifest.json"
        self.receipt_path = matched._authentication_receipt_path(
            self.public_path
        )
        payload = matched._load_json(self.receipt_path)

        validated = matched._validate_repository_receipt_binding(
            self.binding,
            root=self.root,
            path=self.receipt_path,
            artifact_kind="authentication",
            content_sha256=_CONTENT_SHA256,
            payload=payload,
            require_published_commit=True,
        )
        self.assertEqual(
            validated["repository_relative_path"],
            str(self.receipt_path.relative_to(self.root)),
        )

        descendant = self.root / "docs" / "descendant.txt"
        descendant.parent.mkdir()
        descendant.write_text("clean descendant\n", encoding="utf-8")
        self._git("add", "docs/descendant.txt")
        self._git("commit", "-q", "-m", "clean descendant")
        self.assertNotEqual(self._git("rev-parse", "HEAD"), self.published_commit)

        matched._validate_repository_receipt_binding(
            self.binding,
            root=self.root,
            path=self.receipt_path,
            artifact_kind="authentication",
            content_sha256=_CONTENT_SHA256,
            payload=payload,
            require_published_commit=True,
        )

    def test_binding_rejects_unrelated_history_and_tampered_payload(self):
        tampered = dict(self.receipt)
        tampered["status"] = "tampered"
        self._write_json(self.receipt_path, tampered)
        with self.assertRaisesRegex(
            RuntimeError, "repository binding changed"
        ):
            matched._validate_repository_receipt_binding(
                self.binding,
                root=self.root,
                path=self.receipt_path,
                artifact_kind="authentication",
                content_sha256=_CONTENT_SHA256,
                payload=matched._load_json(self.receipt_path),
                require_published_commit=True,
            )

        unrelated = self.parent / "unrelated-checkout"
        unrelated.mkdir(mode=0o700)
        unrelated_receipt = (
            unrelated
            / "results"
            / f"{matched.PANEL_ID}.authentication.json"
        )
        self._write_json(unrelated / "results" / "manifest.json", {"other": True})
        self._write_json(unrelated_receipt, self.receipt)
        self._git("init", "-q", root=unrelated)
        self._git(
            "config", "user.name", "EpiAgentBench Test", root=unrelated
        )
        self._git(
            "config", "user.email", "test@example.invalid", root=unrelated
        )
        self._git("add", "results", root=unrelated)
        self._git("commit", "-q", "-m", "unrelated history", root=unrelated)

        with self.assertRaises(RuntimeError):
            matched._validate_repository_receipt_binding(
                self.binding,
                root=unrelated,
                path=unrelated_receipt,
                artifact_kind="authentication",
                content_sha256=_CONTENT_SHA256,
                payload=self.receipt,
                require_published_commit=True,
            )

    def test_explicit_binding_is_create_once_and_rejects_dirty_checkout(self):
        setup = {
            "status": "passed",
            "public_receipt_binding": {
                **self.binding,
                "published_commit": None,
            },
            "public_receipt_sha256": _CONTENT_SHA256,
        }
        private = {"authentication_setup": setup}
        public = {"test": "manifest"}
        self.private_path.write_text("{}\n", encoding="utf-8")
        os.chmod(self.private_path, 0o600)
        writes: list[dict] = []

        def load_json(path: Path) -> dict:
            if path == self.public_path:
                return public
            if path == self.receipt_path:
                return self.receipt
            raise AssertionError(f"unexpected JSON path: {path}")

        patches = (
            patch.object(
                matched, "assert_durable_live_execution_paths"
            ),
            patch.object(
                matched, "_read_authentication_key", return_value=_AUTHENTICATION_KEY
            ),
            patch.object(
                matched, "_load_private_state", return_value=private
            ),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(
                matched,
                "_validate_claude_secure_storage_dir",
                return_value=self.claude_storage,
            ),
            patch.object(
                matched,
                "_validate_codex_secure_storage_dir",
                return_value=self.codex_storage,
            ),
            patch.object(
                matched,
                "_validate_authentication_contracts",
                return_value=setup,
            ),
            patch.object(matched, "_assert_spend_authorization"),
            patch.object(matched, "_validate_authentication_receipt"),
            patch.object(
                matched,
                "_write_private_state",
                side_effect=lambda _path, value, _key: writes.append(value),
            ),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
        )

        dirty = self.root / "untracked.txt"
        dirty.write_text("dirty\n", encoding="utf-8")
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
            patches[5],
            patches[6],
            patches[7],
            patches[8],
            patches[9],
            patches[10],
            self.assertRaisesRegex(RuntimeError, "worktree must be clean"),
        ):
            matched.bind_panel_receipt_commit(
                root=self.root,
                operation="authentication",
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_storage,
                codex_secure_storage_dir=self.codex_storage,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
        self.assertIsNone(setup["public_receipt_binding"]["published_commit"])
        self.assertEqual(writes, [])
        dirty.unlink()

        with (
            patch.object(
                matched, "assert_durable_live_execution_paths"
            ),
            patch.object(
                matched, "_read_authentication_key", return_value=_AUTHENTICATION_KEY
            ),
            patch.object(
                matched, "_load_private_state", return_value=private
            ),
            patch.object(matched, "_load_json", side_effect=load_json),
            patch.object(
                matched,
                "_validate_claude_secure_storage_dir",
                return_value=self.claude_storage,
            ),
            patch.object(
                matched,
                "_validate_codex_secure_storage_dir",
                return_value=self.codex_storage,
            ),
            patch.object(
                matched,
                "_validate_authentication_contracts",
                return_value=setup,
            ),
            patch.object(matched, "_assert_spend_authorization"),
            patch.object(matched, "_validate_authentication_receipt"),
            patch.object(
                matched,
                "_write_private_state",
                side_effect=lambda _path, value, _key: writes.append(value),
            ),
            patch.object(
                matched, "_exclusive_run_lock", return_value=nullcontext()
            ),
        ):
            first = matched.bind_panel_receipt_commit(
                root=self.root,
                operation="authentication",
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_storage,
                codex_secure_storage_dir=self.codex_storage,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )
            second = matched.bind_panel_receipt_commit(
                root=self.root,
                operation="authentication",
                authentication_key_file=self.key_path,
                claude_secure_storage_dir=self.claude_storage,
                codex_secure_storage_dir=self.codex_storage,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
            )

        self.assertEqual(first, second)
        self.assertEqual(first["published_commit"], self.published_commit)
        self.assertEqual(
            setup["public_receipt_binding"]["published_commit"],
            self.published_commit,
        )
        self.assertEqual(len(writes), 1)

    def test_private_state_survives_checkout_handoff_but_not_state_relocation(self):
        private = {
            "private_state_storage": matched._private_state_storage_binding(
                self.private_path,
                root=self.root,
            ),
            "status": "test",
        }
        matched._write_private_state(
            self.private_path, private, _AUTHENTICATION_KEY
        )
        serialized_binding = json.dumps(
            private["private_state_storage"], sort_keys=True
        )
        self.assertNotIn(str(self.root), serialized_binding)

        relocated_checkout = self.parent / "handoff-checkout"
        self.root.rename(relocated_checkout)
        matched.assert_durable_live_execution_paths(
            root=relocated_checkout,
            private_state_path=self.private_path,
        )
        self.assertEqual(
            matched._load_private_state(
                self.private_path, _AUTHENTICATION_KEY
            ),
            private,
        )

        relocated_state_directory = self.parent / "other-private-state"
        relocated_state_directory.mkdir(mode=0o700)
        relocated_state = relocated_state_directory / self.private_path.name
        shutil.copyfile(self.private_path, relocated_state)
        os.chmod(relocated_state, 0o600)
        with self.assertRaisesRegex(ValueError, "storage binding changed"):
            matched._load_private_state(
                relocated_state, _AUTHENTICATION_KEY
            )

        checkout_state = relocated_checkout / "private" / "state.json"
        checkout_state.parent.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "outside the repository"):
            matched._private_state_storage_binding(
                checkout_state,
                root=relocated_checkout,
            )


if __name__ == "__main__":
    unittest.main()
