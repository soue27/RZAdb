import asyncio
import contextvars
import hashlib
import logging
import queue
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.config import Settings
from app.core.request_context import get_request_context
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender


logger = logging.getLogger(__name__)

ERROR_EMAIL_COOLDOWN_SECONDS = 300.0
ERROR_EMAIL_QUEUE_SIZE = 100
ERROR_EMAIL_SHUTDOWN_TIMEOUT_SECONDS = 35.0
_INTERNAL_LOGGER_PREFIX = "app.infrastructure.emailing.error_notifications"
_HANDLER_MARKER = "_rzadb_error_email_handler"
_LOCAL_PART_ATOM = re.compile(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+")
_DOMAIN_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")


class ErrorEmailConfigurationError(ValueError):
    """Настройки SMTP-уведомлений некорректны при включённом ERROR_EMAIL_TO."""


@dataclass(frozen=True, slots=True)
class _Notification:
    """Минимальные безопасные данные события ошибки, передаваемые в очередь уведомлений.
    """
    timestamp: str
    level: str
    component: str
    request_id: str | None
    exception_type: str | None


def _validate_address(value: str | None, setting_name: str) -> None:
    """Проверяет синтаксис email-адреса для настройки уведомлений.

    Args:
        value: Проверяемый адрес.
        setting_name: Имя настройки для диагностического сообщения.

    Raises:
        ErrorEmailConfigurationError: Если адрес отсутствует или некорректен.
    """
    if not value or len(value) > 254 or value != value.strip():
        raise ErrorEmailConfigurationError(
            f"{setting_name} должен содержать корректный email-адрес."
        )

    local_part, separator, domain = value.partition("@")
    local_atoms = local_part.split(".")
    domain_labels = domain.split(".")
    if (
        not separator
        or "@" in domain
        or not local_part
        or len(local_part) > 64
        or any(not _LOCAL_PART_ATOM.fullmatch(atom) for atom in local_atoms)
        or len(domain) > 253
        or len(domain_labels) < 2
        or any(
            len(label) > 63 or not _DOMAIN_LABEL.fullmatch(label)
            for label in domain_labels
        )
    ):
        raise ErrorEmailConfigurationError(
            f"{setting_name} должен содержать корректный email-адрес."
        )


def validate_error_email_settings(settings: Settings) -> str | None:
    """Проверяет настройки email-уведомлений и возвращает None, если канал отключён."""
    recipient = settings.error_email_to
    if recipient is None:
        return None

    _validate_address(recipient, "ERROR_EMAIL_TO")
    _validate_address(settings.smtp_from_email, "SMTP_FROM_EMAIL")
    if (
        not settings.smtp_host
        or settings.smtp_host != settings.smtp_host.strip()
        or any(char.isspace() for char in settings.smtp_host)
    ):
        raise ErrorEmailConfigurationError("Не задан SMTP_HOST для уведомлений.")
    if not 1 <= settings.smtp_port <= 65535:
        raise ErrorEmailConfigurationError("SMTP_PORT должен быть от 1 до 65535.")
    if bool(settings.smtp_username) != bool(settings.smtp_password):
        raise ErrorEmailConfigurationError(
            "SMTP_USERNAME и SMTP_PASSWORD должны быть заданы одновременно."
        )
    if settings.smtp_starttls and settings.smtp_use_ssl:
        raise ErrorEmailConfigurationError(
            "SMTP_STARTTLS и SMTP_USE_SSL нельзя включать одновременно."
        )
    if not settings.smtp_starttls and not settings.smtp_use_ssl:
        raise ErrorEmailConfigurationError(
            "Для уведомлений включите SMTP_STARTTLS или SMTP_USE_SSL."
        )

    return recipient


class ErrorEmailNotificationHandler(logging.Handler):
    """Неблокирующий обработчик ERROR/CRITICAL с отдельным рабочим потоком доставки."""

    def __init__(
        self,
        *,
        recipient: str,
        sender: SMTPEmailSender,
        queue_size: int = ERROR_EMAIL_QUEUE_SIZE,
        clock=time.monotonic,
    ) -> None:
        """Создаёт обработчик с ограниченной очередью и отдельным рабочим потоком.

        Args:
            recipient: Адрес получателя уведомлений.
            sender: SMTP-адаптер.
            queue_size: Максимальный размер очереди.
            clock: Монотонные часы для контроля cooldown.
        """
        super().__init__(level=logging.ERROR)
        if queue_size < 1:
            raise ValueError("queue_size must be positive")
        setattr(self, _HANDLER_MARKER, True)
        self.recipient = recipient
        self.sender = sender
        self._queue: queue.Queue[_Notification] = queue.Queue(maxsize=queue_size)
        self._clock = clock
        self._fingerprints: OrderedDict[bytes, float] = OrderedDict()
        self._stopping = threading.Event()
        self._shutdown_deadline: float | None = None
        self._dropped_notifications = 0
        self._delivery_failures = 0
        self._thread = threading.Thread(
            target=contextvars.Context().run,
            args=(self._thread_main,),
            name="error-email-notifications",
            daemon=True,
        )

    @property
    def dropped_notifications(self) -> int:
        """Возвращает количество уведомлений, отброшенных из-за переполнения очереди.
        """
        with self.lock:
            return self._dropped_notifications

    @property
    def delivery_failures(self) -> int:
        """Возвращает количество неудачных попыток SMTP-доставки.
        """
        with self.lock:
            return self._delivery_failures

    @property
    def pending_notifications(self) -> int:
        """Возвращает текущее количество уведомлений в очереди.
        """
        return self._queue.qsize()

    def start(self) -> None:
        """Запускает фоновый поток и асинхронный worker доставки.
        """
        self._thread.start()

    def _thread_main(self) -> None:
        """Создаёт event loop рабочего потока и запускает worker уведомлений.
        """
        try:
            asyncio.run(self._run_worker())
        except Exception as exc:
            with self.lock:
                self._delivery_failures += 1
            logger.error(
                "Error notification worker failed (%s)",
                self._sanitize_field(type(exc).__name__),
            )

    def emit(self, record: logging.LogRecord) -> None:
        """Принимает ERROR/CRITICAL запись и помещает безопасную сводку в ограниченную очередь.

        Не выполняет сетевых операций и не блокирует вызывающий поток ожиданием SMTP.
        """
        if record.levelno not in (logging.ERROR, logging.CRITICAL):
            return
        if record.name.startswith(_INTERNAL_LOGGER_PREFIX) or self._stopping.is_set():
            return

        try:
            notification, fingerprint = self._make_notification(record)
            now = self._clock()
            self._expire_fingerprints(now)
            last_accepted = self._fingerprints.get(fingerprint)
            if (
                last_accepted is not None
                and now - last_accepted < ERROR_EMAIL_COOLDOWN_SECONDS
            ):
                return

            try:
                self._queue.put_nowait(notification)
            except queue.Full:
                self._dropped_notifications += 1
                return

            self._fingerprints[fingerprint] = now
            self._fingerprints.move_to_end(fingerprint)
        except Exception:
            # Logging handlers must not raise into the application or log recursively.
            self._dropped_notifications += 1

    def _make_notification(
        self,
        record: logging.LogRecord,
    ) -> tuple[_Notification, bytes]:
        """Формирует безопасную сводку ошибки и fingerprint для подавления повторов.

        Args:
            record: Запись стандартного logging.

        Returns:
            Пара из уведомления и fingerprint-данных для контроля повторов.
        """
        exception_type = None
        if record.exc_info and record.exc_info[0] is not None:
            exception_type = self._sanitize_field(record.exc_info[0].__name__)

        try:
            message = record.getMessage()
        except Exception:
            message = "<unformattable-message>"
        normalized_message = re.sub(
            r"\s+",
            " ",
            unicodedata.normalize("NFC", message),
        ).strip()
        fingerprint_payload = "\0".join(
            (
                record.name,
                record.levelname,
                exception_type or "",
                normalized_message,
            )
        )
        fingerprint = hashlib.sha256(fingerprint_payload.encode("utf-8")).digest()

        request_context = get_request_context()
        request_id = request_context.request_id if request_context is not None else None
        timestamp = datetime.fromtimestamp(record.created, tz=UTC).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        component = self._sanitize_field(record.name)
        notification = _Notification(
            timestamp=timestamp,
            level=record.levelname,
            component=component,
            request_id=request_id,
            exception_type=exception_type,
        )
        return notification, fingerprint

    @staticmethod
    def _sanitize_field(value: str) -> str:
        """Удаляет управляющие символы и ограничивает длину поля письма.

        Args:
            value: Исходное значение.

        Returns:
            Безопасный однострочный текст.
        """
        return "".join(
            character if character.isprintable() else " "
            for character in value
        )

    def _expire_fingerprints(self, now: float) -> None:
        """Удаляет истёкшие fingerprint из окна подавления повторных уведомлений.

        Args:
            now: Текущее монотонное время.
        """
        while self._fingerprints:
            _, accepted_at = next(iter(self._fingerprints.items()))
            if now - accepted_at < ERROR_EMAIL_COOLDOWN_SECONDS:
                break
            self._fingerprints.popitem(last=False)

    async def _run_worker(self) -> None:
        """Последовательно отправляет уведомления из очереди через SMTP.
        """
        while True:
            if self._stopping.is_set():
                deadline = self._shutdown_deadline
                if deadline is not None and self._clock() >= deadline:
                    self._discard_pending()
                    return
                if self._queue.empty():
                    return

            try:
                notification = await asyncio.to_thread(self._queue.get, True, 0.1)
            except queue.Empty:
                continue

            try:
                subject, body = self._format_email(notification)
                try:
                    await self.sender.send(
                        to=self.recipient,
                        subject=subject,
                        body=body,
                    )
                except Exception as exc:
                    with self.lock:
                        self._delivery_failures += 1
                    logger.error(
                        "Error notification delivery failed (%s)",
                        self._sanitize_field(type(exc).__name__),
                    )
            finally:
                self._queue.task_done()

    @staticmethod
    def _format_email(notification: _Notification) -> tuple[str, str]:
        """Формирует тему и текст письма по безопасной сводке ошибки.

        Args:
            notification: Данные уведомления.

        Returns:
            Тема и текст письма.
        """
        subject = f"[RZAdb] {notification.level} error notification"
        fields = [
            f"Timestamp UTC: {notification.timestamp}",
            f"Level: {notification.level}",
            f"Component: {notification.component}",
        ]
        if notification.request_id is not None:
            fields.append(f"Request ID: {notification.request_id}")
        if notification.exception_type is not None:
            fields.append(f"Exception type: {notification.exception_type}")
        return subject, "RZAdb error notification\n\n" + "\n".join(fields) + "\n"

    def _discard_pending(self) -> None:
        """Удаляет оставшиеся в очереди уведомления при завершении worker.
        """
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return
            else:
                self._queue.task_done()
                with self.lock:
                    self._dropped_notifications += 1

    async def stop(self) -> None:
        """Останавливает worker, ожидает завершения ограниченное время и освобождает ресурсы.
        """
        with self.lock:
            self._shutdown_deadline = (
                self._clock() + ERROR_EMAIL_SHUTDOWN_TIMEOUT_SECONDS
            )
            self._stopping.set()
        await asyncio.to_thread(
            self._thread.join,
            ERROR_EMAIL_SHUTDOWN_TIMEOUT_SECONDS,
        )


_handler_registry_lock = threading.Lock()
_active_handler: ErrorEmailNotificationHandler | None = None
_active_settings: Settings | None = None
_active_references = 0


def acquire_error_email_handler(
    settings: Settings,
) -> ErrorEmailNotificationHandler | None:
    """Создаёт и устанавливает обработчик процесса, если email-уведомления настроены."""
    global _active_handler, _active_references, _active_settings

    recipient = validate_error_email_settings(settings)
    if recipient is None:
        return None

    with _handler_registry_lock:
        root_logger = logging.getLogger()
        if _active_handler is not None:
            if _active_references == 0:
                raise ErrorEmailConfigurationError(
                    "Подсистема email-уведомлений завершает работу; "
                    "повторите запуск приложения."
                )
            if _active_settings is not settings:
                raise ErrorEmailConfigurationError(
                    "Несколько приложений с разными настройками ERROR_EMAIL_TO "
                    "не могут работать в одном процессе."
                )
            _active_references += 1
            if _active_handler not in root_logger.handlers:
                root_logger.addHandler(_active_handler)
            return _active_handler

        try:
            sender = SMTPEmailSender(settings)
        except ValueError:
            raise ErrorEmailConfigurationError(
                "SMTP-конфигурация уведомлений неполная или некорректная."
            ) from None
        handler = ErrorEmailNotificationHandler(recipient=recipient, sender=sender)
        handler.start()
        root_logger.addHandler(handler)
        _active_handler = handler
        _active_settings = settings
        _active_references = 1
        return handler


async def release_error_email_handler(
    handler: ErrorEmailNotificationHandler | None,
) -> None:
    """Удаляет обработчик и останавливает worker при завершении последнего приложения."""
    global _active_handler, _active_references, _active_settings

    if handler is None:
        return

    with _handler_registry_lock:
        if handler is not _active_handler or _active_references <= 0:
            return
        _active_references -= 1
        if _active_references > 0:
            return
        logging.getLogger().removeHandler(handler)

    try:
        await handler.stop()
    finally:
        with _handler_registry_lock:
            if handler is _active_handler:
                _active_handler = None
                _active_settings = None
                _active_references = 0
        handler.close()
