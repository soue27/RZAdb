# DATABASE_DESIGN.md --- База данных РЗА

## 1. Назначение

Документ фиксирует актуальную согласованную доменную модель RZAdb и
принятые архитектурные решения.

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

Отдельные домены уровня ПС: схемы селективности, инструкции по РЗА,
инспекции ПС.

## 2. Общие правила

-   Основные сущности используют UUID PK.
-   UUID --- UUID7 через `uuid6.uuid7`.
-   Временные поля --- timezone-aware.
-   Где предусмотрено моделью, используются audit/soft-delete поля:
    `created_at`, `created_by`, `updated_at`, `updated_by`,
    `deleted_at`, `deleted_by`.
-   Архивируемые объекты физически не удаляются там, где предусмотрен
    soft delete.
-   Каскадное архивирование родителя затрагивает потомков. При
    восстановлении необходимо вернуть состояние ветки до каскадного
    архивирования; простого обнуления `deleted_at` недостаточно.
-   Бизнес-правила находятся в application/domain services, а не в
    Jinja-шаблонах или роутерах.
-   Доступ централизован через `AccessService`.
-   Не добавлять сущности и поля без отдельного доменного решения.

## 3. Enterprise

Одна сущность представляет: - Holding; - Branch; - Production
Department.

Поля: `id`, `type`, `parent_id`, `full_name`, `short_name`, `sap_code`.

Только Production Department может содержать Substation.

## 4. User и аутентификация

Поля `User`:

-   `id`
-   `full_name`
-   `role`
-   `email`
-   `password_hash`
-   `enterprise_id`
-   `access_category`
-   `sap_code` nullable
-   `active`
-   стандартные soft-delete/audit поля, где применяются

Аутентификация: - email + password; - регистрации пользователей в первой
версии нет; - пароль хранится только в виде хеша; - для хеширования
используется `pwdlib[argon2]`.

Роли: - Superadmin; - Admin; - Specialist; - Manager; - Engineer.

Привязка: - Specialist → Holding или Branch; - Admin/Manager/Engineer →
Production Department; - Superadmin → без enterprise binding.

Access category: I--IV.

### Архитектура аутентификации

Для MVP и рабочего внутреннего продукта согласован вариант **A ---
подписанная cookie-сессия**.

Принцип:

``` text
Browser
   │
   │ signed session cookie
   ▼
FastAPI
   │
   ├── проверка подписи
   ├── получение user_id
   └── загрузка User из PostgreSQL
             │
             ▼
       AccessService
```

В cookie не хранить: - пароль; - password_hash; - права как источник
истины; - enterprise binding как источник истины.

Cookie должна быть настроена с: - `HttpOnly`; - `SameSite=Lax`; -
`Secure=True` при HTTPS; - секретом приложения из `.env`, не хранящимся
в Git.

Механизм сессии не должен быть связан с `AuthService` и `AccessService`,
чтобы при необходимости позднее можно было перейти на server-side
sessions, AD/LDAP или SSO без переписывания бизнес-логики.

Текущее состояние: - `UserRepository.get_by_email()` реализован; -
`PasswordService` реализован; - `AuthService.authenticate()`
реализован; - проверяются неизвестный email, неверный пароль,
`active=False` и `deleted_at`; - тесты authentication application layer:
**7 passed**; - HTTP login/logout и session middleware ещё не
реализованы.

## 5. AccessService

`AccessService` --- единая точка проверки доступа к
enterprise/substation/connection/URZA.

Правила: - неизвестный, неактивный или архивированный пользователь не
получает доступ; - неизвестный/архивированный enterprise не доступен; -
Superadmin имеет полный доступ; - пользователь без enterprise binding не
получает обычный enterprise-scoped доступ; - Admin/Manager/Engineer
работают в пределах своего Production Department; - Specialist работает
в пределах своего Holding/Branch и подчинённых объектов.

Реализованы и протестированы: - `can_access_enterprise`; -
`can_access_substation`; - `can_access_connection`; - `can_access_urza`.

Известно: **39 тестов AccessService**.

## 6. Substation

Поля: - `id`; - `enterprise_id` → Production Department; -
`highest_voltage`; - `dispatch_name`; - `sap_code` nullable; -
`asureo_code` nullable; - `latitude` nullable; - `longitude` nullable; -
`address` nullable.

Напряжения: 500, 220, 110, 35, 10, 6, 0.4 кВ.

SAP/ASUREO могут отсутствовать.

Открытый вопрос: точная область уникальности SAP/ASUREO.

### Будущие схемы подстанции

После MVP необходимо отдельно рассмотреть сущность **«Схемы
подстанции»**, относящуюся непосредственно к Substation.

