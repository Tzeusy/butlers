"""Security contracts for Dashboard CLI-auth child isolation."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butlers.cli_auth.registry import PROVIDERS

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_stage_output(stage_home: Path) -> tuple[Path, Path]:
    """Create the ordinary private staged output layout without credential content."""
    stage_home.mkdir()
    os.chmod(stage_home, 0o700)
    output = stage_home / ".local" / "share" / "opencode" / "auth.json"
    output.parent.mkdir(parents=True)
    for directory in (stage_home / ".local", stage_home / ".local" / "share", output.parent):
        os.chmod(directory, 0o700)
    output.write_text('{"openai":{"type":"oauth"}}', encoding="utf-8")
    os.chmod(output, 0o600)
    return stage_home, output


@pytest.mark.parametrize(
    ("provider_name", "expected_key", "expected_entry"),
    [
        (
            "opencode-openai",
            "openai",
            {
                "type": "oauth",
                "refresh": "openai-refresh-only",
                "access": "openai-access-only",
                "expires": 1_700_000_000,
                "accountId": "account-only",
                "enterpriseUrl": "https://enterprise.example.test",
            },
        ),
        ("opencode-go", "opencode-go", {"type": "api", "key": "go-only"}),
    ],
)
def test_shared_opencode_authority_is_projected_to_the_calling_provider(
    tmp_path: Path,
    provider_name: str,
    expected_key: str,
    expected_entry: dict[str, object],
) -> None:
    """REQ-core-credentials-002: a shared auth file never leaks a peer authority."""
    from butlers.cli_auth.sandbox import load_validated_readonly_authority

    peer_sentinel = "PEER-OPENCODE-AUTHORITY-MUST-NOT-REACH-CHILD"
    canonical = tmp_path / ".local" / "share" / "opencode" / "auth.json"
    canonical.parent.mkdir(parents=True)
    entries = {
        "openai": {
            "type": "oauth",
            "refresh": peer_sentinel,
            "access": peer_sentinel,
            "expires": 1_700_000_000,
        },
        "opencode-go": {"type": "api", "key": peer_sentinel},
    }
    entries[expected_key] = expected_entry
    canonical.write_text(
        json.dumps(
            {
                **entries,
                "unrelated": {"token": peer_sentinel},
            }
        ),
        encoding="utf-8",
    )
    os.chmod(canonical, 0o600)

    authority = load_validated_readonly_authority(
        replace(PROVIDERS[provider_name], token_path=canonical)
    )

    assert authority is not None
    assert json.loads(authority.content) == {expected_key: expected_entry}
    assert peer_sentinel.encode() not in authority.content


@pytest.mark.parametrize(
    ("provider_name", "document"),
    [
        ("opencode-openai", b'{"opencode-go":{"type":"api","key":"go-only"}}'),
        ("opencode-go", b'{"openai":{"type":"oauth","refresh":"openai-only"}}'),
        ("opencode-openai", b'{"openai":{"type":"api"}}'),
        (
            "opencode-openai",
            b'{"openai":{"type":"oauth","refresh":"refresh-only","expires":1}}',
        ),
        ("opencode-go", b'{"opencode-go":{"type":"api"}}'),
        (
            "opencode-go",
            b'{"opencode-go":{"type":"api","key":"go-only","key":"duplicate"}}',
        ),
        (
            "opencode-openai",
            b'{"openai":{"type":"oauth","refresh":"refresh","access":"access",'
            b'"expires":1,"unexpected":{"sentinel":"must-not-reach-child"}}}',
        ),
        (
            "opencode-go",
            b'{"opencode-go":{"type":"api","key":"go-only","metadata":"must-not-reach-child"}}',
        ),
        (
            "opencode-openai",
            b'{"openai":{"type":"oauth","refresh":"refresh","access":"access","expires":-1}}',
        ),
        (
            "opencode-openai",
            b'{"openai":{"type":"oauth","refresh":"refresh","access":"access","expires":1.5}}',
        ),
        ("opencode-go", b"not-json"),
    ],
)
def test_shared_opencode_authority_missing_or_invalid_provider_entry_fails_closed(
    tmp_path: Path,
    provider_name: str,
    document: bytes,
) -> None:
    """REQ-core-credentials-002: a broad shared-file copy is never a fallback."""
    from butlers.cli_auth.sandbox import load_validated_readonly_authority

    canonical = tmp_path / ".local" / "share" / "opencode" / "auth.json"
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(document)
    os.chmod(canonical, 0o600)

    assert (
        load_validated_readonly_authority(replace(PROVIDERS[provider_name], token_path=canonical))
        is None
    )


@pytest.mark.parametrize(
    ("pid1_terminated", "payload_fds_closed"),
    [(False, True), (True, False)],
)
async def test_device_auth_guard_failure_prevents_staged_bytes_persistence(
    tmp_path: Path,
    pid1_terminated: bool,
    payload_fds_closed: bool,
) -> None:
    """REQ-core-credentials-002: PID1/FD failures persist no device-auth output."""
    from butlers.cli_auth.sandbox import persist_staged_device_auth_output

    provider = replace(
        PROVIDERS["opencode-openai"],
        token_path=tmp_path / ".local" / "share" / "opencode" / "auth.json",
    )
    stage_home, output = _make_stage_output(tmp_path / "stage-home")

    store = MagicMock()
    store.store = AsyncMock()
    stage_home_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        persisted = await persist_staged_device_auth_output(
            provider,
            store,
            stage_home_fd=stage_home_fd,
            relative_output_path=output.relative_to(stage_home),
            expected_uid=os.geteuid(),
            pid1_terminated=pid1_terminated,
            payload_fds_closed=payload_fds_closed,
        )
    finally:
        os.close(stage_home_fd)

    assert persisted is False
    store.store.assert_not_awaited()


async def test_device_auth_persists_validated_bytes_from_trusted_stage_fd(tmp_path: Path) -> None:
    """REQ-core-credentials-002: persistence consumes the staged descriptor, not canonical path."""
    from butlers.cli_auth.sandbox import persist_staged_device_auth_output

    canonical = tmp_path / "canonical" / "auth.json"
    canonical.parent.mkdir()
    canonical.write_text('{"canonical":"must-not-be-read"}', encoding="utf-8")

    stage_home, output = _make_stage_output(tmp_path / "stage-home")
    staged_content = '{"openai":{"type":"oauth"}}'
    output.write_text(staged_content, encoding="utf-8")
    os.chmod(output, 0o600)

    provider = replace(PROVIDERS["opencode-openai"], token_path=canonical)
    store = MagicMock()
    store.store = AsyncMock()
    stage_home_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        persisted = await persist_staged_device_auth_output(
            provider,
            store,
            stage_home_fd=stage_home_fd,
            relative_output_path=output.relative_to(stage_home),
            expected_uid=os.geteuid(),
            pid1_terminated=True,
            payload_fds_closed=True,
        )
    finally:
        os.close(stage_home_fd)

    assert persisted is True
    assert canonical.read_text(encoding="utf-8") == '{"canonical":"must-not-be-read"}'
    store.store.assert_awaited_once_with(
        "cli-auth/opencode-openai",
        staged_content,
        category="cli-auth",
        description="CLI auth token for OpenCode (OpenAI)",
        is_sensitive=True,
    )


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "escape"])
async def test_device_auth_rejects_linked_or_escaped_staged_output_before_persistence(
    tmp_path: Path, attack: str
) -> None:
    """REQ-core-credentials-002: links and paths outside the trusted root persist nothing."""
    from butlers.cli_auth.sandbox import persist_staged_device_auth_output

    stage_home, output = _make_stage_output(tmp_path / "stage-home")
    canonical = tmp_path / "canonical" / "auth.json"
    canonical.parent.mkdir()
    canonical.write_text('{"openai":{"type":"oauth"}}', encoding="utf-8")
    os.chmod(canonical, 0o600)

    relative_output_path = output.relative_to(stage_home)
    if attack == "symlink":
        output.unlink()
        output.symlink_to(canonical)
    elif attack == "hardlink":
        output.unlink()
        os.link(canonical, output)
    else:
        relative_output_path = Path("..") / "canonical" / "auth.json"

    provider = replace(PROVIDERS["opencode-openai"], token_path=canonical)
    store = MagicMock()
    store.store = AsyncMock()
    stage_home_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY)
    try:
        persisted = await persist_staged_device_auth_output(
            provider,
            store,
            stage_home_fd=stage_home_fd,
            relative_output_path=relative_output_path,
            expected_uid=os.geteuid(),
            pid1_terminated=True,
            payload_fds_closed=True,
        )
    finally:
        os.close(stage_home_fd)

    assert persisted is False
    store.store.assert_not_awaited()


class _FakeDeviceAuthProcess:
    """Minimal process-shaped child owned by the sandbox test handle."""

    def __init__(self, stdout: bytes, *, returncode: int = 0) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(stdout)
        self.stdout.feed_eof()
        self.returncode = returncode
        self.terminated = False
        self.wait_calls = 0

    async def wait(self) -> int:
        self.wait_calls += 1
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


class _RecordingDeviceAuthHandle:
    """Sandbox handle that exposes staged bytes only after finalization."""

    def __init__(self, events: list[str], *, staged_output: bytes | None) -> None:
        self.process = _FakeDeviceAuthProcess(b"Successfully logged in\n")
        self._events = events
        self._staged_output = staged_output

    async def finalize(self, *, succeeded: bool) -> bytes | None:
        self._events.append("finalize")
        assert succeeded is True
        assert self.process.wait_calls == 0, "only the sandbox handle may wait the direct child"
        return self._staged_output

    async def terminate(self) -> None:
        self._events.append("terminate")


class _RecordingDeviceAuthLauncher:
    """Records the shared-launcher boundary while preserving session behavior."""

    def __init__(self, events: list[str], *, staged_output: bytes | None) -> None:
        self._events = events
        self._staged_output = staged_output

    async def launch_device_auth(self, _provider):
        self._events.append("launch")
        return _RecordingDeviceAuthHandle(self._events, staged_output=self._staged_output)


async def test_device_auth_session_uses_sandbox_handle_before_persisting_staged_bytes() -> None:
    """REQ-core-credentials-002: device auth has no direct-child fallback or pre-PID1 write."""
    from butlers.cli_auth.session import CLIAuthSession

    events: list[str] = []
    staged_output = b'{"tokens":{"access_token":"not-a-real-token"}}'

    async def _on_success(_provider, *, staged_output: bytes) -> bool:
        events.append("persist")
        assert staged_output == b'{"tokens":{"access_token":"not-a-real-token"}}'
        return True

    with patch(
        "butlers.cli_auth.session.asyncio.create_subprocess_exec", new_callable=AsyncMock
    ) as direct_spawn:
        session = CLIAuthSession(
            id="sandboxed-device-auth",
            provider=PROVIDERS["codex"],
            on_success=_on_success,
            sandbox=_RecordingDeviceAuthLauncher(events, staged_output=staged_output),
        )
        await session.start()
        await session.wait()

    assert session.state == "success"
    assert events == ["launch", "finalize", "persist"]
    direct_spawn.assert_not_awaited()


async def test_device_auth_session_does_not_persist_when_sandbox_finalization_fails() -> None:
    """REQ-core-credentials-002: a failed PID1/FD finalization cannot call persistence."""
    from butlers.cli_auth.session import CLIAuthSession

    events: list[str] = []
    on_success = AsyncMock(return_value=True)
    session = CLIAuthSession(
        id="sandboxed-device-auth-failure",
        provider=PROVIDERS["codex"],
        on_success=on_success,
        sandbox=_RecordingDeviceAuthLauncher(events, staged_output=None),
    )

    await session.start()
    await session.wait()

    assert session.state == "failed"
    assert events == ["launch", "finalize"]
    on_success.assert_not_awaited()


class _BlockingSessionProcess:
    """A sandbox process whose payload holds stdout open indefinitely."""

    def __init__(self, reader_started: asyncio.Event, *, initial_output: bytes = b"") -> None:
        self.stdout = asyncio.StreamReader()
        if initial_output:
            self.stdout.feed_data(initial_output)
        self.returncode: int | None = None
        self._reader_started = reader_started

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = 0


class _BlockingSessionHandle:
    """Records whether reader cancellation reaches the shared domain owner."""

    def __init__(
        self,
        reader_started: asyncio.Event,
        events: list[str],
        *,
        initial_output: bytes = b"",
    ) -> None:
        self.process = _BlockingSessionProcess(reader_started, initial_output=initial_output)
        self._reader_started = reader_started
        self._events = events

    async def finalize(self, *, succeeded: bool) -> bytes | None:
        del succeeded
        self._events.append("finalize")
        return None

    async def terminate(self) -> None:
        self._events.append("terminate")


class _BlockingSessionLauncher:
    def __init__(
        self,
        reader_started: asyncio.Event,
        events: list[str],
        *,
        initial_output: bytes = b"",
    ) -> None:
        self._reader_started = reader_started
        self._events = events
        self._initial_output = initial_output

    async def launch_device_auth(self, _provider):
        self._events.append("launch")
        return _BlockingSessionHandle(
            self._reader_started,
            self._events,
            initial_output=self._initial_output,
        )


async def test_device_auth_reader_cancellation_terminates_the_shared_sandbox_domain() -> None:
    """REQ-core-credentials-002: cancelling the reader cannot abandon a child domain."""
    from butlers.cli_auth.session import CLIAuthSession

    reader_started = asyncio.Event()
    events: list[str] = []
    on_success = AsyncMock(return_value=True)
    session = CLIAuthSession(
        id="sandbox-reader-cancel",
        provider=PROVIDERS["codex"],
        on_success=on_success,
        sandbox=_BlockingSessionLauncher(reader_started, events),
    )

    await session.start()
    assert session._reader_task is not None
    # The current reader has started waiting for payload output; cancelling it
    # must first reach the handle that owns PID1/FD/stage lifecycle.
    await asyncio.sleep(0)
    session._reader_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._reader_task

    assert events == ["launch", "terminate"]
    assert session._done_event.is_set()
    on_success.assert_not_awaited()


async def test_device_auth_success_line_stays_provisional_until_sandbox_finalization() -> None:
    """REQ-core-credentials-002: a payload holding stdout open cannot suppress cleanup."""
    from butlers.cli_auth.session import CLIAuthSession

    events: list[str] = []
    on_success = AsyncMock(return_value=True)
    session = CLIAuthSession(
        id="sandbox-provisional-success",
        provider=replace(PROVIDERS["codex"], timeout_seconds=0.05),
        on_success=on_success,
        sandbox=_BlockingSessionLauncher(
            asyncio.Event(),
            events,
            initial_output=b"Successfully logged in\n",
        ),
    )

    await session.start()
    await asyncio.sleep(0.01)
    assert session.state != "success"
    assert session.message == "Finalizing authentication safely."
    await session.wait(timeout=1.0)

    assert session.state == "expired"
    assert events.count("terminate") >= 1
    on_success.assert_not_awaited()


class _FinalizationBlockingHandle:
    """Lets the test cancel a reader after EOF has entered handle finalization."""

    def __init__(self, finalize_started: asyncio.Event, events: list[str]) -> None:
        self.process = _FakeDeviceAuthProcess(b"Successfully logged in\n")
        self._finalize_started = finalize_started
        self._events = events

    async def finalize(self, *, succeeded: bool) -> bytes | None:
        assert succeeded is True
        self._events.append("finalize")
        self._finalize_started.set()
        await asyncio.Event().wait()
        return None

    async def terminate(self) -> None:
        self._events.append("terminate")


class _FinalizationBlockingLauncher:
    def __init__(self, finalize_started: asyncio.Event, events: list[str]) -> None:
        self._finalize_started = finalize_started
        self._events = events

    async def launch_device_auth(self, _provider):
        self._events.append("launch")
        return _FinalizationBlockingHandle(self._finalize_started, self._events)


async def test_device_auth_cancellation_during_finalization_terminates_the_domain() -> None:
    """REQ-core-credentials-002: cancellation after EOF still cleans PID1/staging ownership."""
    from butlers.cli_auth.session import CLIAuthSession

    finalize_started = asyncio.Event()
    events: list[str] = []
    on_success = AsyncMock(return_value=True)
    session = CLIAuthSession(
        id="sandbox-finalize-cancel",
        provider=PROVIDERS["codex"],
        on_success=on_success,
        sandbox=_FinalizationBlockingLauncher(finalize_started, events),
    )

    await session.start()
    await asyncio.wait_for(finalize_started.wait(), timeout=1.0)
    assert session._reader_task is not None
    session._reader_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await session._reader_task

    assert events == ["launch", "finalize", "terminate"]
    assert session._done_event.is_set()
    on_success.assert_not_awaited()


def test_default_dashboard_cli_auth_sandbox_is_the_concrete_bubblewrap_launcher() -> None:
    """REQ-core-credentials-002: production sessions cannot select a direct-child adapter."""
    from butlers.cli_auth.sandbox import dashboard_cli_auth_sandbox
    from butlers.cli_auth.sandbox_platform import BubblewrapDashboardCLIAuthSandbox

    assert isinstance(dashboard_cli_auth_sandbox(), BubblewrapDashboardCLIAuthSandbox)


def test_default_dashboard_sandbox_binds_exact_image_runtime_input_resolvers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: production construction has no unset-resolver fallback."""
    import butlers.cli_auth.sandbox as sandbox_module
    from butlers.cli_auth.sandbox import dashboard_cli_auth_sandbox
    from butlers.cli_auth.sandbox_platform import (
        resolve_device_auth_runtime_inputs,
        resolve_readonly_runtime_inputs,
    )

    monkeypatch.setattr(sandbox_module, "_DASHBOARD_SANDBOX", None)
    sandbox = dashboard_cli_auth_sandbox()

    assert sandbox._invocation_resolver is resolve_device_auth_runtime_inputs
    assert sandbox._readonly_invocation_resolver is resolve_readonly_runtime_inputs


