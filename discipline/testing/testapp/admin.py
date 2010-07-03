# -*- coding: utf-8 -*-
from django.contrib import admin

from discipline.admin import DisciplinedModelAdmin
from discipline.testing.testapp.models import *

admin.site.register(Concept, DisciplinedModelAdmin)
admin.site.register(Word, DisciplinedModelAdmin)
admin.site.register(WordConceptConnection, DisciplinedModelAdmin)
admin.site.register(LanguageKey, DisciplinedModelAdmin)


