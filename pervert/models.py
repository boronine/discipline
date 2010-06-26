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
import datetime

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

    # Create MicroCommit for each modification
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

def get_uuid():
    return uuid.uuid4().hex

class UUIDField(CharField):

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 32
        kwargs["db_index"] = True
        kwargs["primary_key"] = True
        kwargs["default"] = get_uuid
        kwargs["verbose_name"] = "Unique ID"
        super(UUIDField, self).__init__(*args, **kwargs)

    def contribute_to_class(self, cls, name):
        assert not cls._meta.has_auto_field
        super(UUIDField, self).contribute_to_class(cls, name)
        cls._meta.has_auto_field = True
        cls._meta.auto_field = self

# Allow South to deal with our custom field
try:
    from south.modelsinspector import add_introspection_rules
    add_introspection_rules([], ["^pervert\.models\.UUIDField"])
except ImportError:
    pass

class AbstractPervert(Model):
    
    uid = UUIDField()

    class Meta:
        abstract = True
    
    # I use signals for deletion because when deletion cascades to
    # related objects, Django doesn't call each object's delete method
    def save(self, *args, **kwargs):
        out = super(AbstractPervert, self).save(*args, **kwargs)
        post_save_handler(self)
        return out

    def save_and_return_action(self):
        super(AbstractPervert, self).save()
        return post_save_handler(self)


