# -*- coding: utf-8 -*-
from django.db.models import *
from discipline.models import DisciplinedModel


class LanguageKey(DisciplinedModel):

    code = CharField(max_length=6,unique=True)
    def __unicode__(self):
        return self.code

class Word(DisciplinedModel):

    def __unicode__(self):
        return "%s (%s)" % (self.full, self.language.code)
    # Full representation
    full = CharField(max_length=70,db_index=True)
    # The language of the word
    language = ForeignKey(LanguageKey, related_name="words")

class Concept(DisciplinedModel):
    
    def __unicode__(self, exclude=None):
        cons = [con.word.__unicode__() for con 
                in self.word_connections.all() if con != exclude]
        if cons:
            return "Concept: " + ", ".join(cons)
        return "Abstract Concept"

    def word_list(self):
        cons = [con.word.__unicode__() for con 
                in self.word_connections.all()]
        if cons:
            return ", ".join(cons)
        return ""
            
    word_list.allow_tags = True


# A connection between a concept and a word
class WordConceptConnection(DisciplinedModel):

    word = ForeignKey(Word, related_name="concept_connections")
    concept = ForeignKey(Concept, related_name="word_connections")

    class Meta:
        verbose_name = "word-concept connection"

    def __unicode__(self):
        return u"%s \u2194 %s" % (
            self.word.__unicode__(),
            self.concept.__unicode__(exclude=self)
        )