Согласованные свойства: - может отсутствовать; - может быть несколько
схем; - фиксированной классификации или обязательного назначения пока
нет; - это **не** `SchemaForm`, поскольку `SchemaForm` относится к
URZA; - это отдельный TODO и сейчас не реализуется.

## 7. Connection

Поля: - `id`; - `substation_id`; - `dispatch_name`; - `sap_code`
nullable; - `asureo_code` nullable; - `rdu_subordination`; -
`operational_current_type`.

Типы оперативного тока: - permanent; - rectified; - alternating.

Dispatch name Connection уникален в пределах Production Department.

Одно присоединение может содержать любое количество УРЗА.

## 8. URZA

Поля: - `id`; - `connection_id`; - `dispatch_name`; -
`rdu_subordination`; - `inventory_number` nullable; -
`commissioning_date`; - `status`; - `element_base`; - `category`; -
`room_category`; - `complexity`; - вычисляемый `title`; - вычисляемый
`maintenance_period`.

Статусы: - in_operation; - in_repair; - decommissioned; - reserve.

Element base: - electromechanical; - microelectronic; - microprocessor.

Категории УРЗА: I--IV. Категории помещения: I--III.

Dispatch name уникален внутри Connection.

`complexity` не влияет на период ТО.

Для сложной УРЗА обязательны программы всех трёх типов.

### Title

`Холдинг + Филиал + ПО + ПС + Присоединение + УРЗА`.

Title не редактируется.

### Период ТО

Зависит от `room_category + element_base`.

Используется `MaintenancePeriodRule`, а не hard-coded `if/else`.

После 25 лет UI показывает необходимость решения о продлении/замене.

## 9. ОТД

Один `OTD` на URZA:

``` text
OTD
└── OTDVersion
```

`urza_id` UNIQUE.

Каждая версия --- полный снимок.

Версия содержит технические поля ОТД, назначение РЗ/СА/ПА/РА, дату и
номер версии.

Скан, editable-файл и отдельная подпись не требуются.

Старые версии сохраняются.

Реализованы: - model; - repository; - service; - tests.

## 10. Уставки

Один `SettingsForm` на URZA, `urza_id` UNIQUE.

`SettingsRecord`: - `id`; - `settings_form_id`; - `change_date`; -
`parameter_name`; - `initial_setting`; - `new_setting`; -
`change_reason`; - `created_by`; - `created_at`; -
`signed_form_file_id`; - `task_id` nullable.

Каждая запись содержит только изменённые параметры.

Скан подписанного формуляра обязателен.

Отдельный протокол не формируется.

Реализованы repository/service и tests.

## 11. Схемы URZA

Один `SchemaForm` на URZA, `urza_id` UNIQUE.

Текущий тип --- Исполнительная.

`SchemaRecord`: - `id`; - `schema_form_id`; - `schema_number`; -
`schema_name`; - `change_description`; - `change_justification`; -
`upload_date`; - `created_by`; - `scan_file_id`; - `editable_file_id`; -
`signed_form_file_id`; - `task_id` nullable.

Текущий согласованный комплект: - скан; - editable-схема; - подписанный
формуляр.

История сохраняется.

Реализованы repository/service и tests.

### Селективность ПС

Отдельный домен уровня ПС.

Планируется: - скан; - editable-файл; - история/версии.

Детальная модель пока не финализирована.

Это не `SchemaForm`.

## 12. Инструкция по РЗА

Отдельный домен уровня ПС:

``` text
RZAInstruction
└── RZAInstructionVersion
```

`RZAInstruction.substation_id` UNIQUE.

Версия: - `id`; - `rza_instruction_id`; - `version_number`; -
`effective_date`; - `change_description` nullable; -
`change_justification` nullable; - `created_at`; - `created_by`; -
`scan_file_id`; - `editable_file_id` nullable.

Правила: - одна логическая инструкция на ПС; - новая редакция = новая
версия; - старые версии сохраняются; - signed form не требуется.

**Статус: реализовано.** Не создавать модели повторно.

## 13. Инструкция УРЗА

Логический контейнер на URZA:

``` text
URZAInstruction
└── URZAInstructionVersion
```

Один контейнер на URZA.

Версия: - `version_number`; - `effective_date`; - `change_description`
nullable; - `change_justification` nullable; - `created_at`; -
`created_by`; - `scan_file_id`; - `editable_file_id`; - `task_id`
nullable.

Новые версии сохраняются.

При создании из Task `task_id` устанавливается автоматически.

**Статус: реализовано.** Не создавать повторно уже существующие модели.

## 14. ТО

`TORecord` = одно фактическое мероприятие.

Типы: - В; - К; - К1; - Н; - Т; - ТК; - О; - ОСМ; - ВП; - ПП.

Основные поля: - `urza_id`; - `historical_data`; - `maintenance_date`; -
`maintenance_type`; - `detected_deviations`; - `measures_taken`; -
`created_by`; - protocol files; - `signed_form_file_id`; - `task_id`
nullable.