def test_runtime_input_manifest_resolves_only_declared_provider_inputs(tmp_path: Path) -> None:
    """REQ-core-credentials-002: the image manifest is the only runtime-input authority."""
    from butlers.cli_auth.sandbox_platform import (
        ReadonlySandboxInput,
        RuntimeCLIInputManifest,
        SandboxLaunchValidationError,
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o755)
    executable = runtime_root / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(executable, 0o555)
    manifest_path = tmp_path / "runtime-cli-sandbox-inputs.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "providers": {
                    "codex": {
                        "binary": "codex",
                        "executable": str(executable),
                        "readonly_inputs": [
                            {
                                "source": str(runtime_root),
                                "destination": str(runtime_root),
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o444)
    resolver = RuntimeCLIInputManifest(manifest_path, expected_uid=os.geteuid())

    device_auth = resolver.resolve_device_auth(PROVIDERS["codex"])
    readonly = resolver.resolve_readonly(
        PROVIDERS["codex"],
        ("codex", "auth", "list"),
    )

    assert device_auth.command[0] == str(executable)
    assert device_auth.relative_output_path == Path(".codex") / "auth.json"
    assert readonly.command == (str(executable), "auth", "list")
    assert readonly.readonly_inputs == (
        ReadonlySandboxInput(source=executable, destination=executable),
        ReadonlySandboxInput(source=runtime_root, destination=runtime_root),
    )
    with pytest.raises(SandboxLaunchValidationError, match="provider-declared"):
        resolver.resolve_readonly(PROVIDERS["codex"], ("opencode", "auth", "list"))


def test_runtime_input_manifest_binds_terminal_source_at_logical_loader_path(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: an ELF alias never becomes an unchecked bind source."""
    from butlers.cli_auth.sandbox_platform import (
        ReadonlySandboxInput,
        RuntimeCLIInputManifest,
        SandboxIdentity,
        build_bubblewrap_launch_plan,
    )

    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o755)
    executable = runtime_root / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(executable, 0o555)
    terminal_loader = runtime_root / "ld-linux-terminal.so"
    terminal_loader.write_bytes(b"immutable test loader")
    os.chmod(terminal_loader, 0o444)
    logical_loader = tmp_path / "logical" / "lib64" / "ld-linux-test.so"
    manifest_path = tmp_path / "runtime-cli-sandbox-inputs.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 2,
                "providers": {
                    "codex": {
                        "binary": "codex",
                        "executable": str(executable),
                        "readonly_inputs": [
                            {
                                "source": str(terminal_loader),
                                "destination": str(logical_loader),
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    os.chmod(manifest_path, 0o444)
    readonly = RuntimeCLIInputManifest(
        manifest_path,
        expected_uid=os.geteuid(),
    ).resolve_readonly(PROVIDERS["codex"], ("codex", "auth", "list"))

    assert (
        ReadonlySandboxInput(
            source=terminal_loader,
            destination=logical_loader,
        )
        in readonly.readonly_inputs
    )

    info_read, info_write = os.pipe2(os.O_CLOEXEC)
    block_read, block_write = os.pipe2(os.O_CLOEXEC)
    try:
        plan = build_bubblewrap_launch_plan(
            bwrap_path=Path("/usr/bin/bwrap"),
            shim_path=Path("/usr/local/libexec/butlers/runtime-cli-sandbox-init"),
            identity=SandboxIdentity(uid=61000, gid=61000),
            stage_home=tmp_path / "stage",
            command=readonly.command,
            readonly_inputs=readonly.readonly_inputs,
            info_fd=info_write,
            block_fd=block_read,
        )
    finally:
        for fd in (info_read, info_write, block_read, block_write):
            os.close(fd)

    rendered = tuple(plan.argv)
    assert (
        "--ro-bind",
        str(terminal_loader),
        str(logical_loader),
    ) in tuple(rendered[index : index + 3] for index in range(len(rendered) - 2))


async def test_invocation_identity_pool_never_reuses_a_live_identity() -> None:
    """REQ-core-credentials-002: exhaustion fails closed rather than sharing a child UID."""
    from butlers.cli_auth.sandbox_platform import InvocationIdentityPool, SandboxUnavailableError

    pool = InvocationIdentityPool(first_id=61000, last_id=61000)
    first = await pool.acquire()

    with pytest.raises(SandboxUnavailableError, match="identity pool exhausted"):
        await pool.acquire()

    await pool.release(first)
    assert await pool.acquire() == first


def test_stage_parent_is_traversable_but_not_listable_by_child_identities() -> None:
    """REQ-core-credentials-002: a child can bind only its unguessable 0700 stage."""
    from butlers.cli_auth.sandbox_platform import _STAGE_DIRECTORY_MODE, _STAGE_ROOT_MODE

    assert _STAGE_ROOT_MODE == 0o711
    assert _STAGE_ROOT_MODE & 0o066 == 0
    assert _STAGE_ROOT_MODE & 0o011 == 0o011
    assert _STAGE_DIRECTORY_MODE == 0o700


def test_bubblewrap_launch_plan_is_minimal_and_uses_only_typed_handshake_fds(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: the child view excludes broad host mounts and secrets."""
    from butlers.cli_auth.sandbox_platform import (
        SandboxIdentity,
        build_bubblewrap_launch_plan,
    )

    info_read, info_write = os.pipe2(os.O_CLOEXEC)
    block_read, block_write = os.pipe2(os.O_CLOEXEC)
    try:
        plan = build_bubblewrap_launch_plan(
            bwrap_path=Path("/usr/bin/bwrap"),
            shim_path=Path("/usr/local/libexec/butlers/runtime-cli-sandbox-init"),
            identity=SandboxIdentity(uid=61000, gid=61000),
            stage_home=tmp_path / "stage-home",
            command=("/usr/local/bin/codex", "login", "--device-auth"),
            readonly_inputs=(
                Path("/usr/local/bin/codex"),
                Path("/usr/bin/node"),
                Path("/lib/x86_64-linux-gnu/libc.so.6"),
                Path("/etc/ssl/certs/ca-certificates.crt"),
                Path("/etc/resolv.conf"),
            ),
            info_fd=info_write,
            block_fd=block_read,
        )

        assert plan.pass_fds == (info_write, block_read)
    finally:
        for fd in (info_read, info_write, block_read, block_write):
            os.close(fd)

    assert plan.close_fds is True
    assert plan.environment == {
        "HOME": "/home/runtime",
        "PATH": "/usr/local/bin:/usr/bin",
        "TMPDIR": "/tmp",
        "XDG_CACHE_HOME": "/home/runtime/.cache",
        "XDG_CONFIG_HOME": "/home/runtime/.config",
        "XDG_DATA_HOME": "/home/runtime/.local/share",
    }
    for required in (
        "--unshare-user",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
        "--as-pid-1",
        "--die-with-parent",
        "--clearenv",
        "--proc",
        "--dev",
        "--tmpfs",
        "--info-fd",
        "--block-fd",
    ):
        assert required in plan.argv

    rendered = "\0".join(plan.argv)
    assert "--ro-bind\0/\0/" not in rendered
    assert "--bind\0/\0/" not in rendered
    absolute_values = [value for value in plan.argv if value.startswith("/")]
    for forbidden in ("/root", "/run", "/app"):
        assert not any(
            value == forbidden or value.startswith(f"{forbidden}/") for value in absolute_values
        )
    assert "/proc" in plan.argv
    assert not any(value.startswith("/proc/") for value in absolute_values)
    assert "runtime_probe_control" not in rendered


def test_bubblewrap_handshake_rejects_untyped_or_wrong_direction_fds() -> None:
    """REQ-core-credentials-002: only launcher-created write-info/read-block pipes may pass."""
    from butlers.cli_auth.sandbox_platform import (
        SandboxLaunchValidationError,
        validate_handshake_fds,
    )

    info_read, info_write = os.pipe2(os.O_CLOEXEC)
    block_read, block_write = os.pipe2(os.O_CLOEXEC)
    try:
        assert validate_handshake_fds(info_fd=info_write, block_fd=block_read) == (
            info_write,
            block_read,
        )
        with pytest.raises(SandboxLaunchValidationError, match="info pipe"):
            validate_handshake_fds(info_fd=info_read, block_fd=block_read)
        with pytest.raises(SandboxLaunchValidationError, match="block pipe"):
            validate_handshake_fds(info_fd=info_write, block_fd=block_write)
    finally:
        for fd in (info_read, info_write, block_read, block_write):
            os.close(fd)


class _HandshakeStreamReader(asyncio.StreamReader):
    """Records when the parent can first consume the namespace-init receipt."""

    def __init__(self, events: list[str]) -> None:
        super().__init__()
        self._events = events

    async def readline(self) -> bytes:
        self._events.append("shim_ready")
        return await super().readline()


class _HandshakeProcess:
    """Direct Bubblewrap child stand-in for startup-handshake ordering tests."""

    def __init__(self, events: list[str]) -> None:
        self.stdout = _HandshakeStreamReader(events)
        self.stdout.feed_data(b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\nprovider output\n")
        self.stdout.feed_eof()
        self.returncode: int | None = None
        self.wait_calls = 0

    async def wait(self) -> int:
        self.wait_calls += 1
        self.returncode = 0
        return 0

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = 0


class _BlockingHandshakeProcess(_HandshakeProcess):
    """A child whose namespace-init receipt never arrives before cancellation."""

    def __init__(self, events: list[str]) -> None:
        self.stdout = asyncio.StreamReader()
        self.returncode = None
        self.wait_calls = 0
        self._events = events


async def test_bubblewrap_launcher_opens_pidfd_before_releasing_payload_or_reading_shim(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: PID1 receipt precedes payload release and CLI output."""
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        DeviceAuthSandboxInvocation,
        InvocationIdentityPool,
        SandboxStage,
    )

    events: list[str] = []
    process = _HandshakeProcess(events)
    captured_block_fd: list[int] = []

    async def _spawn(*argv: str, **kwargs: object) -> _HandshakeProcess:
        events.append("spawn")
        assert kwargs["close_fds"] is True
        assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
        assert kwargs["stderr"] is asyncio.subprocess.STDOUT
        assert kwargs["pass_fds"] == (
            int(argv[argv.index("--info-fd") + 1]),
            int(argv[argv.index("--block-fd") + 1]),
        )
        info_fd = int(argv[argv.index("--info-fd") + 1])
        captured_block_fd.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    def _open_pidfd(pid: int, _flags: int = 0) -> int:
        assert pid == 7123
        events.append("pidfd_open")
        return os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)

    def _release_payload(block_fd: int) -> None:
        events.append("block_release")
        os.write(block_fd, b"1")

    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)

    def _stage_factory(_identity) -> SandboxStage:
        return SandboxStage(path=stage_home, root_fd=stage_fd)

    invocation = DeviceAuthSandboxInvocation(
        command=("/usr/bin/true",),
        readonly_inputs=(Path("/usr/bin/true"),),
        relative_output_path=Path(".codex") / "auth.json",
    )
    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        invocation_resolver=lambda _provider: invocation,
        stage_factory=_stage_factory,
        spawn=_spawn,
        pidfd_open=_open_pidfd,
        release_payload=_release_payload,
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    handle = await sandbox.launch_device_auth(PROVIDERS["codex"])
    try:
        assert events == ["spawn", "pidfd_open", "block_release", "shim_ready"]
        assert os.read(captured_block_fd[0], 1) == b"1"
        assert await handle.process.stdout.readline() == b"provider output\n"
    finally:
        for fd in captured_block_fd:
            os.close(fd)
        await handle.terminate()


async def test_readonly_command_stages_authority_before_launch_and_discards_child_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-core-credentials-002: health/API children see only a disposable authority copy."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    canonical = tmp_path / "canonical" / "auth.json"
    canonical.parent.mkdir()
    canonical.write_text('{"canonical":"must-not-change"}', encoding="utf-8")
    os.chmod(canonical, 0o600)
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    process = _HandshakeProcess([])
    stage_calls = 0
    chowns: list[tuple[int, int, int]] = []
    block_readers: list[int] = []

    def _record_fchown(fd: int, uid: int, gid: int) -> None:
        chowns.append((fd, uid, gid))

    monkeypatch.setattr(os, "fchown", _record_fchown)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        nonlocal stage_calls
        assert stage_calls == 1
        staged_authority = stage_home / ".codex" / "auth.json"
        assert staged_authority.read_bytes() == canonical.read_bytes()
        metadata = staged_authority.stat()
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        staged_authority.write_text('{"child":"discarded"}', encoding="utf-8")
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    def _stage_factory(_identity) -> SandboxStage:
        nonlocal stage_calls
        stage_calls += 1
        return SandboxStage(path=stage_home, root_fd=stage_fd)

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=_stage_factory,
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    try:
        result = await sandbox.run_readonly_command(
            PROVIDERS["codex"],
            command=("/usr/bin/true",),
            authority=ReadonlySandboxAuthority(
                relative_path=Path(".codex") / "auth.json",
                content=canonical.read_bytes(),
            ),
            timeout_s=1.0,
        )
    finally:
        for fd in block_readers:
            os.close(fd)

    assert result.returncode == 0
    assert result.output == b"provider output\n"
    assert canonical.read_text(encoding="utf-8") == '{"canonical":"must-not-change"}'
    assert not stage_home.exists()
    assert len(chowns) == 2
    assert all((uid, gid) == (61000, 61000) for _fd, uid, gid in chowns)


async def test_readonly_command_rejects_an_unsafe_authority_target_before_spawn(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: a staged-copy path escape launches no child domain."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority, SandboxUnavailableError
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    spawn = AsyncMock()
    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=spawn,
    )

    with pytest.raises(SandboxUnavailableError, match="startup failed safely"):
        await sandbox.run_readonly_command(
            PROVIDERS["codex"],
            command=("/usr/bin/true",),
            authority=ReadonlySandboxAuthority(
                relative_path=Path("..") / "canonical" / "auth.json",
                content=b"not-a-real-credential",
            ),
            timeout_s=1.0,
        )

    spawn.assert_not_awaited()
    assert not stage_home.exists()


async def test_readonly_command_rejects_oversized_stdout_before_materializing_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: untrusted child stdout has a fixed materialization bound."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority, SandboxUnavailableError
    from butlers.cli_auth.sandbox_platform import (
        _MAX_READONLY_COMMAND_OUTPUT_BYTES,
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    class _BoundedReadStream(asyncio.StreamReader):
        async def read(self, n: int = -1) -> bytes:
            assert 0 < n <= _MAX_READONLY_COMMAND_OUTPUT_BYTES
            return await super().read(n)

    process = _HandshakeProcess([])
    process.stdout = _BoundedReadStream()
    process.stdout.feed_data(
        b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\n" + b"x" * (_MAX_READONLY_COMMAND_OUTPUT_BYTES + 1)
    )
    process.stdout.feed_eof()
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_readers: list[int] = []
    monkeypatch.setattr(os, "fchown", lambda *_args: None)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    try:
        with pytest.raises(SandboxUnavailableError, match="stdout exceeded"):
            await sandbox.run_readonly_command(
                PROVIDERS["codex"],
                command=("/usr/bin/true",),
                authority=ReadonlySandboxAuthority(
                    relative_path=Path(".codex") / "auth.json",
                    content=b'{"safe":"staged"}',
                ),
                timeout_s=1.0,
            )
    finally:
        for fd in block_readers:
            os.close(fd)

    assert not stage_home.exists()


async def test_readonly_command_waits_for_eof_after_a_partial_first_stdout_chunk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: a partial read never looks like a completed child."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    first_chunk_seen = asyncio.Event()

    class _PartialReadStream(asyncio.StreamReader):
        async def read(self, n: int = -1) -> bytes:
            chunk = await super().read(n)
            if chunk:
                first_chunk_seen.set()
            return chunk

    process = _HandshakeProcess([])
    process.stdout = _PartialReadStream()
    process.stdout.feed_data(b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\npartial-result")
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_readers: list[int] = []
    monkeypatch.setattr(os, "fchown", lambda *_args: None)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    task = asyncio.create_task(
        sandbox.run_readonly_command(
            PROVIDERS["codex"],
            command=("/usr/bin/true",),
            authority=ReadonlySandboxAuthority(
                relative_path=Path(".codex") / "auth.json",
                content=b'{"safe":"staged"}',
            ),
            timeout_s=1.0,
        )
    )
    try:
        await asyncio.wait_for(first_chunk_seen.wait(), timeout=1.0)
        await asyncio.sleep(0)
        assert not task.done()
        assert process.wait_calls == 0
        process.stdout.feed_data(b"-second-chunk")
        await asyncio.sleep(0)
        assert process.wait_calls == 0
        process.stdout.feed_eof()
        result = await task
    finally:
        for fd in block_readers:
            os.close(fd)

    assert result.output == b"partial-result-second-chunk"
    assert not stage_home.exists()


async def test_readonly_command_times_out_after_partial_stdout_and_cleans_the_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: a no-EOF child cannot retain its stage or identity."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    process = _HandshakeProcess([])
    process.stdout = asyncio.StreamReader()
    process.stdout.feed_data(b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\npartial-result")
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_readers: list[int] = []
    monkeypatch.setattr(os, "fchown", lambda *_args: None)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    try:
        with pytest.raises(TimeoutError):
            await sandbox.run_readonly_command(
                PROVIDERS["codex"],
                command=("/usr/bin/true",),
                authority=ReadonlySandboxAuthority(
                    relative_path=Path(".codex") / "auth.json",
                    content=b'{"safe":"staged"}',
                ),
                timeout_s=0.01,
            )
    finally:
        for fd in block_readers:
            os.close(fd)

    assert process.wait_calls == 1
    assert not stage_home.exists()


async def test_readonly_command_uses_one_absolute_timeout_across_multiple_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: each small chunk cannot renew the total deadline."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    class _SlowChunkStream(asyncio.StreamReader):
        def __init__(self) -> None:
            super().__init__()
            self.read_calls = 0

        async def read(self, n: int = -1) -> bytes:
            self.read_calls += 1
            await asyncio.sleep(0.05)
            return b"chunk" if self.read_calls == 1 else b"later-chunk"

    process = _HandshakeProcess([])
    process.stdout = _SlowChunkStream()
    process.stdout.feed_data(b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\n")
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_readers: list[int] = []
    monkeypatch.setattr(os, "fchown", lambda *_args: None)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=InvocationIdentityPool(first_id=61000, last_id=61000),
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    try:
        with pytest.raises(TimeoutError):
            await sandbox.run_readonly_command(
                PROVIDERS["codex"],
                command=("/usr/bin/true",),
                authority=ReadonlySandboxAuthority(
                    relative_path=Path(".codex") / "auth.json",
                    content=b'{"safe":"staged"}',
                ),
                timeout_s=0.08,
            )
    finally:
        for fd in block_readers:
            os.close(fd)

    assert process.stdout.read_calls >= 2
    assert process.wait_calls == 1
    assert not stage_home.exists()


async def test_readonly_command_cancellation_waiting_for_next_chunk_cleans_the_domain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQ-core-credentials-002: direct reader cancellation cannot leak the child domain."""
    from butlers.cli_auth.sandbox import ReadonlySandboxAuthority
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        InvocationIdentityPool,
        ReadonlySandboxInvocation,
        SandboxStage,
    )

    first_chunk_seen = asyncio.Event()

    class _BlockingAfterChunkStream(asyncio.StreamReader):
        async def read(self, n: int = -1) -> bytes:
            chunk = await super().read(n)
            if chunk:
                first_chunk_seen.set()
            return chunk

    process = _HandshakeProcess([])
    process.stdout = _BlockingAfterChunkStream()
    process.stdout.feed_data(b"BUTLERS_RUNTIME_CLI_SANDBOX_READY\npartial-result")
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_readers: list[int] = []
    pool = InvocationIdentityPool(first_id=61000, last_id=61000)
    monkeypatch.setattr(os, "fchown", lambda *_args: None)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_readers.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=pool,
        exact_image_preflight=lambda: None,
        readonly_invocation_resolver=lambda _provider, command: ReadonlySandboxInvocation(
            command=command,
            readonly_inputs=(Path("/usr/bin/true"),),
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: None,
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    task = asyncio.create_task(
        sandbox.run_readonly_command(
            PROVIDERS["codex"],
            command=("/usr/bin/true",),
            authority=ReadonlySandboxAuthority(
                relative_path=Path(".codex") / "auth.json",
                content=b'{"safe":"staged"}',
            ),
            timeout_s=1.0,
        )
    )
    try:
        await asyncio.wait_for(first_chunk_seen.wait(), timeout=1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        for fd in block_readers:
            os.close(fd)

    assert process.wait_calls == 1
    assert not stage_home.exists()
    reused = await pool.acquire()
    assert reused.uid == 61000
    await pool.release(reused)


async def test_bubblewrap_startup_cancellation_after_release_terminates_pid1_and_cleans_up(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: cancellation after release cannot leak a live domain."""
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        DeviceAuthSandboxInvocation,
        InvocationIdentityPool,
        SandboxStage,
    )

    events: list[str] = []
    process = _BlockingHandshakeProcess(events)
    pool = InvocationIdentityPool(first_id=61000, last_id=61000)
    released = asyncio.Event()
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    block_observer_fd: list[int] = []

    async def _spawn(*argv: str, **_kwargs: object) -> _BlockingHandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_observer_fd.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    def _release_payload(block_fd: int) -> None:
        events.append("block_release")
        os.write(block_fd, b"1")
        released.set()

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=pool,
        exact_image_preflight=lambda: None,
        invocation_resolver=lambda _provider: DeviceAuthSandboxInvocation(
            command=("/usr/bin/true",),
            readonly_inputs=(Path("/usr/bin/true"),),
            relative_output_path=Path(".codex") / "auth.json",
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        release_payload=_release_payload,
        pidfd_send_signal=lambda *_args: events.append("pidfd_signal"),
        pidfd_is_dead=lambda _pidfd, _timeout: True,
    )

    task = asyncio.create_task(sandbox.launch_device_auth(PROVIDERS["codex"]))
    await asyncio.wait_for(released.wait(), timeout=1.0)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        for fd in block_observer_fd:
            os.close(fd)

    assert events == ["block_release", "pidfd_signal"]
    assert process.wait_calls == 1
    assert not stage_home.exists()
    reused_identity = await pool.acquire()
    assert reused_identity.uid == 61000
    await pool.release(reused_identity)


async def test_bubblewrap_handle_retains_the_identity_when_pid1_death_is_not_proven(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: failed pidfd containment cannot reuse a live UID."""
    from butlers.cli_auth.sandbox import SandboxUnavailableError
    from butlers.cli_auth.sandbox_platform import (
        BubblewrapDashboardCLIAuthSandbox,
        DeviceAuthSandboxInvocation,
        InvocationIdentityPool,
        SandboxStage,
    )

    events: list[str] = []
    process = _HandshakeProcess(events)
    pool = InvocationIdentityPool(first_id=61000, last_id=61000)
    block_observer_fd: list[int] = []
    stage_home = tmp_path / "stage-home"
    stage_home.mkdir(mode=0o700)
    stage_fd = os.open(stage_home, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)

    async def _spawn(*argv: str, **_kwargs: object) -> _HandshakeProcess:
        info_fd = int(argv[argv.index("--info-fd") + 1])
        block_observer_fd.append(os.dup(int(argv[argv.index("--block-fd") + 1])))
        os.write(info_fd, b'{"child-pid": 7123}\n')
        return process

    sandbox = BubblewrapDashboardCLIAuthSandbox(
        bwrap_path=tmp_path / "bwrap",
        shim_path=tmp_path / "runtime-cli-sandbox-init",
        identity_pool=pool,
        exact_image_preflight=lambda: None,
        invocation_resolver=lambda _provider: DeviceAuthSandboxInvocation(
            command=("/usr/bin/true",),
            readonly_inputs=(Path("/usr/bin/true"),),
            relative_output_path=Path(".codex") / "auth.json",
        ),
        stage_factory=lambda _identity: SandboxStage(path=stage_home, root_fd=stage_fd),
        spawn=_spawn,
        pidfd_open=lambda _pid, _flags=0: os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC),
        pidfd_send_signal=lambda *_args: events.append("pidfd_signal"),
        pidfd_is_dead=lambda _pidfd, _timeout: False,
    )

    handle = await sandbox.launch_device_auth(PROVIDERS["codex"])
    try:
        with patch(
            "butlers.cli_auth.sandbox_platform.read_validated_staged_device_auth_output"
        ) as read_stage:
            assert await handle.finalize(succeeded=True) is None
    finally:
        for fd in block_observer_fd:
            os.close(fd)

    read_stage.assert_not_called()
    assert process.wait_calls == 0
    assert events.count("pidfd_signal") == 2
    assert process.returncode == 0
    assert not stage_home.exists()
    with pytest.raises(SandboxUnavailableError, match="identity pool exhausted"):
        await pool.acquire()


@pytest.mark.skipif(shutil.which("cc") is None, reason="C compiler is required for shim contract")
def test_runtime_cli_sandbox_init_closes_inherited_descriptors_before_provider_exec(
    tmp_path: Path,
) -> None:
    """REQ-core-credentials-002: the real PID1 shim removes an inherited secret FD."""
    source = _REPO_ROOT / "scripts" / "runtime_cli_sandbox_init.c"
    shim = tmp_path / "runtime-cli-sandbox-init"
    subprocess.run(
        ["cc", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(shim), str(source)],
        check=True,
        capture_output=True,
        text=True,
    )

    secret_path = tmp_path / "secret-sentinel"
    secret_path.write_text("INHERITED-FD-SENTINEL", encoding="utf-8")
    initial_fd = os.open(secret_path, os.O_RDONLY)
    inherited_fd = os.dup2(initial_fd, 200)
    os.close(initial_fd)
    os.set_inheritable(inherited_fd, True)
    try:
        result = subprocess.run(
            [
                str(shim),
                "--",
                "/bin/sh",
                "-c",
                'test ! -e "/proc/self/fd/$1"; printf provider-ran',
                "sh",
                str(inherited_fd),
            ],
            check=False,
            close_fds=True,
            pass_fds=(inherited_fd,),
            capture_output=True,
            text=True,
            timeout=5,
        )
    finally:
        os.close(inherited_fd)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "BUTLERS_RUNTIME_CLI_SANDBOX_READY\nprovider-ran"
    assert "INHERITED-FD-SENTINEL" not in result.stdout + result.stderr
