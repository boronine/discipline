# -*- coding: utf-8 -*-
import cPickle
import uuid

from django.db.models import *
from django.db.models.query_utils import CollectedObjects
from django.contrib.auth.models import User, UserManager
from django.db.models.signals import post_save, post_delete
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
import settings

from pervert.middleware import threadlocals

def post_save_handler(sender, **kwargs):
    
    if not issubclass(sender, AbstractPervert): return

    instance = kwargs["instance"]
    
    fields = []
    fks = []
    for field in instance.__class__._meta.fields:
        if field.name in ["id", "auto"]: continue
        fields.append(field.name)
        if field.__class__.__name__ == "ForeignKey":
            fks.append(field.name)

    # The object doesn't exist yet
    if not CreationCommit.objects.filter(object_id=instance.id):
        action = Action.objects.create()
        CreationCommit.objects.create(
            object_id = instance.id,
            action = action,
            content_type = ContentType.objects.get_for_model(instance.__class__)
        )
        # Create a modcommit for everything
        mods = fields

    else:
        mods = []
        inst = PervertInstance(instance.id)
        inst.move_to_present()
        for field in fields:
            if inst.get(field) != getattr(instance, field):
                mods.append(field)
        # Make sure there are actual changes
        if not mods: return
        action = Action.objects.create()

    # Create MicroCommit for each modification
    for field in mods:
        if field in fks:
            value = getattr(instance,field).id
        else:
            value = cPickle.dumps(getattr(instance,field))
        ModificationCommit.objects.create(
            object_id = instance.id,
            action = action,
            key = field,
            value = value
        )
    
def post_delete_handler(sender, **kwargs):
    if not issubclass(sender, AbstractPervert): return

    instance = kwargs["instance"]
    action = Action.objects.create()

    DeletionCommit(
        object_id = instance.id,
        action = action,
    ).save()

post_save.connect(post_save_handler)
post_delete.connect(post_delete_handler)


class PervertError(Exception):
    pass

class Editor(Model):

    user = ForeignKey(User, unique=True)
    def __unicode__(self):
        text = self.user.first_name + " " + self.user.last_name
        text = text.strip()
        if not text:
            text = u"Anonymous %d" % self.user.id 
        return text
        
    objects = UserManager()

def get_uuid():
    return uuid.uuid4().hex

class AbstractPervert(Model):
    
    id = CharField(max_length=32, default=get_uuid)
    # Django doesn't like UUID, this is a temparary hack
    auto = AutoField(primary_key=True)

    class Meta:
        abstract = True


class Action(Model):

    editor = ForeignKey(
        Editor, 
        related_name = "commits"
    )

    when = DateTimeField(
        auto_now = True,
        verbose_name = "commit time"
    )

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

    def __unicode__(self):
        return "%s: %s" % (unicode(self.editor), unicode(self.when))
    
    def description(self):

        if self.deletion_commits.count():
            c = self.deletion_commits.all()[0]
            self.inst = PervertInstance(c.object_id)
            self.atype = "dl"
            return "Deleted %s" % self.inst.content_type.name
            
        text = ""
        try:
            c = self.creation_commits.all()[0]
            self.atype = "cr"
            text += "Created "
        except IndexError:
            c = self.modification_commits.all()[0]
            self.atype = "md"
            text += "Modified "

        self.inst = PervertInstance(c.object_id)
        self.inst.move_to_present()
        
        text += self.inst.type_link()
        
        return text

    description.allow_tags = True

    def details(self):
        text = ""
        self.description()
        self.inst.move(self.id)

        if self.atype == "dl":
            fields = self.inst.fields + self.inst.foreignkeys
        else: fields = [i.key for i in self.modification_commits.all()]
            
        for field in fields:
            text += "<strong>%s</strong>: " % field
            if self.atype == "md":
                self.inst.move(self.id - 1)
                try:
                    text += self.inst.field_repr(field) + " --> "
                except:
                    text += "nigger --> "
                self.inst.move(self.id)
            text += self.inst.field_repr(field) + "<br/>"
        #print ": " + text
        return text   

    details.allow_tags = True

    def save(self, commit=True, **kwargs):
        editor = Editor.objects.get(user = threadlocals.get_current_user())
        self.editor = editor
        super(Action, self).save(**kwargs)

    def _type(self):
        return self.description()[0]

    action_type = property(_type)

