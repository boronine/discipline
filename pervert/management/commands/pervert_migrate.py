import json
from django.core.management.base import BaseCommand, CommandError
from pervert.models import AbstractPervert, SchemaState, PervertError

class Command(BaseCommand):
    help = "Registers new schema for Pervert-controlled models"

    def handle(self, quiet=False, *args, **options):
        state = {}
        if not quiet: print "Reading the schema of Pervert-controlled models..."
        state_text = ""
        for cl in AbstractPervert.__subclasses__():
            app = cl._meta.app_label
            model = cl._meta.object_name
            if app not in state.keys(): state[app] = {}
            if model not in state[app].keys(): state[app][model] = {
                "fields": [],
                "foreignkeys": []
            }
            state_text += "%s.models.%s\n" % (app, model,)
            for field in cl._meta.fields:
                state_text += " * %s\n" % field.name
                if field.name == "uid":
                    continue
                if field.__class__.__name__ == "ForeignKey":
                    state[app][model]["foreignkeys"].append(field.name)
                else:
                    state[app][model]["fields"].append(field.name)

        # If the json is identical to the last saved state
        if SchemaState.objects.count() and \
            json.loads(SchemaState.objects.order_by("-when")[0].state) == state:
            if not quiet: print "The state hasn't changed, nothing to do."
        else:
            # Save new state
            ss = SchemaState(state = json.dumps(state))
            ss.save()
            if not quiet: print state_text + "SchemaState saved on %s" % ss.when

