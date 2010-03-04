from django.test import TestCase
from django.contrib.auth.models import User, UserManager
from django.test.client import Client
from pervert.models import *
from testing.models import *

class CreationTest(TestCase):
    def setUp(self):
        self.john = User(
            first_name = "John",
            last_name = "Doe",
            email = "john.doe@example.com",
            username = "johndoe"
        )
        self.john.set_password("sneaky")
        self.john.save()
        self.john = Editor(user=self.john)
        self.john.save()
        LanguageKey(code="eng").save(editor=self.john)
        LanguageKey(code="epo").save(editor=self.john)
        Concept().save(editor=self.john)
        Word(full="dog", language=LanguageKey.objects.get(code="eng")).save()
        Word(full="hundo", language=LanguageKey.objects.get(code="epo")).save()
        #WordConceptConnection(
        
    def runTest(self):
        self.assertEquals(User.objects.count(), 1)        
        self.assertEquals(LanguageKey.objects.count(), 2)

