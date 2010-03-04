# This is a hack from http://code.djangoproject.com/wiki/CookBookThreadlocalsAndUser
# If you know a better way to access current user without a request, please fix this
import settings

try:
    from threading import local
except ImportError:
    from django.utils._threading_local import local

_thread_locals = local()
def get_current_user():    
    # This is a hack inside a hack. I can't login through populate.py script, so 
    # the script stores current user in settings. If you know a better way, please
    # fix this
    return getattr(settings,"CURRENT_USER",getattr(_thread_locals, 'user', None))

class ThreadLocals(object):
    """Middleware that gets various objects from the
    request object and saves them in thread local storage."""
    def process_request(self, request):
        _thread_locals.user = getattr(request, 'user', None)
