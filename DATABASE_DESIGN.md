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

Текущая модель не перерабатывается без отдельного доменного решения.

Исходный workflow предусматривает отдельный процесс ввода исторических ТО.

Вопрос исторических ТО является отложенным.

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

### Назначение

Task — рабочее поручение исполнителю. Task не является конкретной записью документа.

Задание создаётся в контексте:

```text
URZA + TaskWorkType
```

Например:

```text
URZA
└── Уставки
    └── [Выдать задание]
```

означает поручение:

> выполнить работу с уставками для данного URZA.

### Типы задач

```text
OTD
SETTINGS
SCHEMES
MAINTENANCE
PROGRAM
```

### Статусы

```text
CREATED
ASSIGNED
IN_PROGRESS
COMPLETED
UNDER_REVIEW
CLOSED
REJECTED
```

### UI: «Выдать задание»

На каждой вкладке карточки URZA должна быть одна кнопка:

```text
[Выдать задание]
```

Кнопка относится ко всей вкладке, а не к отдельной существующей записи.

```text
ОТД           → OTD
Уставки       → SETTINGS
Схемы         → SCHEMES
ТО            → MAINTENANCE
Программы     → PROGRAM
Инструкция    → соответствующий TaskWorkType
```

При открытии формы уже известны:

```text
urza_id
work_type
```

Не предлагать пользователю выбирать URZA или существующую запись документа повторно.

Кнопку видят только пользователи, имеющие право выдачи задания для данного URZA.

Текущее решение:

```text
MANAGER    → может выдавать в доступной области
SUPERADMIN → может выдавать для доступных ему объектов
ADMIN      → не выдаёт
ENGINEER   → не выдаёт
SPECIALIST → не выдаёт, если отдельным решением не определено иное
```

Право должно учитывать и роль, и область доступа:

```text
can_issue_task(user, urza)
```

Проверка в UI не заменяет проверку в application/service layer.

### Форма выдачи

Минимальный состав:

```text
УРЗА        — read-only
Вид работы  — read-only
Исполнитель — выбор инженера
Срок        — ввод
Описание    — ввод
```

После подтверждения руководитель создаёт/назначает задание конкретному инженеру.

### Workflow

Основной путь:

```text
CREATED
  ↓
ASSIGNED
  ↓
IN_PROGRESS
  ↓
COMPLETED
  ↓
UNDER_REVIEW
  ↓
CLOSED
```

Возврат:

```text
UNDER_REVIEW
  ↓
IN_PROGRESS
  ↓
COMPLETED
  ↓
UNDER_REVIEW
```

Отдельная терминальная ветка:

```text
ASSIGNED → REJECTED
```

`COMPLETED` означает завершение работы исполнителем, а не принятие результата.

### Права

- создание и назначение задания — MANAGER в своей доступной области;
- ADMIN не назначает;
- SUPERADMIN может выполнять операции с любым доступным объектом;
- `COMPLETED → UNDER_REVIEW` — назначенный исполнитель;
- `UNDER_REVIEW → CLOSED` — любой активный MANAGER с доступом к URZA;
- `UNDER_REVIEW → IN_PROGRESS` — любой активный MANAGER с доступом к URZA;
- проверяющий не обязан быть тем же руководителем, который создавал/назначал Task;
- причина возврата на доработку обязательна.

### Выполнение задания

В «Мои задания»:

```text
[Выполнить задание]
```

открывает контекст:

```text
Task
→ URZA
→ вкладка по work_type
```

Соответствие:

```text
OTD         → ОТД
SETTINGS    → Уставки
SCHEMES     → Схемы
MAINTENANCE → ТО
PROGRAM     → Программы
```

`task_id` должен сохраняться при переходе к форме результата.

### Task и результат

Task и документный результат являются двумя отдельными state machine.

Не выполнять автоматическую синхронизацию статусов Task и документа без отдельного решения.

Для `SCHEMES` закрытие Task возможно только при наличии активного `SchemaRecord` со статусом `APPROVED`.

Для остальных типов окончательные gate-условия должны быть отдельно зафиксированы перед реализацией.

Soft-deleted результат не считается активным результатом.

Task-linked результат должен:

- ссылаться на существующий Task;
- иметь тот же URZA;
- соответствовать `work_type`;
- принадлежать текущему назначенному исполнителю;
- создаваться/изменяться в разрешённом состоянии Task;
- не учитывать soft-deleted записи как активные.

### Прямой ввод

Прямой ввод из вкладки URZA не должен обходить review.

После:

```text
[Направить на согласование]
```

результат проходит тот же review workflow:

```text
UNDER_REVIEW
→ MANAGER
→ CLOSED
```

или:

```text
UNDER_REVIEW
→ IN_PROGRESS
→ повторное согласование
```

Отдельную сущность согласования для прямого ввода не создавать.

### Формуляры

Для Уставок, Схем и ТО, где требуется подписанный формуляр, формуляр создаётся на каждую отдельную операцию.

Шаблоны:

```text
data/document_templates/
├── schemes/
├── settings/
└── maintenance/
```

Формуляр содержит шапку конкретного объекта, одну строку текущей операции и место для подписи исполнителя.

На текущем этапе используется DOCX без серверной конвертации в PDF.

### Фактическое состояние по аудиту

Application/service часть Task workflow в значительной степени реализована.

HTTP/UI ещё не завершён:

- нет полноценной выдачи задания из вкладок URZA;
- нет законченного UI назначения;
- нет полного «Мои задания»;
- нет полноценного «Выполнить задание»;
- нет сквозного сохранения `task_id`;
- нет полного HTTP/UI review;
- Task routes теряют tree/sidebar context.

