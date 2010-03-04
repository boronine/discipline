from django.db import models
from pervert.models import AbstractPervert
from django.db.models import *

class LanguageKey(AbstractPervert):
    code = CharField(max_length=6,unique=True)

class Word(AbstractPervert):
    full = CharField(max_length=70,db_index=True)
    language = ForeignKey(LanguageKey, to_field="uid", related_name="words")

class Concept(AbstractPervert):
    pass

class WordConceptConnection(AbstractPervert):
    word = ForeignKey(Word, to_field="uid", related_name="concept_connections")
    concept = ForeignKey(
        Concept, 
        to_field="uid",
        related_name="word_connections"
    )


