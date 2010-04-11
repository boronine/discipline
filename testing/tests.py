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

        eng = LanguageKey.objects.create(code="eng")
        epo = LanguageKey.objects.create(code="epo")

        concept = Concept()
        concept.save()

        dog = Word.objects.create(full="dog", language=eng)
        hundo = Word.objects.create(full="hundo", language=epo)

        WordConceptConnection(concept=concept, word=dog).save()
        WordConceptConnection(concept=concept, word=hundo).save()
        
    def runTest(self):
        self.assertEquals(User.objects.count(), 1)        
        self.assertEquals(LanguageKey.objects.count(), 2)
        self.assertEquals(CreationCommit.objects.count(), 7)
        self.assertEquals(ModificationCommit.objects.count(), 10)


