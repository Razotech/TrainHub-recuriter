from django.db import models
from main.models import *
# Create your models here.


class InviteUserDetails(models.Model):
    
    invite_user_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(MyUser,models.CASCADE,related_name='invite_user_details')
    image_with_id = models.URLField(blank=True,null=True)    
    region = models.CharField(max_length=256, blank=True,null=True)
    location = models.CharField(max_length=100, blank=True,null=True)
    
    first_gov_id_proof = models.CharField(max_length=255,blank=True,null=True)
    first_gov_id_key = models.CharField(max_length=100,blank=True,null=True)
    first_gov_id_upload = models.URLField(blank=True,null=True)
    first_gov_id_verify = models.BooleanField(default=False)

    second_gov_id_proof = models.CharField(max_length=255,blank=True,null=True)
    second_gov_id_key = models.CharField(max_length=100,blank=True,null=True)
    second_gov_id_upload = models.URLField(blank=True,null=True)
    second_gov_id_verify = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    resume = models.URLField(blank=True,null=True)

    def __str__(self):
        return super().__str__()
    


class RecruiterGroup(models.Model):
    """
    A recruiter group. Each user can belong to only one group.
    """
    group_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    user = models.ForeignKey(MyUser,models.SET_NULL,related_name='recruiter_group_created_by',null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f" Id {self.group_id} -{self.name}"


class RecruiterMembership(models.Model):
    """
    Enforces one-to-one relationship between user and group (only one group per user).
    """
    member_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(MyUser, on_delete=models.CASCADE, related_name="recruiter_membership")
    group = models.ManyToManyField(RecruiterGroup,related_name="members")

    def __str__(self):
        return f"{self.user} -> {self.group}"



class JobListing(models.Model):
    job_id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    job_link = models.URLField(blank=True,null=True)
    user = models.ForeignKey(MyUser,models.CASCADE,related_name='user_job_listing')
    group = models.ForeignKey(RecruiterGroup, on_delete=models.CASCADE, related_name='job_listings',blank=True,null=True)
    experience_level_from = models.IntegerField(blank=True,null=True,help_text='minimum exprience level in years')
    experience_level_to = models.IntegerField(blank=True,null=True,help_text='maximum exprience level in years')
    custom_message = models.TextField(blank=True,null=True)
    created_at = models.DateTimeField(default=timezone.now)
    archive = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    
    def __str__(self):
        return f"Job ID : {self.job_id} Title: {self.title} user : {self.user}"


class JobAssessment(models.Model):
    ASSESSMENT_TYPE =(
    ('MIXED_QUESTIONS','mixed_questions'),
    )
    job_assessment_id = models.AutoField(primary_key=True)
    assessment_name = models.CharField(max_length=256)
    assessment_type = models.CharField(max_length=100,choices=ASSESSMENT_TYPE) 
    assessment = models.JSONField(null=True, blank=True)
    assessment_duration = models.DurationField(blank=True,null=True)
    allocted_question = models.IntegerField(default=0)
    job = models.ForeignKey(JobListing,models.CASCADE,related_name='Job_details')
    total_questions = models.IntegerField(default=0)
    total_marks = models.IntegerField(default=0)
    shortlist_percentage = models.IntegerField(default=0)
    review_percentage = models.IntegerField(default=0)
    rejected_percentage = models.IntegerField(default=0)
    proctoring_enable = models.BooleanField(default=False)
    face_detection =models.IntegerField(null=True,blank=True)
    voice_detection=models.IntegerField(null=True,blank=True)
    backgound_detection = models.IntegerField(null=True,blank=True)
    mobile_object_detection = models.IntegerField(null=True,blank=True)
    mobile_monitoring_off_warnings = models.IntegerField(null=True,blank=True)
    object_detection = models.IntegerField(null=True,blank=True)
    window_detection = models.IntegerField(null=True,blank=True)
    eye_capture_detection = models.IntegerField(null=True,blank=True)
    exam_instruction = models.TextField(blank=True,null=True)
    video_instruction_url = models.URLField(blank=True,null=True)
    is_public = models.BooleanField(blank=True,null=True)
    archive = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Job Assessment id : {self.job_assessment_id}, Name :{self.assessment_name}, job:{self.job}'

class JobInvites(models.Model):
    INVITE_STATUS =(
    ('pending','pending'),
    ('accepted','accepted'),
    ('rejected','rejected')
    )
    SUBMIT_STATUS = (
        ('not_started','not_started'),
        ('inprogress','inprogress'),
        ('review','review'),
        ('short_listed','short_listed'),
        ('not_short_listed','not_short_listed'),
        ('completed','completed')
    )
    invite_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(MyUser,models.CASCADE,related_name='invite_user',blank=True,null=True)
    invite_status = models.CharField(max_length=15,choices=INVITE_STATUS,default='pending')
    assessment = models.ForeignKey(JobAssessment,on_delete=models.CASCADE,related_name='job_assessment')
    selection_questions = models.JSONField(blank=True, null=True)
    completed_assessment = models.JSONField(blank=True, null=True)
    marks_scored = models.FloatField(blank=True, null=True)
    percentage = models.FloatField(blank=True, null=True)
    marks_details = models.JSONField(blank=True,null=True)

    is_schduled = models.BooleanField(default=False)
    schdule_start_time = models.DateTimeField(blank=True,null=True)
    schdule_end_time = models.DateTimeField(blank=True,null=True)

    start_time = models.DateTimeField(blank=True,null=True)
    submit_time = models.DateTimeField(blank=True,null=True)
    
    utilized_duration = models.CharField(max_length=100,blank=True,null=True)
    submit_status = models.CharField(max_length=20,choices=SUBMIT_STATUS,default='not_started')
    reason = models.TextField(blank=True,null=True)
    
    mobile_camera_is_on = models.BooleanField(default=False)

    proctoring_detected = models.BooleanField(default=False)
    
    image_proctoring_json = models.JSONField(blank=True,null=True)
    face_detection_count =models.IntegerField(default=0)

    audio_proctoring_json = models.JSONField(blank=True,null=True)
    voice_detection_count = models.IntegerField(default=0)
    
    backgound_detection_json = models.JSONField(blank=True,null=True)
    backgound_detection_count = models.IntegerField(default=0)
    
    object_detection_json = models.JSONField(blank=True,null=True)
    object_detection_count = models.IntegerField(default=0)
    
    window_detection_json = models.JSONField(blank=True,null=True)
    window_detection_count = models.IntegerField(default=0)

    eye_capture_detection_json = models.JSONField(blank=True,null=True)
    eye_capture_detection_count = models.IntegerField(default=0)

    capture_images = models.JSONField(blank=True,null=True)
    capture_audios = models.JSONField(blank=True,null=True)
    capture_surrounding = models.URLField(blank=True,null=True) 
    
    capture_mobile_videos = models.JSONField(blank=True,null=True)
    # capture_screen_videos = models.JSONField(blank=True,null=True)

    mobile_detection_json = models.JSONField(blank=True,null=True)
    mobile_detection_count = models.IntegerField(default=0)

    mobile_warning_json = models.JSONField(blank=True,null=True)
    mobile_warning_count = models.IntegerField(default=0)
    
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    image = models.URLField(blank=True,null=True)
    audio = models.URLField(blank=True,null=True)
    
    is_reake = models.BooleanField(default=False)
    retake_count = models.IntegerField(default=0)
    rekate_allow = models.IntegerField(blank=True,null=True)
    cool_down_period = models.IntegerField(blank=True,null=True)

    def __str__(self):
        return f'Id : {self.invite_id} user : {self.user}  Assessment {self.assessment}'
    
class InviteSubmittedUrl(models.Model):
    invite = models.ForeignKey(JobInvites,models.CASCADE,related_name='capture_screen_videos')
    url_json = models.JSONField()
    url_type = models.CharField(max_length=100,default='screen_recording')
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.invite}"
    

