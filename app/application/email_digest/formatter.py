from dataclasses import dataclass
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo
from uuid import UUID


EKATERINBURG_TZ = ZoneInfo("Asia/Yekaterinburg")

STATUS_LABELS = {
    "assigned": "Назначена",
    "in_progress": "В работе",
    "under_review": "На проверке",
}

ROLE_ENGINEER = "engineer"
ROLE_MANAGER = "manager"


@dataclass(frozen=True, slots=True)
class DigestTask:
    """Минимальные данные задачи, необходимые для email-сводки."""

    description: str
    status: str
    deadline_at: datetime | None
    assigned_to: UUID | None = None
    assignee_name: str | None = None


@dataclass(frozen=True, slots=True)
class EmailDigestMessage:
    """Готовое письмо с текстовой и HTML-версиями."""

    subject: str
    text_body: str
    html_body: str


@dataclass(frozen=True, slots=True)
class TaskDigestInfo:
    """Рассчитанные показатели задачи для отображения."""

    task: DigestTask
    status_label: str
    deadline_label: str
    is_overdue: bool
    days_until_deadline: int | None
    days_overdue: int | None


@dataclass(frozen=True, slots=True)
class DigestCounters:
    """Счётчики задач в сводке."""

    total: int
    overdue: int
    without_deadline: int
    own_total: int | None = None
    own_overdue: int | None = None


