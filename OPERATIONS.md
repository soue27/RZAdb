# RZAdb production operations

Все расписания используют `Asia/Yekaterinburg`. systemd units подготовлены в
`deploy/systemd/`; production SMTP настроен на VPS. На 15.11.2026
`rzadb-email-digest.timer` включён. Digest использует тестовые учётные записи;
доставка на их адреса намеренно не проверялась.

| Job | Time | Unit |
|---|---:|---|
| PostgreSQL backup | ежедневно 03:00 | `rzadb-backup.timer` |
| Email Digest | ПН–ПТ 07:30 | `rzadb-email-digest.timer` |
| Health monitor | ежедневно 08:30 | `rzadb-monitor.timer` |

Email Digest timer использует `Persistent=false`: пропущенный пятничный запуск
не должен отправляться в выходные. Монитор запускается в 08:30, через час
после Digest, и не считает запуск пропущенным, пока service находится в
`active`/`activating`. Для backup и monitor включён `Persistent=true`.

Пока `rzadb-email-digest.timer` disabled, монитор пишет статус
`Email Digest monitoring status: DEFERRED`. Это ожидаемое состояние при
намеренно отложенном Digest и не считается отказом; проверки backup,
свободного места, Docker и backup timer продолжаются. Production SMTP настроен.
При включённом timer отсутствие ожидаемого запуска в рабочий день считается
ошибкой. Текущий статус timer — enabled/active:

```sh
sudo systemctl enable --now rzadb-email-digest.timer
sudo systemctl is-enabled rzadb-email-digest.timer
sudo systemctl is-active rzadb-email-digest.timer
```

В рабочий день до 07:30 состояние Digest — `NOT_DUE`; во время выполняющегося
service — `RUNNING`; успешный завершённый запуск — `OK`. После 07:30 отсутствие
успешного marker или неуспешный service дают `ERROR` и ненулевой код Monitor.

## Подключение к VPS

```sh
ssh srv1016@213.109.106.28
cd /opt/rzadb
```

Не выводите `.env.production`, параметры подключения, SMTP credentials или
содержимое dump-файлов.

## Production SMTP

15.11.2026 production settings были заполнены только необходимыми SMTP
параметрами из локального `.env`; остальные параметры окружения не менялись.
Перед изменением создана резервная копия вне проекта с правами `600`; каталог
резервной копии имеет права `700`. `.env.production` имеет права `600`.
SMTP hostname разрешается с VPS, TCP/TLS и сертификат проверены, SMTP-
аутентификация успешна. Штатный sender отправил одно тестовое сообщение
единственному активному SUPERADMIN; сервер SMTP принял сообщение. Доставка в
почтовый ящик не подтверждена.

Settings использует эти переменные:

| Переменная | Назначение |
|---|---|
| `SMTP_HOST` | SMTP host |
| `SMTP_PORT` | SMTP port |
| `SMTP_USERNAME` | Учётная запись SMTP |
| `SMTP_PASSWORD` | Пароль SMTP |
| `SMTP_FROM_EMAIL` | Адрес отправителя |
| `SMTP_STARTTLS` | STARTTLS для обычного SMTP-соединения |
| `SMTP_USE_SSL` | TLS с момента подключения, например порт 465 |

`SMTP_STARTTLS` и `SMTP_USE_SSL` нельзя включать одновременно. Для смены
параметров создайте резервную копию `.env.production` вне Git с mode `600`,
отредактируйте только эти ключи через `sudoedit`, сохраните mode `600` и
проверьте отсутствие дубликатов. Не передавайте значения через командную
строку и не печатайте файл.

Настройки читаются при старте `web`. Применить их без сборки образа и без
перезапуска БД:

```sh
sudo docker compose --env-file .env.production \
  -f compose.production.yaml up -d --no-deps web
```

Одна тестовая отправка штатным sender только на единственную активную,
неархивированную запись `SUPERADMIN`:

```sh
sudo docker compose --env-file .env.production \
  -f compose.production.yaml exec -T web python - <<'PY'
import asyncio
from sqlalchemy import select
from app.core.config import get_settings
from app.domain.enums import UserRole
from app.domain.user import User
from app.infrastructure.database import models
from app.infrastructure.database.engine import async_session_factory
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender

async def main():
    async with async_session_factory() as session:
        recipients = list((await session.scalars(select(User.email).where(
            User.role == UserRole.SUPERADMIN,
            User.active.is_(True),
            User.deleted_at.is_(None),
        ))).all())
    if len(recipients) != 1 or not recipients[0].strip():
        raise SystemExit("Expected one active SUPERADMIN; message not sent")
    settings = get_settings()
    try:
        await SMTPEmailSender(settings).send(
            to=recipients[0],
            subject="RZAdb SMTP configuration test",
            body="Production SMTP test. SMTP acceptance does not confirm mailbox delivery.",
        )
    except Exception as exc:
        print("SMTP test failed: " + type(exc).__name__)
        raise SystemExit(1) from None
    print("SMTP accepted one test message for the active SUPERADMIN")

asyncio.run(main())
PY
```

Acceptance by the SMTP server does not prove mailbox delivery. Check routing
records separately (`dig MX <domain>`) and confirm delivery with the recipient.
For diagnosis, use the service journals below; never print credentials.

## Timers и services

Показать все RZAdb timers:

```sh
sudo systemctl list-timers --all 'rzadb-*'
```

Проверить конкретный timer и его следующее срабатывание:

```sh
sudo systemctl status rzadb-backup.timer
sudo systemctl list-timers rzadb-backup.timer
```

Проверить результат последнего запуска service:

