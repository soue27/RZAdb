# AGENTS.md --- База данных РЗА (RZAdb)

## 1. Назначение проекта

RZAdb --- веб-приложение для учёта оборудования РЗА, формуляров,
документов, заданий и фактически выполненных работ.

Основная иерархия:

``` text
Холдинг
└── Филиал
    └── Производственное отделение (ПО)
        └── Подстанция
            └── Присоединение
                └── УРЗА
```

Отдельные домены уровня ПС: схемы селективности, инструкции по РЗА,
инспекции ПС. Инспекция ПС --- отдельный домен и не является обычным
Task.

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

Локальная разработка использует PostgreSQL Homebrew. Рабочая БД:
`rzadb`.

## 3. Архитектурные принципы

-   Разделять domain/model, repositories, services, API и UI.
-   Бизнес-правила не размещать в Jinja-шаблонах или роутерах.
-   Доступ централизовать через `AccessService`.
-   Для критичных операций сохранять аудит.
-   Использовать soft delete там, где это предусмотрено.
-   Файлы не хранить в PostgreSQL: БД хранит метаданные и ссылки,
    содержимое --- в S3.
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

## 4. Структура приложения

``` text
app/
├── core/
├── domain/
├── application/
├── infrastructure/
└── presentation/
```

Инфраструктура БД:

``` text
app/infrastructure/database/
├── base.py
├── engine.py
├── mixins.py
└── models.py
```

Используются async engine и `async_sessionmaker`.

## 5. Конфигурация

Настройки --- через `pydantic-settings`.

Основные переменные: - `DATABASE_URL` - `DEBUG` - в дальнейшем timezone
и параметры S3/email.

`.env` не коммитить. В репозитории --- `.env.example`.

## 6. Идентификаторы и время

Основные сущности используют UUID7. Где предусмотрено общей моделью: -
`id` - `created_at` - `created_by` - `updated_at` - `updated_by` -
`deleted_at` - `deleted_by`

Текущие mixins: `UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`.

`created_by`/`updated_by` пока не универсализированы через общий FK
из-за циклических зависимостей.

Временные метки timezone-aware. Преобразования timezone централизовать.

## 7. Роли и область доступа

Роли: - Superadmin - Admin - Specialist - Manager - Engineer

Привязка: - Specialist → Holding или Branch. - Admin/Manager/Engineer →
Production Department. - Superadmin → без enterprise binding.

Права: - Specialist --- просмотр/скачивание. - Admin ---
создание/изменение; удаление по правилам подтверждения. - Manager ---
иерархия, задания, проверка. - Engineer --- выполнение заданий и работа
с формулярами. - Superadmin --- полный доступ.

Все, кроме Superadmin, работают только в пределах своего предприятия и
подчинённых объектов.

## 8. Документальные домены

Для УРЗА: 1. ОТД 2. Уставки 3. Схемы 4. ТО 5. Программы 6. Инструкция
УРЗА

Для ПС: 7. Схемы селективности 8. Инструкции по РЗА 9. Инспекции ПС

Не объединять домены в универсальную таблицу.

## 9. Формуляры и файлы

Формуляр --- логический контейнер; запись --- событие/операция/версия.

Файлы хранятся в S3-compatible storage. В БД --- `File` и явные FK: -
`scan_file_id` - `editable_file_id` - `signed_form_file_id` - и т. п.

Не использовать polymorphic owner.

Системный S3 key строится автоматически по контексту
ПС/присоединения/УРЗА/типа документа/даты.

## 10. ОТД

Один `OTD` на УРЗА:

``` text
OTD
└── OTDVersion
```

Каждая версия --- полный снимок. Старые версии сохраняются. Скан,
editable-файл и отдельная подпись не требуются.

## 11. Уставки

Один `SettingsForm` на УРЗА. `SettingsRecord` содержит дату, параметр,
исходную и новую уставку, причину, автора, `signed_form_file_id`,
`task_id` nullable.

Каждая запись --- только изменённые параметры. Скан подписанного
формуляра обязателен. Отдельный протокол не формируется.

## 12. Схемы

