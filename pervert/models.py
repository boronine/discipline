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
        action = Action.objects.create()
        CreationCommit.objects.create(
            object_uid = instance.uid,
            action = action,
            content_type = ContentType.objects.get_for_model(instance.__class__)
        )
        # Create a modcommit for everything
        if not mods: mods = fields
    else: action = Action.objects.create()

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
    action = Action.objects.create()

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

class AbstractPervert(Model):
    
    uid = CharField(
        max_length = 32, 
        default = get_uuid,
        db_index = True,
        help_text = "The UUID is used for relationships between objects.",
        verbose_name = "unique ID",
        primary_key = True
    )

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

    class Meta:
        # Most of the time you will need most recent
        ordering = ['-id']

    def __unicode__(self):
        return "%s: %s" % (unicode(self.editor), unicode(self.when))
    
    def description(self):

        self.__gather_info()

        inst = self.timemachine.presently

        if self.__action_type == "dl":
            return "Deleted %s" % inst.content_type.name
        if self.__action_type == "cr":
            return "Created %s" % inst.type_link()
        else:
            return "Modified %s" % inst.type_link()

    description.allow_tags = True
    
    def __gather_info(self):
        if not self.__object_uid:
            if self.creation_commits.count():
                self.__object_uid = self.creation_commits.all()[0].object_uid
                self.__action_type = "cr"
            elif self.deletion_commits.count():
                self.__object_uid = self.deletion_commits.all()[0].object_uid
                self.__action_type = "dl"
            elif self.modification_commits.count():
                self.__object_uid = self.modification_commits.all()[0].object_uid
                self.__action_type = "md"
            else:
                # Django probes every object for all properties, so it, in fact,
                # is possible for an action to have no microcommits linking to
                # it.
                pass

    # These are all lazy to cut down on databsse queries
    __object_uid = None
    __action_type = None
    __timemachine = None
    __is_revertible = None
    __undo_errors = None

    def __get_timemachine(self):

        if not self.__timemachine:
            self.__timemachine = TimeMachine(
                self.object_uid,
                self.id
            )
        return self.__timemachine

    timemachine = property(__get_timemachine)

    def __get__object_uid(self):
        self.__gather_info()
        return self.__object_uid
    
    object_uid = property(__get__object_uid) 

    def __get__action_type(self):
        self.__gather_info()
        return self.__action_type

    action_type = property(__get__action_type)

    def __get_is_revertible(self):

        if self.__is_revertible != None: return self.__is_revertible
        
        # If it was already reverted
        if self.reverted:
            self.__is_revertible = False
            return

        errors = []
        inst = self.timemachine

        if self.__action_type in ["dl", "md"]:
            # If undoing deletion, make sure it actually doesn't exist
            if self.__action_type == "dl" and inst.presently.exists:
                errors.append(
                    "Cannot undo action %d: the %s you are trying to"
                    " recreate already exists"
                    % (self.id,
                       inst.content_type.name,))
            # The only problem we can have by reversing this action
            # is that some of its foreignkeys could be pointing to
            # objects that have since been deleted.
            for field in inst.foreignkeys:
                fk = inst.get_timemachine_instance(field)
                if not fk.exists:
                    errors.append(
                        "Cannot undo action %d: the %s used to link to"
                        " a %s that has since been deleted"
                        % (self.id,
                           inst.content_type.name,
                           fk.content_type.name,))

        else: # self.__action_type == "cr"
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
        self.__is_revertible = (len(errors) == 0)
        return self.__is_revertible

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
        self.__gather_info()
        text = ""
        inst = self.timemachine

        # If deleted or created, show every field, otherwise only
        # the modified
        if self.__action_type in ["dl","cr"]:
            fields = inst.fields + inst.foreignkeys
        else: fields = [i.key for i in self.modification_commits.all()]

        for field in fields:
            text += "<strong>%s</strong>: " % field

            # If modified, show what it was like one step earlier
            if self.__action_type == "md":
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

        if not info: info = self.__get_information()

        self.info = info

        for key in info.keys():
            setattr(self, key, info[key])

        if not step: step = self.__present()

        self.step = step 

    def __get_information(self):

        info = {}

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

        return info
    
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
            print ":", self.get(field)

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


