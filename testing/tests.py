from django.test import TestCase
from django.contrib.auth.models import User, UserManager
from django.test.client import Client
from pervert.models import *
from testing.models import *
import settings

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
        settings.CURRENT_USER = self.john
        Editor(user=self.john).save()

        eng = LanguageKey(code="eng")
        eng.save()
        epo = LanguageKey(code="epo")
        epo.save()

        concept = Concept()
        concept.save()

        dog = Word(full="dog", language=eng)
        dog.save()
        hundo = Word(full="hundo", language=epo)
        hundo.save()

        WordConceptConnection(concept=concept, word=dog).save()
        WordConceptConnection(concept=concept, word=hundo).save()
        
        Commit(
            explanation = "blah blah",
        ).save()
        
    def runTest(self):
        self.assertEquals(User.objects.count(), 1)        
        self.assertEquals(LanguageKey.objects.count(), 2)
        self.assertEquals(MicroCommit.objects.filter(commit=None).count(), 0)
        self.assertEquals(MicroCommit.objects.count(), 17)