Правила: - signed form обязателен; - протокол обязателен для требующих
типов; - для ТК, О, ОСМ протокол не нужен; - `detected_deviations` по
умолчанию `Не выявлено`; - `measures_taken` по умолчанию `Не требуется`.

Планирование ТО не входит в MVP.

`planned_maintenance_date` --- выходной/вычисляемый показатель.

Repository/service/tests реализованы.

Открытый технический TODO: при создании результата дополнительно
валидировать, что `task_id` относится к той же URZA.

## 15. Программы

`Program` связана с URZA.

Типы: - commissioning; - decommissioning; - work.

Поля: - `id`; - `urza_id`; - `program_type`; - `program_number`; -
`scan_file_id`; - `editable_file_id` nullable; - `task_id` nullable.

Скан обязателен.

Editable nullable.

`program_number` --- внешний номер.

Signed form отдельно не нужен.

Для сложной URZA нужны все три типа.

Repository/service/tests реализованы.

## 16. File и Object Storage

`File` хранит метаданные: - `id`; - `s3_key`; - `original_name`; -
`display_name`; - `extension`; - `size`; - `mime_type`; -
`uploaded_at`; - audit/soft-delete поля.

Фактическое содержимое файла не хранится в PostgreSQL.

Домены используют явные FK: - `scan_file_id`; - `editable_file_id`; -
`signed_form_file_id`; - и т. п.

Полиморфный `File(owner_type, owner_id)` не используется.

### ObjectStorage abstraction

Файловое хранилище отделено от `FileService` интерфейсом
`ObjectStorage`:

``` text
ObjectStorage
├── LocalObjectStorage        ← текущая реализация
└── YandexS3ObjectStorage     ← будущая реализация
```

Согласованное решение: - S3-compatible storage остаётся целевой
production-моделью; - **не ждём покупки/настройки S3 для разработки**; -
локальное хранилище используется сейчас для dev/tests; - позже
добавляется Yandex S3 без изменения `FileService`; - PostgreSQL хранит
только метаданные файла; - hot/cold storage не меняет `File.id` и
доменную сущность.

Локальное хранилище: - dev/test: `data/uploads/`; - защищено от path
traversal; - ключи генерируются приложением.

`FileService` реализует: - upload; - download; - archive.

Архивирование файла: - не удаляет запись `File`; - выставляет
`deleted_at`; - сохраняет `deleted_by`.

Текущие repository/service/integration tests реализованы.

Известно: после реализации file upload/download и transaction lifecycle
полный suite достиг **311 passed**.

## 17. Task

Одно задание = один тип работы с одной URZA.

Типы: - OTD; - SETTINGS; - SCHEMES; - MAINTENANCE; - PROGRAM.

`maintenance_type` обязателен только для MAINTENANCE.

Workflow:

``` text
CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED
```

Дополнительно: - ASSIGNED → REJECTED; - UNDER_REVIEW → IN_PROGRESS.

Причина обязательна при REJECTED и возврате на доработку.

После возврата --- сразу IN_PROGRESS.

Срок выполнения --- 7 дней от создания.

Acceptance deadline --- 1 день от назначения.

Продление отсутствует.

Переназначение не меняет основной deadline.

Просроченность --- состояние, а не отдельный workflow-статус.

Title формируется автоматически из ПС/присоединения/УРЗА и содержания
работы.

Workflow и основные сервисы реализованы.

## 18. Результат Task

Нельзя завершить Task только изменением статуса.

Перед `COMPLETED` `TaskService` проверяет наличие необходимого
результата в зависимости от `work_type`, а для ТО --- также от
`maintenance_type`.

Связи: - из задания → `task_id` устанавливается автоматически; - вне
задания → `task_id = NULL`.

Остаётся технический TODO: при создании результата дополнительно
проверять соответствие `task_id` и `urza_id`.

## 19. TaskHistory

Неизменяемая история: - `task_id`; - `event_type`; - `old_status`; -
`new_status`; - `actor_id`; - `comment`; - `created_at`.

Фиксируются: - создание; - назначения; - переназначения; - принятие; -
отклонение; - начало работы; - просрочка; - выполнение; - доработка; -
возврат; - подтверждение; - закрытие; - удаление ошибочного задания.

## 20. Инспекции ПС

Инспекция --- отдельный домен уровня Substation и не является обычным
Task.

``` text
Substation
├── InspectionTask
│   └── InspectionHistory
└── Inspection
```

`InspectionTask`: - `substation_id`; - `created_by`; - `assigned_to`; -
`status`; - `created_at`; - `assigned_at`; - `acceptance_deadline_at`; -
`deadline_at`; - `completed_at`; - `closed_at`.

