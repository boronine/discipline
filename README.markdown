Pervert is a work in progress to create a Django model version control system for
a future free online dictionary. Since it could become useful for someone else's
project, I've separated it to become a standalone app.

Pervert records changes in their rawest form, which could be useful for a project 
where many editors are working on data that is most natural to store in a 
relational database. Apart from providing basic version control functions, it will
allow for developers to perform more advanced queries and facilitate migrations.

This is not meant to be a competitor to fine programs such as [Reversion][1], it 
is made for a much narrower niche (in fact, I cannot off the top of my head 
think of a project that might need Pervert. If you think yours does, it probably
doesn't).

To do:
------
1. Implement support for ManyToMany relationships.
1. Make possible to view each object's history.
1. Tie in with [South][2], make them play nicely together, changing schemas shouldn't
cause any problems with Pervert whatsoever. (this will be the main "killer feature")
1. Clean up and document API.
1. Much more.

Features so far
---------------

1. Records all creations, deletions and modifications (from django-admin or not).
1. Displays them as "actions" in a detailed list.
1. Has the ability to undo any action (checks for numerous possible problems before 
proceeding)
1. Has API to look at any object at any point in time.

Overview
--------

To register a model with Pervert, it has to inherit the `pervert.models.AbstractPervert`
class. Note that the `AbstractPervert` forces it to have `uid` (`CharField`) as the primary key.

Every action performed in the administrator interface gets tracked by Pervert. Most of
the records are contained in the `CreationCommit`, `ModificationCommit` and 
`DeletionCommit` objects. Each of those has minimalist models: `CreationCommit` only
records the UUID and content type, `DeletionCommit` only the UUID and `ModificationCommit`
records the UUID and a key-value pair. All of the above are, in turn, connected to 
`Action` objects, each `Action` instance represents one action done by one editor.

Another useful object is the `TimeMachine`. Given a UUID, it is an easy way to browse
through an object's history, get the object's field values at any point in time, etc.

API
---

#### `pervert.models.Action`

Each time an object is created, modified or deleted an `Action` is created.

`action.editor`

The editor, who commited the action. This is a Django field.

`action.when`

The `datetime`, when the action was commited. This is a Django field.

 `action.reverted` and `action.reverts`

A `OneToOneField` linking the reverted action with the one it reverts.

 `action.creation_commits`, `action.modification_commits` and `action.deletion_commits`

Creation, Modification and Deletion microcommit objects respectfully.

 `action.timemachine_instance`

An instance of the `TimeMachine` object for the object on which this action was performed.
The time is set automatically to the time of this action.

 `action.object_uid`

The UUID of the object that the action was performed on.

 `action.action_type`

Either `"cr"`, `"md"` or `"dl"` for creation, modification and deletion, respectifully.

 `action.is_revertible`

`True` or `False` for whether it is possible to undo this action.

 `action.undo_errors`

A list of errors (strings) for why the action is not revertible.

 `action.undo()`

Reverts the action. Returns nothing.

 `action.get_absolute_url()`

Returns the action's URL in Django admin.

#### `pervert.models.TimeMachine`

First argument in constructing a `TimeMachine` is the UUID of the object. Second (optional)
argument is the point in time that you want the `TimeMachine` to be at. This is the `id` of
an `Action`. Note that when looking for the state of the object's field using the `TimeMachine`,
the last `Action` that the `TimeMachine` is going to take into consideration is the one
whose `id` specifies the `TimeMachine`'s current location. So, for example:

    >>> action = Action.objects.get(id=5)
    >>> action.action_type
    'md'
    >>> action.object_uid
    u'554062218b6c4444876cfe5c723ef369'
    >>> action.modification_commits.all()[0].key
    u'revolution'
    >>> action.modification_commits.all()[0].value
    9
    >>> tm = TimeMachine(action.object_uid, action_id)
    >>> tm.get("revolution")
    9
    >>> tm.move(action_id - 1)
    >>> tm.get("revolution")
    8

When the second argument isn't supplied, `TimeMachine` automatically moves to present.

`machine.move(time)`, `machine.move_to_present()`

Moves the `TimeMachine` to `time`. `move_to_present()` moves to the latest `Action` and, therefore,
the present state.

`machine.get(fieldname)`

Gets the value of the field at the point in time. If the field is a `ForeignKey` and the object
it is pointing to doesn't exist, raises `pervert.models.PervertError`.

`machine.get_timemachine_instance(fieldname)`

Returns a `TimeMachine` instance of the object that our object points to with the `ForeignKey`
called `fieldname`.

`machine.get_object()`

Returns the object that the `TimeMachine` is looking at. If it doesn't exist, Django will raise
an error.

`machine.exists()`

Returns whether the object exists at this point in time. Note that when an object is recreated
by undoing a deletion action, it gets its old UUID.

`machine.exists_now()`

Same as `machine.exists()`, but checks the present instead of the `TimeMachine`'s time.

`machine.current_action`

Points to the `Action` object with the `id` equaled to the `TimeMachine`'s time.

[1]: http://code.google.com/p/django-reversion/ 
[2]: http://south.aeracode.org/

