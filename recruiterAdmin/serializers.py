from rest_framework.serializers import ModelSerializer
from recruiterAdmin.models import Recruiter
from main.models import MyUser
from talent.models import RecruiterMembership
from talent.serializers import RecruiterGroupSerializer


class recruitermembershipGroupSerializer(ModelSerializer):
    group = RecruiterGroupSerializer(many=True, read_only=True)
    class Meta:
        model = RecruiterMembership
        fields = "__all__"


class RecruiterUserDetails(ModelSerializer):
    recruiter_membership =recruitermembershipGroupSerializer()
    class Meta:
        model = MyUser
        fields =['id','name','email','Phone_number','emp_id','image','Gender','role','Phone_number','is_first_login','is_suspend','is_recruiter','is_created_by_recruiter_admin','recruiter_membership']

class ViewRecriterSerializer(ModelSerializer):
    user = RecruiterUserDetails()
    class Meta:
        model = Recruiter
        fields = '__all__'