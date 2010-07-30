# -*- coding: utf-8 -*-
from disciplinesite.demo.models import *
from django.contrib import admin
from discipline.admin import DisciplinedModelAdmin

class WordConceptConnectionInline(admin.TabularInline):
    model = WordConceptConnection 
    extra = 0
    raw_id_fields = ("concept","word",)
    exclude = ("uid",)

class WordConceptConnectionAdmin(DisciplinedModelAdmin):
    raw_id_fields = ("concept","word",)

class ConceptAdmin(DisciplinedModelAdmin):
    inlines = [WordConceptConnectionInline]
    list_display = ("uid","word_list",)

class WordAdmin(DisciplinedModelAdmin):
    inlines = (WordConceptConnectionInline,)
    search_fields = ("full",)
    list_display = ("full","language","uid",)
    list_filter = ("language",)

admin.site.register(Concept, ConceptAdmin)
admin.site.register(Word, WordAdmin)
admin.site.register(WordConceptConnection, WordConceptConnectionAdmin)
admin.site.register(LanguageKey, DisciplinedModelAdmin)