`Inspection`: - `substation_id`; - `inspection_task_id` UNIQUE; -
`inspection_date`; - `remarks`; - `scan_file_id` nullable; -
`editable_file_id` nullable; - `created_by`; - `created_at`; -
`updated_at`.

Workflow:
`CREATED → ASSIGNED → IN_PROGRESS → COMPLETED → UNDER_REVIEW → CLOSED`

Дополнительно: - ASSIGNED → REJECTED; - UNDER_REVIEW → IN_PROGRESS.

Исполнитель: Engineer или Manager.

Reviewer: Manager того же Production Department.

Нельзя проверять собственную инспекцию.

Обязательны `inspection_date` и `remarks`.

Файлы необязательны.

Причина обязательна при reject/return.

**Статус: реализовано.** Реализованы модели, workflow,
repository/service и integration tests.

## 21. Notification

Модель уведомлений запланирована, но не является завершённым
MVP-доменом.

Планируемые поля: - `id`; - `user_id`; - `type`; - `title`; -
`message`; - `task_id` nullable; - `created_at`; - `read_at` nullable.

Email-уведомления планируются после основной UI/auth части.

Статистические email-рассылки --- второй этап.

## 22. Архивирование и удаление

Для архивируемых Substation/Connection/URZA используется soft delete.

Каскадное архивирование должно сохранять состояние потомков до операции.

Task: - ошибочно созданный можно удалить до начала работы; - после
IN_PROGRESS физическое удаление запрещено; - закрытые задания
сохраняются; - удаление фиксируется в истории; - Superadmin имеет полный
доступ.

Для File используется архивирование через `deleted_at`/`deleted_by`.

HTTP endpoint для архивирования File будет защищён аутентификацией
текущего пользователя; реализация ещё не завершена.

## 23. Storage lifecycle и backup

Предусмотрены: - backup PostgreSQL; - backup файлов; - hot storage; -
cold storage; - hot → cold; - cold → hot при обращении.

Единый lifecycle-сервис, контроль целостности, retry и правила
восстановления ещё требуют реализации/фиксации.

## 24. Текущее состояние проекта

Реализованы модели и/или application services для: - Enterprise; -
Substation; - Connection; - URZA; - MaintenancePeriodRule; - User; -
AccessService; - OTD / OTDVersion; - SettingsForm / SettingsRecord; -
SchemaForm / SchemaRecord; - RZAInstruction / RZAInstructionVersion; -
URZAInstruction / URZAInstructionVersion; - TORecord; - Program; -
File; - Task / TaskHistory; - Inspection / InspectionTask /
InspectionHistory.

Также реализованы: - repository/service layers для основных завершённых
доменов; - task workflow; - task result completeness validation; - local
ObjectStorage; - File upload/download/archive service; - HTTP
upload/download endpoints для File; - application authentication:
UserRepository lookup by email, PasswordService, AuthService.

Текущий известный полный результат: **311 passed**.

`uv run ruff check app` --- зелёный.

Старый технический долг Ruff в существующих тестах может оставаться и не
является частью текущего MVP-блока.

## 25. Открытые вопросы и TODO

1.  Точная область уникальности SAP/ASUREO.
2.  Детальная модель селективности ПС.
3.  **Схемы подстанции** --- отдельная сущность уровня Substation; может
    отсутствовать, может быть много; фиксированной классификации пока
    нет; реализация после MVP.
4.  Точное восстановление состояния после каскадного archive.
5.  Полная автоматическая проверка комплектности всех типов Task.
6.  Проверка соответствия `task_id` и `urza_id` при создании
    результатов.
7.  Удаление/архивирование исторических записей формуляров по отдельным
    правилам.
8.  Yandex S3 object storage.
9.  Lifecycle hot/cold storage.
10. cold → hot restore.
11. Backup/recovery policy.
12. Будущие типы схем/программ --- только после отдельного доменного
    решения.
13. Notifications/email.
14. HTTP login/logout и session middleware.
15. Возможная интеграция AD/LDAP/SSO в будущем.
16. Статистические email-рассылки второго этапа.

## 26. Порядок работ MVP

Актуальный порядок:

1.  Authentication:
    -   session middleware;
    -   login/logout;
    -   `current_user`;
    -   защита HTTP routes.
2.  AccessService integration в HTTP/UI.
3.  Оставшиеся application services и result validation.
4.  HTTP File archive/delete через `current_user`.
5.  Jinja2 + HTMX UI.
6.  Notifications/email.
7.  Yandex S3 и production storage lifecycle.
8.  Backup и hot/cold storage.
9.  Детальная селективность ПС.
10. Остальные открытые вопросы.

Для каждого незавершённого домена:

``` text
model → migration → registration → repository → service → tests → API/UI
```

Не создавать повторно уже существующие модели.

------------------------------------------------------------------------
