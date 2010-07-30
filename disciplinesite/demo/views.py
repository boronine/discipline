from django.contrib.auth.models import User, Group
from django.contrib.auth import login, authenticate
from django.shortcuts import redirect

from disciplinesite.demo.models import *
from disciplinesite.tools import *
from discipline.models import *

def index(request):
    grp = Group.objects.get(name="editors")
    first = word(True)
    last = word(True)
    user = User(
        first_name = first,
        last_name = last,
        email = "%s%s@example.com" % (first, last),
        username = first + last,
        is_staff = True
    )
    user.set_password("crimson")
    user.save()
    user.groups.add(grp)
    editor = Editor.objects.create(user=user)
    login(request, authenticate(username = first + last, password = "crimson"))
    return redirect("/admin/")

