import cPickle
from django.test import TestCase
from django.contrib.auth.models import User, UserManager
from django.test.client import Client
from pervert.models import *
from test_app.models import *
import settings
from django.contrib.contenttypes.models import ContentType

class PervertTest(TestCase):
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

        self.eng = LanguageKey.objects.create(code="eng")
        self.epo = LanguageKey.objects.create(code="epo")

        self.concept = Concept.objects.create()

        self.dog = Word.objects.create(full="dog", language=self.eng)
        self.hundo = Word.objects.create(full="hundo", language=self.epo)

        WordConceptConnection(concept=self.concept, word=self.dog).save()
        WordConceptConnection(concept=self.concept, word=self.hundo).save()

    def test_creation_basic(self):
        self.assertEquals(User.objects.count(), 1)        
        self.assertEquals(LanguageKey.objects.count(), 2)
        self.assertEquals(CreationCommit.objects.count(), 7)
        self.assertEquals(ModificationCommit.objects.count(), 10)
    
    def test_modification_action(self):
        self.hundo.full = "hundoj"
        self.hundo.save()
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "md")
        self.assertEquals(lastact.object_uid, self.hundo.uid)
        self.assertEquals(lastact.modification_commits.all()[0].key, "full")
        self.assertEquals(lastact.modification_commits.all()[0].value, 
                          cPickle.dumps("hundoj"))
        
    def test_creation_action(self):
        rus = LanguageKey.objects.create(code="rus")
        sobaka = Word.objects.create(full="sobaka", language=rus)
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "cr")
        self.assertEquals(lastact.object_uid, sobaka.uid)
        self.assertEquals(lastact.creation_commits.all()[0].content_type,
                          ContentType.objects.get_for_model(Word))

    def test_deletion_action(self):
        wcc = WordConceptConnection.objects.all()[0]
        uid = wcc.uid
        wcc.delete()
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "dl")
        self.assertEquals(lastact.object_uid, uid)

    def test_deletion_action_cascade(self):
        hundo_uid = self.hundo.uid
        wcc_uid = self.hundo.concept_connections.all()[0].uid
        self.hundo.delete()

        hundo_act = Action.objects.all()[0]
        wcc_act = Action.objects.all()[1]

        self.assertEquals(hundo_act.action_type, "dl")
        self.assertEquals(hundo_act.object_uid, hundo_uid)

        self.assertEquals(wcc_act.action_type, "dl")
        self.assertEquals(wcc_act.object_uid, wcc_uid)
        
    def test_creation_action_undo(self):
        action = CreationCommit.objects.get(object_uid=self.dog.uid).action
        self.assertEquals(action.is_revertible, False)
        # Delete the WCC that keeps the dog from being deleted
        self.dog.concept_connections.all()[0].delete()
        self.assertEquals(action.is_revertible, True)
        action.undo()
        self.assertEquals(Word.objects.filter(full="dog").count(), 0)
        reverted = Action.objects.all()[0]
        self.assertEquals(action.reverted, reverted)

    def test_modification_action_undo(self):
        cc = self.hundo.concept_connections.all()[0]
        cc.word = self.dog
        cc.save()
        action = Action.objects.all()[0]
        self.assertEquals(action.is_revertible, True)
        # The WCC used to link to hundo, deleting hundo will disable undo
        self.hundo.delete()
        self.assertEquals(action.is_revertible, False)
        self.dog.full = "dawg"
        self.dog.save()
        action = Action.objects.all()[0]
        action.undo()
        # Django's caching makes it seem like nothing has changed
        self.assertEquals(Word.objects.get(uid=self.dog.uid).full, "dog")
        reverted = Action.objects.all()[0]
        self.assertEquals(action.reverted, reverted)

    def test_deletion_action_undo(self):
        cc = self.hundo.concept_connections.all()[0]
        cc.delete()
        action = Action.objects.all()[0]
        self.assertEquals(action.is_revertible, True)
        # The WCC used to link to hundo, deleting hundo will disable undo
        self.hundo.delete()
        self.assertEquals(action.is_revertible, False)
        Action.objects.all()[0].undo()
        self.assertEquals(action.is_revertible, True)
        action.undo()
        self.assertEquals(WordConceptConnection.objects.count(), 2)

    def test_timemachine_time(self):
        tm = TimeMachine(self.hundo.uid)
        created_on = CreationCommit.objects.get(object_uid=self.hundo.uid).action.id
        self.assertEquals(tm.exists, True)
        self.assertEquals(tm.at(created_on).exists, True)
        self.assertEquals(tm.at(created_on-1).exists, False)
        self.hundo.delete()
        action = Action.objects.all()[0]
        self.assertEquals(tm.presently.exists, False)
        action.undo()
        self.assertEquals(tm.presently.exists, True)

    def test_timemachine_fields(self):
        tm = TimeMachine(self.hundo.uid)
        self.assertEquals(tm.get("full"), "hundo")
        self.assertEquals(tm.get("language"), self.epo)
        self.hundo.full = "hundooo"
        self.hundo.save()
        self.assertEquals(tm.get("full"), "hundo")
        self.assertEquals(tm.presently.get("full"), "hundooo")

    def test_timemachine_misc(self):
        tm = TimeMachine(self.hundo.uid)
        fktm = tm.get_timemachine_instance("language")
        self.assertEquals(fktm.get("code"), "epo")
        self.assertEquals(tm.get_object(), self.hundo)
