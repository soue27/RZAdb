from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class URZATreeNode(BaseModel):
    """Узел устройства РЗА в дереве подстанции и присоединения.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    inventory_number: str | None = None
    is_archived: bool = False


class ConnectionTreeNode(BaseModel):
    """Узел присоединения с вложенным списком устройств РЗА.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    is_archived: bool = False
    urzas: list[URZATreeNode] = Field(default_factory=list)


class SubstationTreeNode(BaseModel):
    """Узел подстанции с вложенными присоединениями.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispatch_name: str
    is_archived: bool = False
    connections: list[ConnectionTreeNode] = Field(
        default_factory=list,
    )


class EnterpriseTreeAncestor(BaseModel):
    """Краткое представление предка предприятия в иерархии.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    full_name: str


class EnterpriseTreeNode(BaseModel):
    """Узел организационной структуры с предками, дочерними предприятиями и подстанциями.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    full_name: str
    short_name: str
    ancestors: list[EnterpriseTreeAncestor] = Field(default_factory=list)
    children: list["EnterpriseTreeNode"] = Field(
        default_factory=list,
    )
    substations: list[SubstationTreeNode] = Field(
        default_factory=list,
    )


class TreeSearchResult(BaseModel):
    """Результат поиска объекта с полем совпадения и путём в иерархии.
    """
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
    """Страница результатов поиска по дереву с общим количеством и параметрами пагинации.
    """
    items: list[TreeSearchResult]
    total: int
    offset: int
    limit: int
