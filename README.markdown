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

Features so far
---------------

1. Records all creations, deletions and modifications (from django-admin or not).
1. Displays them as "actions" in a detailed list.
1. Has the ability to undo any action (checks for numerous possible problems before 
proceeding)
1. Has API to look at any object at any point in time.

To do:
------
1. Implement support for ManyToMany relationships.
1. Make possible to view each object's history.
1. Tie in with [South][2], make them play nicely together, changing schemas shouldn't
cause any problems with Pervert whatsoever. (this will be the main "killer feature")
1. Clean up and document API.
1. Much more.

[1]: http://code.google.com/p/django-reversion/ 
[2]: http://south.aeracode.org/

