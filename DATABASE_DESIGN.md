# DATABASE_DESIGN.md --- База данных РЗА

## 1. Назначение

Документ фиксирует актуальную согласованную доменную модель RZAdb на
текущем этапе.

``` text
Холдинг
└── Филиал
    └── Производственное отделение (ПО)
        └── Подстанция
            └── Присоединение
                └── УРЗА
```

Домены уровня ПС: схемы селективности, инструкции по РЗА, инспекции ПС.

## 2. Общие правила

Основные сущности используют UUID PK и audit/soft-delete поля: `id`,
`created_at`, `created_by`, `updated_at`, `updated_by`, `deleted_at`,
`deleted_by`.

Архивируемые объекты физически не удаляются. Каскадное архивирование
родителя затрагивает потомков. При восстановлении нужно вернуть
состояние ветки до каскадного архивирования; простого обнуления
`deleted_at` недостаточно.

UUID --- UUID7. Временные поля --- timezone-aware.

## 3. Enterprise

Одна сущность представляет: - Holding; - Branch; - Production
Department.

Поля: `id`, `type`, `parent_id`, `full_name`, `short_name`, `sap_code`.

Только Production Department может содержать Substation.

## 4. User

Поля: `id`, `full_name`, `initials`, `role`, `email`, `password_hash`,
`enterprise_id`, `access_category`, `sap_code` nullable, `active`.

Аутентификация --- email + password. Регистрация пользователей в первой
версии не предусмотрена.

Роли: Superadmin, Admin, Specialist, Manager, Engineer.

Привязка: - Specialist → Holding или Branch; - Admin/Manager/Engineer →
Production Department; - Superadmin → без enterprise binding.

Access category: I--IV.

## 5. Substation

Поля: - `id` - `enterprise_id` → Production Department -
`highest_voltage` - `dispatch_name` - `sap_code` nullable -
`asureo_code` nullable - `latitude` nullable - `longitude` nullable -
`address` nullable

Напряжения: 500, 220, 110, 35, 10, 6, 0.4 кВ.

SAP/ASUREO могут отсутствовать.

**Открытый вопрос:** точная область уникальности SAP/ASUREO.

## 6. Connection

Поля: - `id` - `substation_id` - `dispatch_name` - `sap_code` nullable -
`asureo_code` nullable - `rdu_subordination` -
`operational_current_type`

Типы тока: постоянный, выпрямленный, переменный.

Dispatch name Connection уникален в пределах Production Department. Одно
присоединение может содержать любое количество УРЗА.

## 7. URZA

Поля: - `id` - `connection_id` - `dispatch_name` - `rdu_subordination` -
`inventory_number` nullable - `commissioning_date` - `status` -
`element_base` - `category` - `room_category` - `complexity` -
вычисляемый `title` - вычисляемый `maintenance_period`

Статусы: in_operation, in_repair, decommissioned, reserve. Element base:
electromechanical, microelectronic, microprocessor. Категории: I--IV.
Категории помещения: I--III.

Dispatch name уникален внутри Connection. `complexity` не влияет на
период ТО. Для сложной УРЗА обязательны программы всех трёх типов.

### Title

`Холдинг + Филиал + ПО + ПС + Присоединение + УРЗА`. Не редактируется.

### Период ТО

Зависит от room category + element base. Используется
`MaintenancePeriodRule`: - id - room_category - element_base -
maintenance_period_years

После 25 лет UI показывает необходимость решения о продлении/замене.

## 8. ОТД

Один `OTD` на URZA:

``` text
OTD → OTDVersion
```

`urza_id` UNIQUE.

Версия --- полный снимок и содержит технические поля ОТД, назначение
РЗ/СА/ПА/РА, дату, автора и номер версии.

Скан/редактируемый файл/отдельная подпись не требуются. Старые версии
сохраняются.

## 9. Уставки

Один `SettingsForm` на URZA, `urza_id` UNIQUE.

`SettingsRecord`: - id - settings_form_id - change_date -
parameter_name - initial_setting - new_setting - change_reason -
created_by - created_at - signed_form_file_id - task_id nullable

