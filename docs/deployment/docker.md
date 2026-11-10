# Развёртывание RZAdb через Docker Compose

`Dockerfile` собирает production-образ приложения на Python 3.13.7 / Debian
Bookworm. В образ входят PostgreSQL 18 client tools для backup CLI. Файл
`compose.production.yaml` предназначен для VPS: он запускает PostgreSQL 18 и
FastAPI, но не меняет локальный запуск на macOS и локальную PostgreSQL.

На текущем этапе Compose публикует приложение только на `127.0.0.1:8000`.
HTTPS reverse proxy и домен ещё не настроены; не открывайте приложение в
публичный доступ до настройки TLS.

## Подготовка VPS

Из корня проекта создайте env-файл и сгенерируйте независимые секреты:

```bash
cp .env.production.example .env.production
openssl rand -hex 32  # POSTGRES_PASSWORD; hex-строка безопасна для URL
openssl rand -hex 32  # отдельное значение для SESSION_SECRET
chmod 600 .env.production
```

В `.env.production` установите значения обоих секретов. `POSTGRES_DB`,
`POSTGRES_USER` и `POSTGRES_PASSWORD` должны совпадать с соответствующими
частями `DATABASE_URL`; hex-пароль не требует URL-кодирования. Оставьте
`SESSION_COOKIE_SECURE=true` для HTTPS production. Для почты заполните SMTP
настройки; не включайте backup email, пока не проверен лимит размера вложений.
Файл `.env.production` исключён из Git.

Compose использует `--env-file` для интерполяции `${...}` в YAML, а `env_file`
в сервисе `web` передаёт настройки внутрь приложения. Поэтому команды ниже
указывают `--env-file .env.production`; сервис `db` получает только явно
указанные `POSTGRES_*` переменные.

Каталоги пользовательских файлов и дампов — bind mounts на хосте:

```bash
sudo install -d -o 10001 -g 10001 -m 0750 \
  /srv/rzadb/uploads /srv/rzadb/backups
```

UID/GID приложения по умолчанию `10001`; при их изменении обновите
`RZADB_UID`/`RZADB_GID` и пересоберите образ. Backup CLI устанавливает для
каталога backup права `0700`, для lock/manifest временных файлов — ограниченные
права. PostgreSQL data хранится в отдельном Docker named volume
`rzadb_postgres_data`, смонтированном в `/var/lib/postgresql` согласно layout
официального образа PostgreSQL 18.

## Сборка и запуск

Все команды выполнять из корня checkout проекта:

```bash
docker compose --env-file .env.production -f compose.production.yaml config
docker compose --env-file .env.production -f compose.production.yaml build
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps
docker compose --env-file .env.production -f compose.production.yaml logs -f web db
```

`db` должен стать healthy по `pg_isready`; `web` проходит healthcheck через
`/health/ready`. Endpoint `/health` остаётся liveness-проверкой. Readiness
выполняет только `SELECT 1` и возвращает HTTP 503, если PostgreSQL недоступна.
Cookie сессии в production получает `Secure`; локальное значение по умолчанию
`SESSION_COOKIE_SECURE=false` сохраняет работу по HTTP.

Миграции выполняются отдельно и только после проверки резервной копии и
конфигурации целевого окружения:

```bash
docker compose --env-file .env.production -f compose.production.yaml run --rm web alembic upgrade head
```

Миграции не запускаются при старте Uvicorn.

Ручной запуск CLI:

```bash
docker compose --env-file .env.production -f compose.production.yaml run --rm web python -m app.infrastructure.backup
docker compose --env-file .env.production -f compose.production.yaml run --rm web python -m app.infrastructure.emailing.send_email_digest
```

Одноразовые контейнеры используют env, Compose network и bind mounts сервиса
`web`. Backup каталог доступен по `/app/data/backups`; CLI подключается к `db`
через `DATABASE_URL`. Не запускайте Email Digest для пользователей, пока не
проверены адресаты и SMTP-конфигурация.

На VPS последующее расписание systemd должно использовать timezone
`Asia/Yekaterinburg`: backup ежедневно в 03:00, Email Digest с понедельника по
пятницу в 07:30. Systemd units/timers этим изменением не создаются.

## Остановка и обновление

```bash
docker compose --env-file .env.production -f compose.production.yaml down
docker compose --env-file .env.production -f compose.production.yaml build web
docker compose --env-file .env.production -f compose.production.yaml up -d
```

`down` сохраняет PostgreSQL named volume и bind-mounted каталоги приложения.
Не используйте `docker compose down -v` при обычной остановке или обновлении:
опция удаляет PostgreSQL volume вместе с базой. Не удаляйте и не очищайте
`/srv/rzadb/uploads` или `/srv/rzadb/backups` без отдельной проверки копий.

## Проверки

Без запуска контейнеров можно проверить синтаксис и раскрытие конфигурации:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
docker compose --env-file .env.production -f compose.production.yaml ps
docker compose --env-file .env.production -f compose.production.yaml exec web python --version
docker compose --env-file .env.production -f compose.production.yaml exec web pg_dump --version
docker compose --env-file .env.production -f compose.production.yaml exec web pg_restore --version
```

Не публикуйте вывод полной `docker compose config` в тикетах или логах: он
может содержать значения environment variables.
