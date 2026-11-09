from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.application.connections.repository import ConnectionRepository
from app.application.connections.service import ConnectionService
from app.application.document_templates.service import DocumentTemplateService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.enterprises.service import EnterpriseService
from app.application.feedback.service import FeedbackService
from app.application.files.access_service import FileAccessService
from app.application.files.owner_repository import FileOwnerRepository
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.physical_deletion import PhysicalDeletionService
from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.application.imports.equipment import EquipmentImportService
from app.application.imports.organization import OrganizationImportService
from app.application.inspections.inspection_repository import InspectionRepository
from app.application.inspections.inspection_service import InspectionService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.maintenance.repository import TORecordRepository
from app.application.maintenance.service import TORecordService
from app.application.notifications.repository import TaskNotificationRepository
from app.application.notifications.service import NotificationService
from app.application.objects.archive_repository import ArchiveRepository
from app.application.objects.archive_service import ArchiveService
from app.application.objects.resolver import ObjectResolver
from app.application.objects.service import ObjectService
from app.application.otd.repository import OTDRepository
from app.application.otd.service import OTDService
from app.application.passport_protocol.service import PassportProtocolService
from app.application.programs.repository import ProgramRepository
from app.application.programs.service import ProgramService
from app.application.rza_instructions.repository import RZAInstructionRepository
from app.application.rza_instructions.service import RZAInstructionService
from app.application.schema.repository import SchemaRepository
from app.application.schema.service import SchemaService
from app.application.selectivity_schemes.repository import (
    SelectivitySchemeRepository,
)
from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.application.settings.repository import SettingsRepository
from app.application.settings.service import SettingsService
from app.application.substations.repository import SubstationRepository
from app.application.substations.service import SubstationService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.tasks.statistics import TaskStatisticsService
from app.application.tree.service import TreeService
from app.application.urza_instructions.repository import (
    URZAInstructionRepository,
)
from app.application.urza_instructions.service import URZAInstructionService
from app.application.urzas.repository import URZARepository
from app.application.urzas.service import URZAService
from app.application.users.repository import UserRepository
from app.application.users.service import UserService
from app.application.work_items.service import (
    InspectionTaskWorkItemSource,
    InstructionWorkItemSource,
    MaintenanceWorkItemSource,
    OTDWorkItemSource,
    ProgramWorkItemSource,
    RZAInstructionWorkItemSource,
    SchemaWorkItemSource,
    SelectivitySchemeWorkItemSource,
    SettingsWorkItemSource,
    TaskWorkItemSource,
    WorkItemService,
)
from app.core.config import get_settings
from app.infrastructure.database.session import get_session
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage
"""services: зависимости и DTO presentation-слоя."""

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.access.service import AccessService
from app.application.auth.password import PasswordService
from app.application.auth.service import AuthService
from app.application.connections.repository import ConnectionRepository
from app.application.connections.service import ConnectionService
from app.application.enterprises.repository import EnterpriseRepository
from app.application.enterprises.service import EnterpriseService
from app.application.files.access_service import FileAccessService
from app.application.files.owner_repository import FileOwnerRepository
from app.application.files.owner_resolver import FileOwnerResolver
from app.application.files.repository import FileRepository
from app.application.files.service import FileService
from app.application.files.physical_deletion import PhysicalDeletionService
from app.application.inspections.inspection_repository import InspectionRepository
from app.application.inspections.inspection_service import InspectionService
from app.application.inspections.repository import InspectionTaskRepository
from app.application.inspections.service import InspectionTaskService
from app.application.maintenance.repository import TORecordRepository
from app.application.maintenance.service import TORecordService
from app.application.document_templates.service import DocumentTemplateService
from app.application.objects.archive_repository import ArchiveRepository
from app.application.objects.archive_service import ArchiveService
from app.application.objects.resolver import ObjectResolver
from app.application.objects.service import ObjectService
from app.application.otd.repository import OTDRepository
from app.application.otd.service import OTDService
from app.application.passport_protocol.service import PassportProtocolService
from app.application.programs.repository import ProgramRepository
from app.application.programs.service import ProgramService
from app.application.rza_instructions.repository import RZAInstructionRepository
from app.application.rza_instructions.service import RZAInstructionService
from app.application.schema.repository import SchemaRepository
from app.application.schema.service import SchemaService
from app.application.selectivity_schemes.repository import (
    SelectivitySchemeRepository,
)
from app.application.selectivity_schemes.service import (
    SelectivitySchemeService,
)
from app.application.settings.repository import SettingsRepository
from app.application.settings.service import SettingsService
from app.application.substations.repository import SubstationRepository
from app.application.substations.service import SubstationService
from app.application.tasks.repository import TaskRepository
from app.application.tasks.service import TaskService
from app.application.tasks.statistics import TaskStatisticsService
from app.application.tree.service import TreeService
from app.application.urza_instructions.repository import (
    URZAInstructionRepository,
)
from app.application.urza_instructions.service import URZAInstructionService
from app.application.urzas.repository import URZARepository
from app.application.urzas.service import URZAService
from app.application.users.repository import UserRepository
from app.application.users.service import UserService
from app.application.work_items.service import (
    InspectionTaskWorkItemSource,
    InstructionWorkItemSource,
    MaintenanceWorkItemSource,
    OTDWorkItemSource,
    ProgramWorkItemSource,
    RZAInstructionWorkItemSource,
    SchemaWorkItemSource,
    SelectivitySchemeWorkItemSource,
    SettingsWorkItemSource,
    TaskWorkItemSource,
    WorkItemService,
)
from app.infrastructure.database.session import get_session
from app.infrastructure.storage.base import ObjectStorage
from app.infrastructure.storage.local import LocalObjectStorage
from app.application.notifications.repository import TaskNotificationRepository
from app.application.notifications.service import NotificationService
from app.application.feedback.service import FeedbackService
from app.core.config import get_settings
from app.infrastructure.emailing.smtp_sender import SMTPEmailSender
from app.application.imports.equipment import EquipmentImportService
from app.application.imports.organization import OrganizationImportService


