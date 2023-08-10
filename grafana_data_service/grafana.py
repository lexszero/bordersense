from pydantic import BaseModel, Field
from typing import Any, Optional, List, Union, Literal, Tuple
from datetime import datetime

class Search(BaseModel):
    target: str


class RangeRaw(BaseModel):
    start: str = Field(..., alias='from')
    end: str = Field(..., alias='to')


class Range(BaseModel):
    start: datetime = Field(..., alias='from')
    end: datetime = Field(..., alias='to')
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
    range: Range
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

class Timeserie(BaseModel):
    target: str
    datapoints: List[Tuple[Any, Any]]
