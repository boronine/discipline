
from django.db import models
from discipline.models import DisciplinedModel
from django.db.models import *

class Band(DisciplinedModel):
    name = CharField(max_length = 50)
    awesome = BooleanField(default=False)

class Musician(DisciplinedModel):
    name = CharField(max_length = 50)
    band = ForeignKey("Band", related_name="members")
