from django.contrib import admin
from django.urls import path,include
from talent.views import *
from rest_framework.routers import DefaultRouter


router = DefaultRouter()
router.register(r"recruiter-groups", RecruiterGroupViewSet, basename="recruiter-groups")
router.register(r"recruiter-memberships", RecruiterMembershipViewSet, basename="recruiter-memberships")


urlpatterns=[
path('',include(router.urls)),
path('GenerateJobAssessment/',GenerateJobAssessment.as_view()),
path('AddQuestionInJobAssessmentUsingAI/',AddQuestionInJobAssessmentUsingAI.as_view()),
path('ImportQuestionCSVView/',ImportQuestionCSVView.as_view()),

path('JobListingView/',JobListingView.as_view()),
path('CloneJob/',CloneJob.as_view()),

path('JobAssessmentView/',JobAssessmentView.as_view()),
path('CloneJobAssessment/',CloneJobAssessment.as_view()),

path('UpdateandViewprofile/',UpdateandViewprofile.as_view()),

path('InviteView/',InviteView.as_view()),
path('JobInviteUploadView/',JobInviteUploadView.as_view()),
path('SendReminderEmail/',SendReminderEmail.as_view()),
path('ChagneInviteStatusToAccepted/',ChagneInviteStatusToAccepted.as_view()),
path('MultiInviteRejectAPI/',MultiInviteRejectAPI.as_view()),

# path('CheckProctoring/',CheckProctoring.as_view()),
path('checkAudioProctoring/',checkAudioProctoring.as_view()),
path('DetectionDataStoreAPI/',DetectionDataStoreAPI.as_view()),
path('AddQuestionInJobAssessment/',AddQuestionInJobAssessment.as_view()),

path('PreviewJobAssessment/',PreviewJobAssessment.as_view()),
path('PublishJobAssessment/',PublishJobAssessment.as_view()),

path('InviteLogin/',InviteLogin.as_view()),

path('GetJobAssessment/',GetJobAssessment.as_view()),
path('UserJobAssessment/',UserJobAssessment.as_view()),
path('StartJobAssessment/',StartJobAssessment.as_view()),
path('checkJobAssessmentTime/',checkJobAssessmentTime.as_view()),

path('SubmitSingleAssessmentQuestion/',SubmitSingleAssessmentQuestion.as_view()),
path('SubmitJobAssessment/',SubmitJobAssessment.as_view()),

path('DeleteJobAssessmentQuestionView/',DeleteJobAssessmentQuestionView.as_view()),

path('SubmitJobNPSAPIView/',SubmitJobNPSAPIView.as_view()),
path('JobNpsDashboard/',JobNpsDashboard.as_view()),
path('JobPostingSummaryAPIView/',JobPostingSummaryAPIView.as_view()),
path('InviteAnalytics/',InviteAnalytics.as_view()),

path('AcknowledgeInvite/',AcknowledgeInvite.as_view()),

path('SendCustomEmail/',SendCustomEmail.as_view()),

path('OnOffMobileCameraOfInvite/',OnOffMobileCameraOfInvite.as_view()),
path('AddScreenRecordingVideos/',AddScreenRecordingVideos.as_view()),
path('AddWindowDetectionRecords/',AddWindowDetectionRecords.as_view()),
path('AddMobileWarningDetectionRecords/',AddMobileWarningDetectionRecords.as_view()),
path('AddMobileRecordingChunks/',AddMobileRecordingChunks.as_view()),
path('LiveUserDetails/',LiveUserDetails.as_view()),
path('CheckSurroundingWithObjectDetection/',CheckSurroundingWithObjectDetection.as_view()),

path('JobAssessmentDetails/',JobAssessmentDetails.as_view()),

path('ChatMessagesView/',ChatMessagesView.as_view()),
path('CustomMessageView/',CustomMessageView.as_view()),

path('UpdateInviteAssessmentMarks/',UpdateInviteAssessmentMarks.as_view()),

path('GroupDropdownList/',GroupDropdownList.as_view()),

path('TerminateExam/',TerminateExam.as_view()),

path('InviteAssessmentList/',InviteAssessmentList.as_view()),

path('ViewOldAssessmentDetails/',ViewOldAssessmentDetails.as_view()),


# ================= Applicaiton user list urls =========

path('ApplicationUserManagementView/',ApplicationUserManagementView.as_view()),
path('MultiApplicationReject/',MultiApplicationReject.as_view()),
path('MultiApplicationInvite/',MultiApplicationInvite.as_view()),
path('ApplicationUserSubmitForm/',ApplicationUserSubmitForm.as_view()),
path('JobDropdown/',JobDropdown.as_view()),
path('SaveJobLink/',SaveJobLink.as_view()),
path('ExtractJobSeeker/',ExtractJobSeeker.as_view()),

path('BackgoundDetectionFromDesktop/',BackgoundDetectionFromDesktop.as_view()),
path('ImageProctoringDetection/',ImageProctoringDetection.as_view()),
path('JobAssessmentDropDown/',JobAssessmentDropDown.as_view()),
]