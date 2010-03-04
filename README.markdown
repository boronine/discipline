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

Pervert is pre-alpha. TODO:
---------------------------

1. Implement undo function for object creation and modification.
2. Implement support for ManyToMany relationships
3. Use the powerful Django-admin features to their fullest to display lots of 
useful information in the admin interface. 
4. Much, much more.

[1]: http://code.google.com/p/django-reversion/ 