class ApplicationUserList(models.Model):
    APPLICATION_STATUS = (
        ('pending','pending'),
        ('invited','invited'),
        ('rejected','rejected')
    )
    application_id = models.AutoField(primary_key=True)
    job = models.ForeignKey(JobListing,on_delete=models.CASCADE,related_name='application_list')
    name = models.CharField(max_length=255)
    email = models.EmailField()
    experience = models.IntegerField()
    resume_url = models.URLField()
    application_status = models.CharField(max_length=50,choices=APPLICATION_STATUS ,default='pending')
    resume_score = models.IntegerField(blank=True,null=True)
    
    region = models.CharField(max_length=256, blank=True,null=True)
    first_gov_id_proof = models.CharField(max_length=255,blank=True,null=True)
    first_gov_id_key = models.CharField(max_length=100,blank=True,null=True)
    first_gov_id_upload = models.URLField(blank=True,null=True)
    first_gov_id_verify = models.BooleanField(default=False)

    second_gov_id_proof = models.CharField(max_length=255,blank=True,null=True)
    second_gov_id_key = models.CharField(max_length=100,blank=True,null=True)
    second_gov_id_upload = models.URLField(blank=True,null=True)
    second_gov_id_verify = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    


class SubmittedAssessmentQuestion(models.Model):
    invite = models.ForeignKey(JobInvites, models.CASCADE, related_name="submitted_questions")
    submitted_question = models.JSONField()  
    utilized_duration = models.CharField(max_length=50)  
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Id : {self.id} invite : {self.invite}"


class JobNPSModel(models.Model):
    job_nps_id = models.AutoField(primary_key=True)
    invte_user = models.ForeignKey(JobInvites, on_delete=models.CASCADE, related_name='job_nps_user', blank=False)
    job_assessment = models.ForeignKey(JobAssessment, on_delete=models.CASCADE, related_name='nps_job_assessment', blank=False)
    rating = models.IntegerField(blank=True, null=True)
    feedback = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def category(self):
        if self.rating is None:
            return None
        elif self.rating <= 3:
            return 'poor'
        elif 4 <= self.rating <=6 :
            return 'bad'
        elif 7 <= self.rating <= 8:
            return 'good'
        else:
            return 'excellent'

    def __str__(self):
        return f'NPS {self.job_nps_id}: invite_user : {self.invte_user} : job: {self.job_assessment} '

    class Meta:
        ordering = ['-created_at']




class ChatMessages(models.Model):
    SENDER=(
        ('trainer','trainer'),
        ('invite','invite')
    )
    trainer = models.ForeignKey(MyUser,models.CASCADE,related_name='trainer_chat_message')
    invite = models.ForeignKey(JobInvites,models.CASCADE,related_name='invitee_chat_messages')
    assessment = models.ForeignKey(JobAssessment,models.CASCADE,related_name='asssessment_chat_messages')
    message = models.TextField(blank=True,null=True)
    sender = models.CharField(max_length=15,choices=SENDER)
    is_trainer_read = models.BooleanField(default=False)
    is_invite_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return super().__str__()



class JobInviteOldAttempt(models.Model):
    old_attempt_id = models.AutoField(primary_key=True)
    invite = models.ForeignKey(JobInvites,on_delete=models.CASCADE,related_name='old_attempt')
    assessment_json = models.JSONField()
    retake_no = models.IntegerField()
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"ID :{self.old_attempt_id} invite : {self.invite}   retake : {self.retake_no}"

