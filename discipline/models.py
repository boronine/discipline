# -*- coding: utf-8 -*-

import cPickle
import uuid
import copy
try:
    import json
except ImportError:
    import simplejson as json 
import datetime

from django.db.models import *
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core import urlresolvers

__all__ = (
    "DisciplinedModel", 
    "Editor", 
    "Action", 
    "SchemaState",
    "CreationCommit",
    "ModificationCommit",
    "DeletionCommit",
    "TimeMachine",
    "DisciplineException",
    "DisciplineIntegrityError",
)

def save_object(instance, editor):

    fields = []
    fks = []
    mods = []

    for field in instance.__class__._meta.fields:
        if field.name == "uid": continue
        fields.append(field.name)
        if field.__class__.__name__ == "ForeignKey":
            fks.append(field.name)

    # Existed at least at some point in time
    existed = bool(CreationCommit.objects.filter(object_uid=instance.uid))

    if existed:
        mods = []
        inst = TimeMachine(instance.uid)
        for field in fields:
            if inst.get(field) != getattr(instance, field):
                mods.append(field)
        # Make sure there are actual changes
        if inst.exists and not mods: 
            raise DisciplineException("You are trying to save an " \
                "object with no modifications.")

    # The object doesn't exist
    if not existed or not inst.exists:

        action = Action.objects.create(
            object_uid = instance.uid,
            action_type = "cr",
            editor = editor,
        )

        CreationCommit.objects.create(
            object_uid = instance.uid,
            action = action,
            content_type = ContentType.objects \
                .get_for_model(instance.__class__)
        )
        # Create a modcommit for everything
        if not mods: mods = fields
    else: 
        action = Action.objects.create(
            object_uid = instance.uid,
            action_type = "md",
            editor = editor,
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

class DisciplineException(Exception):
    pass

class DisciplineIntegrityError(Exception):
    pass

class Editor(Model):

    user = ForeignKey(User, unique=True, null=True)

    def __unicode__(self):
        text = self.user.first_name + " " + self.user.last_name
        text = text.strip()
        if not text:
            text = u"Anonymous %d" % self.user.id 
        return text

    def save_object(self, obj):
        """Save an object with Discipline

        Only argument is a Django object. This function saves the object
        (regardless of whether it already exists or not) and registers with
        Discipline, creating a new Action object. Do not use obj.save()!
        """
        obj.save()
        try:
            save_object(obj, editor=self)
        except DisciplineException:
            pass

    def delete_object(self, obj, post_delete=False):
        """Delete an object with Discipline

        Only argument is a Django object. Analogous to Editor.save_object.
        """
        # Collect related objects that will be deleted by cascading
        links = [rel.get_accessor_name() for rel in \
                 obj._meta.get_all_related_objects()]
        # Recursively delete each of them
        for link in links:
            objects = getattr(obj, link).all()
            for o in objects:
                self.delete_object(o, post_delete)
        # Delete the actual object
        self._delete_object(obj, post_delete)

    def _delete_object(self, obj, post_delete):
        action = Action.objects.create(
            object_uid = obj.uid,
            action_type = "dl",
            editor = self,
        )
        DeletionCommit(
            object_uid = obj.uid,
            action = action,
        ).save()
        if not post_delete: obj.delete()

    def undo_action(self, action):
        """Undo the given action"""
        action.undo(self)

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
    add_introspection_rules([], ["^discipline\.models\.UUIDField"])
except ImportError:
    pass

class DisciplinedModel(Model):
    
    uid = UUIDField()

    class Meta:
        abstract = True
    
class Action(Model):

    """Represents a unit of change at a specific point in time by a 
    specific editor."""

    editor = ForeignKey(
        "Editor", 
        related_name = "commits",
        db_index = True,
    )

    when = DateTimeField(
        auto_now_add = True,
        verbose_name = "commit time",
        db_index = True,
    )

    reverted = OneToOneField(
        "Action",
        related_name = "reverts",
        db_index = True,
        null = True,
    )

    object_uid = CharField(
        max_length = 32,
        db_index = True,
    )

    action_type = CharField(
        max_length = 2,
        db_index = True,
    )

    class Meta:
        # Most of the time you will need most recent
        ordering = ["-when"]
        get_latest_by = "id"

    def __unicode__(self):
        return "%s: %s" % (unicode(self.editor), unicode(self.when))
    
    def _description(self):
        """A concise html explanation of this Action."""

        inst = self.timemachine.presently

        if self.action_type == "dl":
            return "Deleted %s" % inst.content_type.name
        elif self.action_type == "cr":
            return "Created %s" % inst._object_type_html()
        else:
            return "Modified %s" % inst._object_type_html()

    _description.allow_tags = True
    
    # To save database queries
    __timemachine = False

    def __get_timemachine(self):
        """Return a TimeMachine for the object on which this action was 
        performed and at the time of this action."""
        if not self.__timemachine:
            self.__timemachine = TimeMachine(
                self.object_uid,
                step = self.id,
            )

        return self.__timemachine.at(self.id)

    timemachine = property(__get_timemachine)

    def __get_is_revertible(self):
        """Return a boolean representing whether this Action is revertible
        or not"""

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
                % (self.id,
                   inst.content_type.name,)]
           return False


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
            check_here = inst.at_previous_action
            for field in inst.foreignkeys:
                fk = check_here.get_timemachine_instance(field)
                # If the ForeignKey doesn't have a value
                if not fk: continue
                if not fk.exists:
                    errors.append(
                        "Cannot undo action %s: the %s used to link to"
                        " a %s that has since been deleted"
                        % (self.id,
                           inst.content_type.name,
                           fk.content_type.name,))

        else: # self.action_type == "cr"
            # Make sure it actually exists
            if not self.timemachine.presently.exists:
                errors.append(
                    "Cannot undo action %s: the %s you are trying"
                    " to delete doesn't currently exist"
                    % (self.id, inst.content_type.name,))
            # The only problem we can have by undoing this action is
            # that it could have foreignkeys pointed to it, so deleting
            # it will cause deletion of other objects
            else:
                links = [rel.get_accessor_name() 
                         for rel in \
                         inst.get_object()._meta.get_all_related_objects()]
                for link in links:
                    objects = getattr(inst.get_object(), link).all()
                    for rel in objects:
                        errors.append(
                           "Cannot undo action %s: you are trying to"
                           " delete a %s that has a %s pointing to it" %
                           (self.id, 
                            inst.content_type.name,
                            ContentType.objects.get_for_model(rel.__class__),))

        self.__undo_errors = errors
        return (len(errors) == 0)

    is_revertible = property(__get_is_revertible)

    def __get__undo_errors(self):
        if self.__undo_errors == None: self._get__is_revertible()
        return self.__undo_errors

    undo_errors = property(__get__undo_errors)

    def undo(self, editor):
        """Create a new Action that undos the effects of this one, or,
        more accurately, reverts the object of this Action to the state
        at which it was right before the Action took place."""
        inst = self.timemachine
        if not self.is_revertible:
            raise DisciplineException("You tried to undo a non-revertible action! "
                               "Check action.is_revertible and action.undo_errors"
                               " before trying to undo.")

        if self.action_type == "dl":
            obj = inst.restore()
            self.reverted = save_object(obj, editor)
            self.save()
        elif self.action_type == "md":
            # Restore as it was *before* the modification
            obj = inst.at_previous_action.restore()
            self.reverted = save_object(obj, editor)
            self.save()
        else:
            editor.delete_object(inst.get_object())
            # This is safe from race conditions but still a pretty inelegant
            # solution. I can't figure out a different way to find the last action
            # for now
            self.reverted = DeletionCommit.objects.filter(
                object_uid = self.object_uid
            ).order_by("-action__id")[0].action
            self.save()

    def _status(self):
        """Return html saying whether this Action is reverted by another
        one or reverts another one."""
        text = ""
        # Turns out that is related field in null, Django
        # doesn't even make it a property of the object
        # http://code.djangoproject.com/ticket/11920
        if hasattr(self, "reverts"):
            text += '(reverts <a href="%s">%s</a>)<br/>' % (
                self.reverts.get_absolute_url(),
                self.reverts.id
            )
        if self.reverted:
            text += '(reverted in <a href="%s">%s</a>)<br/>' % (
                self.reverted.get_absolute_url(),
                self.reverted.id
            )
        return text
    
    _status.allow_tags = True

    def get_absolute_url(self):
        return urlresolvers.reverse(
            "admin:discipline_action_change",
            args = (self.id,)
        ) 

    def __summary(self):
        """A plaintext summary of the Action, useful for debugging."""
        text = "Time: %s\n" % self.when
        text += "Comitter: %s\n" % self.editor

        inst = self.timemachine.presently

        if self.action_type == "dl":
            text += "Deleted %s\n" % inst._object_type_text()
        elif self.action_type == "cr":
            text += "Created %s\n" % inst._object_type_text()
        else:
            text += "Modified %s\n" % inst._object_type_text()
        text += self._details(nohtml=True)
        return text

    summary = property(__summary)

    def _details(self, nohtml=False):
        """Return the html representation of the Action."""
        text = ""
        inst = self.timemachine

        # If deleted or created, show every field, otherwise only
        # the modified
        if self.action_type in ("dl","cr",):
            fields = inst.fields + inst.foreignkeys
        else: fields = [i.key for i in self.modification_commits.all()]

        for field in fields:
            if not nohtml:
                text += "<strong>%s</strong>: " % field
            else:
                text += "%s: " % field

            # If modified, show what it was like one step earlier
            if self.action_type == "md":
                if not nohtml:
                    text += "%s &#8594; " % \
                            inst.at_previous_action._field_value_html(field)
                else:
                    text += "%s -> " % \
                            inst.at_previous_action._field_value_text(field)

            if not nohtml:
                text += "%s<br/>" % inst._field_value_html(field)
            else:
                text += "%s\n" % inst._field_value_text(field)

        return text   

    _details.allow_tags = True

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
 
