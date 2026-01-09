from django.contrib import admin
from talent.models import *
admin.site.register([JobListing,JobAssessment,JobInvites,JobNPSModel,ChatMessages,RecruiterGroup,RecruiterMembership,SubmittedAssessmentQuestion,InviteSubmittedUrl,InviteUserDetails,JobInviteOldAttempt,ApplicationUserList])

# Register your models here.
