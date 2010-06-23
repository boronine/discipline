import json
from django.core.management.base import BaseCommand, CommandError
from pervert.models import AbstractPervert, SchemaState, PervertError

class Command(BaseCommand):
    help = "Registers new schema for Pervert-controlled models"

    def handle(self, *args, **options):
        states = []
        print "Reading the schema of Pervert-controlled models..."
        state_text = ""
        for cl in AbstractPervert.__subclasses__():
            state = {
                "app_label": cl._meta.app_label,
                "model": cl._meta.object_name,
                "fields": [],
                "fks": []
            }
            state_text += "%s.models.%s\n" % (state["app_label"], state["model"],)
            for field in cl._meta.fields:
                state_text += " * %s\n" % field.name
                if field.name == "uid":
                    continue
                if field.__class__.__name__ == "ForeignKey":
                    state["fks"].append(field.name)
                else:
                    state["fields"].append(field.name)
            # Sort to make sure there is a unique json representation of each state
            states.append(state)

        # If the json is identical to the last saved state
        if SchemaState.objects.count() and \
            json.loads(SchemaState.objects.order_by("-when")[0].state) == states:
            print "The state hasn't changed, nothing to do."
        else:
            # Save new state
            ss = SchemaState(state = json.dumps(states))
            ss.save()
            print state_text + "SchemaState saved on %s" % ss.when

