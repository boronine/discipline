"""
I spent two days trying to set up testing properly. At the end
I could somewhat test South integration but that involved lots of
terrible hacks. This script obviously isn't an elegant solution
to automatic testing, but it is the lesser evil.
       -- Alexei
"""

import os
import shutil
import sys
from getopt import getopt, GetoptError
import subprocess
from subprocess import Popen, PIPE

from django.conf import settings as django_settings
from django.core.management import setup_environ
import settings

# Make Django models available
setup_environ(settings)

from discipline.models import *
from testapp.models import *

testing_dir = os.path.normpath(os.path.dirname(__file__))
os.chdir(testing_dir)

# Make the discipline package accessible
sys.path.append("../..")

# Whether to print system output for 'special' tests
verbose = False


def call(command, safe=False):
    # Pipe the output so it won't pollute stdout
    kwargs = {}
    if not verbose: 
        kwargs["stdout"] = PIPE
        kwargs["stderr"] = PIPE
    # If safe, then don't freak out at child's error
    if safe: return subprocess.call(command.split(), **kwargs)
    return subprocess.check_call(command.split(), **kwargs)

def nextphase(phase):
    command = ["python", "runtests.py", "--" + phase]
    if verbose: command += ["-v"]
    subprocess.call(command)

help_text = """
Run Django unit tests and 'special' tests unsuitable for Django
testing framework, currently South integration.

    -u      Run Django unit tests only.
    -s      Run special tests only.
    -v      Print output from side commands of 'special' tests.
            Use for test debugging.
    -h      Print this help text
"""

def main():

    global verbose

    # List of options passed, for eg: ["-s", "-v"]
    try:
        opts = [o[0] for o in getopt(sys.argv[1:], "usvh", ["s1","s2"])[0] ]
    except GetoptError:
        print help_text
        return

    if "-h" in opts or ("-s" in opts and "-u" in opts):
        print help_text
        return

    if "-v" in opts:
        verbose = True

    if "-s" in opts:
        run_special_tests()
    elif "-u" in opts:
        run_unit_tests()
    elif "--s1" in opts:
        special_phase1()
    elif "--s2" in opts:
        special_phase2()
    else:
        # By default run both
        run_unit_tests()
        run_special_tests()


def run_unit_tests():
    global verbose
    print " - Preparing for and running unit tests"
    # Remove migrations
    shutil.rmtree("testapp/migrations", True)
    # Restore original models
    newmodels(unit_test_models)
    # Run Django tests
    if call("python manage.py test testapp", safe=True):
        if not verbose:
            print "Django tests failed! Rerunning verbosely"
            verbose = True
            call("python manage.py test testapp", safe=True)
    else:
        print " - Unit tests sucessful!"



def run_special_tests():
    print " - Preparing for special tests"
    # Prepare for special tests
    shutil.rmtree("testapp/migrations", True)
    newmodels(original_models)
    # Reloading Django's app and model cache turned out to be excruciatingly 
    # difficult, this is an ugly but effective solution.
    nextphase("s1")


def special_phase1():

    # Restore old database from backup or syncdb a new one
    if os.path.exists("testing.db.bak"):
        shutil.copyfile("testing.db.bak", "testing.db")
        print " - Restored old database, if you changed the original models, " \
            "delete testing.db.bak and run the tests again"
    else:
        print " - No backup database found, creating new one"
        os.unlink("testing.db")
        call("python manage.py syncdb --noinput")
        shutil.copyfile("testing.db", "testing.db.bak")

    print " - Running initial schema migration"
    call("python manage.py schemamigration testapp --initial")
    call("python manage.py migrate testapp --fake")

    # If there is a SchemaState object, then Discipline successfully
    # received South's signal
    assert SchemaState.objects.count() == 1

    print " - Creating test objects"

    # Make the editor
    from django.contrib.auth.models import User
    john = User.objects.create(
        first_name = "John",
        last_name = "Doe",
        email = "john.doe@example.com",
        username = "johndoe"
    )
    editor = Editor.objects.create(user=john)

    # Make a bunch of objects
    kc = Band(name="King Crimson", irrelevant_field="KC")
    gg = Band(name="Gentle Giant")
    editor.save_object(kc)
    editor.save_object(gg)
    rf = Member(name="Robert Fripp", band=kc)
    ds = Member(name="Derek Shulman", band=gg)
    editor.save_object(rf)
    editor.save_object(ds)

    # Use change testapp's schema
    newmodels(data_migration_models)

    print " - Running second schema migration, introducing new model"

    # Schema migration to add a new model and a new field 
    # Note that we *have* to migrate now, so that Discipline would
    # know when the schema changed
    call("python manage.py schemamigration testapp --auto")
    call("python manage.py migrate testapp")

    print " - Writing and running the data migration"

    # Write the data migration to transfer from old model to new one
    call("python manage.py datamigration testapp rename")
    migration = open("testapp/migrations/0003_rename.py","w")
    migration.write(data_migration)
    migration.close()

    print " - Running third schema migration, getting rid of the old model"

    # Lastly, a schema migration to get rid of the old one
    newmodels(final_models)
    call("python manage.py schemamigration testapp --auto")
    
    # Migrate
    kwargs = {"shell": True, "stdin": PIPE}
    if not verbose: kwargs.update({"stdout": PIPE, "stderr": PIPE})
    p = Popen("python manage.py migrate testapp", **kwargs)
    p.stdin.write("y") # South asks whether to delete the old model, sure
    p.communicate()

    # Continue special tests after reloading Django's cache
    nextphase("s2")



