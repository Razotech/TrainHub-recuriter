from rest_framework.serializers import ModelSerializer
from talent.models import *
from main.serializers import GetUSerDetailsSerializer

class InviteUserSeralizer(ModelSerializer):
    class Meta:
        model = InviteUserDetails
        fields =  '__all__'


class InviteUserProfileSerializer(ModelSerializer):
    invite_user_details = InviteUserSeralizer(read_only=True)
    class Meta:
        model =MyUser
        fields = ['id','name','email','address','is_first_login','invite_user_details','Gender']


class RecruiterGroupSerializer(ModelSerializer):
    class Meta:
        model = RecruiterGroup
        fields = "__all__"
        read_only_fields = ["group_id", "created_at", "user"]



from main.serializers import GetUSerDetailsSerializer
class ViewRecruiterMembershipSerializer(ModelSerializer):
    group = RecruiterGroupSerializer(many=True)
    user = GetUSerDetailsSerializer()
    class Meta:
        model = RecruiterMembership
        fields = "__all__"



class RecruiterMembershipSerializer(ModelSerializer):
    class Meta:
        model = RecruiterMembership
        fields = "__all__"



class ViewRecruiterGroupSerializer(ModelSerializer):
    members = ViewRecruiterMembershipSerializer(many=True)
    class Meta:
        model = RecruiterGroup
        fields = ['group_id','name','user','members','created_at']


class JobListingSerializer(ModelSerializer):
    class Meta:
        model = JobListing
        fields = '__all__'

class JobAssessmentSerializer(ModelSerializer):
    class Meta:
        model = JobAssessment
        fields = '__all__'
        



class ViewJobListingSerializer(ModelSerializer):
    Job_details = JobAssessmentSerializer(many=True)
    user = GetUSerDetailsSerializer()
    class Meta:
        model = JobListing
        fields = '__all__'

    def to_representation(self, instance):
        # Get the default serialized data
        data = super().to_representation(instance)

        # Filter Job_details where archive=False
        job_details = instance.Job_details.filter(archive=False)
        data['Job_details'] = JobAssessmentSerializer(job_details, many=True).data

        return data


class JobInviteSerializer(ModelSerializer):
    class Meta:
        model = JobInvites
        fields = '__all__'

class ViewJobInviteSerializer(ModelSerializer):
    user = InviteUserProfileSerializer()
    class Meta:
        model = JobInvites
        fields = '__all__'


class jobDetailsWithUserSerializer(ModelSerializer):
    user = GetUSerDetailsSerializer()
    class Meta:
        model = JobListing
        fields = '__all__'

class UserAssessmentDetailsSerializer(ModelSerializer):
    job = jobDetailsWithUserSerializer()
    class Meta:
        model = JobAssessment
        fields = ['job_assessment_id','assessment_name','assessment_type','assessment_duration','allocted_question','job','is_public','exam_instruction','video_instruction_url','face_detection','voice_detection','mobile_object_detection','object_detection','window_detection','total_marks','mobile_monitoring_off_warnings']

class UserInviteDetailsSerializer(ModelSerializer):
    assessment = UserAssessmentDetailsSerializer()
    class Meta:
        model = JobInvites
        exclude = ['completed_assessment']


class JobNPSSerializer(ModelSerializer):
    class Meta:
        model = JobNPSModel
        fields = '__all__'


class InviteeProfileSerializer(ModelSerializer):
    user = GetUSerDetailsSerializer()
    class Meta:
        model = JobInvites
        fields = ['invite_id','user']

class chatMessageSerializer(ModelSerializer):
    trainer = GetUSerDetailsSerializer()
    invite = InviteeProfileSerializer()
    class Meta:
        model = ChatMessages
        fields ='__all__'



class viewJobInviteSerializer(ModelSerializer):
    assessment = UserAssessmentDetailsSerializer()
    user = GetUSerDetailsSerializer()
    class Meta:
        model = JobInvites
        fields = '__all__'


class BasicJobAssessmentDetails(ModelSerializer):
    class Meta:
        model = JobAssessment
        fields = ['job_assessment_id','assessment_name','assessment_duration','total_marks']


class InviteSubmittedUrlSerializer(ModelSerializer):
    class Meta:
        model = InviteSubmittedUrl
        fields = '__all__'

class InviteAnalyticsSerializer(ModelSerializer):
    user = InviteUserProfileSerializer()
    capture_screen_videos = InviteSubmittedUrlSerializer(many=True)
    assessment  = BasicJobAssessmentDetails()
    class Meta:
        model = JobInvites
        fields = '__all__' 


class LiveIniviteUserDetails(ModelSerializer):
    user = GetUSerDetailsSerializer()
    assessment  = BasicJobAssessmentDetails()
    class Meta:
        model = JobInvites
        fields = ['invite_id','user','assessment','mobile_camera_is_on']


class JobInviteOldAttemptSerializer(ModelSerializer):
    class Meta:
        model = JobInviteOldAttempt
        fields = '__all__'


class ApplicationUserListSerializer(ModelSerializer):
    class Meta:
        model = ApplicationUserList
        fields ='__all__'