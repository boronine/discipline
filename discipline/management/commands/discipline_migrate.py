try:
    import json
except ImportError:
    import simplejson as json 
from django.conf import settings
from django.db import models
from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType
from discipline.models import DisciplinedModel, SchemaState, DisciplineException

class Command(BaseCommand):
    help = "Registers new schema for Discipline-controlled models"

    def handle(self, quiet=False, *args, **options):

        state = {}
        if not quiet: print "Reading the schema of Discipline-controlled models..."
        state_text = ""

        # All models in Django
        for cl in models.get_models():

            # Disregard models that don't inherit DisciplinedModel
            if not issubclass(cl, DisciplinedModel): continue

            content_type = ContentType.objects.get_for_model(cl)

            app = content_type.app_label
            model = content_type.model

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
            if not quiet: print "%s\nSchemaState saved on %s" % (state_text, ss.when)