class TimeMachine:

    """Use this to find the state of objects at different moments in time.

    Constructor arguments:
    uid -- The value of the uid field of the object for which you want a
           TimeMachine.
    when -- A Python datetime object representing the time at which the 
           TimeMachine will be. (optional)
    step -- The value of the id field of an Action. The TimeMachine will be
           represent the time right after the Action. (Optional, by default
           the TimeMachine will be at present Action. Incompatible with the
           when argument.)

    """

    def __init__(self, uid, when=None, step=None, info=None):

        self.uid = uid

        if not when and not step: when = datetime.datetime.now()
        
        if when:
            self.when = when 

            try:
                self.step = Action.objects.filter(
                    when__lte = self.when
                )[0].id
            except IndexError:
                raise DisciplineException("You tried to get an a TimeMachine"
                        "at current action, but there is no action!")

        elif step:
            self.step = step
            self.when = Action.objects.get(id = step).when


        if not info:
            info = self.__update_information()
        else:
            self.info = info
            for key in info.keys():
                setattr(self, key, info[key])

        # Find the last SchemaState for this model in this app
        ss = SchemaState.objects.filter(when__lt = self.when)[0]\
                .get_for_content_type(self.content_type)

        self.model_exists = not not ss

        if not self.model_exists: 
            if sorted(self.creation_times)[0] <= self.step:
                raise DisciplineIntegrityError(
                    "%s with uid %s was created before the schema for its" \
                    " model was registered by Discipline (created: %s)." \
                    % (self.content_type.name, self.uid, self.when,)
                )
            return

        # Use it to find out which fields the model had at this point in time
        self.fields = ss["fields"]
        self.foreignkeys = ss["foreignkeys"]

    def __update_information(self):
        """Gether information that doesn't change at different points in
        time"""

        info = {}

        info["actions_count"] = Action.objects.count()
        
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
            raise DisciplineException("You tried to make a TimeMachine out of"
                               " an object that doesn't exist!")

        self.info = info

        for key in info.keys():
            setattr(self, key, info[key])
    
    def at(self, step):
        """Return a TimeMachine for the same object at a different time.

        Takes an integer argument representing the id field of an Action.
        Returns the TimeMachine at the time of that Action. (Less ambiguously:
        at the time right after the Action.

        """
        return TimeMachine(
            self.uid,
            step = step,
            info = copy.deepcopy(self.info)
        )
        
    def __presently(self):
        return self.at(Action.objects.order_by("-id")[0].id)
    
    presently = property(__presently)

    def __at_previous_action(self):
        return self.at(self.step - 1)

    at_previous_action = property(__at_previous_action)

    def _get_modcommit(self, key):
        """Return the last modcommit of the given field. If no
        modcommit exists (for example after a migration that created
        new fields) returns None.
        """
        try:
            return ModificationCommit.objects.filter(
                object_uid = self.uid,
                key = key,
                action__id__lte = self.step
            ).order_by("-action__id")[0]
        except IndexError:
            return None

    def get(self, key):
        """Return the value of a field.
        
        Take a string argument representing a field name, return the value of
        that field at the time of this TimeMachine. When restoring a 
        ForeignKey-pointer object that doesn't exist, raise 
        DisciplineException

        """
        modcommit = self._get_modcommit(key)
        if not modcommit: return None
        # If this isn't a ForeignKey, then just return the value
        if key not in self.foreignkeys:
            return cPickle.loads(str(modcommit.value))
        # If it is, then return the object instance
        try:
            return TimeMachine(uid = modcommit.value).get_object()
        except self.content_type.DoesNotExist:
            raise DisciplineException("When restoring a ForeignKey, the " \
                "%s %s was not found." % (self.content_type.name, self.uid))

    def get_timemachine_instance(self, key):
        """Return a TimeMachine for a related object.

        Take a string argument representing a ForeignKey field name, find what
        object was related to this one at the time of this TimeMachine and 
        return a TimeMachine for that related object.

        """
        modcommit = self._get_modcommit(key)
        if not modcommit: 
            return None
        return TimeMachine(uid = modcommit.value)

    def get_object(self):
        """Return the object of this TimeMachine"""
        return self.content_type.model_class().objects.get(uid = self.uid)

    def __exists(self):
        
        # Make sure no actions have been created since!
        if Action.objects.count() != self.actions_count:
            self.__update_information()

        created_on = None
        deleted_on = None

        # Get the *last* time that it was created
        for c in reversed(self.creation_times):
            if c <= self.step:
                created_on = c
                break

        if not created_on: return False

        # Get the *last* time that it was deleted
        for d in reversed(self.deletion_times):
            if d <= self.step:
                deleted_on = d
                break

        if deleted_on and deleted_on > created_on: return False

        return True
    
    exists = property(__exists)

    __current_action = None

    def __get_current_action(self):
        if not self.__current_action:
            self.__current_action = Action.objects.get(id = self.step)
        return self.__current_action

    current_action = property(__get_current_action)

    def restore(self, nosave=False):
        """Restore all of the object attributes to the attributes. Return the
        Django object.
        """
        if self.exists:
            obj = self.content_type.model_class().objects.get(uid=self.uid)
        else:
            obj = self.content_type.model_class()(uid=self.uid)
        for field in self.fields + self.foreignkeys:
            obj.__setattr__(field, self.get(field))
        if not nosave: obj.save()
        return obj
    
    def __unicode__(self):
        return "%s (%s)" % (unicode(self.content_type), self.uid,)
            
    def url(self):
        """Return the admin url of the object."""
        return urlresolvers.reverse(
            "admin:%s_%s_change" % (self.content_type.app_label,
                                    self.content_type.model),
            args = (self.get_object().uid,))
            

    def _object_type_html(self):
        """Return an html admin link with the object's type as text. If the 
        object doesn't exist, return the object's type crossed out.
        """

        if self.exists:
            return "<a href=\"%s\">%s</a>" % (self.url(), 
                                              self.content_type.name,)
        else:
            return "<s>%s</s>" % self.content_type.name
    
    def _object_name_html(self):
        """Return an html admin link with the object's name as text. If the 
        object doesn't exist, return "(deleted)".
        """
        if self.presently.exists:
            url = self.url()
            return "<a href=\"%s\">%s</a>" % (url,
                                              unicode(self.get_object()),)
        else:
            return "(deleted)"
    
    def _field_value_html(self, field):
        """Return the html representation of the value of the given field"""
        if field in self.fields:
            return unicode(self.get(field))
        else:
            return self.get_timemachine_instance(field)._object_name_html()

    def _field_value_text(self, field):
        """Return the html representation of the value of the given field"""
        if field in self.fields:
            return unicode(self.get(field))
        else:
            return self.get_timemachine_instance(field)._object_name_text()

    def _object_name_text(self):
        """Return the object's unicode representation. If the object doesn't 
        exist, return "(deleted)".
        """
        if self.presently.exists:
            return unicode(self.get_object())
        else:
            return "(deleted)"

    def _object_type_text(self):
        """Return the name of the object's content type."""
        return self.content_type.name

class SchemaState(Model):

    """Record the state of each relevant model's fields at a point in time.

    Fields:
    when -- BooleanField representing the time of this snapshot
    state -- TextField holding the json representation of the schema state.
             Do not use this field, use public methods.

    """

    when = DateTimeField(auto_now_add=True, verbose_name="Saved")
    state = TextField()

    def get_for_content_type(self, ct):
        """Return the schema for the model of the given ContentType object"""
        try:
            return json.loads(self.state)[ct.app_label][ct.model]
        except KeyError:
            return None

    class Meta:
        ordering = ["-when"]

    def html_state(self):
        """Display state in HTML format for the admin form."""
        ret = ""
        state = json.loads(self.state)
        for (app, appstate) in state.items():
            for (model, modelstate) in appstate.items():
                ret += "<p>%s.models.%s</p>" % (app, model,)
                ret += "<ul>"
                for field in modelstate["fields"] + ["uid"]:
                    ret += "<li>%s</li>" % field
                for fk in modelstate["foreignkeys"]:
                    ret += "<li>%s (foreign key)</li>" % fk
                ret += "</ul>"
        return ret

    html_state.allow_tags = True
    html_state.short_description = "State"



