## 1. Назначение проекта

RZAdb --- внутреннее веб-приложение для учёта оборудования РЗА,
формуляров, документов, заданий и фактически выполненных работ.

Основная иерархия:

``` text
Холдинг
└── Филиал
    └── Производственное отделение (ПО)
        └── Подстанция
            └── Присоединение
                └── УРЗА
```

Отдельные домены уровня ПС: - схемы селективности; - инструкции по
РЗА; - инспекции ПС.

Инспекция ПС --- отдельный домен и не является обычным Task.

## 2. Технологический стек

-   Python 3.13.7
-   uv
-   FastAPI
-   Jinja2
-   HTMX
-   PostgreSQL
-   SQLAlchemy 2.x async
-   asyncpg
-   Alembic
-   Pydantic / pydantic-settings
-   pytest / pytest-asyncio
-   httpx
-   Ruff
-   S3-compatible object storage
-   aioboto3
-   Docker
-   GitHub Actions
-   structlog
-   `pwdlib[argon2]` для хеширования паролей

Локальная разработка использует PostgreSQL Homebrew.

Рабочая локальная БД: `rzadb`.

## 3. Архитектурные принципы

-   Разделять `domain/model`, `repositories`, `services`, API и UI.
-   Бизнес-правила не размещать в Jinja-шаблонах или роутерах.
-   Доступ централизовать через `AccessService`.
-   Для критичных операций сохранять аудит.
-   Использовать soft delete там, где это предусмотрено.
-   Файлы не хранить в PostgreSQL: БД хранит метаданные, содержимое ---
    object storage.
-   Не использовать полиморфный `File(owner_type, owner_id)`, если
    возможны обычные FK.
-   Использовать UUID7 через `uuid6`.
-   Workflow-статусы --- Python `StrEnum`.
-   Не добавлять сущности и поля без доменного решения.
-   Версионируемые документы не перезаписывают старые версии.
-   `hot/cold` storage не меняет доменную сущность и историю файла.
-   Нетипичную бизнес-логику выносить в services.
-   В нетривиальных функциях оставлять короткие комментарии «что и
    зачем».
-   Не комментировать очевидный код и простые модели без необходимости.
-   Не дублировать уже реализованные доменные модели.
-   Не смешивать authentication, authorization и domain business rules.

## 4. Структура приложения

``` text
app/
├── core/
├── domain/
├── application/
├── infrastructure/
└── presentation/
```

Infrastructure database:

``` text
app/infrastructure/database/
├── base.py
├── engine.py
├── mixins.py
├── models.py
└── session.py
```

Используются async engine и `async_sessionmaker`.

## 5. Конфигурация

Настройки --- через `pydantic-settings`.

Основные переменные: - `DATABASE_URL`; - `DEBUG`; - `SESSION_SECRET` для
подписанной cookie-сессии; - в дальнейшем параметры S3/email и другие
инфраструктурные настройки.

`.env` не коммитить.

В репозитории хранится `.env.example`.

Секрет сессии никогда не хранить в Git.

## 6. Идентификаторы и время

Основные сущности используют UUID7.

Текущие mixins: - `UUIDMixin`; - `TimestampMixin`; - `SoftDeleteMixin`.

`created_by`/`updated_by` пока не универсализированы через общий FK
из-за циклических зависимостей.

Временные метки timezone-aware.

Преобразования timezone централизовать.

## 7. Authentication

Authentication и authorization разделены.

### Authentication

Используется: - email + password; - `UserRepository.get_by_email()`; -
`PasswordService`; - `AuthService`; - Argon2 через `pwdlib`.

`AuthService` должен возвращать `User` только если: - пользователь
найден; - `active=True`; - `deleted_at is None`; - пароль корректен.

Для всех неуспешных случаев используется единая ошибка
`InvalidCredentialsError`.

### Session

Для MVP и рабочего внутреннего продукта согласован **вариант A ---
signed cookie session**.

Не использовать JWT без отдельного решения.

Cookie: - `HttpOnly`; - `SameSite=Lax`; - `Secure=True` при HTTPS; -
секрет из `SESSION_SECRET`.

В cookie не хранить чувствительные данные и права как источник истины.

Бизнес-логика не должна зависеть от конкретной реализации session
storage.

Будущая замена на server-side sessions, AD/LDAP/SSO должна быть возможна
без переписывания `AuthService` и `AccessService`.

