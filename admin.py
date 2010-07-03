# -*- coding: utf-8 -*-
from django.contrib import admin
from models import *
from middleware import threadlocals
from django import forms
from django.contrib import messages
from django.views.generic.simple import redirect_to
from django.core import urlresolvers

class DisciplinedModelAdmin(admin.ModelAdmin):
    readonly_fields = ("uid",)
    def get_actions(self, request):
        actions = super(DisciplinedModelAdmin, self).get_actions(request)
        return actions
    def history_view(self, request, object_id, extra_context=None):
        url = urlresolvers.reverse('admin:discipline_action_changelist')
        # Redirect to Action list, but filtered for the specific action
        return redirect_to(request, url + "?q=" + object_id)
    def log_addition(self, request, obj):
        editor = Editor(user=request.user)
        editor.save_object(obj)
    def log_change(self, request, obj, method):
        editor = Editor(user=request.user)
        editor.save_object(obj)
    def log_deletion(self, request, obj, obj_repr):
        pass
    
class ActionAdmin(admin.ModelAdmin):
    
    list_display = (
        "id",
        "commit_time",
        "editor",
        "_description",
        "_status",
    )
    readonly_fields = (
        "id",
        "editor",
        "when",
        "_description",
        "_details",
        "_status",
    )
    exclude = ("reverted","action_type","object_uid")
    list_filter = ("editor",)
    actions = ("undo_actions",)
    search_fields = ("=object_uid",)
    list_select_related = True
    list_per_page = 50
    
    def commit_time(self, obj):
        return obj.when.strftime('%d %b %Y %H:%M')

    def undo_actions(self, request, queryset):
        
        actions = list(queryset.order_by("-when"))
        errors = []

        for action in actions:
            if action.is_revertible: action.undo()
            else: errors.extend(action.undo_errors)

        for error in errors:
            messages.error(request, error)
    
    # You cannot delete commits
    def get_actions(self, request):
        actions = super(ActionAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

class SchemaStateAdmin(admin.ModelAdmin):

    list_display = ("when",)
    exclude = ("state",)
    readonly_fields = ("when","html_state",)

    def get_actions(self, request):
        actions = super(SchemaStateAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

admin.site.register(Action, ActionAdmin)
admin.site.register(SchemaState, SchemaStateAdmin)

