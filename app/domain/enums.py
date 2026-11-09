from enum import StrEnum


class EnterpriseType(StrEnum):
"""Определяет уровни организационной структуры предприятия."""

    HOLDING = "holding"
    BRANCH = "branch"
    DEPARTMENT = "department"


class HighestVoltage(StrEnum):
"""Содержит допустимые классы высшего напряжения подстанции."""

    KV_500 = "500"
    KV_220 = "220"
    KV_110 = "110"
    KV_35 = "35"
    KV_10 = "10"
    KV_6 = "6"
    KV_0_4 = "0.4"


class OperationalCurrentType(StrEnum):
"""Определяет тип оперативного тока на подстанции."""

    PERMANENT = "permanent"
    RECTIFIED = "rectified"
    ALTERNATING = "alternating"

    @property
    def label(self) -> str:
        return {
            self.PERMANENT: "Постоянный ток",
            self.RECTIFIED: "Выпрямленный ток",
            self.ALTERNATING: "Переменный ток",
        }[self]


class URZAStatus(StrEnum):
"""Описывает эксплуатационное состояние устройства РЗА."""

    IN_OPERATION = "in_operation"
    IN_REPAIR = "in_repair"
    DECOMMISSIONED = "decommissioned"
    RESERVE = "reserve"

    @property
    def label(self) -> str:
        return {
            self.IN_OPERATION: "В эксплуатации",
            self.IN_REPAIR: "В ремонте",
            self.DECOMMISSIONED: "Выведено из эксплуатации",
            self.RESERVE: "Резерв",
        }[self]

    @property
    def badge_class(self) -> str:
        return {
            self.IN_OPERATION: "text-bg-success",
            self.IN_REPAIR: "text-bg-warning",
            self.DECOMMISSIONED: "text-bg-danger",
            self.RESERVE: "text-bg-primary",
        }[self]


class ElementBase(StrEnum):
"""Определяет элементную базу устройства РЗА."""

    ELECTROMECHANICAL = "electromechanical"
    MICROELECTRONIC = "microelectronic"
    MICROPROCESSOR = "microprocessor"

    @property
    def label(self) -> str:
        return {
            self.ELECTROMECHANICAL: "Электромеханическая",
            self.MICROELECTRONIC: "Микроэлектронная",
            self.MICROPROCESSOR: "Микропроцессорная",
        }[self]


class URZACategory(StrEnum):
"""Задаёт категорию устройства РЗА."""

    I = "I"
    II = "II"
    III = "III"
    IV = "IV"

    @property
    def label(self) -> str:
        return self.value


class RoomCategory(StrEnum):
"""Задаёт категорию помещения, в котором установлено устройство."""

    I = "I"
    II = "II"
    III = "III"

    @property
    def label(self) -> str:
        return self.value


class OTDPurpose(StrEnum):
"""Определяет назначение устройства, указываемое в формуляре ОТД."""

    RZA = "rza"
    SA = "sa"
    PA = "pa"
    RA = "ra"

    @property
    def label(self) -> str:
        return {
            self.RZA: "РЗА",
            self.SA: "СА",
            self.PA: "ПА",
            self.RA: "РА",
        }[self]


class AccessCategory(StrEnum):
"""Задаёт категорию допуска пользователя к работам."""

    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class UserRole(StrEnum):
"""Определяет системную роль пользователя и его уровень полномочий."""

    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SPECIALIST = "specialist"
    MANAGER = "manager"
    ENGINEER = "engineer"


class TaskWorkType(StrEnum):
"""Определяет вид работы, для выполнения которой создана задача."""

    OTD = "otd"
    SETTINGS = "settings"
    SCHEMES = "schemes"
    MAINTENANCE = "maintenance"
    PROGRAM = "program"
    INSTRUCTION = "instruction"

    @property
    def label(self) -> str:
        return {
            self.OTD: "ОТД",
            self.SETTINGS: "Уставки",
            self.SCHEMES: "Схема",
            self.MAINTENANCE: "Техническое обслуживание",
            self.PROGRAM: "Программа",
            self.INSTRUCTION: "Инструкция",
        }[self]


class MaintenanceType(StrEnum):
"""Содержит обозначения видов технического обслуживания РЗА."""

    V = "В"
    K = "К"
    K1 = "К1"
    N = "Н"
    T = "Т"
    TK = "ТК"
    O = "О"
    OSM = "ОСМ"
    VP = "ВП"
    PP = "ПП"


class TaskStatus(StrEnum):
"""Определяет состояние рабочей задачи в её жизненном цикле."""

    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"
    REJECTED = "rejected"


class ArchiveEventType(StrEnum):
"""Определяет тип события в истории архивирования объектов."""

    ARCHIVED = "archived"
    RESTORED = "restored"


class DocumentStatus(StrEnum):
"""Определяет состояние документа в процессе подготовки и согласования."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"

    @property
    def label(self) -> str:
        return {
            self.DRAFT: "Черновик",
            self.UNDER_REVIEW: "На согласовании",
            self.APPROVED: "Утверждено",
        }[self]

    @property
    def badge_class(self) -> str:
        return {
            self.DRAFT: "text-bg-secondary",
            self.UNDER_REVIEW: "text-bg-warning",
            self.APPROVED: "text-bg-success",
        }[self]


class ProgramType(StrEnum):
"""Определяет назначение программы работ для устройства РЗА."""

    COMMISSIONING = "commissioning"
    DECOMMISSIONING = "decommissioning"
    WORK = "work"

    @property
    def label(self) -> str:
        return {
            self.COMMISSIONING: "Ввод в работу",
            self.DECOMMISSIONING: "Вывод из работы",
            self.WORK: "Рабочая программа",
        }[self]