Текущее состояние: - `UserRepository.get_by_email()` --- реализован; -
`PasswordService` --- реализован; - `AuthService` --- реализован; -
application tests authentication --- зелёные; - HTTP
login/logout/session middleware --- следующий блок.

## 8. Authorization и роли

Роли: - Superadmin; - Admin; - Specialist; - Manager; - Engineer.

Привязка: - Specialist → Holding или Branch; - Admin/Manager/Engineer →
Production Department; - Superadmin → без enterprise binding.

Все, кроме Superadmin, работают только в пределах своего предприятия и
подчинённых объектов.

`AccessService` --- единственная централизованная точка проверки
доступа.

Реализованы проверки: - enterprise; - substation; - connection; - URZA.

Не дублировать эти правила в роутерах и шаблонах.

## 9. Документальные домены

Для URZA: 1. ОТД; 2. Уставки; 3. Схемы; 4. ТО; 5. Программы; 6.
Инструкция URZA.

Для ПС: 7. Схемы селективности; 8. Инструкции по РЗА; 9. Инспекции ПС.

Не объединять домены в универсальную таблицу.

Не создавать повторно: - `RZAInstruction`; - `URZAInstruction`; -
`SchemaForm`; - `SettingsForm`; - `File`; - другие уже существующие
модели.

## 10. Формуляры и файлы

Формуляр --- логический контейнер.

Запись --- событие/операция/версия.

Файлы: - PostgreSQL хранит metadata; - содержимое хранится через
`ObjectStorage`; - домены используют явные FK; - polymorphic owner
запрещён.

### ObjectStorage

Интерфейс:

``` text
ObjectStorage
├── LocalObjectStorage
└── YandexS3ObjectStorage
```

Сейчас используется `LocalObjectStorage` для dev/test.

Путь dev: `data/uploads/`.

Целевой production storage --- S3-compatible, в том числе Yandex S3.

`FileService` не должен зависеть от конкретного storage backend.

S3 key генерируется приложением.

При переходе hot → cold: - `File.id` не меняется; - доменная история не
меняется; - целостность должна быть проверена до удаления hot-копии.

## 11. ОТД

Один `OTD` на URZA.

``` text
OTD
└── OTDVersion
```

Каждая версия --- полный снимок.

Старые версии сохраняются.

Скан/editable/signed form не требуются.

Реализовано.

## 12. Уставки

Один `SettingsForm` на URZA.

`SettingsRecord` содержит дату, параметр, исходную и новую уставку,
причину, автора, `signed_form_file_id`, `task_id`.

Скан подписанного формуляра обязателен.

Реализовано.

## 13. Схемы URZA

Один `SchemaForm` на URZA.

Текущий тип --- Исполнительная.

`SchemaRecord` содержит номер, название, описание/обоснование изменения,
дату загрузки, автора, scan/editable/signed form, `task_id`.

Текущий согласованный комплект: - scan; - editable; - signed form.

Реализовано.

Селективность ПС --- отдельный домен и пока не финализирована.

## 14. Инструкция по РЗА

`RZAInstruction` --- логический контейнер на ПС.

``` text
RZAInstruction
└── RZAInstructionVersion
```

`substation_id` UNIQUE.

Новая редакция создаёт новую версию.

Editable-файл nullable.

Signed form не требуется.

**Реализовано.**

## 15. Инструкция URZA

``` text
URZAInstruction
└── URZAInstructionVersion
```

Один контейнер на URZA.

Версии сохраняются.

`task_id` nullable.

При создании из Task связь устанавливается автоматически.

**Реализовано.**

## 16. ТО

`TORecord` --- фактическое мероприятие.

Типы: - В; - К; - К1; - Н; - Т; - ТК; - О; - ОСМ; - ВП; - ПП.

Правила: - signed form обязателен; - для ТК/О/ОСМ протокол не
требуется; - для остальных требующих типов протокол обязателен; -
deviations = `Не выявлено` по умолчанию; - measures = `Не требуется` по
умолчанию.

Планирование ТО не входит в MVP.

Использовать `MaintenancePeriodRule`.

## 17. Программы

Типы: - commissioning; - decommissioning; - work.

Скан обязателен.

Editable nullable.

Signed form отдельно не нужен.

Для сложной URZA нужны все три типа.

Реализовано.

## 18. Иерархия

`Enterprise`: - Holding; - Branch; - Production Department.

