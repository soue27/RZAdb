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