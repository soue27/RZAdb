from enum import StrEnum


class EnterpriseType(StrEnum):
    HOLDING = "holding"
    BRANCH = "branch"
    DEPARTMENT = "department"


class HighestVoltage(StrEnum):
    KV_500 = "500"
    KV_220 = "220"
    KV_110 = "110"
    KV_35 = "35"
    KV_10 = "10"
    KV_6 = "6"
    KV_0_4 = "0.4"


class OperationalCurrentType(StrEnum):
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
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"

    @property
    def label(self) -> str:
        return self.value


class RoomCategory(StrEnum):
    I = "I"
    II = "II"
    III = "III"

    @property
    def label(self) -> str:
        return self.value


class OTDPurpose(StrEnum):
    RZA = "rza"
    SA = "sa"
    PA = "pa"
    RA = "ra"


class AccessCategory(StrEnum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class UserRole(StrEnum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    SPECIALIST = "specialist"
    MANAGER = "manager"
    ENGINEER = "engineer"


class TaskWorkType(StrEnum):
    OTD = "otd"
    SETTINGS = "settings"
    SCHEMES = "schemes"
    MAINTENANCE = "maintenance"
    PROGRAM = "program"


class MaintenanceType(StrEnum):
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
    CREATED = "created"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    UNDER_REVIEW = "under_review"
    CLOSED = "closed"
    REJECTED = "rejected"


class ProgramType(StrEnum):
    COMMISSIONING = "commissioning"
    DECOMMISSIONING = "decommissioning"
    WORK = "work"