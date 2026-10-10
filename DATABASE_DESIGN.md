# DATABASE_DESIGN.md — RZAdb

## 1. Назначение

RZAdb — внутренняя система учёта оборудования РЗА, подстанций, присоединений, устройств РЗА и связанной технической документации.

Этот документ фиксирует согласованные доменные и архитектурные решения по базе данных.

Главное правило:

> Не добавлять новые сущности, поля, связи, ограничения или бизнес-правила без отдельного доменного решения.

---

## 2. Иерархия предметной области

```text
Holding
└── Branch
    └── Production Department
        └── Substation
            └── Connection
                └── URZA
```

Подстанция может содержать множество присоединений.

Присоединение может содержать множество устройств РЗА.

---

## 3. Enterprise hierarchy

Верхний уровень:

```text
Holding
Branch
Production Department
```

Подстанция, присоединение и URZA находятся ниже.

Доступ пользователей должен учитывать принадлежность объекта соответствующему enterprise-контексту.

---

## 4. Роли

Используются:

```text
SUPERADMIN
ADMIN
SPECIALIST
MANAGER
ENGINEER
```

`AccessService` является централизованной точкой authorization.

Проверки:

```text
can_access_enterprise()
can_access_substation()
can_access_connection()
can_access_urza()
get_accessible_enterprise_roots()
```

Authorization не должен дублироваться в UI.

---

## 5. Подстанция

Подстанция является контейнером для:

```text
Connections
URZA
```

Диспетчерское имя подстанции уникально в соответствующей доменной области.

SAP и ASUREO не считаются глобально уникальными без отдельного доменного решения.

---

## 6. Присоединение

Присоединение принадлежит подстанции.

Присоединение может содержать множество URZA.

Диспетчерское имя должно быть уникальным в соответствующей доменной области.

---

## 7. URZA

URZA принадлежит присоединению.

Имя URZA уникально внутри присоединения.

### Напряжение

Допустимые значения:

```text
500
220
110
35
10
6
0.4
```

### Статусы

```text
IN_OPERATION
IN_REPAIR
DECOMMISSIONED
RESERVE
```

### Элементная база

```text
ELECTROMECHANICAL
MICROELECTRONIC
MICROPROCESSOR
```

### Категория URZA

Используются категории:

```text
I
II
III
IV
```

URZA II может обслуживаться персоналом категорий:

```text
II
III
IV
```

---

## 8. Формуляр

Формуляр — логическая группировка документов и данных URZA.

На одном логическом уровне под URZA находятся:

```text
ОТД
Уставки
Схемы
ТО
Программы
```

Инструкция URZA также является отдельным документным разделом URZA.

---

## 9. ОТД

ОТД имеет текущую версию и исторические версии.

```text
OTD
├── current version
└── historical versions
```

Старые версии не удаляются.

### Назначение ОТД

```text
RZA
SA
PA
RA
```

Для ОТД подпись не обязательна.

### Versioning

Создание новой версии:

```text
current version
      ↓
new version
      ↓
old version remains in history
```

Одна бизнес-операция создания новой версии должна быть атомарной.

В UI исторические версии доступны через HTMX.

---

## 10. Уставки

`SettingsForm` относится к одному URZA.

```text
URZA
└── SettingsForm
    └── SettingsRecord[]
```

`SettingsRecord` фиксирует:

```text
change_date
parameter_name
initial_setting
new_setting
change_reason
signed_form_file
 task
creator
```

История изменений не должна уничтожаться физически.

---

## 11. Схемы

`SchemaForm` относится к одному URZA.

```text
URZA
└── SchemaForm
    └── SchemaRecord[]
```

Запись схемы содержит:

```text
schema_number
schema_name
change_description
change_justification
upload_date
scan_file
editable_file
signed_form_file
task
creator
```

Файлы имеют явные FK на `files.id`.

---

## 12. ТО

ТО относится непосредственно к URZA.

```text
URZA
└── TORecord[]
```

### Типы ТО

```text
В   — Профилактическое восстановление
К   — Профилактический контроль
К1  — Первый профилактический контроль
Н   — Наладка
Т   — Тестовый контроль
ТК  — Технический контроль
О   — Опробование
ОСМ — Технический осмотр
ВП  — Внеочередная проверка
ПП  — Послеаварийная проверка
```

