# AGENTS.md — RZAdb / База Данных РЗА

## 1. Назначение

RZAdb — внутреннее веб-приложение для учёта оборудования РЗА, подстанций, присоединений, устройств РЗА, технической документации, формуляров, уставок, схем, ТО, программ, инструкций, осмотров и задач.

Проект некоммерческий.

Этот файл — рабочие инструкции для coding agents. `DATABASE_DESIGN.md` фиксирует согласованные доменные и архитектурные решения.

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
- Alembic
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
- uuid6 для UUID7

`.env` не коммитить.

---

## 3. Архитектура

Основное разделение:

```text
domain → application → infrastructure → presentation
```

### `app/domain/`

Доменные сущности, enum и доменные правила.

Модели находятся здесь.

### `app/application/`

Repositories, services, DTO и use cases.

### `app/infrastructure/`

SQLAlchemy, PostgreSQL, Alembic, object storage и интеграции.

### `app/presentation/`

FastAPI routes/dependencies, Jinja2 и HTMX.

Бизнес-логику не помещать в templates и routes.

Не смешивать authentication, authorization и domain logic.

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

Модели регистрируются в `app/infrastructure/database/models.py`.

Alembic: `migrations/`.

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

---

## 6. Роли и доступ

Роли:

```text
SUPERADMIN
ADMIN
SPECIALIST
MANAGER
ENGINEER
```

`AccessService` централизует проверки:

```text
can_access_enterprise()
can_access_substation()
can_access_connection()
can_access_urza()
get_accessible_enterprise_roots()
```

Не дублировать правила доступа в каждом route/service.

---

## 7. UI

Стек:

- Bootstrap 5
- Material Icons
- Roboto
- HTMX
- Jinja2

### Вкладки URZA

```text
ОТД | Уставки | Схемы | ТО | Программы | Инструкция
```

Все шесть вкладок URZA реализованы на текущем этапе.

### Вкладки Substation

```text
Основные сведения | Присоединения | Осмотры | Инструкции | Схемы селективности
```

`Inspection` не переименовывать в БД только из-за UI. В интерфейсе используется «Осмотры».

PDF viewer не создавать. Для файлов целевой UI:

```text
[Просмотр] [Скачать]
```

---

## 8. Доменные правила

- Напряжения: `500, 220, 110, 35, 10, 6, 0.4`.
- SAP/ASUREO не делать глобально уникальными без отдельного доменного решения.
- Диспетчерские имена уникальны в соответствующих доменных областях.
- Имя УРЗА уникально внутри присоединения.
- УРЗА II обслуживается персоналом категорий II, III, IV.
- ОТД, Уставки, Схемы, ТО и Программы — один логический уровень под URZA.
- Инструкция URZA — отдельная версионируемая сущность под URZA.
- Инструкция РЗА — отдельная сущность уровня Substation.
- Формуляр — логическая группировка.
- Старые версии документов не удаляются.
- Для ТО подписанная форма/скан обязательна.
- Для ОТД подпись не обязательна.
- Плановая дата ТО хранится для последующего микросервиса.
- Inspection/Осмотр ПС — отдельный процесс, не обычная Task.

---

## 9. Versioning

Версионируемые документы не перезаписывать:

```text
current version
      ↓
new version
      ↓
old version remains in history
```

ОТД имеет текущую и исторические версии.

Инструкция URZA также имеет версии.

Переключение исторических версий в UI выполняется через HTMX без полной перезагрузки страницы.

История при первом открытии свернута; после перехода между версиями через историю она остаётся раскрытой.

---

## 10. Files

Бинарные файлы не хранить в PostgreSQL.

Целевой storage: S3-compatible object storage.

Не использовать универсальную полиморфную связь:

```text
File(owner_type, owner_id)
```

Использовать явные FK от доменных сущностей к `files.id`.

Целевой общий механизм:

```text
доменный объект
→ проверка доступа
→ File
→ ObjectStorage
→ Просмотр / Скачать
```

Не реализовывать отдельные одноразовые file routes для каждой сущности, если подходит общий механизм.

---

## 11. Tasks

Типы:

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

Инспекции/осмотры ПС — отдельный процесс.

---

## 12. Audit

Универсальный audit-refactor завершён.

Целевой набор:

