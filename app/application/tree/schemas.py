from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class URZATreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    inventory_number: str | None = None
    is_archived: bool = False


class ConnectionTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    is_archived: bool = False
    urzas: list[URZATreeNode] = Field(default_factory=list)


class SubstationTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    is_archived: bool = False
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


class TreeSearchResult(BaseModel):
    id: UUID
    object_type: str
    type_label: str
    name: str
    matched_field: str
    matched_value: str
    path: list[str]
    path_ids: list[UUID]
    archived: bool = False
    has_card: bool = False
    relevance: int


class TreeSearchPage(BaseModel):
    items: list[TreeSearchResult]
    total: int
    offset: int
    limit: int
