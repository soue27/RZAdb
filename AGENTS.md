# AGENTS.md — RZAdb / База Данных РЗА

## 1. Назначение

RZAdb — внутреннее веб-приложение для учёта оборудования РЗА, подстанций, присоединений, устройств РЗА, технической документации, формуляров, уставок, схем, ТО, программ, инструкций, осмотров и задач.

Проект некоммерческий.

Этот файл — рабочие инструкции для coding agents. `DATABASE_DESIGN.md` фиксирует доменные и архитектурные решения по базе данных.

Главное правило: **не добавлять новые сущности, поля, связи или бизнес-правила без отдельного доменного решения пользователя.**

---

## 2. Стек

- Python 3.13.7
- uv
- FastAPI
- Jinja2
- HTMX
- PostgreSQL
- SQLAlchemy 2.x asyncio
- asyncpg
- Alembic (`migrations/`)
- Pydantic / pydantic-settings
- pytest / pytest-asyncio
- httpx
- Ruff
- S3-compatible object storage
- aioboto3
- Docker
- GitHub Actions
- structlog
- pwdlib[argon2]

`.env` не коммитить.

---

## 3. Архитектура

Основное разделение:

```text
domain → application → infrastructure → presentation
```

### `app/domain/`

Доменные сущности, enum и доменные правила.

**Модели находятся здесь.**

### `app/application/`

Repositories, services, DTO и use cases.

### `app/infrastructure/`

SQLAlchemy, PostgreSQL, Alembic, object storage и интеграции.

### `app/presentation/`

FastAPI routes/dependencies, Jinja2 и HTMX.

Бизнес-логику не помещать в templates и routes.

Не смешивать:
- authentication;
- authorization;
- domain logic.

`AccessService` является централизованной точкой проверки авторизации.

---

## 4. База данных

SQLAlchemy 2.x asyncio.

Session lifecycle централизован. Repository не должен делать `commit()` без явной архитектурной причины.

UUID — UUID7 через `uuid6.uuid7`.

Базовые mixins:

```text
UUIDMixin
TimestampMixin
SoftDeleteMixin
```

Модели регистрируются в:

```text
app/infrastructure/database/models.py
```

Alembic:

```text
migrations/
```

После изменения моделей:

```text
изменение модели
→ Alembic migration
→ проверка migration
→ применение
→ тесты
```

---

## 5. Иерархия

```text
Holding
└── Branch
    └── Production Department
        └── Substation
            └── Connection
                └── URZA
```

`Enterprise` представляет Holding, Branch или Production Department и использует `parent_id`.

---

## 6. Роли и границы доступа

Роли:

```text
SUPERADMIN
ADMIN
SPECIALIST
MANAGER
ENGINEER
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

Границы:

```text
SUPERADMIN → корневые Holding
SPECIALIST → свой Holding/Branch
ADMIN/MANAGER/ENGINEER → своё Production Department
```

Пользователь не должен видеть объекты выше своей границы доступа.

---

## 7. TreeService

DTO:

```text
EnterpriseTreeNode
├── children[]
└── substations[]

SubstationTreeNode
└── connections[]

ConnectionTreeNode
└── urzas[]

URZATreeNode
```

Repositories:

```text
EnterpriseRepository:
  get_by_id()
  get_all_active()
  is_ancestor_or_same()

SubstationRepository:
  get_by_id()
  get_all_active()
  get_by_enterprise_ids()

ConnectionRepository:
  get_by_id()
  get_all_active()
  get_by_substation_ids()

URZARepository:
  get_by_id()
  get_all_active()
  get_by_connection_ids()
```

TreeService получает корни через AccessService, загружает активную иерархию и строит DTO.

Сортировка:

- Enterprise → `full_name`;
- Substation/Connection/URZA → `dispatch_name`.

Архивные объекты не попадают в sidebar.

Для MVP допустима фильтрация потомков в памяти; при росте данных оптимизировать.

---

## 8. Authentication

MVP использует signed cookie session с минимальным `user_id`.

`AuthService` отвечает за authentication.

`AccessService` отвечает за authorization.

Пароли — Argon2 через `pwdlib[argon2]`.

Не смешивать authentication и authorization.

---

## 9. UI

Основной sidebar:

```text
Holding
└── Branch
    └── Production Department
        └── Substation
            └── Connection
                └── URZA
