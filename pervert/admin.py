# -*- coding: utf-8 -*-
from django.contrib import admin
from pervert.models import *
from pervert.middleware import threadlocals

class MicroCommitInline(admin.TabularInline):
    model = MicroCommit
    extra = 0
    fields = ("object_uid","commit","ctype","key","value",)
    readonly_fields = ("object_uid","commit","ctype","key","value")

class PervertAdmin(admin.ModelAdmin):
    readonly_fields = ("uid",)
    def get_actions(self, request):
        actions = super(PervertAdmin, self).get_actions(request)
        return actions

# For debugging mainly
class MicroCommitAdmin(admin.ModelAdmin):
    readonly_fields = ("object_uid","ctype","key","value",)
    list_display = ("ctype","object_uid","editor",)

# This will be refactored into MicroCommitAdmin
class CommitAdmin(admin.ModelAdmin):
    
    readonly_fields = ("uid","editor")
    list_display = ("editor","when","uid","explanation")
    actions = ["undo_commit"]
    inlines = [MicroCommitInline]

    def undo_commit(self, request, queryset):
        
        allgood = True
        errors = []
        commituids = []

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
            commituids.append(commit.uid)

            # Separate all microcommits into groups by type
            for mc in commit.microcommits.all():
                if mc.ctype == "dl":
                    # Deleting microcommits will be stored in this dict
                    # there is a reason for this
                    mcommits_dl[mc.object_uid] = mc
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
                    if fk.uid in mcommits_dl.keys():
                        # Indeed, we are planning to restore it. Let's check
                        # if it was already restored:
                        if fk.uid in restored_objects.keys():
                            print "step2"
                            overrides[key] = restored_objects[fk.uid]
                        else:
                            overrides[key] = handle_dl(mcommits_dl[fk.uid])
                            print "step3"
                        # This ForeignKey is now okay, continue
                        continue

                    allgood = False
                    errors.append("You cannot undelete %s %s, because " \
                                  "it used to link to %s %s, which was deleted." % 
                                  (inst.object_type_name, inst.uid, 
                                   fk.object_type_name, fk.uid))

            if allgood:
                print overrides
                newuid = inst.recreate(newcommit, overrides)
                restored_objects[inst.uid] = newuid
                return newuid

        restored_objects = {}
        for mcommit in mcommits_dl.values():
            if mcommit.object_uid not in restored_objects.keys():
                handle_dl(mcommit)


        
        # Everything is fine, save the commit and all microcommits
        if allgood:
            
            # List all commits that have been undone
            newcommit.explanation = "Undid commits: "
            for uid in commituids:
                newcommit.explanation += uid + " "
                
            newcommit.save()
        
        # At least one error, print the errors
        else:             
            self.message_user(request, " ".join(errors))
    
    # You cannot delete commits
    def get_actions(self, request):
        actions = super(CommitAdmin, self).get_actions(request)
        del actions['delete_selected']
        return actions

admin.site.register(MicroCommit, MicroCommitAdmin)

