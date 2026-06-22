from pydantic import BaseModel, Field
from typing import Optional


class MachineModel(BaseModel):
    name: str
    category: str
    city: str
    price_per_day: float
    description: str
    rating: Optional[float] = 0