
try:
    from management.commands.discipline_migrate import Command
    from south.signals import post_migrate
    def command(app, *args, **kwargs): 
        print "Discipline detected a South migration, it will now save the new" \
            " schema state automatically."
        Command().handle()
    # Every time a user performs a South migration, Pervert should
    # perform a migration of its own, this is in case the user forgets
    # to run "manage.py pervert_migrate"
    post_migrate.connect(command)
except ImportError:
    pass

__version__ = "0.9.1"

