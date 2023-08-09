from pydantic import BaseModel
from typing import Any, Optional, List, Union, Literal

class Search(BaseModel):
    target: str


class RangeRaw(BaseModel):
    # from: str
    to: str


class Range(BaseModel):
    # from: str
    to: str
    raw: RangeRaw


class Target(BaseModel):
    target: str
    refId: str
    type: str


class Query(BaseModel):
    app: str
    requestId: str
    timezone: str
    panelId: Union[int, str]
    dashboardId: Optional[str] = None
    range: dict
    interval: str
    intervalMs: int
    targets: List[Target]
    maxDataPoints: Optional[int] = None
    scopedVars: dict
    startTime: int
    rangeRaw: RangeRaw
    adhocFilters: list


class TableColumn(BaseModel):
    type: Literal['time', 'string', 'number']
    text: str

class Table(BaseModel):
    type: Literal['table'] = 'table'
    columns: List[TableColumn]
    rows: List[List[Any]] = []