Один `SchemaForm` на УРЗА. Текущий тип --- Исполнительная.
`SchemaRecord` содержит номер, название, описание/обоснование изменения,
дату загрузки, автора, scan/editable/signed form, `task_id`.

Текущий согласованный комплект: скан схемы, редактируемая схема,
подписанный формуляр.

Селективность ПС --- отдельный домен; детальная модель пока не
финализирована.

## 13. Инструкция по РЗА

`RZAInstruction` --- логический контейнер на ПС:

``` text
RZAInstruction
└── RZAInstructionVersion
```

`substation_id` --- UNIQUE.

Версия: - `version_number` - `effective_date` - `change_description`
nullable - `change_justification` nullable - `created_at` -
`created_by` - `scan_file_id` - `editable_file_id` nullable в текущей
реализации

Новая редакция создаёт новую версию. Старые версии сохраняются.
Отдельный signed form не требуется.

Важно: модели `RZAInstruction` и `RZAInstructionVersion` уже существуют
в текущем коде. Не создавать их повторно.

## 14. Инструкция УРЗА

Логический контейнер на УРЗА:

``` text
URZAInstructionForm
└── URZAInstructionRecord
```

Версия содержит номер, дату действия, описание/обоснование, дату
загрузки, автора, scan/editable files и `task_id` nullable. Новые версии
сохраняются. При создании из Task `task_id` устанавливается
автоматически.

## 15. ТО

`TORecord` --- одно фактически выполненное мероприятие. Типы: В, К, К1,
Н, Т, ТК, О, ОСМ, ВП, ПП.

Правила: - signed form обязателен; - протокол обязателен для типов, где
он требуется; - для ТК, О, ОСМ протокол не нужен; - даже для них signed
form обязателен; - deviations по умолчанию `Не выявлено`; - measures по
умолчанию `Не требуется`; - `task_id` nullable.

Планирование ТО не входит в первую версию. Период ТО зависит от
категории помещения и элементной базы; `complexity` не влияет.
Использовать `MaintenancePeriodRule`, а не hard-coded if/else. После 25
лет UI показывает необходимость решения о продлении/замене.

## 16. Программы

`Program` связана с УРЗА. Типы: commissioning, decommissioning, work.
Одна УРЗА может иметь несколько программ одного типа.

Скан обязателен, editable nullable, `task_id` nullable. `program_number`
--- внешний номер. Отдельный signed form не нужен. Для сложной УРЗА
обязательны все три типа. Удаление допускается после подтверждения;
Superadmin может удалить напрямую.

## 17. Иерархия

`Enterprise` представляет Holding, Branch, Production Department. Только
Production Department содержит Substation.

Substation: - enterprise_id - highest_voltage - dispatch_name - SAP
nullable - ASUREO nullable - latitude/longitude/address nullable

Напряжения: 500, 220, 110, 35, 10, 6, 0.4 кВ.

Connection: - substation_id - dispatch_name - SAP/ASUREO nullable -
RDU - operational current: permanent/rectified/alternating

Имя Connection уникально в Production Department.

URZA: - принадлежит Connection; - dispatch name уникален внутри
Connection; - inventory nullable; - commissioning date; - status; -
element base; - category; - room category; - complexity; - вычисляемые
title и maintenance period.

## 18. Title URZA

Вычисляется из: `Холдинг + Филиал + ПО + ПС + Присоединение + УРЗА`. Не
редактируется.

## 19. Task

Одно задание --- один тип работы с одной УРЗА. Типы: OTD, SETTINGS,
SCHEMES, MAINTENANCE, PROGRAM. Для MAINTENANCE `maintenance_type`
обязателен.

Workflow:

``` text
CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED
```

Дополнительно: - ASSIGNED → REJECTED; - UNDER_REVIEW → IN_PROGRESS.

Причина обязательна при отклонении и возврате на доработку. После
возврата --- сразу IN_PROGRESS, повторное принятие не требуется.

Срок выполнения --- 7 дней от создания. Срок принятия --- 1 день от
назначения. Продление не предусмотрено. Переназначение не пересчитывает
deadline.

После истечения acceptance deadline статус остаётся ASSIGNED,
руководитель уведомляется, инженер всё ещё может принять/отклонить.

