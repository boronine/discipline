import os
import cPickle
import datetime

from django.test import TestCase
from django.contrib.auth.models import User, UserManager
from discipline.models import *
from testapp.models import *

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command

class SchemaStateTest(TestCase):

    def setUp(self):

        self.john = User(
            first_name = "John",
            last_name = "Doe",
            email = "john.doe@example.com",
            username = "johndoe"
        )
        self.john.save()
        settings.CURRENT_USER = self.john
        Editor(user=self.john).save()

    def test_too_late(self):
        """
        If during a schemastate migration you delete a model but
        don't delete its every instance with Discipline, raise
        a DisciplineIntegrityError
        """

        call_command("discipline_migrate", quiet=True)

        epo = LanguageKey.objects.create(code="epo")

        # Create a changed schema state
        ss = SchemaState.objects.order_by("-when")[0]
        newss = copy.deepcopy(json.loads(ss.state))
        del newss["testapp"]["languagekey"]
        SchemaState.objects.create(state = json.dumps(newss))

        # Object not deleted before schema migration
        self.assertRaises(DisciplineIntegrityError, TimeMachine, epo.uid)

    def test_timemachine_schemastates(self):
        """
        Test to see if TimeMachine changes its 'fields' and 
        'foreignkeys' properties when moved to a time with a 
        different schema state. Test that Discipline doesn't allow
        you to revert an Action at a different schema.
        """

        call_command("discipline_migrate", quiet=True)

        epo = LanguageKey.objects.create(code="epo")
        eng = LanguageKey.objects.create(code="eng")
        hundo = Word.objects.create(full="hundo", language=epo)

        tm = TimeMachine(hundo.uid)
        self.assertEquals(tm.fields, ["full"])
        self.assertEquals(tm.foreignkeys, ["language"])

        # Create a changed schema state
        ss = SchemaState.objects.order_by("-when")[0]
        newss = copy.deepcopy(json.loads(ss.state))
        newss["testapp"]["word"]["fields"] = ["text"]
        newss["testapp"]["word"]["foreignkeys"] = \
                ["language","type"]
        SchemaState.objects.create(state = json.dumps(newss))

        hundo.language = eng
        hundo.save()
        self.assertEquals(tm.presently.fields, ["text"])
        self.assertEquals(tm.presently.foreignkeys, ["language", "type"])

        # The second-last action must not be revertible, since
        # the schema has changed
        hundoacts = Action.objects.filter(object_uid = hundo.uid).order_by("-when")
        self.assertTrue(hundoacts[0].is_revertible)
        self.assertFalse(hundoacts[1].is_revertible)


class GeneralDisciplineTests(TestCase):

    def setUp(self):

        call_command("discipline_migrate", quiet=True)

        self.john = User(
            first_name = "John",
            last_name = "Doe",
            email = "john.doe@example.com",
            username = "johndoe"
        )
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
        """
        Test the creation of a modification action.
        """
        self.hundo.full = "hundoj"
        self.hundo.save()
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "md")
        self.assertEquals(lastact.object_uid, self.hundo.uid)
        self.assertEquals(lastact.modification_commits.all()[0].key, "full")
        self.assertEquals(lastact.modification_commits.all()[0].value, 
                          cPickle.dumps("hundoj"))
        
    def test_creation_action(self):
        """
        Test the creation of a creation action.
        """
        rus = LanguageKey.objects.create(code="rus")
        sobaka = Word.objects.create(full="sobaka", language=rus)
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "cr")
        self.assertEquals(lastact.object_uid, sobaka.uid)
        self.assertEquals(lastact.creation_commits.all()[0].content_type,
                          ContentType.objects.get_for_model(Word))

    def test_deletion_action(self):
        """
        Test the creation of a deletion action.
        """
        wcc = WordConceptConnection.objects.all()[0]
        uid = wcc.uid
        wcc.delete()
        lastact = Action.objects.all()[0]
        self.assertEquals(lastact.action_type, "dl")
        self.assertEquals(lastact.object_uid, uid)

    def test_deletion_action_cascade(self):
        """
        Make sure when deleting an object with ForeignKeys pointing
        to it, Discipline will register the deletion of related objects.
        """
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
        """
        Test undo of a creation action and the 'is_revertible' preperty
        for creation actions.
        """
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
        """
        Test undo of a modification action and the 'is_revertible' preperty
        for modification actions.
        """
        cc = self.hundo.concept_connections.all()[0]
        cc.word = self.dog
        cc.save()
        action = Action.objects.all()[0]
        self.assertTrue(action.is_revertible)
        # The WCC used to link to hundo, deleting hundo will disable undo
        self.hundo.delete()
        self.assertFalse(action.is_revertible)
        self.dog.full = "dawg"
        self.dog.save()
        action = Action.objects.all()[0]
        action.undo()
        # Django's caching makes it seem like nothing has changed
        self.assertEquals(Word.objects.get(uid=self.dog.uid).full, "dog")
        reverted = Action.objects.all()[0]
        self.assertEquals(action.reverted, reverted)

    def test_deletion_action_undo(self):
        """
        Test undo of a deletion action and the 'is_revertible' preperty
        for deletion actions.
        """
        cc = self.hundo.concept_connections.all()[0]
        cc.delete()
        action = Action.objects.all()[0]
        self.assertTrue(action.is_revertible)
        # The WCC used to link to hundo, deleting hundo will disable undo
        self.hundo.delete()
        self.assertFalse(action.is_revertible)
        Action.objects.all()[0].undo()
        self.assertTrue(action.is_revertible)
        action.undo()
        self.assertEquals(WordConceptConnection.objects.count(), 2)

    def test_timemachine_time(self):
        """
        Test the TimeMachine's 'at' and 'presently' properties.
        """
        tm = TimeMachine(self.hundo.uid)
        created_on = CreationCommit.objects.get(object_uid=self.hundo.uid).action.id
        self.assertTrue(tm.exists)
        self.assertTrue(tm.at(created_on).exists)
        self.assertFalse(tm.at(created_on).at_previous_action.exists)
        self.hundo.delete()
        action = Action.objects.all()[0]
        self.assertFalse(tm.presently.exists)
        action.undo()
        self.assertTrue(tm.presently.exists)

    def test_timemachine_fields(self):
        """
        Test the TimeMachine's 'get' method.
        """
        tm = TimeMachine(self.hundo.uid)
        self.assertEquals(tm.get("full"), "hundo")
        self.assertEquals(tm.get("language"), self.epo)
        self.hundo.full = "hundooo"
        self.hundo.save()
        self.assertEquals(tm.get("full"), "hundo")
        self.assertEquals(tm.presently.get("full"), "hundooo")

    def test_timemachine_get_timemachine_instance(self):
        """
        Test TimeMachine's 'get_timemachine_instance' method.
        """
        tm = TimeMachine(self.hundo.uid)
        fktm = tm.get_timemachine_instance("language")
        self.assertEquals(fktm.get("code"), "epo")

    def test_timemachine_get_object(self):
        """
        Test TimeMachine's "get_object" method.
        """
        tm = TimeMachine(self.hundo.uid)
        self.assertEquals(tm.get_object(), self.hundo)

    def test_timemachine_current_action(self):
        """
        Test the TimeMachine's 'current_action' property
        """
        hundouid = self.hundo.uid
        self.hundo.delete()
        curact = Action.objects.all()[0]
        self.assertEquals(curact.id, TimeMachine(hundouid).current_action.id)


