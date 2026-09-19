# AGENTS.md — RZAdb / База Данных РЗА

## Назначение
RZAdb — внутреннее веб-приложение для учёта оборудования РЗА, подстанций, присоединений, устройств РЗА, документов, формуляров, уставок, схем, ТО, программ, инструкций, инспекций и задач.

## Стек
- Python 3.13.7, uv
- FastAPI, Jinja2, HTMX
- PostgreSQL, SQLAlchemy 2.x asyncio, asyncpg
- Alembic (`migrations/`)
- Pydantic / pydantic-settings
- pytest / pytest-asyncio, httpx
- Ruff
- S3-compatible storage, aioboto3
- Docker, GitHub Actions
- structlog
- pwdlib[argon2]

`.env` не коммитить.

## Архитектура
Разделение:
```text
domain → application → infrastructure → presentation
```
- `app/domain/`: доменные сущности, enum, правила.
- `app/application/`: repositories, services, DTO/use cases.
- `app/infrastructure/`: SQLAlchemy, PostgreSQL, Alembic, storage, integrations.
- `app/presentation/`: FastAPI routes/dependencies, Jinja, HTMX.

Бизнес-логику не помещать в templates/routes. Authentication, authorization и domain logic не смешивать.

## Структура
```text
app/
├── application/
│   ├── access/
│   ├── connections/
│   ├── enterprises/
│   ├── substations/
│   ├── tree/
│   ├── urzas/
│   └── users/
├── core/
├── domain/
├── infrastructure/
└── presentation/
```
Модели находятся в `app/domain/`. Регистрация моделей — `app/infrastructure/database/models.py`. Миграции — `migrations/`.

## БД
Async SQLAlchemy 2.x. Session lifecycle централизован. Не делать commit в repository без явной причины.

UUID — UUID7 (`uuid6.uuid7`). Базовые mixins: `UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`.

## Иерархия
```text
Holding
└── Branch
    └── Production Department
        └── Substation
            └── Connection
                └── URZA
```
`Enterprise` представляет Holding, Branch или Production Department и использует `parent_id`.

## Роли и границы
Роли:
```text
SUPERADMIN ADMIN SPECIALIST MANAGER ENGINEER
```
Привязка:
- SUPERADMIN — без enterprise binding;
- SPECIALIST — Holding/Branch;
- ADMIN/MANAGER/ENGINEER — Production Department.

Централизованный `AccessService`:
```text
can_access_enterprise()
can_access_substation()
can_access_connection()
can_access_urza()
get_accessible_enterprise_roots()
```

Граница дерева:
- SUPERADMIN → корневые Holding;
- SPECIALIST → своё Holding/Branch;
- ADMIN/MANAGER/ENGINEER → своё Production Department.

## TreeService
`TreeService` формирует DTO дерева для sidebar.

```text
EnterpriseTreeNode
├── children: EnterpriseTreeNode[]
└── substations: SubstationTreeNode[]
SubstationTreeNode
└── connections: ConnectionTreeNode[]
ConnectionTreeNode
└── urzas: URZATreeNode[]
URZATreeNode
```

Используемые repositories:
```text
EnterpriseRepository:
  get_by_id(), get_all_active(), is_ancestor_or_same()
SubstationRepository:
  get_by_id(), get_all_active(), get_by_enterprise_ids()
ConnectionRepository:
  get_by_id(), get_all_active(), get_by_substation_ids()
URZARepository:
  get_by_id(), get_all_active(), get_by_connection_ids()
```

TreeService получает корни через AccessService, активную иерархию и дочерние объекты, затем строит DTO. Enterprise сортируются по `full_name`, остальные уровни по `dispatch_name`. Архивные объекты не попадают в sidebar.

Текущая выборка Enterprise загружает active Enterprise и фильтрует потомков в памяти. Для MVP допустимо; при росте данных оптимизировать.

## Authentication
MVP использует signed cookie session с минимальным `user_id`. AuthService отвечает за аутентификацию, AccessService — за авторизацию. Пароли — Argon2 через `pwdlib[argon2]`.

## UI
Sidebar:
- дерево Holding → Branch → Department → Substation → Connection → URZA;
- начально свернуто;
- поиск над деревом;
- путь к найденному объекту раскрывается;
- resizable: 280–520 px, базово около 340 px;
- полностью свернуто около 56 px;
- collapse button на правой границе.

Bootstrap 5, Material Icons, Roboto.
Палитра:
```text
Primary #0068B3
Hover #005A9C
Soft #EEF6FC
Background #F5F7F9
Surface #FFFFFF
Text #263238
Secondary #687782
Border #E1E7EC
Success #198754
Warning #F0A500
Danger #D9363E
```
Темы: light/dark/system + сохранение ручного выбора.

URZA tabs:
```text
ОТД | Уставки | Схемы | ТО | Программы | Инструкция
```
Substation tabs:
```text
Основные сведения | Присоединения | Инспекции | Инструкции | Схемы селективности
```
PDF viewer не создавать; использовать `[Просмотр] [Скачать]`.

## Доменные правила
- Уровни напряжения: 500, 220, 110, 35, 10, 6, 0.4.
- SAP/ASUREO не делать глобально уникальными без доменного решения.
- Диспетчерские имена и имена УРЗА уникальны в соответствующих доменных областях.
- УРЗА II обслуживается персоналом категорий II, III, IV.
- ОТД, Уставки, Схемы, ТО, Программы — один логический уровень под URZA.
- Формуляр — логическая группировка.
- ОТД: текущая версия + история; старая версия не исчезает.
- Для ТО подписанная форма/скан обязательна.
- Для ОТД подпись не обязательна.
- Плановая дата ТО хранится для последующего микросервиса.
- Инспекция ПС — отдельный процесс, не обычная Task.

## Versioning / files / archive
Версионируемые документы не перезаписывать. Старая версия становится исторической, новая — текущей.

Бинарные файлы хранить в S3-compatible object storage, не в PostgreSQL. Не использовать полиморфный `File(owner_type, owner_id)`. Связи файлов с доменом должны быть явными.

Архивирование — soft delete/архивное состояние, не физическое удаление.

## Tasks
Типы:
```text
OTD SETTINGS SCHEMES MAINTENANCE PROGRAM
```
Статусы:
```text
CREATED ASSIGNED IN_PROGRESS COMPLETED UNDER_REVIEW CLOSED REJECTED
```
Активные в UI:
```text
ASSIGNED IN_PROGRESS UNDER_REVIEW
```

## Testing
После существенных изменений:
```bash
uv run ruff check app tests
uv run pytest -q
```
Для локального цикла можно запускать затронутую область:
```bash
uv run pytest -q tests/application/tree
```

Текущий `tests/application/tree/test_service.py` проверяет:
1. полное дерево SUPERADMIN;
2. границу ENGINEER;
3. границу SPECIALIST;
4. исключение архивных объектов.

Не создавать дублирующие тестовые файлы.

## Git
После логического этапа:
```bash
git add ...
git commit -m "..."
git push
```
Перед commit:
```bash
uv run ruff check app tests
uv run pytest -q
```
`.env` не коммитить.

## Текущий статус и следующий шаг
Уже реализованы и проверены: authentication, signed cookie session, AccessService, repositories Enterprise/Substation/Connection/URZA, TreeService, Tree DTO, границы SUPERADMIN/SPECIALIST/ENGINEER, soft-delete filtering, базовый sidebar UI.

Следующий этап:
```text
TreeService
→ FastAPI dependency/route
→ Jinja/HTMX
→ реальный sidebar
```
Затем: поиск по дереву, раскрытие пути, выбор объекта и карточка объекта.