Для `ТК`, `О`, `ОСМ` протокол не требуется согласно исходному workflow.

Подписанная форма/скан для обычной записи ТО обязательна.

Плановая дата ТО хранится для последующего микросервиса.

### Исторические ТО

`historical_data` — булево поле (`bool`), а не текстовое описание. Исторические ТО остаются в общей таблице `TORecord`; отдельную таблицу истории ТО не создавать. Отдельный сценарий ввода исторических записей может быть самостоятельным workflow/UI, но не меняет согласованную структуру модели.

---

## 13. Программы

Программа относится непосредственно к URZA.

Типы:

```text
COMMISSIONING
DECOMMISSIONING
WORK
```

Запись программы содержит:

```text
program_type
program_number
scan_file
editable_file
task
creator
```

Скан программы является обязательным.

Файлы хранятся через object storage, а в БД хранится ссылка/метаданные файла.

---

## 14. Инструкция URZA

Инструкция URZA является отдельной сущностью уровня URZA.

```text
URZA
└── URZAInstruction
    └── URZAInstructionVersion[]
```

`URZAInstruction` — логическая группа.

`URZAInstructionVersion` — конкретная версия документа.

Для URZA существует одна группа инструкции:

```text
URZAInstruction.urza_id UNIQUE
```

### Версия инструкции

Содержит:

```text
version_number
effective_date
change_description
change_justification
scan_file
editable_file
creator
```

Скан инструкции обязателен.

Редактируемый файл необязателен.

Исторические версии не удаляются.

Создание новой версии:

```text
current version
      ↓
new version
      ↓
old version remains available
```

В UI история версий доступна через HTMX.

При первом открытии истории она свернута.

После выбора версии через историю она остаётся раскрытой.

---

## 15. Инструкция РЗА уровня подстанции

Инструкция РЗА подстанции — другая сущность и не должна объединяться с `URZAInstruction`.

```text
Substation
└── RZAInstruction
    └── RZAInstructionVersion[]
```

Она относится к уровню Substation.

Не использовать `URZAInstruction` для инструкции РЗА подстанции.

---

## 16. Схемы селективности

Схемы селективности относятся к уровню Substation.

```text
Substation
└── SelectivityScheme
    └── SelectivitySchemeVersion[]
```

Это отдельная сущность от `SchemaForm` / `SchemaRecord`, относящихся к URZA.

---

## 17. Tasks

### 17.1. Назначение и типы

Task представляет назначенную работу по документу/результату URZA. Осмотры подстанций — отдельный процесс и не должны автоматически становиться обычными Tasks.

В согласованном списке типов Tasks зафиксированы:

```text
OTD
SETTINGS
SCHEMES
MAINTENANCE
PROGRAM
```

**Несогласованность реализации:** в текущем коде также есть `TaskWorkType.INSTRUCTION` и UI выдачи заданий этого типа. Сам факт наличия enum/UI не считается доменным решением. До отдельного подтверждения пользователя тип `INSTRUCTION` имеет статус `NEEDS DOMAIN DECISION`: не удалять его из кода и не объявлять частью утверждённого доменного контракта; не создавать миграции только для документационного выравнивания.

### 17.2. Статусы

```text
CREATED
ASSIGNED
IN_PROGRESS
COMPLETED
UNDER_REVIEW
CLOSED
REJECTED
```

Основной workflow:

```text
CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED
                   ↑                           │
                   └──── return for revision ──┘
```

Дополнительный переход:

```text
ASSIGNED → REJECTED
```

`REJECTED` — отказ назначенного исполнителя с обязательной причиной.

### 17.3. Переходы и ответственность

- `CREATED → ASSIGNED`: задание назначается исполнителю. Текущий HTTP/UI-сценарий создания одновременно назначает выбранного инженера.
- `ASSIGNED → IN_PROGRESS`: назначенный исполнитель принимает задание (`accept_task`).
- `ASSIGNED → REJECTED`: назначенный исполнитель отказывается от задания; причина обязательна (`reject_task`).
- `IN_PROGRESS → COMPLETED`: назначенный исполнитель завершает работу (`complete_task`) после проверки наличия требуемого результата.
- `COMPLETED → UNDER_REVIEW`: исполнитель отправляет результат руководителю (`submit_for_review`).
- `UNDER_REVIEW → CLOSED`: руководитель закрывает задание после проверки результата (`close_task`).
- `UNDER_REVIEW → IN_PROGRESS`: руководитель возвращает задание на доработку (`return_for_revision`).