```sh
sudo systemctl show rzadb-backup.service \
  -p ActiveState -p Result -p ExecMainStatus -p ExecMainStartTimestamp
```

Посмотреть журнал одного или всех заданий:

```sh
sudo journalctl -u rzadb-backup.service --since today --no-pager
sudo journalctl -u rzadb-email-digest.service --since today --no-pager
sudo journalctl -u rzadb-monitor.service --since today --no-pager
```

Узнать состояние Docker Compose без просмотра env:

```sh
sudo docker compose --env-file .env.production \
  -f compose.production.yaml ps
```

## Резервные копии

Запустить backup вручную и проверить результат:

```sh
sudo systemctl start rzadb-backup.service
sudo systemctl show rzadb-backup.service \
  -p Result -p ExecMainStatus -p ExecMainStartTimestamp
sudo find /srv/rzadb/backups -maxdepth 1 -type f \
  \( -name 'rzadb_*.json' -o -name 'rzadb_*.dump' \) -printf '%TY-%Tm-%Td %TH:%TM %f %s bytes\n' \
  | sort | tail -10
```

Manifest хранит SHA-256 и результат первоначальной проверки `pg_restore --list`.
Для отдельной проверки конкретного dump укажите его basename:

```sh
sudo docker compose --env-file .env.production \
  -f compose.production.yaml exec -T web \
  pg_restore --list /app/data/backups/<dump-basename>
```

Ротация остаётся частью существующего BackupCoordinator. Новый dump и его
проверка завершаются до удаления старых копий. PostgreSQL dump **не включает**
`/srv/rzadb/uploads`; резервирование uploads в текущем наборе units не
настроено.

## Email Digest

На 15.11.2026 timer включён и активен. Systemd расписание:
`Mon..Fri *-*-* 07:30:00 Asia/Yekaterinburg`; следующий запуск назначен на
16.11.2026 в 07:30 `Asia/Yekaterinburg`. Учётные записи получателей пока
тестовые; фактическая доставка на их адреса не проверялась и будет проверяться
после согласования реальных пользователей. Для включённого timer Monitor
контролирует ожидаемый запуск.

Обычный ручной запуск рассылает сводки фактическим активным ENGINEER и MANAGER,
которых выберет штатный сервис. До ручного запуска подтвердите получателей и
маршрутизацию почты. Изолированная проверка бизнес-логики без отправки писем:

```sh
cd /opt/rzadb
uv run pytest -q tests/application/email_digest \
  tests/infrastructure/emailing/test_send_email_digest.py
```

Production SMTP задаётся переменными из раздела выше. Для диагностики
сверяйте только наличие настроек, не печатая их значения, затем смотрите журнал:

```sh
sudo journalctl -u rzadb-email-digest.service --since today --no-pager
sudo journalctl -u rzadb-monitor.service --since today --no-pager
```

Контрольные письма состояния отправляются только единственной активной и не
архивированной записи `SUPERADMIN`. При отсутствии или неоднозначности адреса
уведомление пропускается и причина остаётся в journald.

Для управления timer используйте `systemctl enable --now` или
`systemctl disable --now rzadb-email-digest.timer`. При отключённом timer
Monitor показывает `DEFERRED` и продолжает контролировать Backup; при включённом
timer контролирует своевременный запуск Digest.

## Изменение времени расписания

Измените соответствующий `OnCalendar` в `deploy/systemd/rzadb-*.timer`, затем
скопируйте только эти units на VPS и проверьте выражение:

```sh
sudo cp deploy/systemd/rzadb-*.service deploy/systemd/rzadb-*.timer \
  /etc/systemd/system/
sudo systemd-analyze calendar 'Mon..Fri *-*-* 07:30:00 Asia/Yekaterinburg'
sudo systemctl daemon-reload
sudo systemctl restart rzadb-email-digest.timer
sudo systemctl list-timers rzadb-email-digest.timer
```

Для backup и monitor используйте соответственно `*-*-* 03:00:00` и
`*-*-* 08:30:00`, также с явным `Asia/Yekaterinburg`.

## Восстановление timer и проверка после reboot

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now rzadb-backup.timer rzadb-monitor.timer
sudo systemctl is-enabled rzadb-backup.timer rzadb-monitor.timer
sudo systemctl is-active rzadb-backup.timer rzadb-monitor.timer
sudo systemctl list-timers --all 'rzadb-*'
```

В production на 15.11.2026 `rzadb-email-digest.timer` включён. Если его
останавливали для обслуживания, после согласования возобновления расписания
включите timer отдельно; не запускайте service вручную для проверки timer:

```sh
sudo systemctl enable --now rzadb-email-digest.timer
```

После согласованной перезагрузки VPS повторите команды `is-enabled`, `is-active`
и `list-timers`, а затем проверьте сервисы и журналы. Если timer был остановлен,
восстановите только его:

```sh
sudo systemctl enable --now rzadb-backup.timer
```

## Диагностика уведомлений

```sh
sudo journalctl -u rzadb-monitor.service --since today --no-pager
sudo journalctl -u rzadb-backup.service --since today --no-pager
sudo journalctl -u rzadb-email-digest.service --since today --no-pager
```

Монитор подавляет повторные письма при неизменном наборе неисправностей и
отправляет одно уведомление при изменении состояния, включая восстановление.
Если SMTP недоступен, в journald записывается тип ошибки без ответа SMTP и
секретов. Проверяйте SMTP и маршрутизацию через защищённую панель почтового
провайдера; принятие письма SMTP-сервером само по себе не доказывает
catch-all или пересылки.
