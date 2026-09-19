from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class URZATreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str


class ConnectionTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    urzas: list[URZATreeNode] = Field(default_factory=list)


class SubstationTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    connections: list[ConnectionTreeNode] = Field(
        default_factory=list,
    )


class EnterpriseTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    full_name: str
    short_name: str
    children: list["EnterpriseTreeNode"] = Field(
        default_factory=list,
    )
    substations: list[SubstationTreeNode] = Field(
        default_factory=list,
    )