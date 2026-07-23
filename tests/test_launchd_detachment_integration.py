"""Opt-in integration proof for launchd ownership of a fake local job.

This test is deliberately excluded from normal test runs.  It creates an
owner-only temporary LaunchAgent which runs the production
``PersistentSupervisor`` core around a local fake child.  The child waits
behind a file gate, allowing the test to prove that the authenticated
supervisor and child remain alive after the separate process which
bootstrapped the job has exited.

No benchmark code, credentials, Keychain entries, provider tools, model CLIs,
or network services are used.
"""

from __future__ import annotations

import json
import os
import plistlib
import secrets
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path


_ENABLE_FLAG = "EPIAGENTBENCH_RUN_LAUNCHD_INTEGRATION"
_LAUNCHCTL = Path("/bin/launchctl")
_CAFFEINATE = Path("/usr/bin/caffeinate")

_FAKE_CHILD = r'''#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

started = Path(sys.argv[1])
release = Path(sys.argv[2])
completed = Path(sys.argv[3])
nonce = sys.argv[4]

started.write_text(
    json.dumps({"nonce": nonce, "pid": os.getpid(), "ppid": os.getppid()}),
    encoding="utf-8",
)

deadline = time.monotonic() + 20.0
while time.monotonic() < deadline:
    if release.is_file():
        completed.write_text(
            json.dumps({"nonce": nonce, "pid": os.getpid()}),
            encoding="utf-8",
        )
        raise SystemExit(0)
    time.sleep(0.05)

raise SystemExit(3)
'''

_CORE_WORKER = r'''#!/usr/bin/env python3
import os
import sys
from pathlib import Path

repository_root = Path(sys.argv[1]).resolve()
source_root = str(repository_root / "src")
if source_root not in sys.path:
    sys.path.insert(0, source_root)

from epiagentbench.persistent_supervisor import run_supervised_command

(
    _,
    _,
    supervisor_runtime,
    authentication_key,
    fake_child,
    started,
    release,
    completed,
    nonce,
) = sys.argv

environment = {
    "HOME": str(Path.home()),
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "PYTHONPATH": source_root,
}
raise SystemExit(
    run_supervised_command(
        runtime_dir=Path(supervisor_runtime),
        operation="production",
        command=(
            str(Path(sys.executable).resolve()),
            fake_child,
            started,
            release,
            completed,
            nonce,
        ),
        child_environment=environment,
        authentication_key=Path(authentication_key),
        execution_context_sha256="sha256:" + "a" * 64,
        heartbeat_interval_seconds=10.0,
    )
)
'''

_STARTER = r'''#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path

launchctl, domain, plist_path, label, started_path = sys.argv[1:]
subprocess.run(
    [launchctl, "bootstrap", domain, plist_path],
    check=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    timeout=5,
)
subprocess.run(
    [launchctl, "kickstart", domain + "/" + label],
    check=True,
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    timeout=5,
)

deadline = time.monotonic() + 5.0
while time.monotonic() < deadline:
    if Path(started_path).is_file():
        raise SystemExit(0)
    time.sleep(0.05)

raise SystemExit(4)
'''


