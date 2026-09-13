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


class URZAStatus(StrEnum):
    IN_OPERATION = "in_operation"
    IN_REPAIR = "in_repair"
    DECOMMISSIONED = "decommissioned"
    RESERVE = "reserve"


class ElementBase(StrEnum):
    ELECTROMECHANICAL = "electromechanical"
    MICROELECTRONIC = "microelectronic"
    MICROPROCESSOR = "microprocessor"


class URZACategory(StrEnum):
    I = "I"
    II = "II"
    III = "III"
    IV = "IV"


class RoomCategory(StrEnum):
    I = "I"
    II = "II"
    III = "III"


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