Назначение, принятие, завершение, отказ, отправка на согласование, закрытие и возврат должны фиксироваться в истории задания существующим механизмом истории. Не вводить параллельную историю или дублирующие сущности без отдельного решения.

### 17.4. Дедлайны

Текущая реализация `TaskService` задаёт срок выполнения по умолчанию на 7 дней и срок принятия назначения на 1 день. Не менять эти значения и семантику без отдельного доменного решения.

### 17.5. Проверка результата

`complete_task()` валидирует наличие результата в зависимости от типа задания. Существующие проверки включают:

- OTD — связанная `OTDVersion`;
- SCHEMES — связанная `SchemaRecord` и обязательные документы/файлы по действующим правилам;
- SETTINGS — связанная `SettingsRecord`;
- MAINTENANCE — связанная `TORecord`, совпадение типа ТО с заданием и соблюдение правил обязательности протокола;
- PROGRAM — связанная `Program`;
- INSTRUCTION — соответствующая проверка уже существует в коде, но доменный статус самого типа `INSTRUCTION` требует отдельного решения.

Не ослаблять эти проверки ради добавления HTTP-кнопки. Если результата ещё нет, route должен отобразить понятную ошибку сервиса, а не обходить валидацию.

### 17.6. HTTP/UI: текущее состояние и следующий этап

В коде уже существуют список и карточка задания, создание с назначением, а также HTTP/UI для:

```text
submit-for-review
close
return-for-revision
```

Сервисные методы `accept_task`, `complete_task`, `reject_task` существуют, но на контрольной точке 2026-10-08 HTTP/UI для этих действий ещё отсутствовал. Следующий этап — добавить:

```text
POST /tasks/{task_id}/accept
POST /tasks/{task_id}/complete
POST /tasks/{task_id}/reject
```

Ожидаемые действия интерфейса:

- `ASSIGNED` + назначенный исполнитель: принять / отказаться;
- `IN_PROGRESS` + назначенный исполнитель: завершить;
- `COMPLETED` + назначенный исполнитель: отправить на согласование;
- `UNDER_REVIEW` + руководитель, имеющий право review: закрыть / вернуть на доработку.

Причина отказа обязательна. Обычные POST используют redirect на карточку; HTMX возвращает обновлённый фрагмент. Доступ к URZA проверяется единообразно через существующий механизм, а окончательная проверка роли, назначения и статуса остаётся в application service.

Это UI-расширение не требует новых сущностей, полей или миграций само по себе.

### 17.7. Связь задания с результатом

Увязка Task с результатами реализована не полностью. На контрольной точке:

- Schemes и Maintenance write-flow принимают `task_id`;
- Settings, Programs и URZA Instruction write-flow ещё не завершены для сценария создания результата из задания;
- у OTD отсутствует полноценный write/create path в этом потоке.

Не считать полный task-result workflow готовым, пока каждый утверждённый тип задания не имеет корректного пути создания/привязки результата и регрессионных тестов. Не добавлять новые поля связи, пока не исследованы существующие модели и не подтверждена необходимость доменным решением.

### 17.8. Правила изменения Tasks

- Не помещать workflow-валидацию в routes или Jinja.
- Не дублировать проверки `TaskService` в presentation layer.
- `get_available_actions()` должен учитывать состояние, назначенного исполнителя и доступ к review; UI не должен показывать действия пользователю, который не может их выполнить.
- Routes обязаны проверять доступ пользователя к URZA через существующий механизм.
- Изменения покрывать unit- и HTTP-тестами, включая action visibility, ошибки, передачу причины отказа, HTMX и OpenAPI.

## 18. Inspections / Осмотры

В domain/database сохраняется существующая сущность `Inspection`.

Название `Inspection` в коде и БД не меняется только ради UI.

В интерфейсе отображается:

```text
Осмотры
```

Inspection — отдельный процесс.

---

## 19. Files

Бинарные данные не хранить в PostgreSQL.

Целевая архитектура:

```text
Domain entity
    ↓
File metadata
    ↓
ObjectStorage
```