Каждая запись содержит только изменённые параметры. Скан подписанного
формуляра обязателен. Отдельный протокол не формируется.

## 10. Схемы

Один `SchemaForm` на URZA, `urza_id` UNIQUE. Текущий тип ---
Исполнительная.

`SchemaRecord`: - id - schema_form_id - schema_number - schema_name -
change_description - change_justification - upload_date - created_by -
scan_file_id - editable_file_id - signed_form_file_id - task_id nullable

Текущий комплект: скан, editable-схема, подписанный формуляр. История
сохраняется.

### Селективность ПС

Отдельный домен уровня ПС: скан, editable-файл, история. Детальная
модель пока не финализирована.

## 11. Инструкция по РЗА

Отдельный домен уровня ПС:

``` text
RZAInstruction → RZAInstructionVersion
```

`RZAInstruction.substation_id` UNIQUE.

Версия: - id - rza_instruction_id - version_number - effective_date -
change_description nullable - change_justification nullable -
created_at - created_by - scan_file_id - editable_file_id nullable

Правила: - одна логическая инструкция на ПС; - новая редакция = новая
версия; - старые версии сохраняются; - signed form не требуется.

**Статус:** модели `RZAInstruction` и `RZAInstructionVersion` уже
существуют в текущем коде. Editable-файл в текущей реализации nullable.
Не создавать модели повторно без необходимости.

## 12. Инструкция УРЗА

``` text
URZAInstructionForm → URZAInstructionRecord
```

Один контейнер на URZA.

Record: - id - urza_instruction_form_id - version_number -
effective_date - change_description nullable - change_justification
nullable - upload_date - created_by - scan_file_id - editable_file_id -
task_id nullable

Новые версии сохраняются. При создании из Task `task_id` устанавливается
автоматически.

## 13. ТО

`TORecord` = одно фактическое мероприятие.

Типы: - В - К - К1 - Н - Т - ТК - О - ОСМ - ВП - ПП

Основные поля: `urza_id`, `historical_data`, `maintenance_date`,
`maintenance_type`, `detected_deviations`, `measures_taken`, author,
protocol files, `signed_form_file_id`, `task_id`.

Правила: - signed form обязателен; - для требующих типов протокол
обязателен; - для ТК, О, ОСМ протокол не нужен; - deviations default =
`Не выявлено`; - measures default = `Не требуется`.

Планирование ТО не входит в MVP. `planned_maintenance_date` ---
вычисляемый/выходной показатель.

## 14. Программы

`Program` связана с URZA.

Типы: - commissioning; - decommissioning; - work.

Поля: `id`, `urza_id`, `program_type`, `program_number`, `scan_file_id`,
`editable_file_id` nullable, `task_id` nullable.

Скан обязателен. Editable nullable. `program_number` --- внешний номер.
Signed form отдельно не нужен. Для сложной URZA нужны все три типа.
Удаление после подтверждения; Superadmin может удалить напрямую.

## 15. File

`File` хранит метаданные: - id - s3_key - original/display name -
extension - size - mime_type - uploaded_at - audit fields

Контент --- S3-compatible storage. Домены используют явные FK.
Полиморфный owner не используется.

При удалении нужно корректно удалить/переместить S3-объект и не оставить
orphan DB records.

## 16. Task

Одно задание = один тип работы с одной URZA.

Типы: - OTD - SETTINGS - SCHEMES - MAINTENANCE - PROGRAM

`maintenance_type` обязателен только для MAINTENANCE.

Workflow:

``` text
CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED
```

Дополнительно: - ASSIGNED → REJECTED; - UNDER_REVIEW → IN_PROGRESS.

Причина обязательна при REJECTED и возврате на доработку. После возврата
--- сразу IN_PROGRESS.

Срок выполнения --- 7 дней от создания. Acceptance deadline --- 1 день
от назначения. Продление отсутствует. Переназначение не меняет основной
deadline.

Просроченность --- состояние, не отдельный workflow-статус.

Title формируется автоматически из ПС/присоединения/УРЗА и содержания
работы.

