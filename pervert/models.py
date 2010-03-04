# -*- coding: utf-8 -*-
from django.db.models import *
from django.db.models.query_utils import CollectedObjects
from django.contrib.auth.models import User, UserManager
import uuid, cPickle
from pervert.middleware import threadlocals
import cPickle
from django.db.models.signals import post_save, post_delete

def post_save_handler(sender, **kwargs):
    if not issubclass(sender, AbstractPervert): return
    
    instance = kwargs["instance"]
    editor = Editor.objects.get(user = threadlocals.get_current_user())

    # If this object has not been created yet
    if not MicroCommit.objects.filter(object_uid=instance.uid):
        MicroCommit(
            object_uid = instance.uid,
            editor = editor,
            ctype = "cr",
            value = cPickle.dumps(sender)
        ).save()
        
    # Create MicroCommit for each modification
    for key, (foreignkey, value) in instance.mods.items():
        
        if key in "uid": continue

        if not foreignkey:
            value = cPickle.dumps(value)

        MicroCommit(
            object_uid = instance.uid,
            editor = editor,
            ctype = "md",
            key = key,
            value = value
        ).save()
    
    # Freaky Django bug or feature causing the dict to carry same items
    # into next other models. Must be cleared explicitly.
    instance.mods.clear()
    
def post_delete_handler(sender, **kwargs):
    if not issubclass(sender, AbstractPervert): return

    instance = kwargs["instance"]
    editor = Editor.objects.get(user = threadlocals.get_current_user())

    MicroCommit(
        object_uid = instance.uid,
        editor = editor,
        ctype = "dl"
    ).save()
    
    # WARNING, the following is a monkey-patch. When an object is deleted
    # from the Django admin, related objects are deleted automatically.
    # problem is: their delete() method is not executed, making their 
    # deletion invisible to Pervert. So I'll have to delete them manually
    # See Model.delete here: 
    # http://code.djangoproject.com/browser/django/trunk/django/db/models/base.py
    return 
    seen_objs = CollectedObjects()
    self._collect_sub_objects(seen_objs)
    
    for (model, objlist) in seen_objs.items():
        for obj in objlist.values():
            if obj != self:
                obj.delete(commit=commit)


post_save.connect(post_save_handler)
post_delete.connect(post_delete_handler)


class UUIDVersionError(Exception):
    pass


class UUIDField(CharField):
    def _uuid(self):
        return unicode(uuid.uuid4())
    def __init__(self, **kwargs):
        kwargs['max_length'] = 36
        kwargs['db_index'] = True
        kwargs['verbose_name'] = "UUID"
        kwargs['default'] = self._uuid
        CharField.__init__(self, **kwargs)

class PervertError(Exception):
    pass

class Editor(Model):
    user = ForeignKey(User, unique=True)
    uid = UUIDField()
    def __unicode__(self):
        text = self.user.first_name + " " + self.user.last_name
        text = text.strip()
        if not text:
            text = u"Anonymous %d" % self.user.id 
        return text
        
    objects = UserManager()
 
class AbstractPervert(Model):
    uid = UUIDField()
    
    class Meta:
        abstract = True

    # We will store modifications here, to turn them into MicroCommits later
    mods = {}
    def __setattr__(self, key, value):
        if not key == "id" and key in self._meta.get_all_field_names():
            # There must be a better way to find this...
            if self._meta.get_field(key).__class__.__name__ == "ForeignKey":
                # Don't dump the whole object, just the uid
                self.mods[key] = (True, value.uid)
            else:
                self.mods[key] = (False, value)
        super(AbstractPervert, self).__setattr__(key, value)
        
class Commit(Model):
    uid = UUIDField(primary_key=True)
    editor = ForeignKey(
        Editor, 
        related_name = "commits"
    )
    when = DateTimeField(
        auto_now = True,
        verbose_name = "Commit time"
    )
    explanation = CharField(max_length=300,null=True,blank=True)
    class Meta:
        # Most of the time you will need most recent
        ordering = ['-when']

    def __unicode__(self):
        return "%s: %s" % (unicode(self.editor), unicode(self.when))

    def save(self, force_insert=False, force_update=False, commit=True):
        editor = Editor.objects.get(user = threadlocals.get_current_user())
        self.editor = editor
        super(Commit, self).save()
        # Looks like due to a bug, the code below doesn't work. Temporary workaround below
        # microcommits = MicroCommit.objects.filter(editor=editor, commit=None)
        for m in [m for m in MicroCommit.objects.filter(commit=None) if m.editor == editor]:
            m.commit = self
            m.save()

