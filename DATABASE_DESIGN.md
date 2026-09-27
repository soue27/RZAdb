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

Типы задач:

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

Активные рабочие состояния:

```text
ASSIGNED
IN_PROGRESS
UNDER_REVIEW
```

Инспекции/осмотры ПС — отдельный процесс и не должны автоматически становиться обычными Tasks.

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

Локальное хранилище может использоваться в development.

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
File
 ↓
ObjectStorage
 ↓
Просмотр / Скачать
```

Не создавать отдельную несогласованную реализацию доступа к файлам для каждой сущности.

PDF viewer не требуется.

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

Завершено:

```text
Authentication
AccessService
Enterprise
Substation
Connection
URZA
Tree
Sidebar
URZA card
OTD
OTD versioning
OTD history
Settings
Schemes
Maintenance
Programs
URZA Instruction
URZA Instruction versioning
Universal audit
```

Все шесть вкладок URZA реализованы:

```text
ОТД
Уставки
Схемы
ТО
Программы
Инструкция
```

---

## 26. Контрольный аудит — следующий этап

Перед следующим крупным функциональным изменением необходимо провести аудит фактического состояния проекта:

```text
current code
→ models
→ repositories
→ services
→ DTO
→ routes
→ dependencies
→ templates
→ tests
→ migrations
→ storage
→ DATABASE_DESIGN
→ AGENTS
→ TODO
```

Результат:

```text
DONE
PARTIAL
TODO
NEEDS DOMAIN DECISION
TECHNICAL DEBT
```

После аудита обновляется roadmap.

Если для полного аудита недостаточно информации из текущего контекста, coding agent может собрать фактическую информацию из репозитория. Его отчёт следует использовать как источник фактического состояния, а не предполагать наличие кода.

---

## 27. Предварительный roadmap

Порядок подлежит пересмотру после аудита:

```text
1. Контрольный аудит
2. Обновление roadmap / TODO

3. Общий механизм файлов
   ├── File access
   ├── Просмотр
   ├── Скачать
   └── ObjectStorage abstraction

4. Подключение файлов ко всем URZA-вкладкам

5. Полноценный CRUD документов URZA
   ├── ОТД
   ├── Уставки
   ├── Схемы
   ├── ТО
   ├── Программы
   └── Инструкция

6. Tasks workflow

7. Substation
   ├── Основные сведения
   ├── Присоединения
   ├── Осмотры
   ├── Инструкции
   └── Схемы селективности

8. Inspection workflow

9. Production S3

10. Backup

11. Cold S3 / archive

12. Notifications / automation
```

Порядок может быть изменён после контрольного аудита.

---

## 28. Отложенные вопросы

### Исторические ТО

Не изменять `historical_data` без отдельного решения.

Исходный workflow требует отдельного процесса ввода исторических данных.

### Files

Сначала общий file contract, затем подключение к сущностям.

### S3

Production S3 подключать после стабилизации file abstraction.

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