Только Production Department содержит Substation.

`Connection` принадлежит Substation.

`URZA` принадлежит Connection.

Dispatch name: - Connection --- уникален в Production Department; - URZA
--- уникален в Connection.

## 19. Task

Одно задание --- один тип работы с одной URZA.

Типы: - OTD; - SETTINGS; - SCHEMES; - MAINTENANCE; - PROGRAM.

Workflow:

``` text
CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED
```

Дополнительно: - ASSIGNED → REJECTED; - UNDER_REVIEW → IN_PROGRESS.

Причина обязательна при reject/return.

Срок выполнения --- 7 дней.

Acceptance deadline --- 1 день от назначения.

Продление не предусмотрено.

Переназначение не пересчитывает deadline.

Просроченность --- состояние, не отдельный статус.

## 20. Результат Task

Перед `COMPLETED` проверять комплектность результата.

Не разрешать завершение Task только кнопкой.

`task_id`: - из Task → устанавливается автоматически; - вне Task → NULL.

Остаётся TODO: проверка, что `task_id` и `urza_id` результата совпадают
по URZA.

## 21. TaskHistory

История неизменяема.

Фиксировать изменения workflow и критичные действия.

Не удалять историю вместе с Task.

## 22. Инспекции ПС

Inspection --- отдельный домен уровня Substation.

Не использовать обычный Task как замену Inspection.

Реализованы: - models; - workflow; - repository; - service; -
integration tests.

Исполнитель --- Engineer/Manager.

Reviewer --- Manager того же Production Department.

Нельзя проверять собственную инспекцию.

## 23. Архивирование

Использовать soft delete там, где это предусмотрено.

Для File архивирование: - не удаляет DB metadata; - устанавливает
`deleted_at`; - записывает `deleted_by`; - HTTP archive/delete endpoint
должен использовать `current_user`.

Каскадное архивирование должно сохранять состояние ветки для корректного
восстановления.

## 24. Тестирование

Использовать: - pytest; - pytest-asyncio; - реальный PostgreSQL для
integration tests.

После каждого логического изменения:

``` text
изменение
→ focused tests
→ полный suite
→ при необходимости alembic check
→ commit
→ push
```

Текущий известный полный результат: **311 passed**.

`uv run ruff check app` --- зелёный.

Не тратить время на старый Ruff technical debt в неизменённых тестах,
если он не относится к текущему изменению.

## 25. Alembic

Изменения схемы выполнять через Alembic.

Alembic находится в каталоге `migrations`.

Не искать каталог `alembic/` как источник истины.

После изменения моделей, которое затрагивает БД: 1. migration; 2.
registration в `app/infrastructure/database/models.py`; 3.
`alembic check`; 4. integration tests.

## 26. Git workflow

Правило:

``` text
изменение
→ тест
→ зелёный результат
→ commit
→ push
```

После каждого логического блока давать точные команды:

``` bash
git add ...
git commit -m "..."
git push
```

Не просить пользователя присылать `git status`, если это не требуется
для диагностики.

## 27. MVP --- актуальный порядок

1.  Authentication:
    -   session middleware;
    -   login/logout;
    -   `current_user`.
2.  Authorization integration в HTTP/UI.
3.  Оставшиеся application services.
4.  HTTP archive/delete для File.
5.  Jinja2 + HTMX UI.
6.  Notifications/email.
7.  Yandex S3.
8.  Backup и hot/cold lifecycle.
9.  Детальная селективность ПС.
10. Остальные открытые вопросы.

## 28. TODO после MVP

-   Схемы подстанции --- отдельная сущность уровня Substation, 0..N, без
    фиксированной классификации.
-   Детальная селективность ПС.
-   Yandex S3.
-   hot/cold lifecycle.
-   backup/recovery.
-   AD/LDAP/SSO при необходимости.
-   notifications/email.
-   дополнительные типы схем/программ после отдельного решения.
-   статистические email-рассылки второго этапа.

## 29. Не делать без отдельного решения

-   статистическую email-рассылку;
-   самостоятельное планирование ТО;
-   отдельный workflow просроченных заданий;
-   продление deadline;
-   отдельный контроль просроченных заданий;
-   регистрацию пользователей;
-   JWT как основной механизм браузерной сессии;
-   новые сущности/поля без согласования;
-   новые типы схем/программ без доменного решения.

Если решение не зафиксировано в документации --- считать его открытым.
