Introduction
============

Discipline is a BSD-licensed model versioning system for the `Django <http://djangoproject.com>`_ framework. It stores all changes performed on a database in their rawest form, which allows for advanced database-level queries.

Features
""""""""

* Django admin integration.
* Gives the ability to undo any action (that is undoable).
* In the admin interface provides a detailed list of actions, Discipline-controlled models get a custom history page with a list of actions filtered for the specific object.
* Provides low-level API for checking the state of any object that ever existed at any point in time (with the ability to restore it, of course).
* Supports schema migrations, integrates with `South <http://south.aeracode.org/>`_, provides API to enable Discipline-controlled South data migrations.

Limitations
"""""""""""

Both of these are compromises made to keep the code simple, they may be addressed in the future, but they are not a priority at the moment.

* Does not support Django's ``ManyToManyField`` and ``OneToOneField``. The former can be emulated by creating a connecting model.
* Forces each Discipline-controlled model to have a ``discipline.models.UUIDField`` as its primary key.

