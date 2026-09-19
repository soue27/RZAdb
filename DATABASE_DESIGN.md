# DATABASE_DESIGN.md — RZAdb / База Данных РЗА

## 1. Назначение
RZAdb — база и веб-приложение для учёта оборудования РЗА, подстанций, присоединений, УРЗА, технической документации, формуляров, уставок, схем, ТО, программ, инструкций, инспекций и задач.

Документ фиксирует согласованные решения. Новые сущности/поля не добавлять без отдельного доменного решения.

## 2. Иерархия
```text
Holding
└── Branch
    └── Production Department
        └── Substation
            └── Connection
                └── URZA
```
`Enterprise` представляет Holding, Branch или Production Department и использует `parent_id`.

## 3. Enterprise
Таблица `enterprises`:
```text
id, type, parent_id, full_name, short_name, sap_code,
created_at, updated_at, deleted_at, deleted_by
```
Типы: `HOLDING`, `BRANCH`, `DEPARTMENT`.

## 4. Substation
Таблица `substations`:
```text
id, enterprise_id, highest_voltage, dispatch_name,
sap_code, asureo_code, latitude, longitude, address,
created_at, updated_at, deleted_at, deleted_by
```
`enterprise_id` → Production Department.
Высшее напряжение: `500, 220, 110, 35, 10, 6, 0.4`.

## 5. Connection
Таблица `connections`:
```text
id, substation_id, dispatch_name, sap_code, asureo_code,
rdu_subordination, operational_current_type,
created_at, updated_at, deleted_at, deleted_by
```
Оперативный ток: `PERMANENT | RECTIFIED | ALTERNATING`.

## 6. URZA
Таблица `urzas`:
```text
id, connection_id, dispatch_name, rdu_subordination,
inventory_number, commissioning_date, status, element_base,
category, room_category, complexity,
created_at, updated_at, deleted_at, deleted_by
```
Статусы: `IN_OPERATION | IN_REPAIR | DECOMMISSIONED | RESERVE`.
База: `ELECTROMECHANICAL | MICROELECTRONIC | MICROPROCESSOR`.
Категория УРЗА: `I | II | III | IV`.
Категория помещения: `I | II | III`.
Инвентарный номер nullable.

## 7. Users
Минимальные поля:
```text
id, full_name, email, password_hash, role, enterprise_id,
access_category, active, created_at, updated_at, deleted_at, deleted_by
```
Роли: `SUPERADMIN | ADMIN | SPECIALIST | MANAGER | ENGINEER`.
Привязка: SUPERADMIN без enterprise binding; SPECIALIST — Holding/Branch; ADMIN/MANAGER/ENGINEER — Department.

## 8. AccessService
Доступ централизован:
```text
can_access_enterprise()
can_access_substation()
can_access_connection()
can_access_urza()
get_accessible_enterprise_roots()
```
Корни дерева: SUPERADMIN → Holding roots; SPECIALIST → bound Holding/Branch; ADMIN/MANAGER/ENGINEER → bound Department.
Пользователь не видит уровни выше своей границы.

## 9. Soft delete
Основные сущности используют `deleted_at` и `deleted_by`. Обычные active queries исключают `deleted_at IS NOT NULL`. Архивирование не означает физическое удаление.

## 10. TreeService
DTO:
```text
EnterpriseTreeNode
├── id
├── type
├── full_name
├── short_name
├── children[]
└── substations[]

SubstationTreeNode
├── id
├── dispatch_name
└── connections[]

ConnectionTreeNode
├── id
├── dispatch_name
└── urzas[]

URZATreeNode
├── id
└── dispatch_name
```
Алгоритм: корни через AccessService → active Enterprise → ПС → Connection → URZA → DTO.
Сортировка: Enterprise по `full_name`; Substation/Connection/URZA по `dispatch_name`.
Текущая реализация загружает active Enterprise и фильтрует потомков в памяти. Для MVP допустимо; при росте данных оптимизировать.

## 11. Repository API
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
Repository отвечает за доступ к данным, не за UI.

## 12. Versioning
Версионируемые документы не перезаписывать:
```text
current version
      ↓
new version
      ↓
old version remains in history
```
Для ОТД старая версия становится исторической, новая — текущей.

## 13. Формуляр
Формуляр — логическая группировка. ОТД имеет текущую версию и историю. ОТД, Уставки, Схемы, ТО и Программы — один логический уровень под URZA.

## 14. ОТД
`OTDPurpose`: `RZA | SA | PA | RA`. Подпись для ОТД не обязательна.

## 15. ТО
Типы: `В | К | К1 | Н | Т | ТК | О | ОСМ | ВП | ПП`.
Подписанная форма/скан обязательна. Плановая дата ТО хранится для последующего микросервиса.

## 16. Программы
Типы: `COMMISSIONING | DECOMMISSIONING | WORK`.
Сканы хранятся в object storage и доступны для просмотра/скачивания.

## 17. Tasks
Типы работ: `OTD | SETTINGS | SCHEMES | MAINTENANCE | PROGRAM`.
Статусы: `CREATED | ASSIGNED | IN_PROGRESS | COMPLETED | UNDER_REVIEW | CLOSED | REJECTED`.
Активные в UI: `ASSIGNED | IN_PROGRESS | UNDER_REVIEW`.
Инспекции ПС — отдельный процесс, не обычная Task.

## 18. Files
Бинарные файлы не хранить в PostgreSQL. Использовать S3-compatible storage.
Не использовать универсальную полиморфную связь `File(owner_type, owner_id)`. Использовать явные связи с доменными сущностями.

## 19. Аудит
Аудит обязателен для критических операций: права; критические данные РЗА; версии документов; архивирование/восстановление; загрузка/замена документов; изменение статусов задач. Аудит не зависит от UI.

## 20. Индексы и ограничения
Индексы создавать исходя из реальных запросов: foreign keys, `deleted_at` в active queries, search fields, поля уникальности, часто используемые фильтры.
SAP/ASUREO не делать глобально уникальными без отдельного доменного решения.

## 21. Транзакции
Одна бизнес-операция атомарна. Например новая версия:
```text
BEGIN
  old → historical
  new → current
  metadata update
COMMIT
```

## 22. Миграции
Alembic находится в `migrations/`. После изменения модели: создать migration → проверить → применить → прогнать тесты.

## 23. Текущий статус
Реализованы: AccessService, EnterpriseRepository, SubstationRepository, ConnectionRepository, URZARepository, TreeService, Tree DTO.

`tests/application/tree/test_service.py` содержит 4 зелёных теста:
1. SUPERADMIN — полное дерево;
2. ENGINEER — дерево от своего Department;
3. SPECIALIST — дерево от своего Branch;
4. архивные Enterprise/Substation исключаются.

## 24. Следующий этап
```text
TreeService
→ FastAPI dependency/route
→ Jinja/HTMX
→ реальный sidebar
```
Затем: выбор объекта, карточка, поиск, раскрытие пути, HTMX-обновления.