class Action(Model):

    uid = UUIDField()

    editor = ForeignKey(
        Editor, 
        related_name = "commits",
        db_index = True
    )

    when = DateTimeField(
        auto_now_add = True,
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
        ordering = ['-when']

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
                self.when
            )

        return self.__timemachine.at(self.when)

    timemachine = property(__get_timemachine)

    def __get_is_revertible(self):

        # If it was already reverted
        if self.reverted:
            return False

        errors = []
        inst = self.timemachine
        
        if inst.fields != inst.presently.fields or \
           inst.foreignkeys != inst.presently.foreignkeys:
           self.__undo_errors = [
               "Cannot undo action %s. The database schema"
               " for %s has changed"
                % (self.uid,
                   inst.content_type.name,)]
           return False


        if self.action_type in ["dl", "md"]:
            # If undoing deletion, make sure it actually doesn't exist
            if self.action_type == "dl" and inst.presently.exists:
                errors.append(
                    "Cannot undo action %d: the %s you are trying to"
                    " recreate already exists"
                    % (self.uid,
                       inst.content_type.name,))
            # The only problem we can have by reversing this action
            # is that some of its foreignkeys could be pointing to
            # objects that have since been deleted.
            check_here = inst.at_previous_action
            for field in inst.foreignkeys:
                fk = check_here.get_timemachine_instance(field)
                # If the ForeignKey doesn't have a value
                if not fk: continue
                if not fk.exists:
                    errors.append(
                        "Cannot undo action %s: the %s used to link to"
                        " a %s that has since been deleted"
                        % (self.uid,
                           inst.content_type.name,
                           fk.content_type.name,))

        else: # self.action_type == "cr"
            # Make sure it actually exists
            if not self.timemachine.presently.exists:
                errors.append(
                    "Cannot undo action %s: the %s you are trying"
                    " to delete doesn't currently exist"
                    % (self.uid, inst.content_type.name,))
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
                            "Cannot undo action %s: you are trying to"
                            " delete a %s that has a %s pointing to it"
                            % (self.uid, 
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
            obj = inst.at_previous_action.restore()
            self.reverted = obj.save_and_return_action()
            self.save()
        else:
            inst.get_object().delete()
            # This is safe from race conditions but still a pretty inelegant
            # solution. I can't figure out a different way to find the last action
            # because delete handler *has* to be in a signal
            self.reverted = DeletionCommit.objects.filter(
                object_uid = self.object_uid
            ).order_by("-action__when")[0].action
            self.save()

    def status(self):
        text = ""
        # Turns out that is related field in null, Django
        # doesn't even make it a property of the object
        if hasattr(self, "reverts"):
            text += '(reverts <a href="%s">%s</a>)<br/>' % (
                self.reverts.get_absolute_url(),
                self.reverts.uid
            )
        if self.reverted:
            text += '(reverted in <a href="%s">%s</a>)<br/>' % (
                self.reverted.get_absolute_url(),
                self.reverted.uid
            )
        return text
    
    status.allow_tags = True

    def get_absolute_url(self):
        return urlresolvers.reverse(
            "admin:pervert_action_change",
            args = (self.uid,)
        ) 

    def details(self):
        text = ""
        inst = self.timemachine

        # If deleted or created, show every field, otherwise only
        # the modified
        if self.action_type in ("dl","cr",):
            fields = inst.fields + inst.foreignkeys
        else: fields = [i.key for i in self.modification_commits.all()]

        for field in fields:
            text += "<strong>%s</strong>: " % field

            # If modified, show what it was like one step earlier
            if self.action_type == "md":
                text += "%s &#8594; " % inst.at_previous_action.field_repr(field)

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
    uid = UUIDField()

    def __unicode__(self):
        return "%s %s" % (self.content_type.name, self.object_uid,)

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
    uid = UUIDField()

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
    uid = UUIDField()
 
class TimeMachine:
    """
    Use this to find the state of objects at different moments in time
    """
    def __init__(self, uid, when=None, info=None):

        self.uid = uid

        if not when: when = datetime.datetime.now()

        self.when = when 

        if not info:
            info = self.__update_information()
        else:
            self.info = info
            for key in info.keys():
                setattr(self, key, info[key])

        # Find the last SchemaState for this model in this app
        ss = SchemaState.objects.filter(when__lt = self.when)[0]\
                .get_for_content_type(self.content_type)

        # Use it to find out which fields the model had at this point in time
        self.fields = ss["fields"]
        self.foreignkeys = ss["foreignkeys"]

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
            info["creation_times"].append(ccommit.action.when)
        info["creation_times"].sort()

        for dcommit in DeletionCommit.objects.filter(object_uid=self.uid):
            info["deletion_times"].append(dcommit.action.when)
        info["deletion_times"].sort()

        try:
            info["content_type"] = ccommit.content_type
        except NameError:
            raise PervertError("You tried to make a TimeMachine out of"
                               " an object that doesn't exist!")

        self.info = info

        for key in info.keys():
            setattr(self, key, info[key])
    
    def at(self, when):
        """
        Returns an instance of the same object at a different time.
        """
        return TimeMachine(
            self.uid,
            when,
            copy.deepcopy(self.info)
        )
        
    def __presently(self):
        return self.at(datetime.datetime.now())
    
    presently = property(__presently)

    def __at_previous_action(self):
        try:
            prev_action = Action.objects.filter(
                when__lte = self.when
            )[1]
            return self.at(prev_action.when)
        except IndexError:
            raise PervertError("You tried to get an a TimeMachine at previous "
                               "action, but no previous action exists!")

    at_previous_action = property(__at_previous_action)

    def get_modcommit(self, key):
        """
        Return the last modcommit of the given field. If no
        modcommit exists (for example after a migration that created
        new fields) returns None.
        """
        try:
            return ModificationCommit.objects.filter(
                object_uid = self.uid,
                key = key,
                action__when__lte = self.when
            ).order_by("-action__when")[0]
        except IndexError:
            return None

    def get(self, key):
        """
        Returns the value of a field at the TimeMachine's current time.
        """
        modcommit = self.get_modcommit(key)
        if not modcommit: return None
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
        to this one by the given foreignkey name.
        """
        modcommit = self.get_modcommit(key)
        if not modcommit: return None
        return TimeMachine(uid = modcommit.value)

    def get_object(self):
        return self.content_type.model_class().objects.get(uid = self.uid)

    def __exists(self):
        
        # Make sure no actions have been created since!
        if Action.objects.count() != self.actions_count:
            self.__update_information()

        created_on = None
        deleted_on = None

        # Get the *last* time that it was created
        for c in reversed(self.creation_times):
            if c <= self.when:
                created_on = c
                break

        if not created_on: return False

        # Get the *last* time that it was deleted
        for d in reversed(self.deletion_times):
            if d <= self.when:
                deleted_on = d
                break

        if deleted_on and deleted_on > created_on: return False

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
            self.__current_action = Action.objects.get(when_lte = self.when)
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

import json

class SchemaState(Model):

    when = DateTimeField(auto_now_add=True)
    state = TextField()

    def schema_state(self):
        return json.loads(self.state)

    def get_for_content_type(self, ct):
        return json.loads(self.state)[ct.app_label][ct.model_class().__name__]

    class Meta:
        ordering = ["-when"]

    def html_state(self):
        """
        Display state in HTML format for the admin form
        """
        ret = ""
        state = json.loads(self.state)
        for (app, appstate) in state.items():
            for (model, modelstate) in appstate.items():
                ret += "<p>%s.models.%s</p>" % (app, model,)
                ret += "<ul>"
                for field in modelstate["fields"] + ["uid"]:
                    ret += "<li>%s</li>" % field
                for fk in modelstate["fks"]:
                    ret += "<li>%s (foreign key)</li>" % fk
                ret += "</ul>"
        return ret

    html_state.allow_tags = True
    html_state.short_description = "State"