Целевой storage:

```text
S3-compatible object storage
```

Локальное хранилище используется в development.

Не использовать универсальную полиморфную модель:

```text
File(owner_type, owner_id)
```

Использовать явные FK:

```text
scan_file_id
editable_file_id
signed_form_file_id
...
```

### Общий механизм доступа

```text
User
 ↓
AccessService
 ↓
domain object access
 ↓
FileAccessService
 ↓
File
 ↓
ObjectStorage
 ↓
Просмотр / Скачать
```

### Принятые решения

- `AccessService` — источник истины для доступа к доменным объектам.
- `FileOwnerResolver` определяет владельца `File` через явные FK.
- Один `File` имеет одного однозначного владельца; несколько file roles у одного владельца допустимы.
- Разные владельцы одного `File` считаются неоднозначным техническим состоянием; доступ запрещается.
- Orphan-файлы без владельца остаются техническим состоянием и не доступны обычному пользователю.
- Архивирование владельца не блокирует чтение его файлов, если пользователь может просматривать архивный объект.
- Архивированный `File` сам по себе недоступен через обычные read routes.
- Для `Inspection` владелец файла определяется через `Inspection.substation_id`.
- Для уже созданного результата осмотра авторизация не зависит от `InspectionTask`.
- Просмотр и скачивание используют общий защищённый механизм; PDF viewer не требуется.

### Текущее состояние

Уже реализованы и проверены:

- `FileOwnerResolver`;
- `FileAccessService`;
- защищённые `/view` и `/download` routes;
- authentication / owner / archive / orphan / ambiguous ownership checks.

Следующий этап Files — write/UI: upload, привязка файлов и полноценные file actions в документных вкладках URZA.

---

## 20. Архивирование

Документы и объекты не удаляются физически без отдельного доменного решения.

Используется soft delete / archive state.

Архивные объекты не должны попадать в обычные active queries и sidebar.

---

## 21. Audit contract

Универсальный audit-refactor завершён.

Стандартный набор:

```text
created_at
created_by
updated_at
updated_by
deleted_at
deleted_by
```

Смысл:

```text
created_at  — когда создано
created_by  — кто создал

updated_at  — когда последний раз изменено
updated_by  — кто последний изменил

deleted_at  — когда архивировано
 deleted_by  — кто архивировал
```

Audit-поля должны быть реализованы централизованно через базовые mixins.

Audit не должен зависеть от UI.

Текущий Alembic head после audit-refactor:

```text
a74c1d8f2b90
```

---

## 22. Транзакции

Одна бизнес-операция должна быть атомарной.

Пример создания новой версии:

```text
BEGIN

create new version
update required metadata
preserve old version

COMMIT
```

Не оставлять частично выполненную бизнес-операцию.

Repository не выполняет `commit()` без архитектурной причины.

---

## 23. Миграции

Alembic:

```text
migrations/
```

Стандартный процесс:

```text
изменение модели
→ создать migration
→ проверить migration
→ применить migration
→ тесты
```

Для значимых database changes:

```text
inspect
→ plan
→ domain decision
→ implementation
→ migration
→ tests
```

Не создавать migration до согласования структуры изменения.

---

## 24. Индексы и ограничения

Индексы создаются исходя из реальных запросов.

Основные кандидаты:

- foreign keys;
- `deleted_at` в active queries;
- поля поиска;
- поля уникальности;
- часто используемые фильтры.

Не добавлять индексы «на всякий случай».

SAP/ASUREO не делать глобально уникальными без отдельного доменного решения.

---

## 25. Текущий статус

Контрольная точка feature-ветки `feature/document-results-workflow`, HEAD `6215205` (`feat: complete maintenance write workflow`, 2026-10-08): локально проходило 791 тест. Это результат на указанной контрольной точке; после новых изменений тесты необходимо запускать повторно.

Завершено или реализовано на этой контрольной точке:

```text
Authentication
AccessService
Enterprise / Substation / Connection / URZA read flows
Tree / Sidebar
OTD read/versioning/history
Settings read/write workflow
Schemes read/write workflow
Maintenance write workflow (including task_id)
Programs read/write workflow
URZA Instruction read/versioning/write workflow
Universal audit
FileOwnerResolver
FileAccessService
Secure file view/download
Task service transitions/history/permissions/result validation
Task list/detail UI
Task create + assign UI
Task manager review/close/return HTTP/UI
```

