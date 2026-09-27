# DATABASE_DESIGN.md — RZAdb / База Данных РЗА

## 1. Назначение

RZAdb — база и веб-приложение для учёта оборудования РЗА, подстанций, присоединений, УРЗА, технической документации, формуляров, уставок, схем, ТО, программ, инструкций, осмотров и задач.

Документ фиксирует согласованные доменные и архитектурные решения.

**Новые сущности, поля, связи и бизнес-правила не добавлять без отдельного доменного решения.**

---

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

---

## 3. Enterprise

Таблица `enterprises` концептуально содержит:

```text
id
type
parent_id
full_name
short_name
sap_code
audit fields
```

Типы:

```text
HOLDING
BRANCH
DEPARTMENT
```

---

## 4. Substation

Таблица `substations`:

```text
id
enterprise_id
highest_voltage
operational_current_type
dispatch_name
sap_code
asureo_code
latitude
longitude
address
audit fields
```

`enterprise_id` → Production Department.

Высшее напряжение:

```text
500
220
110
35
10
6
0.4
```

---

## 5. Connection

Таблица `connections`:

```text
id
substation_id
dispatch_name
sap_code
asureo_code
rdu_subordination
operational_current_type
audit fields
```

Оперативный ток:

```text
PERMANENT
RECTIFIED
ALTERNATING
```

Не добавлять дополнительные поля без доменного решения.

---

## 6. URZA

Таблица `urzas`:

```text
id
connection_id
dispatch_name
rdu_subordination
inventory_number
commissioning_date
status
element_base
category
room_category
complexity
audit fields
```

Статусы:

```text
IN_OPERATION
IN_REPAIR
DECOMMISSIONED
RESERVE
```

База:

```text
ELECTROMECHANICAL
MICROELECTRONIC
MICROPROCESSOR
```

Категория УРЗА:

```text
I
II
III
IV
```

Категория помещения:

```text
I
II
III
```

`inventory_number` nullable.

УРЗА II обслуживается персоналом категорий II, III, IV.

---

## 7. Users

Минимальная концептуальная структура:

```text
id
full_name
email
password_hash
role
enterprise_id
access_category
active
audit fields
```

Роли:

```text
SUPERADMIN
ADMIN
SPECIALIST
MANAGER
ENGINEER
```

Привязка:

```text
SUPERADMIN → без enterprise binding
SPECIALIST → Holding/Branch
ADMIN/MANAGER/ENGINEER → Department
```

---

## 8. AccessService

Доступ централизован:

```text
can_access_enterprise()
can_access_substation()
can_access_connection()
can_access_urza()
get_accessible_enterprise_roots()
```

Корни дерева:

```text
SUPERADMIN → Holding roots
SPECIALIST → bound Holding/Branch
ADMIN/MANAGER/ENGINEER → bound Department
```

Пользователь не видит уровни выше своей границы.

---

## 9. Soft delete

Основные сущности используют:

```text
deleted_at
deleted_by
```

Обычные active queries исключают:

```sql
deleted_at IS NOT NULL
```

Архивирование не означает физическое удаление.

---

## 10. Универсальный аудит

Принято направление к единому набору audit-полей для моделей:

```text
created_at
created_by
updated_at
updated_by
deleted_at
deleted_by
```

Смысл:

| Поле | Назначение |
|---|---|
| `created_at` | время создания |
| `created_by` | пользователь, создавший запись |
| `updated_at` | время последнего изменения |
| `updated_by` | пользователь, последним изменивший запись |
| `deleted_at` | время soft delete/архивирования |
| `deleted_by` | пользователь, выполнивший soft delete |

### Архитектурный принцип

Audit-поля должны предоставляться централизованно базовыми mixins и не дублироваться вручную в каждой модели.

Целевой подход:

```text
UUIDMixin
TimestampMixin
SoftDeleteMixin
```

где audit-поля распределены между базовыми mixins.

Точная реализация FK, nullable/NOT NULL и способ автоматического заполнения `created_by`/`updated_by` ещё требуют реализации после отдельного анализа.

### Важное ограничение

Нельзя придумывать автора старых записей.

Если существующие записи не содержат исторического автора, миграция должна иметь явно согласованную стратегию:

```text
unknown / NULL / system actor / другое решение
```

Выбор стратегии — доменное решение пользователя.

---

## 11. Audit критических операций

Аудит обязателен для:

