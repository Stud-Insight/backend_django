from ninja import Schema
from datetime import date
from typing import List, Optional
from backend_django.users.schemas import UserSchema
from backend_django.projects.schemas import ProjectSchema

class TERCreateSchema(Schema):
	title: str
	code: str
	year: int
	start_date: date
	end_date: date


class TERNotationSchema(Schema):
	titre: str
	max_notation: int
	coef: float


class GroupObjectiveSchema(Schema):
	title: str
	done: bool

class TERGroupSchema(Schema):
	id: int
	titre: str
	leader: Optional[UserSchema] = None
	members: List[UserSchema] = []
	objectives: Optional[List[GroupObjectiveSchema]] = []
	project: Optional[ProjectSchema] = None
	correcteur: Optional[UserSchema] = None

class TERSchema(Schema):
	title: str
	code: str
	year: int
	groups: List[TERGroupSchema] = []
	projects: List[ProjectSchema] = []
	notation: List[TERNotationSchema] = []
	max_allowed_groups: int
	status: str
	start_date: str
	end_date: str

class TERListSchema(Schema):
    items: List[TERSchema]