Ограничения, которые нельзя считать закрытыми:

- executor HTTP/UI для `accept`, `complete`, `reject`;
- сквозная связь задания с результатом для Settings / Programs / Instruction / OTD;
- единообразная очистка загруженных файлов при ошибке сохранения во всех write routes;
- write/create flow ОТД;
- generic archive UI для файлов;
- восстановление и регрессионное покрытие навигационного дерева на `/tasks` и `/tasks/{task_id}`;
- формальное доменное решение о `TaskWorkType.INSTRUCTION`.

Фактический статус следует перепроверять по коду и тестам перед каждым новым этапом; этот документ не заменяет проверку ветки.

## 26. Контрольный аудит — завершён

Контрольный аудит выполнен по фактическому состоянию проекта и использован для обновления roadmap.

Проверены:

```text
models
→ repositories
→ services
→ DTO
→ routes / DI
→ templates
→ tests
→ migrations
→ storage
→ DATABASE_DESIGN
→ AGENTS
→ TODO / roadmap
```

Классификация используется как рабочий принцип:

```text
DONE
PARTIAL
TODO
NEEDS DOMAIN DECISION
TECHNICAL DEBT
```

Дальнейший полный UI-аудит не должен вытеснять реализацию основного функционала, если обнаруженное замечание не влияет на безопасность, целостность данных или корректность workflow.

---

## 27. Актуальный roadmap

Порядок ближайшей работы на основе контрольной точки 2026-10-08:

```text
1. Tasks executor HTTP/UI
   ├── POST accept
   ├── POST complete
   ├── POST reject (reason required)
   ├── action visibility
   └── HTTP / HTMX / OpenAPI regression tests

2. Task → document result linking
   ├── Settings
   ├── Programs
   ├── URZA Instruction (after domain decision where relevant)
   └── OTD write/create path

3. Write-route file cleanup
   ├── failed Programs save
   ├── failed URZA Instruction save
   └── consistency tests for upload cleanup

4. Restore tree navigation in task pages
   ├── /tasks
   ├── /tasks/{task_id}
   └── regression tests for Holding → Branch → Production Department → Substation → Connection → URZA

5. Complete file write/UI and document CRUD where still partial
6. Inspection workflow via HTTP/UI
7. Write functionality for Substation / Connection / URZA
8. Production S3
9. Database + file backup/restore
10. Cold S3 transfer and archive UI
11. Search
12. Notifications / automation
```

Не начинать следующий крупный этап до закрытия тестов текущего этапа. Не блокировать основной функционал косметическими UI-аудитами, кроме дефектов безопасности, целостности данных или навигации, мешающей рабочему сценарию.

## 28. Отложенные вопросы

### Исторические ТО

Решение по модели принято: `historical_data` — boolean, записи остаются в `TORecord`, отдельная history table не создаётся. Отдельный UI/workflow ввода исторических ТО ещё может требовать реализации, но не является основанием менять модель.

### Уникальность dispatch_name

Перед добавлением DB-ограничений необходимо отдельно зафиксировать области уникальности `dispatch_name` для Enterprise / Substation / Connection / URZA и проверить существующие данные.

### TaskWorkType.INSTRUCTION

В коде есть `TaskWorkType.INSTRUCTION` и UI выдачи таких заданий, но утверждённый список типов Tasks в этом документе пока включает только OTD, SETTINGS, SCHEMES, MAINTENANCE и PROGRAM. Требуется отдельное решение пользователя: включить INSTRUCTION в доменный контракт или оставить его вне утверждённого списка. До решения не менять код/БД по собственной инициативе.

### S3

Production S3 подключать после стабилизации file abstraction и завершения базовой write/UI работы с файлами.

### Backup / cold storage

Проектировать после стабилизации storage contract.

---

## 29. Основной принцип

База данных должна отражать согласованную предметную область.

Не:

- добавлять поля «на всякий случай»;
- создавать дублирующие сущности;
- менять БД ради косметического UI;
- физически удалять исторические версии;
- смешивать domain rules и infrastructure details.

При неоднозначности:

```text
исследование
→ вопрос пользователю
→ доменное решение
→ реализация
```