def get_object_storage() -> ObjectStorage:
    """Создаёт адаптер объектного хранилища, настроенный для текущего окружения.
    """
    return LocalObjectStorage(root=Path("data/uploads"))


def get_file_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> FileService:
    """Создаёт сервис загрузки, чтения и архивирования файлов.
    """
    repository = FileRepository(session)

    return FileService(
        repository=repository,
        storage=storage,
    )


def get_password_service() -> PasswordService:
    """Создаёт сервис хеширования и проверки паролей.
    """
    return PasswordService()


def get_auth_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
) -> AuthService:
    """Создаёт сервис аутентификации на базе репозитория пользователей и PasswordService.
    """
    return AuthService(
        user_repository=UserRepository(session),
        password_service=password_service,
    )


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    password_service: Annotated[PasswordService, Depends(get_password_service)],
) -> UserService:
    """Создаёт сервис административного управления пользователями.
    """
    return UserService(
        repository=UserRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        password_service=password_service,
    )


def get_access_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccessService:
    """Создаёт централизованный сервис проверки прав доступа к предприятиям и оборудованию.
    """
    return AccessService(
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
    )


def get_physical_deletion_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> PhysicalDeletionService:
    """Создаёт сервис физического удаления документных записей и освобождённых файлов.
    """
    return PhysicalDeletionService(
        session=session,
        access_service=access_service,
        file_owners=FileOwnerRepository(session),
        storage=storage,
    )


def get_organization_import_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrganizationImportService:
    """Создаёт сервис предварительной проверки и импорта организационной структуры.
    """
    return OrganizationImportService(
        repository=EnterpriseRepository(session),
    )


def get_equipment_import_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> EquipmentImportService:
    """Создаёт сервис предварительной проверки и импорта оборудования РЗА.
    """
    return EquipmentImportService(
        session=session,
        access_service=access_service,
    )


def get_file_access_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> FileAccessService:
    """Создаёт сервис проверки доступа к файлам через их доменных владельцев.
    """
    return FileAccessService(
        file_repository=FileRepository(session),
        owner_resolver=FileOwnerResolver(FileOwnerRepository(session)),
        access_service=access_service,
    )


def get_tree_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> TreeService:
    """Создаёт сервис формирования дерева предприятий и оборудования.
    """
    return TreeService(
        enterprise_repository=EnterpriseRepository(session),
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        access_service=access_service,
    )


def get_document_form_service(
    tree_service: Annotated[TreeService, Depends(get_tree_service)],
) -> DocumentTemplateService:
    """Создаёт сервис формирования DOCX-документов из шаблонов.
    """
    return DocumentTemplateService(
        tree_service=tree_service,
        templates_dir=get_settings().document_templates_dir,
    )


