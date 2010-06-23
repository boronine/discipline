import json
from django.core.management.base import BaseCommand, CommandError
from pervert.models import AbstractPervert, SchemaState, PervertError

class Command(BaseCommand):
    help = "Registers new schema for Pervert-controlled models"

    def handle(self, *args, **options):
        ret = []
        print "Reading the schema of Pervert-controlled models..."
        for cl in AbstractPervert.__subclasses__():
            state = {
                "app_label": cl._meta.app_label,
                "model": cl._meta.object_name,
                "fields": [],
                "fks": []
            }
            print "%s.models.%s" % (state["app_label"], state["model"],)
            for field in cl._meta.fields:
                print " * %s" % field.name
                if field.name == "uid":
                    continue
                if field.__class__.__name__ == "ForeignKey":
                    state["fks"].append(field.name)
                else:
                    state["fields"].append(field.name)
            ret.append(state)
        ss = SchemaState(state = json.dumps(ret))
        ss.save()
        print "SchemaState saved on %s" % ss.when

"""
from south.signals import post_migrate
from south.models import MigrationHistory
post_migrate.connect(Command.handle)

try:
    from south.signals import post_migrate
    from south.models import MigrationHistory
    post_migrate.connect(Command.handle)
except ImportError:
    pass
"""

