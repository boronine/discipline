API Reference
=============

.. module:: discipline.models

:class:`~Action` -- `A unit of change`
--------------------------------------------------------

.. class:: Action

An :class:`~Action` object represents a single unit of change (creation, modification, deletion) done by a single :class:`~Editor` at a specific point in time.

.. attribute:: Action.editor

A :class:`ForeignKey` for the :class:`Editor` that performed this action.

.. attribute:: Action.when

A :class:`DateTimeField` representing the time when the action was performed.

.. attribute:: Action.reverted
.. attribute:: Action.reverts

A self-referencing :class:`OneToOneField`. If :class:`~Action` *A* reverts :class:`~Action` *B*, ``A.reverts`` will equal *B* and ``B.reverted`` will equal *A*.

.. attribute:: Action.creation_commits 
.. attribute:: Action.modification_commits 
.. attribute:: Action.deletion_commits

The :class:`~CreationCommit`, :class:`~ModificationCommit`, :class:`~DeletionCommit` objects, respectfully, associated with this action.

.. attribute:: Action.timemachine

An instance of the :class:`~TimeMachine` object for the object on which this action was performed. The time is set automatically to the time of this action.

.. attribute:: Action.object_uid

The UUID of the object that the action was performed on.

.. attribute:: Action.action_type

Either ``"cr"``, ``"md"`` or ``"dl"`` for creation, modification and deletion, respectfully.

.. attribute:: Action.is_revertible

A boolean representing whether it is possible to undo the action or not.

.. attribute:: Action.undo_errors

If it is not possible to undo the action, this will be a list of strings, each the text of an error, explaining why it is not possible.

.. attribute:: Action.summary

A plaintext summary of the action: includes the editor, the time, the type and each modified field (if modification or creation). Useful for debugging::

    >>> print Action.objects.all()[0]
    Time: 2010-07-04 00:11:53.520869
    Comitter: John Doe
    Modified musician
    name: Robert Frip -> Robert Fripp

.. method:: Action.get_absolute_url()

The URL to the Action object in the Django admin.

:class:`~Editor`
----------------------------------

.. class:: Editor

.. attribute:: Editor.user

A :class:`ForeignKey` pointing to a :class:`django.contrib.auth.models.User`. Every user that is going to work on Discipline-controlled models has to have an :class:`~Editor` instance.

.. method:: Editor.save_object(obj)

Save a Django object *obj* and record everything necessary for Discipline. Use this in scripts, migrations and whenever you want to edit or create an instance of a Discipline-controlled model outside of the Django admin::

    >>> obj = Concept()
    >>> obj.save() # Do NOT do this, instead, do this:
    >>> editor.save_object(obj)

.. method:: Editor.delete_object(obj)

Similarly to :meth:`~Editor.save_object` above, use this instead of ``obj.delete()`` when interfacing with a Discipline-controlled model.

.. method:: Editor.undo_action(act)

If *act* is revertible (see :meth:`~Action.is_revertible`), undo the action.

For a deletion action, this will recreate the object just as it was before it was deleted (including its *uid* field!). For a creation action, it will delete the object. For a modification action, it will restore the object's state as it was right before it was modified.

:class:`~TimeMachine` -- `Objects at different points in time`
--------------------------------------------------------------------------------

.. class:: TimeMachine(uid[, when=None[, step=None]])

Create a :class:`TimeMachine` for the object with *uid* as the unique id. If *step* is given, initialize this :class:`TimeMachine` right before the :class:`~Action` whose *id* matches *step*, if *when* (a :class:`datetime` object) is given, initialize the :class:`TimeMachine` at *when*, otherwise initialize in the present, *after* the last :class:`~Action` in the database.

.. method:: TimeMachine.at(step)

Creates a new :class:`TimeMachine` instance for the same object initialized right before the :class:`Action` with the id *step*.

.. attribute:: TimeMachine.presently

A shortcut using the above, the :class:`TimeMachine` for the current object initialized after the last :class:`~Action` in the database.

.. attribute:: TimeMachine.at_previous_action

A :class:`TimeMachine` for the current object initialized at the :class:`~Action` before the current action of the :class:`TimeMachine`.

.. attribute:: TimeMachine.current_action

The action whose *id* field matches the *step* of this :class:`TimeMachine`. Effectively, the action right "before" the time of the :class:`TimeMachine`.

.. attribute:: TimeMachine.exists

A boolean indicating whether the :class:`TimeMachine`'s object exits at the :class:`TimeMachine`'s point in time.

.. method:: TimeMachine.get_object()

Returns the Django object at which the :class:`TimeMachine` is looking. If it doesn't exist, Django will raise an error.

.. method:: TimeMachine.get(fieldname)

Returns the value of the field *fieldname* of the :class:`TimeMachine`'s object as it was at the time of this :class:`TimeMachine`, if a related object doesn't exist anymore, Django will raise an error.

.. method:: TimeMachine.get_timemachine_instance(fieldname)

Returns a :class:`TimeMachine` for the object pointed by the field *fieldname*. It will be initialized in the present.

:class:`~SchemaState` -- Schema Migrations
------------------------------------------

.. class:: SchemaState

Discipline stores schema states initially and after every schema migration so that the :class:`~TimeMachine` can know what fields an object has at different points in time.

.. attribute:: SchemaState.when

A :class:`DateTimeField` indicating when the schema state was saved.

.. attribute:: SchemaState.state

A :class:`TextField` holding the *json* representation of the schema state. Do not use this.

.. method:: SchemaState.get_for_content_type(ct)

Takes a :class:`django.contrib.contenttypes.models.ContentType` object and returns a dict in the form of ``{"fields":["field1", "field2"], "foreignkeys":["fk1"]}`` where *fields* are all non-:class:`ForeignKey` fields.

:class:`~CreationCommit`, :class:`~ModificationCommit`, :class:`~DeletionCommit` -- `At the lowest level`
---------------------------------------------------------------------------------------------------------

The essense of each change is stored in :class:`CreationCommit`, :class:`ModificationCommit` and :class:`DeletionCommit` objects. Every creation action is composed of one :class:`CreationCommit` and as many :class:`ModificationCommit` objects as there are fields. Every modification action is composed of as many :class:`ModificationCommit` objects as there are fields *modified*. Every deletion action is composed of a single :class:`DeletionCommit`.

.. class:: CreationCommit

Records the creation of an object. Has three fields:

.. attribute:: CreationCommit.content_type

A :class:`ForeignKey` pointing at a :class:`django.contrib.contenttypes.models.ContentType` object.

.. attribute:: CreationCommit.object_uid

A :class:`UUIDField` storing the new object's unique id.

.. attribute:: CreationCommit.action

A :class:`ForeignKey` pointing at an :class:`~Action` to which this :class:`CreationCommit` belongs.

.. class:: ModificationCommit

Records the modification of a single field of a single object. Has four fields:

.. attribute:: CreationCommit.object_uid
.. attribute:: CreationCommit.action

See above.

.. attribute:: CreationCommit.key

A :class:`CharField` storing the fieldname.

.. attribute:: CreationCommit.value

A :class:`TextField` storing the value of the field serialized by :class:`cPickle`.

.. class:: DeletionCommit

Records the deletion of a single object. Has two fields:

.. attribute:: CreationCommit.object_uid
.. attribute:: CreationCommit.action

See above.