def _write_private(path: Path, contents: str) -> None:
    """Create one owner-readable file without following or replacing links."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def _wait_for_file(path: Path, *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for local marker {path.name}")


@unittest.skipUnless(
    os.environ.get(_ENABLE_FLAG) == "1",
    f"set {_ENABLE_FLAG}=1 to run the real launchd integration test",
)
@unittest.skipUnless(sys.platform == "darwin", "launchd integration requires macOS")
class LaunchdDetachmentIntegrationTest(unittest.TestCase):
    def test_fake_job_outlives_starter_and_completes(self) -> None:
        self.assertTrue(_LAUNCHCTL.is_file(), "launchctl is unavailable")
        self.assertTrue(_CAFFEINATE.is_file(), "caffeinate is unavailable")

        domain = f"gui/{os.getuid()}"
        label = f"org.epiagentbench.integration.{uuid.uuid4().hex}"
        nonce = secrets.token_hex(16)
        helper: subprocess.Popen[bytes] | None = None

        with tempfile.TemporaryDirectory(
            prefix="epiagentbench-launchd-integration-",
            dir="/private/tmp",
        ) as temporary:
            runtime = Path(temporary)
            os.chmod(runtime, 0o700)
            self.assertEqual(stat.S_IMODE(runtime.stat().st_mode), 0o700)

            worker = runtime / "core_worker.py"
            fake_child = runtime / "fake_child.py"
            starter = runtime / "starter.py"
            plist_path = runtime / "agent.plist"
            supervisor_runtime = runtime / "supervisor"
            authentication_key = runtime / "authentication.key"
            started = runtime / "started.json"
            release = runtime / "release"
            completed = runtime / "completed.json"

            supervisor_runtime.mkdir(mode=0o700)
            _write_private(authentication_key, secrets.token_bytes(32).hex())
            _write_private(worker, _CORE_WORKER)
            _write_private(fake_child, _FAKE_CHILD)
            _write_private(starter, _STARTER)

            plist = {
                "Label": label,
                "ProgramArguments": [
                    str(_CAFFEINATE),
                    "-dimsu",
                    str(Path(sys.executable).resolve()),
                    str(worker),
                    str(Path(__file__).resolve().parents[1]),
                    str(supervisor_runtime),
                    str(authentication_key),
                    str(fake_child),
                    str(started),
                    str(release),
                    str(completed),
                    nonce,
                ],
                "RunAtLoad": False,
                "KeepAlive": False,
                "ProcessType": "Background",
                "StandardOutPath": "/dev/null",
                "StandardErrorPath": "/dev/null",
                "Umask": 0o077,
            }
            _write_private(plist_path, plistlib.dumps(plist).decode("utf-8"))

            try:
                helper = subprocess.Popen(
                    [
                        str(Path(sys.executable).resolve()),
                        str(starter),
                        str(_LAUNCHCTL),
                        domain,
                        str(plist_path),
                        label,
                        str(started),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )
                helper_pid = helper.pid
                helper_return_code = helper.wait(timeout=12)

                self.assertEqual(helper_return_code, 0)
                self.assertIsNotNone(helper.poll(), "starter must have exited")
                self.assertTrue(started.is_file(), "fake job never started")
                self.assertFalse(
                    completed.exists(),
                    "fake job crossed its release gate before the starter exited",
                )

                started_payload = json.loads(started.read_text(encoding="utf-8"))
                self.assertEqual(started_payload["nonce"], nonce)
                self.assertNotEqual(started_payload["pid"], helper_pid)
                self.assertNotEqual(started_payload["ppid"], helper_pid)

                _write_private(release, "continue\n")
                _wait_for_file(completed, timeout_seconds=12)
                completed_payload = json.loads(completed.read_text(encoding="utf-8"))
                self.assertEqual(completed_payload["nonce"], nonce)
                self.assertEqual(completed_payload["pid"], started_payload["pid"])

                source_root = str(Path(__file__).resolve().parents[1] / "src")
                if source_root not in sys.path:
                    sys.path.insert(0, source_root)
                from epiagentbench.persistent_supervisor import (
                    read_supervisor_status,
                )

                supervisor_deadline = time.monotonic() + 12.0
                while True:
                    supervisor_status = read_supervisor_status(
                        supervisor_runtime,
                        authentication_key=authentication_key,
                    )
                    if supervisor_status["lifecycle"] == "completed":
                        break
                    if time.monotonic() >= supervisor_deadline:
                        self.fail("authenticated supervisor did not become terminal")
                    time.sleep(0.05)
                self.assertEqual(supervisor_status["lifecycle"], "completed")
                self.assertEqual(supervisor_status["assignment_phase"], "terminal")
                self.assertEqual(supervisor_status["completed_assignments"], 1)
                self.assertEqual(supervisor_status["total_assignments"], 1)
            finally:
                try:
                    if helper is not None and helper.poll() is None:
                        helper.kill()
                        try:
                            helper.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            pass
                finally:
                    try:
                        subprocess.run(
                            [str(_LAUNCHCTL), "bootout", f"{domain}/{label}"],
                            check=False,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        # Cleanup was attempted; the unique label and owner-only
                        # temporary directory prevent collision with other jobs.
                        pass


if __name__ == "__main__":
    unittest.main()