class EmailDigestFormatter:
    """Формирует email-сводки по задачам без доступа к БД и SMTP."""

    def format_engineer_digest(
        self,
        *,
        recipient_name: str,
        recipient_id: UUID,
        tasks: list[DigestTask],
        now: datetime,
    ) -> EmailDigestMessage:
        """Формирует сводку активных задач конкретного инженера."""
        self._validate_now(now)

        task_infos = [self._build_task_info(task, now) for task in tasks]

        counters = self._build_counters(task_infos)

        return self._render(
            title="Сводка задач инженера",
            recipient_name=recipient_name,
            task_infos=task_infos,
            counters=counters,
            now=now,
            role=ROLE_ENGINEER,
        )

    def format_manager_digest(
        self,
        *,
        recipient_name: str,
        recipient_id: UUID,
        tasks: list[DigestTask],
        now: datetime,
    ) -> EmailDigestMessage:
        """Формирует сводку задач предприятия для руководителя."""
        self._validate_now(now)

        task_infos = [self._build_task_info(task, now) for task in tasks]

        own_tasks = [
            info for info in task_infos if info.task.assigned_to == recipient_id
        ]

        counters = self._build_counters(
            task_infos,
            own_tasks=own_tasks,
        )

        return self._render(
            title="Сводка задач предприятия",
            recipient_name=recipient_name,
            task_infos=task_infos,
            counters=counters,
            now=now,
            role=ROLE_MANAGER,
        )

    @staticmethod
    def _validate_now(now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

    @staticmethod
    def _to_local(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("deadline_at must be timezone-aware")

        return value.astimezone(EKATERINBURG_TZ)

    def _build_task_info(
        self,
        task: DigestTask,
        now: datetime,
    ) -> TaskDigestInfo:
        local_now = self._to_local(now)
        status_label = STATUS_LABELS.get(task.status, task.status)

        if task.deadline_at is None:
            return TaskDigestInfo(
                task=task,
                status_label=status_label,
                deadline_label="Не установлен",
                is_overdue=False,
                days_until_deadline=None,
                days_overdue=None,
            )

        deadline = self._to_local(task.deadline_at)
        is_overdue = deadline < local_now

        calendar_difference = (deadline.date() - local_now.date()).days

        return TaskDigestInfo(
            task=task,
            status_label=status_label,
            deadline_label=deadline.strftime("%d.%m.%Y %H:%M"),
            is_overdue=is_overdue,
            days_until_deadline=(
                max(calendar_difference, 0) if not is_overdue else None
            ),
            days_overdue=(max(-calendar_difference, 0) if is_overdue else None),
        )

    @staticmethod
    def _build_counters(
        task_infos: list[TaskDigestInfo],
        *,
        own_tasks: list[TaskDigestInfo] | None = None,
    ) -> DigestCounters:
        overdue = sum(info.is_overdue for info in task_infos)
        without_deadline = sum(info.task.deadline_at is None for info in task_infos)

        if own_tasks is None:
            return DigestCounters(
                total=len(task_infos),
                overdue=overdue,
                without_deadline=without_deadline,
            )

        return DigestCounters(
            total=len(task_infos),
            overdue=overdue,
            without_deadline=without_deadline,
            own_total=len(own_tasks),
            own_overdue=sum(info.is_overdue for info in own_tasks),
        )

    def _render(
        self,
        *,
        title: str,
        recipient_name: str,
        task_infos: list[TaskDigestInfo],
        counters: DigestCounters,
        now: datetime,
        role: str,
    ) -> EmailDigestMessage:
        local_now = self._to_local(now)
        subject = f"{title} — {local_now.strftime('%d.%m.%Y')}"

        text_lines = [
            f"Здравствуйте, {recipient_name}!",
            "",
            title,
            f"Дата формирования: {local_now:%d.%m.%Y %H:%M}",
            "",
            f"Всего активных задач: {counters.total}",
            f"Просроченных задач: {counters.overdue}",
            f"Задач без срока: {counters.without_deadline}",
        ]

        if role == ROLE_MANAGER:
            text_lines.extend(
                [
                    f"Ваших задач в работе: {counters.own_total}",
                    f"Ваших просроченных задач: {counters.own_overdue}",
                ]
            )

        text_lines.append("")

        if not task_infos:
            text_lines.append("Активных задач нет.")
        else:
            text_lines.append("Список задач:")

            for index, info in enumerate(task_infos, start=1):
                task = info.task
                description = task.description.strip() or "Без описания"

                text_lines.extend(
                    [
                        "",
                        f"{index}. {description}",
                        f"Статус: {info.status_label}",
                        f"Срок: {info.deadline_label}",
                    ]
                )

                if role == ROLE_MANAGER:
                    text_lines.append(
                        f"Исполнитель: {task.assignee_name or 'Не назначен'}"
                    )

                if info.is_overdue:
                    text_lines.append(f"ПРОСРОЧЕНО на {info.days_overdue} кал. дн.")
                elif info.days_until_deadline is not None:
                    text_lines.append(f"До срока: {info.days_until_deadline} кал. дн.")

        text_body = "\n".join(text_lines)
        html_body = self._render_html(
            title=title,
            recipient_name=recipient_name,
            task_infos=task_infos,
            counters=counters,
            local_now=local_now,
            role=role,
        )

        return EmailDigestMessage(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

    @staticmethod
    def _render_html(
        *,
        title: str,
        recipient_name: str,
        task_infos: list[TaskDigestInfo],
        counters: DigestCounters,
        local_now: datetime,
        role: str,
    ) -> str:
        """Формирует HTML-письмо с экранированием пользовательских данных."""
        rows: list[str] = []

        for info in task_infos:
            task = info.task
            description = escape(task.description.strip() or "Без описания")
            status = escape(info.status_label)
            deadline = escape(info.deadline_label)

            row_class = ' class="overdue"' if info.is_overdue else ""

            details = f"<p>Статус: {status}</p><p>Срок: {deadline}</p>"

            if role == ROLE_MANAGER:
                details += (
                    f"<p>Исполнитель: {escape(task.assignee_name or 'Не назначен')}</p>"
                )

            if info.is_overdue:
                details += (
                    "<p><strong>ПРОСРОЧЕНО на "
                    f"{info.days_overdue} кал. дн.</strong></p>"
                )
            elif info.days_until_deadline is not None:
                details += f"<p>До срока: {info.days_until_deadline} кал. дн.</p>"

            rows.append(f"<li{row_class}><strong>{description}</strong>{details}</li>")

        task_list = (
            "<ul>" + "".join(rows) + "</ul>" if rows else "<p>Активных задач нет.</p>"
        )

        manager_counters = ""
        if role == ROLE_MANAGER:
            manager_counters = (
                f"<li>Ваших задач в работе: {counters.own_total}</li>"
                f"<li>Ваших просроченных задач: {counters.own_overdue}</li>"
            )

        return (
            '<!doctype html><html lang="ru"><head>'
            '<meta charset="utf-8"><style>'
            ".overdue{color:#b42318}"
            "</style></head><body>"
            f"<p>Здравствуйте, {escape(recipient_name)}!</p>"
            f"<h2>{escape(title)}</h2>"
            f"<p>Дата формирования: {local_now:%d.%m.%Y %H:%M}</p>"
            "<ul>"
            f"<li>Всего активных задач: {counters.total}</li>"
            f"<li>Просроченных задач: {counters.overdue}</li>"
            f"<li>Задач без срока: {counters.without_deadline}</li>"
            f"{manager_counters}"
            "</ul>"
            f"<h3>Список задач</h3>{task_list}"
            "</body></html>"
        )
