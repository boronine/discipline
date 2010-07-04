Tutorial
========

Getting Started
---------------

Get the latest code from `the downloads page <http://github.com/alexeiboronine/discipline/downloads>`_, unpack and run ``python setup.py install``

Add Discipline to the ``INSTALLED_APPS`` in your project's ``settings.py`` file. It is highly advised to use Discipline with `South <http://south.aeracode.org/>`_::

    INSTALLED_APPS = (
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.sites',
        'django.contrib.messages',
        'django.contrib.admin',
        'discipline',
        'south',
        'testapp',
    )

Every model controlled by Discipline has to inherit from the :class:`discipline.models.DisciplinedModel` class, keep in mind the following limitations:

* Discipline can't work with ``ManyToManyField`` or ``OneToOneField``.
* If a Discipline-controlled model is related to another model, the other one *has* to be Discipline-controlled as well.
* Discipline will force every Discipline-controlled model to have a :class:`discipline.models.UUIDField` as its primary key, with the field name ``uid``. 

::

    from django.db import models
    from discipline.models import DisciplinedModel

    class LanguageKey(DisciplinedModel):
        code = models.CharField(max_length=6,unique=True)

    class Word(DisciplinedModel):
        text = models.CharField(max_length=70,db_index=True)
        language = models.ForeignKey("LanguageKey", related_name="words")

    class Concept(DisciplinedModel):
        pass

    class WordConceptConnection(DisciplinedModel):
        word = models.ForeignKey(
            "Word", 
            related_name="concept_connections"
        )
        concept = models.ForeignKey(
            "Concept", 
            related_name="word_connections"
        )

Similarly, in your ``admin.py`` file, you have to register these models with :class:`discipline.admin.DisciplinedModelAdmin`::

    from django.contrib import admin

    from discipline.admin import DisciplinedModelAdmin
    from testproject.testapp.models import *

    admin.site.register(Concept, DisciplinedModelAdmin)
    admin.site.register(Word, DisciplinedModelAdmin)
    admin.site.register(WordConceptConnection, DisciplinedModelAdmin)
    admin.site.register(LanguageKey, DisciplinedModelAdmin)

A very important step, you have to tell Discipline about your current models (More about this in :ref:`migrations`)::

    $ python manage.py discipline_migrate

Lastly, you need to create a :class:`discipline.models.Editor` object to be able to use Discipline (assuming you have run ``syncdb`` and have a user object)::

    >>> from django.contrib.auth.models import User
    >>> from discipline.models import Editor
    >>> me = User.objects.all()[0]
    >>> editorme = Editor.objects.create(user=me)

Now your environment should be Discipline-ready, fire up the test server and experiment with creating, modifying and deleting objects.

Introduction to the API
-----------------------

When using the shell, you should never call Django objects' `save` and `delete` methods: these don't register the actions with Discipline and can compromise the integrity of your data. Instead, you should use the :class:`discipline.models.Editor`'s :meth:`~discipline.models.Editor.save_object` and :meth:`~discipline.models.Editor.delete_object`::

    >>> editor = Editor.objects.all()[0]
    >>> lk = LanguageKey(code="eng")
    >>> editor.save_object(lk) # CREATION
    >>> lk.code = "rus"
    >>> editor.save_object(lk) # MODIFICATION
    >>> editor.delete_object(lk) # DELETION

For every change, a :class:`discipline.models.Action` object is created, let's look at the last ones::

    >>> for action in Action.objects.all(): 
    ...     print action.summary
    ...
    Time: 2010-07-04 01:28:09.922254
    Comitter: John Doe
    Deleted language key 
    code: rus  

    Time: 2010-07-04 01:28:04.107404 
    Comitter: John Doe
    Modified language key 
    code: eng -> rus

    Time: 2010-07-04 01:27:58.230695 
    Comitter: John Doe
    Created language key 
    code: eng

You can undo many actions with :meth:`~discipline.models.Editor.undo_action()`::

    >>> editor.undo_action(Action.objects.all()[0]) # Undo last action
    >>> Action.objects.latest().summary # A new action has been created
    Time: 2010-07-04 01:27:58.230695 
    Comitter: John Doe
    Created language key 
    code: rus

Some actions you can't undo, however::

    >>> privet = Word(text="privet", language=lk)
    >>> editor.save_object(privet) # Create privet
    >>> editor.delete_object(privet) # Delete privet
    >>> deleted_privet = Action.objects.latest()
    >>> editor.delete_object(lk) # Delete privet's language
    >>> deleted_privet.is_revertible
    False
    >>> deleted_privet.undo_errors
    ["Cannot undo action 5: the word used to link to a language key that has since been deleted"]

We can look at objects at different points in time with :class:`discipline.models.TimeMachine`::

    >>> tm = TimeMachine(privet.uid)
    >>> tm.presently.exists
    False
    >>> tm.at_previous_action.exists
    False
    >>> tm.at(4).exists # At action with id 4
    True
    >>> tm.at(4).get("text")
    "privet"

Take a look at :doc:`reference` for more API.

.. _migrations:

Migrations
----------

Discipline is designed to gracefully handle schema migrations and offers :meth:`~discipline.models.Editor.save_object()` and :meth:`~discipline.models.Editor.delete_object()` for data migrations.
 
Every time you run a schema migration you must run::

    $ python manage.py discipline_migrate

for Discipline to register the new schema state. If you use `South <http://south.aeracode.org/>`_ (and you should!), Discipline will run this command whenever it senses a South migration.

If you have a data migration that creates models or fields *and* deletes models or fields (for example, renaming actually involves creating a new one, migrating the data, then deleting the old one), you must run *discipline_migrate* after *each* schema migration!

1. Create new models and fields.

2. Migrate schema with South or manually.

3. Run ``python manage.py discipline_migrate``.

4. Migrate data using :meth:`~discipline.models.Editor.save_object()` and :meth:`~discipline.models.Editor.delete_object()`.

5. Delete obsolete models and fields.

6. Migrate schema with South or manually.

7. Run ``python manage.py discipline_migrate``.