def special_phase2():

    print " - Testing objects"

    # Did the data migration work?
    assert Musician.objects.count() == 2, "Musicians were not created after migration"

    ck = Band.objects.get(name="King Crimson")
    tm = TimeMachine(uid = ck.uid)
    assert tm.exists
    assert set(tm.fields) == set(["name", "awesome"])
    assert tm.get("name") == "King Crimson"
    # Default value at migration
    assert not tm.get("awesome")
    ck.awesome = True
    ck.save()




data_migration = """
# encoding: utf-8
import datetime
from south.db import db
from south.v2 import DataMigration
from django.db import models
from discipline.models import Editor

class Migration(DataMigration):

    def forwards(self, orm):
        john = Editor.objects.all()[0]
        for m in orm.Member.objects.all():
            musician = orm.Musician(name = m.name, band = m.band)
            john.save_object(musician)
            john.delete_object(m)

    def backwards(self, orm):
        "Write your backwards methods here."


    models = {
        'testapp.band': {
            'Meta': {'object_name': 'Band'},
            'awesome': ('django.db.models.fields.BooleanField', [], {'default': 'False', 'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'uid': ('discipline.models.UUIDField', [], {'default': "'acbff0ae6e42412d9409c2e8ce15224a'", 'max_length': '32', 'primary_key': 'True', 'db_index': 'True'})
        },
        'testapp.member': {
            'Meta': {'object_name': 'Member'},
            'band': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'members_old'", 'to': "orm['testapp.Band']"}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'uid': ('discipline.models.UUIDField', [], {'default': "'7c913a3123394057912b33c060b2b96c'", 'max_length': '32', 'primary_key': 'True', 'db_index': 'True'})
        },
        'testapp.musician': {
            'Meta': {'object_name': 'Musician'},
            'band': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'members'", 'to': "orm['testapp.Band']"}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'}),
            'uid': ('discipline.models.UUIDField', [], {'default': "'9332677ce9cb49e3b25da7356e575d69'", 'max_length': '32', 'primary_key': 'True', 'db_index': 'True'})
        }
    }

    complete_apps = ['testapp']
"""


unit_test_models = """
from django.db import models
from discipline.models import DisciplinedModel
from django.db.models import *

class LanguageKey(DisciplinedModel):
    code = CharField(max_length=6,unique=True)

class Word(DisciplinedModel):
    full = CharField(max_length=70,db_index=True)
    language = ForeignKey(LanguageKey, related_name="words")

class Concept(DisciplinedModel):
    pass

class WordConceptConnection(DisciplinedModel):
    word = ForeignKey(Word, related_name="concept_connections")
    concept = ForeignKey(
        Concept, 
        related_name="word_connections"
    )
"""

original_models = """
from django.db import models
from discipline.models import DisciplinedModel
from django.db.models import *

class Band(DisciplinedModel):
    name = CharField(max_length = 50)
    irrelevant_field = CharField(max_length = 40, null=True)

class Member(DisciplinedModel):
    name = CharField(max_length = 50)
    band = ForeignKey("Band", related_name="members")
"""

data_migration_models = """
from django.db import models
from discipline.models import DisciplinedModel
from django.db.models import *

class Band(DisciplinedModel):
    name = CharField(max_length = 50)
    awesome = BooleanField(default=False)

class Member(DisciplinedModel):
    name = CharField(max_length = 50)
    band = ForeignKey("Band", related_name="members_old")

class Musician(DisciplinedModel):
    name = CharField(max_length = 50)
    band = ForeignKey("Band", related_name="members")
"""

final_models = """
from django.db import models
from discipline.models import DisciplinedModel
from django.db.models import *

class Band(DisciplinedModel):
    name = CharField(max_length = 50)
    awesome = BooleanField(default=False)

class Musician(DisciplinedModel):
    name = CharField(max_length = 50)
    band = ForeignKey("Band", related_name="members")
"""

def newmodels(mods):
    models = open("testapp/models.py", "w")
    models.write(mods)
    models.close()

if __name__ == "__main__": 
    main()

