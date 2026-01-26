from typing import List, Optional
from datetime import datetime
from uuid import UUID
from ninja import Schema
from backend_django.users.schemas import UserSchema


class ProjectStatusSchema(str):
	pass


class ProjectSchema(Schema):
	id: UUID
	ter_id: Optional[UUID] = None
	author: Optional[List[UserSchema]] = []
	externes: Optional[List[UserSchema]] = []
	title: str
	description: str
	tasks: Optional[List[str]] = []
	language: Optional[List[str]] = []
	created_date: Optional[str] = None
	status: str
	min_person: Optional[int] = None
	max_person: Optional[int] = None
