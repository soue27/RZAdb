"""Host-side health check for RZAdb systemd jobs and PostgreSQL backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Yekaterinburg")
PROJECT = Path("/opt/rzadb")
BACKUP_DIR = Path("/srv/rzadb/backups")
MONITOR_STATE = Path("/var/lib/rzadb-monitor/alert-state.json")
SUCCESS_MARKER = Path("/srv/rzadb/monitor/email-digest.success")
COMPOSE = [
    "/usr/bin/docker",
    "compose",
    "--env-file",
    ".env.production",
    "-f",
    "compose.production.yaml",
]
MIN_FREE_BYTES = 2 * 1024**3
MIN_FREE_RATIO = 0.10
logger = logging.getLogger("rzadb-monitor")


def run_command(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def _systemd_properties(unit: str) -> dict[str, str]:
    result = run_command(
        [
            "/usr/bin/systemctl",
            "show",
            unit,
            "--property=ActiveState,UnitFileState,Result,ExecMainStatus",
        ]
    )
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def _successful_backups(now: datetime, backup_dir: Path) -> list[tuple[datetime, Path, dict[str, Any]]]:
    backups: list[tuple[datetime, Path, dict[str, Any]]] = []
    if not backup_dir.is_dir():
        return backups
    for manifest_path in backup_dir.glob("rzadb_*.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            started = datetime.fromisoformat(manifest["started_at"])
            if started.tzinfo is None:
                continue
            started_local = started.astimezone(TZ)
            if (
                manifest.get("status") == "success"
                and manifest.get("dump_created") is True
                and manifest.get("pg_restore_list_validation") == "passed"
                and manifest.get("local_storage", {}).get("status") == "success"
                and started_local <= now
            ):
                backups.append((started_local, manifest_path, manifest))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            logger.warning("Ignoring unreadable backup manifest: %s", manifest_path.name)
    return sorted(backups, key=lambda item: item[0], reverse=True)


def _validate_backup(
    backup: tuple[datetime, Path, dict[str, Any]],
) -> list[str]:
    _, manifest_path, manifest = backup
    issues: list[str] = []
    filename = manifest.get("dump_filename")
    expected_hash = manifest.get("sha256")
    if not isinstance(filename, str) or Path(filename).name != filename:
        return ["backup manifest has an invalid dump filename"]
    dump_path = manifest_path.parent / filename
    if not dump_path.is_file():
        return ["backup manifest points to a missing dump"]
    digest = hashlib.sha256()
    try:
        with dump_path.open("rb") as dump_file:
            for chunk in iter(lambda: dump_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ["backup dump could not be read for SHA-256 verification"]
    if not isinstance(expected_hash, str) or digest.hexdigest() != expected_hash:
        issues.append("backup SHA-256 does not match its manifest")
    checked = run_command(
        [
            *COMPOSE,
            "exec",
            "-T",
            "web",
            "pg_restore",
            "--list",
            f"/app/data/backups/{filename}",
        ]
    )
    if checked.returncode:
        issues.append("pg_restore --list failed for the latest backup")
    return issues


def _compose_health() -> list[str]:
    result = run_command([*COMPOSE, "ps", "--format", "json"])
    if result.returncode:
        return ["Docker Compose status could not be read"]
    services: dict[str, dict[str, Any]] = {}
    try:
        for line in result.stdout.splitlines():
            if line.strip():
                item = json.loads(line)
                services[item["Service"]] = item
    except (ValueError, KeyError, TypeError):
        return ["Docker Compose status output was invalid"]
    issues = []
    for name in ("web", "db"):
        item = services.get(name)
        if not item or item.get("State") != "running" or item.get("Health") != "healthy":
            issues.append(f"Docker Compose service {name} is not healthy")
    return issues


def _email_digest_status(now: datetime) -> tuple[str, list[str]]:
    timer = _systemd_properties("rzadb-email-digest.timer")
    unit_file_state = timer.get("UnitFileState")
    if unit_file_state in {"disabled", "disabled-runtime"}:
        return "DEFERRED", []
    if unit_file_state not in {"enabled", "enabled-runtime"}:
        return "ERROR", ["Email Digest timer is not installed or enabled"]
    if timer.get("ActiveState") != "active":
        return "ERROR", ["systemd timer rzadb-email-digest.timer is not active"]
    if now.weekday() >= 5 or now.time() < time(7, 30):
        return "NOT_DUE", []

    service = _systemd_properties("rzadb-email-digest.service")
    if service.get("ActiveState") in {"active", "activating"}:
        return "RUNNING", []
    if service.get("Result") == "failed":
        return "ERROR", ["systemd reports the latest Email Digest service run failed"]
    try:
        marker_time = datetime.fromtimestamp(SUCCESS_MARKER.stat().st_mtime, TZ)
    except OSError:
        return "ERROR", ["weekday Email Digest has no successful run marker for today"]
    if marker_time.date() != now.date():
        return "ERROR", ["weekday Email Digest did not complete today"]
    return "OK", []


def collect_health(now: datetime | None = None) -> dict[str, Any]:
    current = now or datetime.now(TZ)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    current = current.astimezone(TZ)
    issues: list[str] = []
    for unit in ("rzadb-backup.timer", "rzadb-monitor.timer"):
        if _systemd_properties(unit).get("ActiveState") != "active":
            issues.append(f"systemd timer {unit} is not active")

    digest_status, digest_issues = _email_digest_status(current)
    issues.extend(digest_issues)

    backups = _successful_backups(current, BACKUP_DIR)
    if not backups:
        issues.append("no successful PostgreSQL backup manifest is available")
    else:
        latest = backups[0]
        if latest[0].date() != current.date():
            issues.append("no successful PostgreSQL backup exists for today")
        if current - latest[0] > timedelta(hours=24):
            issues.append("last successful PostgreSQL backup is older than 24 hours")
        issues.extend(_validate_backup(latest))

    for unit in ("rzadb-backup.service",):
        if _systemd_properties(unit).get("Result") == "failed":
            today_success = bool(backups and backups[0][0].date() == current.date())
            if not today_success:
                issues.append(f"systemd reports the latest {unit} run failed")

    usage = shutil.disk_usage(BACKUP_DIR if BACKUP_DIR.exists() else Path("/srv/rzadb"))
    if usage.free < MIN_FREE_BYTES or usage.free / max(usage.total, 1) < MIN_FREE_RATIO:
        issues.append("free disk space is below the configured monitor threshold")
    issues.extend(_compose_health())
    return {
        "checked_at": current.isoformat(),
        "status": "ERROR" if issues else "OK",
        "statuses": {"email_digest": digest_status},
        "failures": sorted(set(issues)),
        "last_successful_backup": backups[0][0].isoformat() if backups else None,
    }


def _load_previous() -> set[str]:
    try:
        value = json.loads(MONITOR_STATE.read_text(encoding="utf-8"))
        failures = value.get("failures", [])
        return {item for item in failures if isinstance(item, str)}
    except (OSError, ValueError, AttributeError):
        return set()


def _save_current(failures: set[str]) -> None:
    MONITOR_STATE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(MONITOR_STATE.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".alert-state-", dir=MONITOR_STATE.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump({"failures": sorted(failures)}, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, MONITOR_STATE)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def notify_changes(failures: set[str], previous: set[str]) -> None:
    new = sorted(failures - previous)
    recovered = sorted(previous - failures)
    if not new and not recovered:
        return
    payload = json.dumps({"failures": new, "recoveries": recovered}, ensure_ascii=False)
    result = run_command(
        [*COMPOSE, "exec", "-T", "web", "python", "-m", "app.infrastructure.monitor.notify"],
        input_text=payload,
    )
    if result.returncode:
        logger.error(
            "SUPERADMIN health email was not sent (notifier exit status %d)",
            result.returncode,
        )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="scheduled")
    parser.parse_args()
    try:
        health = collect_health()
        failures = set(health["failures"])
        previous = _load_previous()
        notification_previous = previous.copy()
        if health["statuses"]["email_digest"] == "DEFERRED":
            notification_previous.discard(
                "systemd timer rzadb-email-digest.timer is not active"
            )
        notify_changes(failures, notification_previous)
        _save_current(failures)
        logger.info(
            "Email Digest monitoring status: %s",
            health["statuses"]["email_digest"],
        )
        if failures:
            logger.error("Health check found %d issue(s)", len(failures))
        else:
            logger.info("Health check passed; last successful backup: %s", health["last_successful_backup"])
        return 1 if failures else 0
    except Exception as exc:  # noqa: BLE001 — report unexpected monitor failures safely.
        logger.error("Health check failed (%s)", type(exc).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(main())