Просроченность --- состояние по времени, не отдельный workflow-статус.

## 20. Результат Task

Нельзя завершить Task только кнопкой. Перед COMPLETED система проверяет
обязательный результат по work type и, для ТО, maintenance type.

Записи формуляров имеют nullable `task_id`. Из Task → связь ставится
автоматически. Вне Task → `task_id = NULL`.

## 21. TaskHistory

Неизменяемая история: - task_id - event_type - old_status - new_status -
actor_id - comment - created_at

Фиксируются создание, назначение, переназначение, принятие, отклонение,
начало работы, просрочка, выполнение, доработка, возврат, подтверждение,
закрытие и удаление ошибочного задания.

## 22. Инспекции ПС

Инспекция --- отдельный домен уровня Substation:

``` text
Substation
├── InspectionTask
│   └── InspectionHistory
└── Inspection
```

InspectionTask: - substation_id - created_by - assigned_to - status -
created_at - assigned_at - acceptance_deadline_at - deadline_at -
completed_at - closed_at

Inspection: - substation_id - `inspection_task_id` UNIQUE -
inspection_date - remarks - scan_file_id nullable - editable_file_id
nullable - created_by - created_at/updated_at

Workflow:
`CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED`
плюс ASSIGNED → REJECTED и UNDER_REVIEW → IN_PROGRESS.

Исполнитель --- Engineer или Manager. Проверяющий --- Manager того же
Production Department. Manager не может проверять собственную инспекцию.

Обязательны `inspection_date` и `remarks`; файлы необязательны. Причина
обязательна при reject/return.

Уже реализованы модели, workflow, repository/service и integration tests
с PostgreSQL. Последний известный результат полного набора: **121
passed**.

## 23. Уведомления

`Notification`: - user_id - type - title - message - task_id nullable -
created_at - read_at nullable

`read_at = NULL` --- непрочитано. После просмотра уведомление исчезает
из основного списка, но остаётся в БД.

Email обязателен: - новое задание; - напоминания; - просрочка; -
непринятое задание; - действия руководителя.

Напоминания: за 3, 2 и 1 день до deadline, затем просрочка.
Статистические рассылки --- второй этап.

## 24. Архив и удаление

Для архивируемых ПС/Connection/URZA используется soft delete. Каскадное
архивирование требует сохранения состояния потомков до операции.

Task: - ошибочное задание можно удалить до начала работы; - после
IN_PROGRESS физическое удаление запрещено; - закрытые задания
сохраняются; - удаление фиксируется в истории; - Superadmin имеет полный
доступ.

Для других объектов действует подтверждаемое удаление по ролям.

## 25. Тестирование

Использовать pytest/pytest-asyncio и реальный PostgreSQL для integration
tests. Тестовая транзакция откатывается после каждого теста. После
изменения логики: тест → зелёный результат → следующий блок.

Известный результат: **121 passed**.

## 26. Alembic

Изменения схемы БД выполнять через Alembic. После миграции проверять
модели и связанные integration tests.

## 27. Git workflow

Работать так: `изменение → тест → зелёный результат → commit → push`.

После логического блока давать точные команды `git add`,
`git commit -m`, `git push`. Не просить пользователя присылать
`git status`, если это не нужно для конкретной диагностики.

## 28. Приоритет MVP

1.  AccessService и права.
2.  Оставшиеся domain/application services.
3.  Автоматическая проверка комплектности Task.
4.  File/S3 service.
5.  UI Jinja2 + HTMX.
6.  Notifications/email.
7.  Backup и hot/cold storage.
8.  Детальная селективность ПС.
9.  Остальные открытые вопросы.

Codex подключать, когда появляется большой объём повторяющегося кода, а
не ради самой автоматизации.

## 29. Не делать без отдельного решения

-   статистическую email-рассылку;
-   самостоятельное планирование ТО;
-   отдельный workflow просроченных заданий;
-   продление deadline;
-   отдельный контроль просроченных заданий;
-   регистрацию пользователей;
-   новые сущности/поля без согласования;
-   новые типы схем/программ без доменного решения.

Если решение не зафиксировано в документации --- считать его открытым.
