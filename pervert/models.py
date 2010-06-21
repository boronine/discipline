# -*- coding: utf-8 -*-
import cPickle
import uuid
import copy

from django.db.models import *
from django.db.models.query_utils import CollectedObjects
from django.contrib.auth.models import User, UserManager
from django.db.models.signals import post_save, post_delete
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core import urlresolvers
import settings

from pervert.middleware import threadlocals

def post_save_handler(instance):

    fields = []
    fks = []
    mods = []

    for field in instance.__class__._meta.fields:
        if field.name == "uid": continue
        fields.append(field.name)
        if field.__class__.__name__ == "ForeignKey":
            fks.append(field.name)

    # The object has been created at least once
    if CreationCommit.objects.filter(object_uid=instance.uid):
        mods = []
        inst = TimeMachine(instance.uid)
        for field in fields:
            if inst.get(field) != getattr(instance, field):
                mods.append(field)
        # Make sure there are actual changes
        if inst.exists and not mods: return

    # The object doesn't exist
    if (not CreationCommit.objects.filter(object_uid=instance.uid)
        or not inst.exists):
        action = Action.objects.create(
            object_uid = instance.uid,
            action_type = "cr"
        )
        CreationCommit.objects.create(
            object_uid = instance.uid,
            action = action,
            content_type = ContentType.objects.get_for_model(instance.__class__)
        )
        # Create a modcommit for everything
        if not mods: mods = fields
    else: 
        action = Action.objects.create(
            object_uid = instance.uid,
            action_type = "md"
        )

    # Create ModificationCommit for each modification
    for field in mods:
        if field in fks:
            value = getattr(instance,field).uid
        else:
            value = cPickle.dumps(getattr(instance,field))
        ModificationCommit.objects.create(
            object_uid = instance.uid,
            action = action,
            key = field,
            value = value
        )

    return action
    
def post_delete_handler(sender, **kwargs):
    
    if not issubclass(sender, AbstractPervert): return

    instance = kwargs["instance"]

    action = Action.objects.create(
        object_uid = instance.uid,
        action_type = "dl"
    )

    DeletionCommit(
        object_uid = instance.uid,
        action = action,
    ).save()

    return action

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

class UUIDField(CharField):

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 32
        kwargs["db_index"] = True
        kwargs["primary_key"] = True
        super(UUIDField, self).__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name):
        assert not cls._meta.has_auto_field
        super(UUIDField, self).contribute_to_class(cls, name)
        cls._meta.has_auto_field = True
        cls._meta.auto_field = self

# Allow South to deal with our custom field
from south.modelsinspector import add_introspection_rules
add_introspection_rules([], ["^pervert\.models\.UUIDField"])

class AbstractPervert(Model):
    
    uid = UUIDField()

    class Meta:
        abstract = True
    
    # I use signals for deletion because when deletion cascades to
    # related objects, Django doesn't call each object's delete method
    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid4().hex
        out = super(AbstractPervert, self).save(*args, **kwargs)
        post_save_handler(self)
        return out

    def save_and_return_action(self):
        super(AbstractPervert, self).save()
        return post_save_handler(self)