```text
created_at
created_by
updated_at
updated_by
deleted_at
deleted_by
```

Смысл:

- `created_by` — пользователь, создавший запись;
- `updated_by` — последний изменивший;
- `deleted_by` — выполнивший архивирование/soft delete.

Audit должен быть частью domain/database contract, а не зависеть от UI.

Текущий Alembic head после audit-refactor: `a74c1d8f2b90`.

---

## 13. Тестирование

После существенных изменений:

```bash
uv run pytest -q
```

Для локального цикла:

```bash
uv run pytest -q tests/application/<area>
```

Ruff запускать по необходимости; полный Ruff сейчас содержит известные pre-existing issues и не должен блокировать логический этап без отдельного решения.

Правила:

- не создавать дублирующие тестовые файлы;
- изменять существующие тесты, если они покрывают изменённое поведение;
- для нового business rule добавлять тест;
- после миграций проверять миграцию отдельно и полный test suite;
- не ломать существующие зелёные тесты без объяснения причины.

---

## 14. Работа coding agent

Перед изменением кода:

1. Прочитать `AGENTS.md`.
2. Прочитать относящиеся разделы `DATABASE_DESIGN.md`.
3. Исследовать фактический существующий код.
4. Не дублировать существующие модели/services/repositories.
5. Определить минимальный набор файлов для изменения.

Для неоднозначной задачи:

```text
inspect
→ plan
→ domain decision
→ implementation
→ migration
→ tests
```

Не создавать migration до согласования схемы изменения.

Не выполнять большие архитектурные изменения только по одной фразе пользователя.

Если для точного аудита нужна полная информация о коде, попросить пользователя использовать coding agent (Codex) для сбора фактического состояния проекта.

---

## 15. Код

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

## 16. Git

Работать небольшими логическими этапами.

После завершённого этапа:

```bash
git add <конкретные-файлы>
git commit -m "<message>"
git push
```

Не выполнять `git reset --hard`, `git checkout -- .` и другие разрушительные команды без явного разрешения пользователя.

Не коммитить `.env`.

---

## 17. Текущий проектный статус

Завершено и проверено:

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
- сохранение состояния раскрытия истории ОТД;
- универсальный audit-refactor;
- вкладка Уставки;
- вкладка Схемы;
- вкладка ТО;
- вкладка Программы;
- вкладка Инструкция URZA;
- история версий Инструкции URZA.

### Следующий этап

Не начинать новый крупный функциональный блок вслепую.

Сначала выполнить контрольный аудит фактического состояния проекта:

```text
current code
→ models
→ repositories
→ services
→ routes / DI
→ templates
→ tests
→ migrations
→ DOMAIN / DATABASE_DESIGN
→ TODO / roadmap
```

Результат классифицировать:

```text
DONE
PARTIAL
TODO
NEEDS DOMAIN DECISION
TECHNICAL DEBT
```

После аудита обновить roadmap.

---

## 18. Предварительный план крупных этапов

Порядок должен быть подтверждён после аудита:

```text
1. Контрольный аудит проекта
2. Обновление roadmap / TODO
3. Общий механизм файлов
4. Подключение файлов ко всем URZA-вкладкам
5. Полноценный CRUD документов URZA
6. Tasks workflow
7. Substation-функциональность
8. Осмотры / Inspection workflow
9. S3 production storage
10. Backup
11. Cold S3 / архивирование
12. Уведомления и автоматизация
```

---

## 19. Особые отложенные вопросы

### Исторические ТО

Текущее поле `historical_data` в модели ТО пока не перерабатывать без отдельного доменного решения.

По исходному workflow исторические ТО должны вводиться отдельным процессом.

### Files

Общий механизм файлов отложен до завершения URZA-вкладок и контрольного аудита.

### Production S3

Сначала определить общий file contract и storage abstraction, затем подключать production S3.

### Backup / cold storage

Проектировать после стабилизации file/storage contract.

---

## 20. Основной принцип

База данных отражает согласованную предметную область.

Не добавлять поля «на всякий случай».

Не менять структуру БД ради косметического UI-изменения.

Не дублировать сущности.

Не удалять исторические версии документов.

Не смешивать инфраструктурные детали с доменными правилами.

При сомнении сначала исследовать существующий код и исходные проектные документы, затем задать пользователю доменный вопрос.
