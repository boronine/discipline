Discipline is a Django model version control system for
a future free online dictionary. 

It records changes in their rawest form, which could be useful for a project 
where many editors are working on data that is most natural to store in a 
relational database. Apart from providing basic version control functions, it will
allow for developers to perform more advanced queries and facilitate migrations.

Features 
---------------

1. Records all creations, deletions and modifications (from django-admin or not).
1. Displays them as "actions" in a detailed list.
1. Each object's "history" page points to Discipline's detailed list of actions that
were performed on it.
1. Has the ability to undo any action (checks for numerous possible problems before 
proceeding)
1. Has API to look at any object at any point in time.

Overview
--------

To register a model with Discipline, it has to inherit the `discipline.models.DisciplinedModel`
class. Note that the `DisciplinedModel` forces it to have `uid` (`CharField`) as the primary key.

Every action performed in the administrator interface gets tracked by Discipline. Most of
the records are contained in the `CreationCommit`, `ModificationCommit` and 
`DeletionCommit` objects. Each of those has minimalist models: `CreationCommit` only
records the UUID and content type, `DeletionCommit` only the UUID and `ModificationCommit`
records the UUID and a key-value pair. All of the above are, in turn, connected to 
`Action` objects, each `Action` instance represents one action done by one editor.

Another useful object is the `TimeMachine`. Given a UUID, it is an easy way to browse
through an object's history, get the object's field values at any point in time, etc.

API
---

#### `discipline.models.Action`

Each time an object is created, modified or deleted an `Action` is created.

 `action.editor`

The editor, who commited the action. This is a Django field.

 `action.when`

The `datetime`, when the action was commited. This is a Django field.

 `action.reverted` and `action.reverts`

A `OneToOneField` linking the reverted action with the one it reverts.

 `action.creation_commits`, `action.modification_commits` and `action.deletion_commits`

Creation, Modification and Deletion microcommit objects respectfully.

 `action.timemachine`

An instance of the `TimeMachine` object for the object on which this action was performed.
The time is set automatically to the time of this action.

 `action.object_uid`

The UUID of the object that the action was performed on.

 `action.action_type`

Either `"cr"`, `"md"` or `"dl"` for creation, modification and deletion, respectfully.

 `action.is_revertible`

Boolean indicating whether it is possible to undo this action.

 `action.undo_errors`

A list of errors (strings) for why the action is not revertible.

 `action.undo()`

Reverts the action. Returns nothing.

 `action.get_absolute_url()`

Returns the action's URL in Django admin.

#### `discipline.models.TimeMachine`

First argument in constructing a `TimeMachine` is the UUID of the object. Second (optional)
argument is the datetime object specifying the point in time that you want the `TimeMachine` 
to be at. Note that if the `TimeMachine` is *exactly* at the time of some action, it will
take that action into consideration when asked for field values.

    >>> action = Action.objects.all()[0]
    >>> action.modification_commits.all()[0].key
    u'revolution'
    >>> action.modification_commits.all()[0].value
    9
    >>> tm = TimeMachine(action.object_uid, action.id)
    >>> tm.get("revolution")
    9
    >>> tm.at_previous_action.get("revolution")
    8

When the second argument isn't supplied, `TimeMachine` automatically moves to present.

`machine.at(time)` 

Returns a new `TimeMachine` instance for the same object, but moved to a different point in time. 
Its arguments is the `id` field of an Action objects.

`machine.presently`

A shortcut for the above that uses `datetime.datetime.now()` for the time field.

`machine.at_previous_action`

A shortcut for `at(time)` that uses the time of the action previous to one right before or right at the `TimeMachine`.

`machine.get(fieldname)`

Gets the value of the field at the point in time. If the field is a `ForeignKey` and the object
it is pointing to doesn't exist, raises `discipline.models.DisciplineError`.

`machine.get_timemachine_instance(fieldname)`

Returns a `TimeMachine` instance of the object that our object points to with the `ForeignKey`
called `fieldname`.

`machine.get_object()`

Returns the object that the `TimeMachine` is looking at. If it doesn't exist, Django will raise
an error.

`machine.exists`

A boolean for whether the object exists at this point in time. Note that when an object is recreated
by undoing a deletion action, it gets its old UUID.

`machine.current_action`

Points to the `Action` object with the `id` equaled to the `TimeMachine`'s time.

