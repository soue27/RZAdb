from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

MODULE_PATH = Path(__file__).parents[3] / "deploy" / "systemd" / "rzadb_monitor.py"
SPEC = importlib.util.spec_from_file_location("rzadb_monitor", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)
TZ = ZoneInfo("Asia/Yekaterinburg")


def make_backup(tmp_path, *, status="success", hash_matches=True):
    dump = tmp_path / "sample.dump"
    dump.write_bytes(b"verified backup bytes")
    import hashlib

    checksum = hashlib.sha256(dump.read_bytes()).hexdigest()
    manifest = {
        "started_at": "2026-11-16T00:30:00+00:00",
        "dump_filename": "sample.dump",
        "dump_created": True,
        "pg_restore_list_validation": "passed",
        "sha256": checksum if hash_matches else "wrong",
        "status": status,
        "local_storage": {"status": "success"},
    }
    path = tmp_path / "rzadb_sample.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_manifest_for_local_day_and_verified_sha_is_accepted(tmp_path, monkeypatch):
    make_backup(tmp_path)
    now = datetime(2026, 11, 16, 8, 0, tzinfo=TZ)
    monkeypatch.setattr(monitor, "run_command", lambda *_args, **_kwargs: type("R", (), {"returncode": 0})())

    items = monitor._successful_backups(now, tmp_path)

    assert len(items) == 1
    assert monitor._validate_backup(items[0]) == []


def test_backup_hash_mismatch_is_reported(tmp_path, monkeypatch):
    make_backup(tmp_path, hash_matches=False)
    now = datetime(2026, 11, 16, 8, 0, tzinfo=TZ)
    monkeypatch.setattr(monitor, "run_command", lambda *_args, **_kwargs: type("R", (), {"returncode": 0})())

    item = monitor._successful_backups(now, tmp_path)[0]

    assert "backup SHA-256 does not match its manifest" in monitor._validate_backup(item)


def test_manifest_for_failed_backup_is_not_accepted(tmp_path):
    make_backup(tmp_path, status="failed")
    now = datetime(2026, 11, 16, 8, 0, tzinfo=TZ)

    assert monitor._successful_backups(now, tmp_path) == []


def test_compose_health_requires_healthy_web_and_database(monkeypatch):
    def fake_run(args, **_kwargs):
        result = type("Result", (), {})()
        result.returncode = 0
        result.stdout = "\n".join(
            [
                json.dumps({"Service": "web", "State": "running", "Health": "healthy"}),
                json.dumps({"Service": "db", "State": "running", "Health": "starting"}),
            ]
        )
        return result

    monkeypatch.setattr(monitor, "run_command", fake_run)

    assert monitor._compose_health() == ["Docker Compose service db is not healthy"]