def get_object_resolver(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ObjectResolver:
    """Создаёт резолвер типов и идентификаторов доменных объектов.
    """
    return ObjectResolver(
        substation_repository=SubstationRepository(session),
        connection_repository=ConnectionRepository(session),
        urza_repository=URZARepository(session),
        enterprise_repository=EnterpriseRepository(session),
    )


def get_object_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> ObjectService:
    """Создаёт сервис проверки доступа и получения выбранного объекта.
    """
    return ObjectService(
        access_service=access_service,
        object_resolver=ObjectResolver(
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
            enterprise_repository=EnterpriseRepository(session),
        ),
    )


def get_archive_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> ArchiveService:
    """Создаёт сервис архивирования и восстановления объектов.
    """
    return ArchiveService(
        repository=ArchiveRepository(session),
        access_service=access_service,
    )


def get_substation_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SubstationService:
    """Создаёт сервис подстанций.
    """
    return SubstationService(
        repository=SubstationRepository(session),
    )


def get_enterprise_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EnterpriseService:
    """Создаёт сервис производственных отделений.
    """
    return EnterpriseService(
        repository=EnterpriseRepository(session),
    )


def get_connection_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConnectionService:
    """Создаёт сервис присоединений.
    """
    return ConnectionService(
        repository=ConnectionRepository(session),
    )


def get_urza_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> URZAService:
    """Создаёт сервис устройств РЗА.
    """
    return URZAService(
        repository=URZARepository(session),
    )


def get_inspection_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InspectionService:
    """Создаёт сервис результатов осмотров подстанций.
    """
    return InspectionService(
        repository=InspectionRepository(session),
    )


def get_inspection_task_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InspectionTaskService:
    """Создаёт сервис жизненного цикла задач осмотра.
    """
    return InspectionTaskService(
        repository=InspectionTaskRepository(session),
        user_repository=UserRepository(session),
        substation_repository=SubstationRepository(session),
    )


def get_inspection_task_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InspectionTaskRepository:
    """Создаёт репозиторий задач осмотра на текущей SQLAlchemy-сессии.
    """
    return InspectionTaskRepository(session)


def get_rza_instruction_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RZAInstructionService:
    """Создаёт сервис инструкций РЗА подстанций.
    """
    return RZAInstructionService(
        repository=RZAInstructionRepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )


def get_selectivity_scheme_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SelectivitySchemeService:
    """Создаёт сервис схем селективности подстанций.
    """
    return SelectivitySchemeService(
        repository=SelectivitySchemeRepository(session),
        access_service=AccessService(
            user_repository=UserRepository(session),
            enterprise_repository=EnterpriseRepository(session),
            substation_repository=SubstationRepository(session),
            connection_repository=ConnectionRepository(session),
            urza_repository=URZARepository(session),
        ),
    )


def get_otd_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> OTDService:
    """Создаёт сервис формуляров ОТД и их версий.
    """
    return OTDService(
        repository=OTDRepository(session),
        access_service=access_service,
        task_repository=TaskRepository(session),
    )


def get_settings_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> SettingsService:
    """Создаёт сервис формуляров уставок и записей изменений.
    """
    return SettingsService(
        repository=SettingsRepository(session),
        access_service=access_service,
    )


def get_schema_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> SchemaService:
    """Создаёт сервис формуляров схем и записей изменений.
    """
    return SchemaService(
        repository=SchemaRepository(session),
        access_service=access_service,
        task_repository=TaskRepository(session),
    )


def get_notification_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskNotificationRepository:
    """Создаёт репозиторий уведомлений на текущей SQLAlchemy-сессии.
    """
    return TaskNotificationRepository(session)


def get_notification_service(
    repository: Annotated[
        TaskNotificationRepository,
        Depends(get_notification_repository),
    ],
) -> NotificationService:
    """Создаёт сервис внутренних уведомлений пользователей.
    """
    return NotificationService(repository=repository)


def get_task_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TaskRepository:
    """Создаёт репозиторий задач и истории на текущей SQLAlchemy-сессии.
    """
    return TaskRepository(session)


def get_task_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    notification_service: Annotated[
        NotificationService,
        Depends(get_notification_service),
    ],
) -> TaskService:
    """Создаёт сервис управления жизненным циклом задач.
    """
    return TaskService(
        task_repository=task_repository,
        access_service=access_service,
        urza_instruction_repository=URZAInstructionRepository(session),
        notification_service=notification_service,
    )


def get_maintenance_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> TORecordService:
    """Создаёт сервис записей технического обслуживания.
    """
    return TORecordService(
        repository=TORecordRepository(session),
        access_service=access_service,
        task_repository=task_repository,
        user_repository=UserRepository(session),
        urza_repository=URZARepository(session),
        task_service=task_service,
    )


def get_passport_protocol_service(
    otd_service: Annotated[OTDService, Depends(get_otd_service)],
    settings_service: Annotated[SettingsService, Depends(get_settings_service)],
    schema_service: Annotated[SchemaService, Depends(get_schema_service)],
    maintenance_service: Annotated[TORecordService, Depends(get_maintenance_service)],
    urza_service: Annotated[URZAService, Depends(get_urza_service)],
    document_template_service: Annotated[
        DocumentTemplateService,
        Depends(get_document_form_service),
    ],
    file_access_service: Annotated[
        FileAccessService,
        Depends(get_file_access_service),
    ],
    file_service: Annotated[FileService, Depends(get_file_service)],
) -> PassportProtocolService:
    """Создаёт сервис подготовки комплекта документов паспорта УРЗА.
    """
    return PassportProtocolService(
        otd_service=otd_service,
        settings_service=settings_service,
        schema_service=schema_service,
        maintenance_service=maintenance_service,
        urza_service=urza_service,
        document_template_service=document_template_service,
        file_access_service=file_access_service,
        file_service=file_service,
    )