- прав доступа;
- критических данных РЗА;
- версий документов;
- архивирования/восстановления;
- загрузки/замены документов;
- изменения статусов задач.

Аудит не зависит от UI.

---

## 12. TreeService

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

Алгоритм:

```text
AccessService
→ active Enterprise
→ Substation
→ Connection
→ URZA
→ DTO
```

Сортировка:

- Enterprise → `full_name`;
- Substation/Connection/URZA → `dispatch_name`.

Текущая реализация может фильтровать потомков в памяти. Для MVP допустимо; при росте данных оптимизировать.

---

## 13. Repository API

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

Repository отвечает за доступ к данным, а не за UI или бизнес-правила.

---

## 14. Versioning

Версионируемые документы не перезаписывать:

```text
current version
      ↓
new version
      ↓
old version remains in history
```

Для ОТД:

```text
OTD
├── current version
└── historical versions
```

Старая версия остаётся доступной.

---

## 15. Формуляр

Формуляр — логическая группировка.

Под URZA на одном логическом уровне находятся:

```text
ОТД
Уставки
Схемы
ТО
Программы
```

---

## 16. ОТД

`OTDPurpose`:

```text
RZA
SA
PA
RA
```

Для ОТД подпись не обязательна.

ОТД имеет:

```text
current version
historical versions
```

Текущая UI-реализация позволяет выбирать историческую версию через HTMX без полной перезагрузки страницы.

---

## 17. ТО

Типы:

```text
В
К
К1
Н
Т
ТК
О
ОСМ
ВП
ПП
```

Подписанная форма/скан обязательна.

Плановая дата ТО хранится для последующего микросервиса.

---

## 18. Программы

Типы:

```text
COMMISSIONING
DECOMMISSIONING
WORK
```

Сканы хранятся в object storage и доступны для просмотра/скачивания.

---

## 19. Tasks

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

Инспекции/осмотры ПС — отдельный процесс, не обычная Task.

---

## 20. Inspections / Осмотры

**Структура БД не меняется ради изменения названия в UI.**

Существующие domain/application/database сущности `Inspection` и связанные с ними процессы сохраняются.

В пользовательском интерфейсе используется русское отображение:

```text
Осмотры
```

Не создавать отдельную сущность `Inspection` только из-за UI-названия.

---

## 21. Files

Бинарные файлы не хранить в PostgreSQL.

Использовать:

```text
S3-compatible object storage
```

Не использовать универсальную полиморфную связь:

```text
File(owner_type, owner_id)
```

Использовать явные связи файлов с доменными сущностями.

---

## 22. Индексы и ограничения

Индексы создавать исходя из реальных запросов:

- foreign keys;
- `deleted_at` в active queries;
- search fields;
- поля уникальности;
- часто используемые фильтры.

SAP/ASUREO не делать глобально уникальными без отдельного доменного решения.

---

## 23. Уникальность

Доменные ограничения:

- SAP/ASUREO не глобально уникальны без отдельного решения;
- диспетчерское имя подстанции уникально в соответствующей области;
- имя УРЗА уникально внутри присоединения;
- остальные ограничения добавлять только при наличии доменного основания.

---

## 24. Транзакции

Одна бизнес-операция атомарна.

Пример создания новой версии:

```text
BEGIN
  old → historical
  new → current
  metadata update
COMMIT
```

---

## 25. Миграции

Alembic находится в:

```text
migrations/
```

После изменения модели:

```text
изменить model
→ создать migration
→ проверить migration
→ применить migration
→ запустить тесты
```

Для универсального audit-refactor:

```text
inspect current schema
→ согласовать audit contract
→ изменить mixins/models
→ создать migration
→ определить стратегию старых данных
→ применить migration
→ тесты
```

Не создавать migration до согласования структуры изменения.

---

## 26. Текущий статус

На текущем этапе реализованы и проверены:

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
- сохранение состояния раскрытия истории при переключении версии.

Текущая рабочая ветка:

```text
refactor/universal-audit
```

Следующий этап:

```text
исследование текущего audit-состояния
→ проектирование универсального audit contract
→ доменное решение
→ implementation
→ migration
→ tests
```

---

## 27. Основной принцип

База данных отражает согласованную предметную область.

Не добавлять поля «на всякий случай».

Не менять структуру БД ради косметического UI-изменения.

Не дублировать сущности.

Не удалять исторические версии документов.

Не смешивать инфраструктурные детали с доменными правилами.