## 17. TaskHistory

Неизменяемая история: - id - task_id - event_type - old_status -
new_status - actor_id - comment - created_at

Фиксирует создание, назначения, переназначения, принятие, отклонение,
начало работы, просрочку, выполнение, доработку, возврат, подтверждение,
закрытие и удаление ошибочного Task.

## 18. Связь Task с результатом

Доменные записи имеют nullable `task_id`.

Из задания → связь устанавливается автоматически. Вне задания → NULL.

Перед COMPLETED система проверяет комплектность результата по типу
работы и типу ТО.

Точная автоматическая проверка каждого типа пока требует окончательной
фиксации.

## 19. Инспекции ПС

Отдельный домен уровня Substation:

``` text
Substation
├── InspectionTask
│   └── InspectionHistory
└── Inspection
```

InspectionTask: - id - substation_id - created_by - assigned_to -
status - created_at - assigned_at - acceptance_deadline_at -
deadline_at - completed_at - closed_at

Inspection: - id - substation_id - inspection_task_id UNIQUE -
inspection_date - remarks - scan_file_id nullable - editable_file_id
nullable - created_by - created_at - updated_at

Workflow:
`CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED`
плюс `ASSIGNED → REJECTED` и `UNDER_REVIEW → IN_PROGRESS`.

Исполнитель: Engineer или Manager. Reviewer: Manager того же Production
Department. Нельзя проверять собственную инспекцию.

Обязательны `inspection_date` и `remarks`. Файлы необязательны. Причина
обязательна при reject/return.

**Статус:** модели, workflow, repository/service и integration tests уже
реализованы. Последний известный результат: **121 passed**.

## 20. Notification

Планируемая модель: - id - user_id - type - title - message - task_id
nullable - created_at - read_at nullable

`read_at = NULL` → непрочитано. После просмотра запись сохраняется.

Email: новое задание, напоминания, просрочка, непринятое задание,
действия руководителя. Статистические рассылки --- второй этап.

## 21. Архивирование и удаление

Для архивируемых ПС/Connection/URZA --- soft delete. Восстановление
должно учитывать состояние до каскадного архивирования.

Task: - ошибочно созданный можно удалить до начала работы; - после
IN_PROGRESS физическое удаление запрещено; - закрытые сохраняются; -
удаление фиксируется в истории.

## 22. Storage lifecycle и backup

Предусмотрены: - backup PostgreSQL; - защита/backup файлов; - hot
storage; - cold storage; - hot → cold; - cold → hot при обращении.

Единый сервис lifecycle, контроль целостности, retry и правила
восстановления ещё требуют реализации/фиксации.

## 23. Текущее состояние проекта

На текущем этапе известны реализованные домены: - Enterprise; -
Substation; - Connection; - URZA; - OTD; - User; -
SettingsForm/SettingsRecord; - File; - Task; - TaskHistory; - OTD ↔
Task; - Inspection; - InspectionTask; - InspectionHistory; - inspection
workflow; - RZAInstruction / RZAInstructionVersion models.

Последний известный результат тестов: **121 passed**.

## 24. Открытые вопросы

1.  Область уникальности SAP/ASUREO.
2.  Детальная модель селективности ПС.
3.  Точное восстановление состояния после каскадного archive.
4.  Полная автоматическая проверка комплектности Task.
5.  Удаление исторических записей формуляров.
6.  Полная реализация URZAInstruction.
7.  Lifecycle hot/cold S3.
8.  cold → hot restore.
9.  Будущие типы схем/программ.
10. Статистические email-рассылки второго этапа.

## 25. Ближайший порядок работ

Не создавать повторно уже существующие модели.

Для каждого незавершённого домена проверять:

``` text
model → migration → registration → repository → service → tests
```

Приоритет MVP: 1. AccessService и права. 2. Оставшиеся services. 3.
Автоматическая проверка результата Task. 4. File/S3 service. 5. Jinja2 +
HTMX UI. 6. Notifications/email. 7. Backup и hot/cold storage. 8.
Селективность ПС. 9. Остальные открытые вопросы.