class Action(Model):

    editor = ForeignKey(
        Editor, 
        related_name = "commits",
        db_index = True
    )

    when = DateTimeField(
        auto_now = True,
        verbose_name = "commit time",
        db_index = True
    )

    reverted = OneToOneField(
        "Action",
        related_name = "reverts",
        db_index = True,
        null = True
    )

    object_uid = CharField(
        max_length = 32,
        db_index = True
    )

    action_type = CharField(
        max_length = 2,
        db_index = True
    )

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

    def __unicode__(self):
        return "%s: %s" % (unicode(self.editor), unicode(self.when))
    
    def description(self):

        inst = self.timemachine.presently

        if self.action_type == "dl":
            return "Deleted %s" % inst.content_type.name
        if self.action_type == "cr":
            return "Created %s" % inst.type_link()
        else:
            return "Modified %s" % inst.type_link()

    description.allow_tags = True
    
    # To save database queries
    __timemachine = False

    def __get_timemachine(self):
        """
        Return a TimeMachine for the object on which this action was performed
        and at the time of this action.
        """
        if not self.__timemachine:
            self.__timemachine = TimeMachine(
                self.object_uid,
                self.id
            )

        return self.__timemachine.at(self.id)

    timemachine = property(__get_timemachine)

    def __get_is_revertible(self):

        # If it was already reverted
        if self.reverted:
            return False

        errors = []
        inst = self.timemachine

        if self.action_type in ["dl", "md"]:
            # If undoing deletion, make sure it actually doesn't exist
            if self.action_type == "dl" and inst.presently.exists:
                errors.append(
                    "Cannot undo action %d: the %s you are trying to"
                    " recreate already exists"
                    % (self.id,
                       inst.content_type.name,))
            # The only problem we can have by reversing this action
            # is that some of its foreignkeys could be pointing to
            # objects that have since been deleted.
            check_here = inst.at(self.id-1)
            for field in inst.foreignkeys:
                fk = check_here.get_timemachine_instance(field)
                if not fk.exists:
                    errors.append(
                        "Cannot undo action %d: the %s used to link to"
                        " a %s that has since been deleted"
                        % (self.id,
                           inst.content_type.name,
                           fk.content_type.name,))

        else: # self.action_type == "cr"
            # Make sure it doesn't actually exist
            if not self.timemachine.presently.exists:
                errors.append(
                    "Cannot undo action %d: the %s you are trying"
                    " to delete doesn't currently exist"
                    % (self.id, inst.content_type.name,))
            # The only problem we can have by undoing this action is
            # that it could have foreignkeys pointed to it, so deleting
            # it will cause deletion of other objects
            else:
                links = [rel.get_accessor_name() 
                         for rel in inst.get_object()._meta.get_all_related_objects()]
                for link in links:
                    objects = getattr(inst.get_object(), link).all()
                    for rel in objects:
                        errors.append(
                            "Cannot undo action %d: you are trying to"
                            " delete a %s that has a %s pointing to it"
                            % (self.id, 
                               inst.content_type.name,
                               ContentType.objects.get_for_model(rel.__class__),))

        self.__undo_errors = errors
        return (len(errors) == 0)

    is_revertible = property(__get_is_revertible)

    def __get__undo_errors(self):
        if self.__undo_errors == None: self._get__is_revertible()
        return self.__undo_errors

    undo_errors = property(__get__undo_errors)

    def undo(self):
        inst = self.timemachine
        if not self.is_revertible:
            raise PervertError("You tried to undo a non-revertible action! "
                               "Check action.is_revertible and action.undo_errors"
                               " before trying to undo.")

        if self.action_type == "dl":
            obj = inst.recreate()
            self.reverted = obj.save_and_return_action()
            self.save()
        elif self.action_type == "md":
            # Restore as it was *before* the modification
            obj = inst.at(self.id - 1).restore()
            self.reverted = obj.save_and_return_action()
            self.save()
        else:
            inst.get_object().delete()
            # This is safe from race conditions but still a pretty inelegant
            # solution. I can't figure out a different way to find the last action
            # because delete handler *has* to be in a signal
            self.reverted = DeletionCommit.objects.filter(
                object_uid = self.object_uid
            ).order_by("-id")[0].action
            self.save()

    def status(self):
        text = ""
        # Turns out that is related field in null, Django
        # doesn't even make it a property of the object
        if hasattr(self, "reverts"):
            text += '(reverts <a href="%s">#%s</a>)<br/>' % (
                self.reverts.get_absolute_url(),
                self.reverts.id
            )
        if self.reverted:
            text += '(reverted in <a href="%s">#%s</a>)<br/>' % (
                self.reverted.get_absolute_url(),
                self.reverted.id
            )
        return text
    
    status.allow_tags = True

    def get_absolute_url(self):
        return urlresolvers.reverse(
            "admin:pervert_action_change",
            args = (self.id,)
        ) 

    def details(self):
        text = ""
        inst = self.timemachine

        # If deleted or created, show every field, otherwise only
        # the modified
        if self.action_type in ["dl","cr"]:
            fields = inst.fields + inst.foreignkeys
        else: fields = [i.key for i in self.modification_commits.all()]

        for field in fields:
            text += "<strong>%s</strong>: " % field

            # If modified, show what it was like one step earlier
            if self.action_type == "md":
                text += "%s &#8594; " % inst.at(self.id - 1).field_repr(field)

            text += inst.field_repr(field) + "<br/>"

        return text   

    details.allow_tags = True

    def save(self, commit=True, **kwargs):
        editor = Editor.objects.get(user = threadlocals.get_current_user())
        self.editor = editor
        super(Action, self).save(**kwargs)

class CreationCommit(Model):

    content_type = ForeignKey(
        ContentType,
        db_index = True
    )
    object_uid = CharField(
        max_length = 32,
        db_index = True
    )
    action = ForeignKey(
        Action, 
        related_name = "creation_commits",
        db_index = True
    )

    def __unicode__(self):
        return "%s %s" % (self.content_type.name, self.object_uid,)

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class DeletionCommit(Model):

    object_uid = CharField(
        max_length = 32,
        db_index = True
    )
    action = ForeignKey(
        Action, 
        related_name = "deletion_commits",
        db_index = True
    )

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class ModificationCommit(Model):

    object_uid = CharField(
        max_length = 32,
        db_index = True
    )
    action = ForeignKey(
        Action, 
        related_name = "modification_commits",
        db_index = True
    )
    key = CharField(
        max_length = 30,
        null = True
    )
    value = TextField(null=True)
 
    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