def get_program_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
) -> ProgramService:
    """Создаёт сервис программ УРЗА и их согласования.
    """
    return ProgramService(
        repository=ProgramRepository(session),
        access_service=access_service,
        user_repository=UserRepository(session),
        urza_repository=URZARepository(session),
        task_repository=TaskRepository(session),
        task_service=task_service,
    )


def get_urza_instruction_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
) -> URZAInstructionService:
    """Создаёт сервис версионируемых инструкций УРЗА.
    """
    return URZAInstructionService(
        repository=URZAInstructionRepository(session),
        access_service=access_service,
        user_repository=UserRepository(session),
        urza_repository=URZARepository(session),
    )


def get_work_item_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    task_repository: Annotated[TaskRepository, Depends(get_task_repository)],
    task_service: Annotated[TaskService, Depends(get_task_service)],
    program_service: Annotated[ProgramService, Depends(get_program_service)],
    maintenance_service: Annotated[
        TORecordService,
        Depends(get_maintenance_service),
    ],
) -> WorkItemService:
    """Создаёт агрегатор рабочего списка из специализированных источников.
    """
    settings_service = SettingsService(
        repository=SettingsRepository(session),
        access_service=access_service,
    )
    schema_service = SchemaService(
        repository=SchemaRepository(session),
        access_service=access_service,
        task_repository=task_repository,
    )
    instruction_service = URZAInstructionService(
        repository=URZAInstructionRepository(session),
        access_service=access_service,
        user_repository=UserRepository(session),
        urza_repository=URZARepository(session),
    )
    rza_instruction_service = RZAInstructionService(
        repository=RZAInstructionRepository(session),
        access_service=access_service,
    )
    selectivity_scheme_service = SelectivitySchemeService(
        repository=SelectivitySchemeRepository(session),
        access_service=access_service,
    )
    otd_service = OTDService(
        repository=OTDRepository(session),
        access_service=access_service,
        task_repository=task_repository,
    )
    return WorkItemService(
        sources=[
            TaskWorkItemSource(task_repository, access_service, task_service),
            OTDWorkItemSource(otd_service),
            ProgramWorkItemSource(program_service),
            MaintenanceWorkItemSource(maintenance_service),
            SettingsWorkItemSource(settings_service),
            SchemaWorkItemSource(schema_service),
            InstructionWorkItemSource(instruction_service),
            RZAInstructionWorkItemSource(rza_instruction_service),
            SelectivitySchemeWorkItemSource(selectivity_scheme_service),
        ]
    )


def get_inspection_work_item_source(
    inspection_repository: Annotated[
        InspectionTaskRepository,
        Depends(get_inspection_task_repository),
    ],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    inspection_service: Annotated[
        InspectionTaskService,
        Depends(get_inspection_task_service),
    ],
) -> InspectionTaskWorkItemSource:
    """Создаёт источник элементов рабочего списка для задач осмотра.
    """
    return InspectionTaskWorkItemSource(
        repository=inspection_repository,
        access_service=access_service,
        inspection_service=inspection_service,
    )


def get_task_statistics_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    access_service: Annotated[AccessService, Depends(get_access_service)],
    work_item_service: Annotated[
        WorkItemService,
        Depends(get_work_item_service),
    ],
    inspection_work_item_source: Annotated[
        InspectionTaskWorkItemSource,
        Depends(get_inspection_work_item_source),
    ],
) -> TaskStatisticsService:
    """Создаёт сервис статистики задач с учётом области доступа.
    """
    return TaskStatisticsService(
        task_repository=TaskRepository(session),
        inspection_repository=InspectionTaskRepository(session),
        enterprise_repository=EnterpriseRepository(session),
        access_service=access_service,
        work_item_service=work_item_service,
        inspection_work_item_source=inspection_work_item_source,
    )


def get_feedback_service() -> FeedbackService:
    """Создаёт сервис отправки обратной связи по электронной почте.
    """
    settings = get_settings()

    if not settings.feedback_email:
        raise HTTPException(
            status_code=503,
            detail="Обратная связь временно недоступна.",
        )

    try:
        sender = SMTPEmailSender(settings)
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="Отправка сообщений временно недоступна.",
        ) from exc

    return FeedbackService(
        sender=sender,
        recipient=settings.feedback_email,
        app_base_url=settings.app_base_url,
    )


def get_enterprise_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EnterpriseRepository:
    """Создаёт репозиторий организационной структуры на текущей SQLAlchemy-сессии.
    """
    return EnterpriseRepository(session)