```

Требования:

- начально свернут;
- поиск над деревом;
- найденный путь раскрывается;
- resizable 280–520 px;
- базовая ширина около 340 px;
- полностью свернут около 56 px;
- collapse button на правой границе.

Стек UI:

- Bootstrap 5;
- Material Icons;
- Roboto;
- HTMX.

Палитра:

```text
Primary    #0068B3
Hover      #005A9C
Soft       #EEF6FC
Background #F5F7F9
Surface    #FFFFFF
Text       #263238
Secondary  #687782
Border     #E1E7EC
Success    #198754
Warning    #F0A500
Danger     #D9363E
```

Темы:

```text
light / dark / system
```

с сохранением ручного выбора.

### Вкладки URZA

```text
ОТД | Уставки | Схемы | ТО | Программы | Инструкция
```

### Вкладки Substation

```text
Основные сведения | Присоединения | Осмотры | Инструкции | Схемы селективности
```

Важно: в базе данных существующая сущность/процесс `Inspection` не переименовывается и структура БД не меняется.

Слово **«Осмотры»** используется только как UI-отображение для inspection-раздела.

PDF viewer не создавать. Для файлов использовать:

```text
[Просмотр] [Скачать]
```

---

## 10. Доменные правила

- Высшие напряжения: `500, 220, 110, 35, 10, 6, 0.4`.
- SAP/ASUREO не делать глобально уникальными без отдельного доменного решения.
- Диспетчерские имена уникальны в соответствующих доменных областях.
- Имя УРЗА уникально внутри присоединения.
- УРЗА II обслуживается персоналом категорий II, III, IV.
- ОТД, Уставки, Схемы, ТО и Программы — один логический уровень под URZA.
- Формуляр — логическая группировка.
- ОТД имеет текущую версию и историю.
- Старые версии документов не удаляются.
- Для ТО подписанная форма/скан обязательна.
- Для ОТД подпись не обязательна.
- Плановая дата ТО хранится для последующего микросервиса.
- Inspection/Осмотр ПС — отдельный процесс, не обычная Task.

---

## 11. Versioning

Версионируемые документы не перезаписывать.

```text
current version
      ↓
new version
      ↓