class TimeMachine:
    """
    Use this to find the state of objects at different moments in time
    """
    def __init__(self, uid, step=None, info=None):

        self.uid = uid

        if not step: step = self.__present()

        self.step = step 

        if not info:
            info = self.__update_information()
        else:
            self.info = info
            for key in info.keys():
                setattr(self, key, info[key])

    def __update_information(self):

        info = {}

        info["actions_count"] = Action.objects.count()
        info["fields"] = []
        info["foreignkeys"] = []
        
        info["creation_times"] = []
        info["deletion_times"] = []

        info["content_type"] = None

        # Find object type and when it was created

        for ccommit in CreationCommit.objects.filter(object_uid=self.uid):
            info["creation_times"].append(ccommit.action.id)
        info["creation_times"].sort()

        for dcommit in DeletionCommit.objects.filter(object_uid=self.uid):
            info["deletion_times"].append(dcommit.action.id)
        info["deletion_times"].sort()

        try:
            info["content_type"] = ccommit.content_type
        except NameError:
            raise PervertError("You tried to make a TimeMachine out of"
                               " an object that doesn't exist!")

        # Create lists with fields
        for field in info["content_type"].model_class()._meta.fields:
            if field.name == "uid":
                continue
            if field.__class__.__name__ == "ForeignKey":
                info["foreignkeys"].append(field.name)
            else:
                info["fields"].append(field.name)

        self.info = info

        for key in info.keys():
            setattr(self, key, info[key])
    
    def at(self, step):
        """
        Returns an instance of the same object at a different step.
        """
        return TimeMachine(
            self.uid,
            step,
            copy.deepcopy(self.info)
        )
        
    def __presently(self):
        return self.at(self.__present())
    
    presently = property(__presently)

    def __present(self):
        if Action.objects.count():
            return Action.objects.all()[0].id
        else: return 0

    def get_modcommit(self, key):
        """
        Return the last modcommit of the given field
        """
        try:
            modcommit = ModificationCommit.objects.filter(
                object_uid = self.uid,
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
            return TimeMachine(uid = modcommit.value).get_object()
        except self.content_type.DoesNotExist:
            raise PervertError("When restoring a ForeignKey, the " \
                "%s %s was not found." % (self.content_type.name, self.uid))

    def get_timemachine_instance(self, key):
        """
        Returns the pervert instance of the object that is/was related
        to this one by the given foreignkey
        """
        modcommit = self.get_modcommit(key)
        return TimeMachine(uid = modcommit.value)

    def get_object(self):
        return self.content_type.model_class().objects.get(uid = self.uid)

    def __exists(self):
        
        # Make sure no actions have been created since!
        if Action.objects.count() != self.actions_count:
            self.__update_information()

        created_on = None
        deleted_on = None
        
        for c in reversed(self.creation_times):
            if c <= self.step:
                created_on = c
                break

        if not created_on: return False

        for d in reversed(self.deletion_times):
            if d <= self.step:
                deleted_on = d
                break

        if deleted_on > created_on: return False

        return True
    
    exists = property(__exists)

    def recreate(self):
        """ 
        If the object was deleted, recreate it as it was at this point in time.
        Returns the instance.
        """

        new = self.content_type.model_class()(uid = self.uid)
        self.restore(new)

        return new
        
    __current_action = None

    def __get_current_action(self):
        if not self._current_action:
            self.__current_action = Action.objects.get(id = self.step)
        return self.__current_action

    current_action = property(__get_current_action)

    def restore(self, obj=None):
        """ 
        Restore all of the object attributes to the attributes. Returns the
        instance.
        """
        if not obj:
            obj = self.content_type.model_class().objects.get(uid=self.uid)
        for field in self.fields + self.foreignkeys:
            obj.__setattr__(field, self.get(field))

        return obj
    
    def __unicode__(self):
        return "%s (%s)" % (unicode(self.content_type), self.uid,)
            
    def url(self):
        if self.exists:
            return urlresolvers.reverse(
                "admin:%s_%s_change" % (self.content_type.app_label,
                                        self.content_type.model),
                args = (self.get_object().uid,))
            
        else:
            return None

    def type_link(self):
        """ 
        Provides a link with the object type as text. If the object doesn't
        exist, the link is crossed out.
        """

        url = self.url()
        if url:
            return "<a href=\"%s\">%s</a>" % (url, self.content_type.name,)
        else:
            return "<s>%s</s>" % self.content_type.name
    
    def name_link(self):
        if self.presently.exists:
            url = self.url()
            return "<a href=\"%s\">%s</a>" % (url,
                                              unicode(self.get_object()),)
        else:
            return "(deleted)"
    
    def field_repr(self, field):
        if field in self.fields:
            return unicode(self.get(field))
        else:
            return self.get_timemachine_instance(field).name_link()

class SchemaState(Model):
    when = DateTimeField(auto_now=True)
    app = CharField(max_length=50)
    schema = TextField()

from south.signals import post_migrate
from south.models import MigrationHistory

def register_schema_change(**kwargs):
    """
    Get the new migration and put its schema info into
    the pervert database.
    """

    last = MigrationHistory.objects.all()[0].get_migration()

    SchemaState.objects.create(
        schema = cPickle.dumps(last.migration_class().models),
        app = kwargs["app"]
    )
       
post_migrate.connect(register_schema_change)

