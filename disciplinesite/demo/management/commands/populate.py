# -*- coding: utf-8 -*-
import os
import sys
import random
import shutil
from optparse import make_option

from django.conf import settings
from django.contrib.auth.models import User, Group, Permission
from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

from disciplinesite.demo.models import *
from disciplinesite.tools import word, mutate
from discipline.models import *

class Command(BaseCommand):

    def handle(self, *args, **options):

        db = settings.DATABASES["default"]["NAME"]
        if os.path.exists(db):
            os.unlink(db)

        call_command("syncdb", interactive=False)
        call_command("discipline_migrate")
        
        languages = []
        editors = []
                
        me = User(
            first_name = "Alexei",
            last_name = "Boronine",
            email = "alexei.boronine@gmail.com",
            username = "alex",
            is_staff = True,
            is_superuser = True
        )
        me.set_password("crimson")
        me.save()
        editorme = Editor.objects.create(user=me)
        editors.append(editorme)
        epo = LanguageKey(code="epo")
        editorme.save_object(epo)
        eng = LanguageKey(code="eng")
        editorme.save_object(eng)
        editorme.save_object(Concept())
        
        languages.append(epo)
        languages.append(eng)
        
        # Make the editor group
        perms = list(Permission.objects.filter(
                     content_type__app_label = "demo"))
        perms.append(
            Permission.objects.get(
                content_type__app_label = "discipline", 
                codename = "change_action"
            )
        )
        perms.append(
            Permission.objects.get(
                content_type__app_label = "discipline", 
                codename = "change_schemastate"
            )
        )
        grp = Group.objects.create(name="editors")
        grp.permissions.add(*perms)
        
        # Make 10 editors
        for i in range(10):
            first = word(True)
            last = word(True)
            user = User(
                first_name = first,
                last_name = last,
                email = "%s%s@example.com" % (first, last),
                username = "user%s" % (i+1),
                is_staff = True
            )
            user.set_password("crimson")
            user.save()
            user.groups.add(grp)
            editor = Editor.objects.create(user=user)
            editors.append(editor)
            print user 

        # Make a bunch of random actions
        for i in range(100):
            user = random.choice(editors)
            
            # Create word
            if random.randint(0,2) == 1 and Concept.objects.count() != 0:
                w = Word(
                    full = word(),
                    language = random.choice(languages)
                )
                editor.save_object(w)
                wc = WordConceptConnection(
                    concept = Concept.objects.order_by('?')[0],
                    word = w
                )
                editor.save_object(wc)
                print "Created word"

            # Modify word
            if random.randint(0,2) == 1 and Word.objects.count():
                w = Word.objects.order_by('?')[0]
                w.full = mutate(w.full)
                editor.save_object(w)
                print "Modified word"
            
            # Delete word 
            if random.randint(0,6) == 1 and Word.objects.count():
                w = Word.objects.order_by('?')[0]
                user.delete_object(w)
                print "Deleted word"
            
            # Create concept
            if random.randint(0,4) == 1:
                editor.save_object(Concept())
                print "Created concept"

