from datetime import date
from pydantic import BaseModel


class TERListSchema(BaseModel):
    id: int
    title: str
    code: str
    year: int
    status: str
    start_date: date
    end_date: date

    class Config:
        from_attributes = True