def test_low_disk_space_is_reported(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    marker = tmp_path / "digest.success"
    marker.touch()
    monkeypatch.setattr(monitor, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(monitor, "SUCCESS_MARKER", marker)
    monkeypatch.setattr(monitor, "_systemd_properties", lambda _unit: {"ActiveState": "active", "Result": "success"})
    monkeypatch.setattr(monitor, "_compose_health", list)
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _path: type("U", (), {"free": 1, "total": 100})())
    monkeypatch.setattr(monitor, "_successful_backups", lambda *_args: [])

    health = monitor.collect_health(datetime(2026, 11, 16, 8, 0, tzinfo=TZ))

    assert "free disk space is below the configured monitor threshold" in health["failures"]


def test_disabled_digest_is_deferred_without_masking_backup_failure(
    tmp_path, monkeypatch
):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    monkeypatch.setattr(monitor, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(monitor, "_systemd_properties", lambda unit: {
        "ActiveState": "inactive" if unit == "rzadb-email-digest.timer" else "active",
        "UnitFileState": "disabled" if unit == "rzadb-email-digest.timer" else "enabled",
        "Result": "success",
    })
    monkeypatch.setattr(monitor, "_compose_health", list)
    monkeypatch.setattr(monitor.shutil, "disk_usage", lambda _path: type("U", (), {"free": 50 * 1024**3, "total": 100 * 1024**3})())
    monkeypatch.setattr(monitor, "_successful_backups", lambda *_args: [])

    health = monitor.collect_health(datetime(2026, 11, 16, 8, 30, tzinfo=TZ))

    assert health["statuses"]["email_digest"] == "DEFERRED"
    assert not any("Email Digest" in item for item in health["failures"])
    assert "no successful PostgreSQL backup manifest is available" in health["failures"]


def test_monitor_passes_with_valid_backup_and_deferred_digest(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    make_backup(backup_dir)
    monkeypatch.setattr(monitor, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(monitor, "_systemd_properties", lambda unit: {
        "ActiveState": "inactive" if unit == "rzadb-email-digest.timer" else "active",
        "UnitFileState": "disabled" if unit == "rzadb-email-digest.timer" else "enabled",
        "Result": "success",
    })
    monkeypatch.setattr(
        monitor,
        "run_command",
        lambda args, **_kwargs: type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": "\n".join(
                    [
                        json.dumps({"Service": "web", "State": "running", "Health": "healthy"}),
                        json.dumps({"Service": "db", "State": "running", "Health": "healthy"}),
                    ]
                ) if args[-1] == "json" else "",
            },
        )(),
    )
    monkeypatch.setattr(
        monitor.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": 50 * 1024**3, "total": 100 * 1024**3})(),
    )

    health = monitor.collect_health(datetime(2026, 11, 16, 8, 30, tzinfo=TZ))

    assert health["status"] == "OK"
    assert health["statuses"]["email_digest"] == "DEFERRED"
    assert health["failures"] == []


def test_enabled_digest_missing_weekday_run_is_an_error(tmp_path, monkeypatch):
    marker = tmp_path / "digest.success"
    monkeypatch.setattr(monitor, "SUCCESS_MARKER", marker)
    monkeypatch.setattr(monitor, "_systemd_properties", lambda unit: {
        "ActiveState": "active" if unit.endswith(".timer") else "inactive",
        "UnitFileState": "enabled",
        "Result": "success",
    })

    status, issues = monitor._email_digest_status(
        datetime(2026, 11, 16, 8, 30, tzinfo=TZ)
    )

    assert status == "ERROR"
    assert issues == ["weekday Email Digest has no successful run marker for today"]


def test_running_digest_is_not_reported_as_missed(tmp_path, monkeypatch):
    monkeypatch.setattr(monitor, "SUCCESS_MARKER", tmp_path / "missing-marker")
    monkeypatch.setattr(monitor, "_systemd_properties", lambda unit: {
        "ActiveState": "activating" if unit.endswith(".service") else "active",
        "UnitFileState": "enabled",
        "Result": "success",
    })

    status, issues = monitor._email_digest_status(
        datetime(2026, 11, 16, 8, 30, tzinfo=TZ)
    )

    assert status == "RUNNING"
    assert issues == []


def test_failed_digest_service_is_an_error_even_with_a_marker(tmp_path, monkeypatch):
    marker = tmp_path / "digest.success"
    marker.touch()
    monkeypatch.setattr(monitor, "SUCCESS_MARKER", marker)
    monkeypatch.setattr(monitor, "_systemd_properties", lambda unit: {
        "ActiveState": "active" if unit.endswith(".timer") else "inactive",
        "UnitFileState": "enabled",
        "Result": "failed" if unit.endswith(".service") else "success",
    })

    status, issues = monitor._email_digest_status(
        datetime(2026, 11, 16, 8, 30, tzinfo=TZ)
    )

    assert status == "ERROR"
    assert issues == ["systemd reports the latest Email Digest service run failed"]


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 11, 15, 8, 30, tzinfo=TZ), "NOT_DUE"),
        (datetime(2026, 11, 16, 7, 29, tzinfo=TZ), "NOT_DUE"),
    ],
)
def test_enabled_digest_is_not_due_on_weekends_or_before_schedule(
    monkeypatch, now, expected
):
    monkeypatch.setattr(monitor, "_systemd_properties", lambda _unit: {
        "ActiveState": "active",
        "UnitFileState": "enabled",
        "Result": "success",
    })

    status, issues = monitor._email_digest_status(now)

    assert status == expected
    assert issues == []


def test_clearing_deferred_digest_does_not_send_recovery_notification(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("sys.argv", ["rzadb_monitor"])
    state = tmp_path / "state.json"
    monkeypatch.setattr(monitor, "MONITOR_STATE", state)
    monkeypatch.setattr(
        monitor,
        "collect_health",
        lambda: {
            "status": "OK",
            "statuses": {"email_digest": "DEFERRED"},
            "failures": [],
            "last_successful_backup": "2026-11-16T03:00:00+05:00",
        },
    )
    monkeypatch.setattr(
        monitor,
        "_load_previous",
        lambda: {"systemd timer rzadb-email-digest.timer is not active"},
    )
    notifications = []
    monkeypatch.setattr(
        monitor,
        "notify_changes",
        lambda failures, previous: notifications.append((failures, previous)),
    )

    result = monitor.main()

    assert result == 0
    assert notifications == [(set(), set())]


def test_notification_state_suppresses_duplicates_and_reports_recovery(tmp_path, monkeypatch):
    state = tmp_path / "state.json"
    monkeypatch.setattr(monitor, "MONITOR_STATE", state)
    sent = []
    monkeypatch.setattr(monitor, "run_command", lambda _args, input_text=None: sent.append(input_text) or type("R", (), {"returncode": 0})())
    previous = set()
    active = {"backup failed"}

    monitor.notify_changes(active, previous)
    monitor.notify_changes(active, active)
    monitor.notify_changes(set(), active)

    assert len(sent) == 2
    assert json.loads(sent[0]) == {"failures": ["backup failed"], "recoveries": []}
    assert json.loads(sent[1]) == {"failures": [], "recoveries": ["backup failed"]}


def test_notification_transport_failure_is_journalled_without_response_text(monkeypatch, caplog):
    result = type("R", (), {"returncode": 1})()
    monkeypatch.setattr(monitor, "run_command", lambda *_args, **_kwargs: result)

    monitor.notify_changes({"smtp failed"}, set())

    assert "notifier exit status 1" in caplog.text
    assert "smtp failed" not in caplog.text
