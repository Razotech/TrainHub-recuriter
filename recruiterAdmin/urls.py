from django.urls import path
from recruiterAdmin.views import *

urlpatterns = [

path('MarkUserAsRecruiter/',MarkUserAsRecruiter.as_view()),
path('RecuriterProfile/',RecuriterProfile.as_view()),
path('RecuriterUserManagement/',RecuriterUserManagement.as_view()),
path('RemoveRecuriter/',RemoveRecuriter.as_view()),
path('UpdateSuspendRecuriter/',UpdateSuspendRecuriter.as_view()),
path('DeleteInviteOldRecord/',DeleteInviteOldRecord.as_view()),


#  ==================== Dashboard ========================

path('RecuriterOverview/',RecuriterOverview.as_view()),
path('StatusDestribution/',StatusDestribution.as_view()),
path('InvitationAnalytics/',InvitationAnalytics.as_view()),
path('Jobseekeranalytics/',Jobseekeranalytics.as_view()),

]