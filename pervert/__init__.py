from management.commands.pervert_migrate import Command
def command(app, *args, **kwargs): 
    print "Pervert detected a South migration, it will now save the new" \
        " schema state automatically."
    Command().handle()

try:
    from south.signals import post_migrate
    from south.models import MigrationHistory
    # Every time a user performs a South migration, Pervert should
    # perform a migration of its own, this is in case the user forgets
    # to run "manage.py pervert_migrate"
    post_migrate.connect(command)
except ImportError:
    pass