class MicroCommit(Model):
    
    object_uid = UUIDField()
    commit = ForeignKey(Commit, to_field="uid", related_name="microcommits", null=True)
    editor = ForeignKey(Editor, to_field="uid", related_name="microcommits")
    # cr md dl
    ctype = CharField(max_length=2)
    # Used for modification microcommits
    key = CharField(max_length=30,null=True)
    # Used either for mod microcommits or for creation microcommits (for model
    # name)
    value = TextField(null=True)
    
    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']
    
    def instance(self):
        return PervertInstance(uid = self.object_uid, step = self.id)

    def __unicode__(self):
        text = {"cr":"created","md":"modified","dl":"deleted"}[self.ctype]
        if self.ctype == "md": text += " " + self.key
        text += " " + self.object_uid
        return text

class PervertInstance:
    """
    Use this to find the state of objects at different moments in time
    """
    def __init__(self, uid, step=1):
        self.uid = uid
        self.step = step
        self.fields = []
        self.foreignkeys = []
        
        # Find object type and when it was created
        try:
            createcommit = MicroCommit.objects.get(
                object_uid = self.uid,
                ctype = "cr"
            )
            self.object_type = cPickle.loads(str(createcommit.value))
            self.object_type_name = self.object_type.__name__
            self.created_on = createcommit.id
        except MicroCommit.DoesNotExist:
            raise PervertError("An object with UUID: %s has no creation " \
                "commit" % self.uid)
        
        # Create lists with fields
        for field in self.object_type._meta.fields:
            if field.name in ["id", "uid"]:
                continue
            if field.__class__.__name__ == "ForeignKey":
                self.foreignkeys.append(field.name)
            else:
                self.fields.append(field.name)
    
    def move(self, step):
        """
        Move the instance to a different step.
        """
        self.step = step
        
    def move_to_present(self):
        self.move(MicroCommit.objects.all()[0].id)
    
    def get_modcommit(self, key):
        """
        Return the last modcommit of the given field
        """
        try:
            modcommit = MicroCommit.objects.filter(
                object_uid = self.uid,
                key = key,
                ctype = "md",
                id__lt = self.step
            )[0]
        except IndexError:
            raise PervertError("No modification microcommit for attribute "\
            "'%s' of PervertInstance" % key)
        return modcommit

    def get(self, key):
        modcommit = self.get_modcommit(key)
        # If this isn't a ForeignKey, then just return the value
        if key not in self.foreignkeys:
            return cPickle.loads(str(modcommit.value))
        # If it is, then return the object instance
        try:
            return PervertInstance(uid = modcommit.value).get_object()
        except self.object_type.DoesNotExist:
            raise PervertError("When restoring a ForeignKey, the " \
                "%s %s was not found." % (self.object_type_name, self.uid))

    def get_pervert_instance(self, key):
        modcommit = self.get_modcommit(key)
        return PervertInstance(uid = modcommit.value)

    def get_object(self):
        return self.object_type.objects.get(uid = self.uid)

    def exists(self):
        # If it wasn't even created yet
        if self.created_on > self.step:
            return False
        # There is a delete commit before the given step
        try:
            delcommit = MicroCommit.objects.get(
                object_uid = self.uid,
                ctype = "dl",
                id__lte = self.step
            )
            print self.uid, self.object_type_name
            return False
        except MicroCommit.DoesNotExist:
            return True
    
    def recreate(self, commit, overrides = {}):
        """ If the object was deleted, recrete it as it was at this instance, 
        adding the microcommits to the given commit, overriding some fields as
        given by the optional 2nd dictionary argument."""
        new = self.object_type()
        
        MicroCommit(
            object_uid = new.uid,
            commit = commit,
            ctype = "cr",
            value = cPickle.dumps(self.object_type)
        ).save()
        self.restore(commit, new, overrides)
        
        return new.uid
        
        
    def restore(self, commit, obj=None, overrides = {}):
        """ Restore all of the object attributes to the attributes of this
        instance, adding the microcommits to the given commit, overriding some
        fields as given by the optional 2nd dictionary argument."""
        print overrides
        if not obj:
            obj = self.object_type.objects.get(uid=self.uid)
        for field in self.fields + self.foreignkeys:
            if field in overrides.keys():
                obj.__setattr__(field, PervertInstance(overrides[field]).get_object())
                continue
            obj.__setattr__(field, self.get(field))
        obj.hard_save()
        
    
    def __unicode__(self):
        return "%s (%s)" % (unicode(self.object_type), self.uid,)
            
            




