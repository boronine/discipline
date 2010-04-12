# -*- coding: utf-8 -*-
from django.contrib import admin
from pervert.models import *
from pervert.middleware import threadlocals
from django import forms
from django.contrib import messages

class PervertAdmin(admin.ModelAdmin):
    readonly_fields = ("id",)
    def get_actions(self, request):
        actions = super(PervertAdmin, self).get_actions(request)
        return actions

class ActionAdmin(admin.ModelAdmin):
    
    list_display = (
        "id",
        "commit_time",
        "editor",
        "description",
        "status"
    )
    readonly_fields = ("editor","when","description","details",)
    list_filter = ("editor",)
    actions = ["undo_commit"]
    list_select_related = True
    list_per_page = 50
    
    def commit_time(self, obj):
        return obj.when.strftime('%d %b %Y %H:%M')

    def undo_commit(self, request, queryset):
        
        actions = list(queryset.order_by("id"))
        errors = []

        for action in actions:
            inst = action.instance()

            if action.action_type == "dl":
                # The only problem we can have by undeleting this action
                # is that some of its foreignkeys could be poining to
                # objects that have since been deleted.
                allgood = True
                for field in inst.foreignkeys:
                    fk = inst.get_pervert_instance(field)
                    if not fk.exists():
                        allgood = False
                        errors.append(
                            "Cannot undo action %d: when %s was deleted, "
                            "it was linked to to a %s that has since "
                            "been deleted"
                            % (action.id,
                               inst.content_type.name,
                               fk.content_type.name))

                if allgood:
                    inst.recreate()
        if errors:
            messages.error(request, "<br/>".join(errors))
    
    # You cannot delete commits
    def get_actions(self, request):
        actions = super(ActionAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

admin.site.register(Action, ActionAdmin)
admin.site.register(ModificationCommit)
admin.site.register(CreationCommit)
admin.site.register(DeletionCommit)

