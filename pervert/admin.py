# -*- coding: utf-8 -*-
from django.contrib import admin
from pervert.models import *
from pervert.middleware import threadlocals
from django import forms

class PervertAdmin(admin.ModelAdmin):
    readonly_fields = ("id",)
    def get_actions(self, request):
        actions = super(PervertAdmin, self).get_actions(request)
        return actions

class ActionAdmin(admin.ModelAdmin):
    
    list_display = ("commit_time","editor","description","details",)
    readonly_fields = ("editor","when","description","details",)
    list_filter = ("editor",)
    actions = ["undo_commit"]
    
    def commit_time(self, obj):
        return obj.when.strftime('%d %b %Y %H:%M')

    def undo_commit(self, request, queryset):
        
        allgood = True
        errors = []
        commitids = []

        mcommits_dl = {}
        mcommits_md = []
        mcommits_cr = []

        newcommit = Commit(
            editor = threadlocals.get_current_user(),
        )     
        
        # temporarily allow only one commit
        if queryset.count() > 1:
            errors.append("Currently you can only undo one commit at a time")
            allgood = False

        for commit in queryset:
            
            # Keep track of all UUID for an explanation
            commitids.append(commit.id)

            # Separate all microcommits into groups by type
            for mc in commit.microcommits.all():
                if mc.ctype == "dl":
                    # Deleting microcommits will be stored in this dict
                    # there is a reason for this
                    mcommits_dl[mc.object_id] = mc
                elif mc.ctype == "md":
                    mcommits_md.append(mc)
                else:
                    mcommits_cr.append(mc)

        def handle_dl(mcommit):
            
            allgood = True

            # So this is a deletion microcommit. The only problem we can
            # encounter by undoing it is if it had ForeignKeys pointing 
            # to objects that have since been deleted.
            inst = mcommit.instance()
            
            overrides = {}

            for key in inst.foreignkeys:

                fk = inst.get_pervert_instance(key)
                fk.move_to_present()

                if not fk.exists():
                    # Oh no, a related object doesn't exist anymore. Perhaps
                    # we were planning to restore it anyways?
                    print "step1"
                    if fk.id in mcommits_dl.keys():
                        # Indeed, we are planning to restore it. Let's check
                        # if it was already restored:
                        if fk.id in restored_objects.keys():
                            print "step2"
                            overrides[key] = restored_objects[fk.id]
                        else:
                            overrides[key] = handle_dl(mcommits_dl[fk.id])
                            print "step3"
                        # This ForeignKey is now okay, continue
                        continue

                    allgood = False
                    errors.append("You cannot undelete %s %s, because " \
                                  "it used to link to %s %s, which was deleted." % 
                                  (inst.object_type_name, inst.id, 
                                   fk.object_type_name, fk.id))

            if allgood:
                print overrides
                newid = inst.recreate(newcommit, overrides)
                restored_objects[inst.id] = newid
                return newid

        restored_objects = {}
        for mcommit in mcommits_dl.values():
            if mcommit.object_id not in restored_objects.keys():
                handle_dl(mcommit)


        
        # Everything is fine, save the commit and all microcommits
        if allgood:
            
            # List all commits that have been undone
            newcommit.explanation = "Undid commits: "
            for id in commitids:
                newcommit.explanation += id + " "
                
            newcommit.save()
        
        # At least one error, print the errors
        else:             
            self.message_user(request, " ".join(errors))
    
    # You cannot delete commits
    def get_actions(self, request):
        actions = super(ActionAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

admin.site.register(Action, ActionAdmin)
admin.site.register(ModificationCommit)
admin.site.register(CreationCommit)
admin.site.register(DeletionCommit)