class CreationCommit(Model):

    content_type = ForeignKey(ContentType)
    object_id = CharField(max_length=32)
    action = ForeignKey(Action, related_name="creation_commits")

    def __unicode__(self):
        return "%s %s" % (self.content_type.name, self.object_id,)

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class DeletionCommit(Model):
    object_id = CharField(max_length=32)
    action = ForeignKey(Action, related_name="deletion_commits")

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class ModificationCommit(Model):
    object_id = CharField(max_length=32)
    action = ForeignKey(Action, related_name="modification_commits")
    key = CharField(max_length=30,null=True)
    value = TextField(null=True)
 
    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class PervertInstance:
    """
    Use this to find the state of objects at different moments in time
    """
    def __init__(self, id, step=1):
        self.id = id
        self.step = step
        self.fields = []
        self.foreignkeys = []
        
        # Find object type and when it was created
        try:
            cc = CreationCommit.objects.get(
                object_id = self.id,
            )
            self.content_type = cc.content_type
            self.content_type_name = self.content_type.name
            self.created_on = cc.action.id
        except CreationCommit.DoesNotExist:
            self.created_on = None
            return
        
        # Create lists with fields
        for field in self.content_type.model_class()._meta.fields:
            if field.name in ["id", "auto"]:
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
        if Action.objects.count():
            self.move(Action.objects.all()[0].id)
        else:
            self.move(1)
    
    def get_modcommit(self, key):
        """
        Return the last modcommit of the given field
        """
        try:
            modcommit = ModificationCommit.objects.filter(
                object_id = self.id,
                key = key,
                action__id__lte = self.step
            )[0]
        except IndexError:
            raise PervertError("No modification microcommit for attribute "\
            "'%s' of %s at %d" % (key, self.__unicode__(), self.step,))
        return modcommit

    def get(self, key):
        modcommit = self.get_modcommit(key)
        # If this isn't a ForeignKey, then just return the value
        if key not in self.foreignkeys:
            return cPickle.loads(str(modcommit.value))
        # If it is, then return the object instance
        try:
            return PervertInstance(id = modcommit.value).get_object()
        except self.content_type.DoesNotExist:
            raise PervertError("When restoring a ForeignKey, the " \
                "%s %s was not found." % (self.content_type_name, self.id))

    def get_pervert_instance(self, key):
        modcommit = self.get_modcommit(key)
        return PervertInstance(id = modcommit.value)

    def get_object(self):
        return self.content_type.model_class().objects.get(id = self.id)

    def exists(self):
        # If it wasn't even created yet
        if not self.created_on or self.created_on > self.step:
            return False
        # There is a delete commit before the given step
        try:
            delcommit = DeletionCommit.objects.get(
                object_id = self.id,
                action__id__lte = self.step
            )
            return False
        except DeletionCommit.DoesNotExist:
            return True
    
    def recreate(self, action, overrides = {}):
        """ If the object was deleted, recrete it as it was at this instance, 
        adding the microcommits to the given commit, overriding some fields as
        given by the optional 2nd dictionary argument."""
        new = self.content_type()
        
        CreationCommit.objects.create(
            object_id = new.id,
            action = action,
            value = cPickle.dumps(self.content_type)
        )
        self.restore(action, new, overrides)
        
        return new.id
        
        
    def restore(self, action, obj=None, overrides = {}):
        """ Restore all of the object attributes to the attributes of this
        instance, adding the microcommits to the given commit, overriding some
        fields as given by the optional 2nd dictionary argument."""
        if not obj:
            obj = self.content_type.objects.get(id=self.id)
        for field in self.fields + self.foreignkeys:
            if field in overrides.keys():
                obj.__setattr__(field, PervertInstance(overrides[field]).get_object())
                continue
            obj.__setattr__(field, self.get(field))
        obj.hard_save()
        
    
    def __unicode__(self):
        return "%s (%s)" % (unicode(self.content_type), self.id,)
            
    def url(self):
        if self.exists():
            return "/admin/%s/%s/%i" % (self.content_type.app_label,
                                        self.content_type.model,
                                        self.get_object().auto)
            
        else:
            return None

    def type_link(self):
        """ Provides a link with the object type as text. If the object doesn't
        exist, the link is crossed out"""

        url = self.url()
        if url:
            return "<a href=\"%s\">%s</a>" % (url, self.content_type.name,)
        else:
            return "<s>%s</s>" % self.content_type.name
    
    def name_link(self):
        t = self.id
        self.move_to_present()
        if self.exists():
            url = self.url()
            self.move(t)
            return "<a href=\"%s\">%s</a>" % (url,
                                              unicode(self.get_object()),)
        else:
            return "(deleted)"
    
    def field_repr(self, field):
        if field in self.fields:
            return unicode(self.get(field))
        else:
            return self.get_pervert_instance(field).name_link()