Подтверждённые технические замечания:

- `return_for_revision()` должен реально вызывать проверку обязательной причины;
- запросы результатов для OTD/Settings/Program/TO должны исключать soft-deleted записи;
- условие закрытия должно проверять именно активный результат;
- один активный `SchemaRecord` на Task уже ограничивается отдельным partial unique index.
---

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

### DONE

```text
Authentication
AccessService
Enterprise
Substation read UI
Connection read UI
URZA card
Tree / Sidebar
OTD read + history + versioning
Settings workflow
Schemes workflow
Programs status/review workflow
URZA Instruction version workflow
Universal audit
FileOwnerResolver
FileAccessService
Secure file view/download
Substation read-only tabs
RZA Instruction read/history
```

Все шесть вкладок URZA существуют:

```text
ОТД
Уставки
Схемы
ТО
Программы
Инструкция
```

Навигация остаётся:

```text
Holding → Branch → Production Department → Substation → Connection → URZA
```

Дочерние объекты не дублируются отдельными вкладками карточек.

### PARTIAL

```text
OTD
Settings
Schemes
Maintenance
Programs
URZA Instruction
Tasks
Files
Inspection
Substation Instruction
Selectivity Scheme
Substation / Connection / URZA write
```

Причины PARTIAL:

- ОТД: отсутствует write route/UI; специальный workflow остаётся отдельным доменным решением.
- Уставки: основной workflow реализован; остаются общие Tasks/file integration issues.
- Схемы: основной workflow реализован; остаются CSS и Task end-to-end.
- ТО: отсутствуют write routes/UI и DocumentStatus workflow.
- Программы: нет полноценного UI изменения APPROVED через новую запись/версию.
- Инструкция URZA: workflow реализован; остаётся race-safe version numbering и Task integration.
- Tasks: service/application готов в значительной степени, HTTP/UI end-to-end отсутствует.
- Files: защищённое чтение готово, write/upload/attach UI не завершены.
- Inspection: read/service есть, полноценный write UI отсутствует.
- Substation Instruction / Selectivity Scheme: read/history есть, write workflow отсутствует.

### Подтверждённые UI/technical issues

1. Task routes не загружают `tree`, поэтому Tasks теряет ожидаемый sidebar/tree context.
2. В таблице Schemes CSS ширины колонок не соответствуют фактическим 8 колонкам.
3. В таблице Maintenance последняя колонка не имеет корректной ширины, file action buttons слишком малы.
4. `return_for_revision()` должен валидировать обязательную причину.
5. Soft-deleted результаты не должны считаться активными результатами Task.
6. `Connections` не являются вкладкой Substation; дерево — основной способ навигации.

Контрольный аудит является текущим baseline и не должен повторяться без изменения кода или отдельной причины.
---

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

Рабочий порядок реализации:

```text
1. Tasks HTTP/UI end-to-end
   ├── «Выдать задание» на каждой вкладке URZA
   ├── can_issue_task
   ├── форма выдачи
   ├── выбор инженера
   ├── «Мои задания»
   ├── «Выполнить задание»
   ├── переход URZA + вкладка
   ├── task_id context
   ├── submit for review
   ├── review руководителем
   ├── обязательная причина возврата
   └── history / tests

2. Подтверждённые Task/document fixes
   ├── soft-delete filtering
   ├── tree/sidebar в Tasks
   └── проверки gate conditions

3. Write/UI документных вкладок URZA
   ├── ОТД
   ├── Уставки
   ├── Схемы
   ├── ТО
   ├── Программы
   └── Инструкция

4. File write/UI
   ├── upload
   ├── atomic attach
   ├── file actions
   └── orphan cleanup

5. Inspection workflow HTTP/UI

6. Write Substation / Connection / URZA

7. Production S3

8. Backup / Restore

9. Cold S3 / archive

10. Archive UI

11. Search

12. Notifications / automation
```

Не откладывать основной workflow из-за косметического UI-аудита.
---

## 28. Отложенные вопросы

### Исторические ТО

Не изменять `historical_data` без отдельного решения.

Исходный workflow требует отдельного процесса ввода исторических данных.

### Уникальность dispatch_name

Перед добавлением DB-ограничений необходимо отдельно зафиксировать области уникальности `dispatch_name` для Enterprise / Substation / Connection / URZA и проверить существующие данные.

### S3

Production S3 подключать после стабилизации file abstraction и завершения базовой write/UI работы с файлами.

### Backup / cold storage

Проектировать после стабилизации storage contract.

---

## 29. Зафиксированные UI-решения по Tasks

### Кнопка «Выдать задание»

Кнопка находится **на уровне вкладки карточки URZA**.

Правильно:

```text
URZA
└── Уставки
    └── [Выдать задание]
```

Неправильно:

```text
URZA
└── Уставки
    ├── запись №1 [Выдать задание]
    ├── запись №2 [Выдать задание]
    └── запись №3 [Выдать задание]
```

Кнопка означает:

> выдать инженеру работу с данным типом данных для данного URZA.

Она не создаёт связь с существующей записью документа на момент выдачи.

Форма выдачи получает:

```text
urza_id
work_type
```

и предлагает руководителю выбрать исполнителя, срок и описание.

После выполнения конкретный результат может быть связан с Task через `task_id`.

### Навигация

Task является входной точкой в рабочий процесс, но результат выполняется в контексте:

```text
Task
→ URZA
→ вкладка
→ форма результата
```

Поэтому UI должен сохранять контекст Task при переходе из «Мои задания» в соответствующую вкладку.


## 30. Основной принцип

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
