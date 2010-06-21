# -*- coding: utf-8 -*-
from django.contrib import admin
from pervert.models import *
from pervert.middleware import threadlocals
from django import forms
from django.contrib import messages
from django.views.generic.simple import redirect_to
from django.core import urlresolvers

class PervertAdmin(admin.ModelAdmin):
    readonly_fields = ("uid",)
    def get_actions(self, request):
        actions = super(PervertAdmin, self).get_actions(request)
        return actions
    def history_view(self, request, object_id, extra_context=None):
        url = urlresolvers.reverse('admin:pervert_action_changelist')
        # Redirect to Action list, but filtered for the specific action
        return redirect_to(request, url + "?q=" + object_id)
    
class ActionAdmin(admin.ModelAdmin):
    
    list_display = (
        "id",
        "commit_time",
        "editor",
        "description",
        "status"
    )
    readonly_fields = (
        "editor",
        "when",
        "description",
        "details",
        "status",
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
        
        actions = list(queryset.order_by("-id"))
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

admin.site.register(Action, ActionAdmin)