old version remains in history
```

Для ОТД:

```text
current version
historical versions
```

Переключение версии ОТД в текущем UI выполняется через HTMX без полной перезагрузки страницы.

История версии должна сохранять возможность просмотра старых данных.

---

## 12. Files

Бинарные файлы хранить в S3-compatible object storage, не в PostgreSQL.

Не использовать:

```text
File(owner_type, owner_id)
```

как универсальную полиморфную связь.

Связи файлов с доменными сущностями должны быть явными.

Архивирование — soft delete/архивное состояние, не физическое удаление.

---

## 13. Tasks

Типы работ:

```text
OTD
SETTINGS
SCHEMES
MAINTENANCE
PROGRAM
```

Статусы:

```text
CREATED
ASSIGNED
IN_PROGRESS
COMPLETED
UNDER_REVIEW
CLOSED
REJECTED
```

Активные в UI:

```text
ASSIGNED
IN_PROGRESS
UNDER_REVIEW
```

---

## 14. Универсальный аудит — согласованное направление

Принято архитектурное решение постепенно привести модели к единому набору audit-полей:

```text
created_at
created_by
updated_at
updated_by
deleted_at
deleted_by
```

Целевой принцип:

- `created_by` — пользователь, создавший запись;
- `updated_by` — пользователь, последний изменивший запись;
- `deleted_by` — пользователь, выполнивший архивирование/soft delete;
- `created_at` / `updated_at` / `deleted_at` — соответствующие timestamps.

Audit-поля должны быть реализованы централизованно через базовые mixins, а не дублироваться вручную в каждой модели.

### ВАЖНО

Универсальный аудит **ещё не реализован полностью**.

Перед изменением моделей необходимо:

1. исследовать фактическое состояние всех моделей;
2. исследовать модель `User`;
3. определить FK на `users.id`;
4. решить вопрос старых записей, для которых исторический автор неизвестен;
5. определить nullable/NOT NULL;
6. определить централизованный способ заполнения `created_by` / `updated_by`;
7. только после этого создавать Alembic migration.

Не делать эти решения самостоятельно.

Особенно не подставлять фиктивного пользователя в исторические данные без явного решения пользователя.

---

## 15. Audit и критические операции

Аудит обязателен для:

- изменения прав;
- критических данных РЗА;
- версий документов;
- архивирования/восстановления;
- загрузки/замены документов;
- изменения статусов задач.

Аудит не должен зависеть от UI.

---

## 16. Инспекции / Осмотры

Структура БД не изменяется только ради переименования отображения.

В domain/application/database используются существующие `Inspection` / inspection-сущности.

В пользовательском интерфейсе отображаем:

```text
Осмотры
```

Не создавать новую сущность только потому, что в UI используется другое русское название.

---

## 17. Тестирование

После существенных изменений:

```bash
uv run ruff check app tests
uv run pytest -q
```

Для локального цикла можно запускать затронутую область:

```bash
uv run pytest -q tests/application/<area>
```

Правила:

- не создавать дублирующие тестовые файлы;
- изменять существующие тесты, если они покрывают изменённое поведение;
- для нового business rule добавлять тест;
- после миграций проверять миграцию отдельно и полный test suite.

Целевой принцип: существующие зелёные тесты нельзя ломать без объяснения причины.

---

## 18. Работа coding agent

Перед изменением кода:

1. прочитать `AGENTS.md`;
2. прочитать относящиеся разделы `DATABASE_DESIGN.md`;
3. исследовать существующий код;
4. не дублировать уже существующие модели/services/repositories;
5. определить минимальный набор файлов для изменения.

Для неоднозначной задачи сначала сделать исследование и план.

Не выполнять большие архитектурные изменения только по одной фразе пользователя, если отсутствует доменное решение.

Для database refactoring:

```text
inspect
→ plan
→ domain decision
→ implementation
→ migration
→ tests
```

Не создавать migration до согласования схемы изменения.

---

## 19. Код

Предпочитать:

- простые функции;
- маленькие services;
- явные зависимости;
- типизацию;
- SQLAlchemy 2.x style;
- async API;
- Pydantic DTO;
- понятные имена.

Не помещать бизнес-правила в Jinja.

Не делать лишние абстракции «на будущее».

Комментарии писать только для нетривиального `why`.

Не переписывать рабочий код без причины.

---

## 20. Git

Работать небольшими логическими этапами.

После завершённого этапа:

```bash
git add <конкретные-файлы>
git commit -m "..."
git push
```

Перед commit:

```bash
uv run ruff check app tests
uv run pytest -q
```

Не выполнять `git reset --hard`, `git checkout -- .` или другие разрушительные команды без явного разрешения пользователя.

Не коммитить `.env`.

---

## 21. Текущий проектный статус

Уже реализованы и проверены:

- authentication;
- signed cookie session;
- AccessService;
- EnterpriseRepository;
- SubstationRepository;
- ConnectionRepository;
- URZARepository;
- TreeService;
- Tree DTO;
- границы SUPERADMIN/SPECIALIST/ENGINEER;
- soft-delete filtering;
- sidebar UI;
- карточка URZA;
- карточка ОТД;
- версии ОТД;
- история версий ОТД;
- переключение версии ОТД через HTMX;
- сохранение состояния раскрытия истории при HTMX-переключении.

Текущая рабочая ветка для следующего этапа:

```text
refactor/universal-audit
```

Следующий этап — исследование и проектирование универсального audit-подхода.

---

## 22. Рабочий стиль

Пользователь предпочитает:

- русский язык;
- небольшие последовательные шаги;
- точные команды;
- сначала понять архитектуру, затем писать код;
- после каждого существенного этапа запускать тесты;
- получать конкретные команды для commit/push.

Не просить пользователя показывать `git status`, если для задачи это не требуется.
