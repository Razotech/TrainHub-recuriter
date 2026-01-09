# Create your models here.
from typing import Iterable
from django.db import models
from django.contrib.auth.models import BaseUserManager,AbstractBaseUser,PermissionsMixin
from django.utils import timezone
import uuid
from datetime import date,timedelta
from django.core.exceptions import ValidationError
# Create your models here.

class CustomUserManager(BaseUserManager):
    def create_user(self, id=None, password=None, **extra_fields):
        if not id:
            raise ValueError("The user must have an ID")
        
        user = self.model(id=id, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, id, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        return self.create_user(id, password, **extra_fields)

class Organization(models.Model):
    PAYMENT_STATUS = (
        ('Done','Done'),
        ('Pending','Pending'),
    )
    company_name = models.CharField(max_length=256,primary_key=True)
    domainName = models.JSONField(default=list)
    orgId = models.UUIDField(default=uuid.uuid4)
    is_mfa = models.BooleanField(default=False)
    is_number_login = models.BooleanField(default=False)
    docusign_signature = models.BooleanField(default=False)
    telnet_id = models.CharField(max_length=256,blank=True,null=True,unique=True)
    logo = models.URLField(blank=True,null=True)
    image = models.TextField(blank=True,null=True)
    email_template_image = models.URLField(blank=True,null=True)
    static_content = models.TextField(blank=True,null=True)
    is_suspend = models.BooleanField(default=False)
    main_org = models.BooleanField(default=False)
    allocated_token = models.IntegerField(default=0)
    utilized_token = models.IntegerField(default=0)
    idle_timeout = models.IntegerField(blank=True,null=True)
    enforce_failed_login_limit = models.BooleanField(default=False)
    max_login_attempts = models.IntegerField(blank=True,null=True)
    lockout_duration = models.IntegerField(blank=True,null=True)
    payment_status = models.CharField(max_length=10,choices=PAYMENT_STATUS,blank=True,null=True)
    user_limit = models.IntegerField(default=1)
    job_assessment_limit = models.IntegerField(default=1)
    job_assessment_count = models.IntegerField(default=0)
    template_screens_limit = models.IntegerField(default=0)
    template_videos_limit = models.IntegerField(default=0)
    org_videos_limit = models.IntegerField(default=0)
    email_host = models.CharField(max_length=255,blank=True,null=True)
    email_host_app_password = models.CharField(max_length=100, blank=True,null=True)
    
    def __str__(self):
        return f'{self.company_name} '
    
    class Meta:
        indexes = [models.Index(fields=['orgId']),]

class Division(models.Model):
    division_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=256)
    organization = models.ForeignKey(Organization,models.CASCADE,related_name='org_division')

    def __str__(self):
        return f'{self.division_id} {self.name}'
    
    

class Branch(models.Model):
    branch_id = models.AutoField(primary_key=True)
    branch_location = models.CharField(max_length= 256)
    address = models.CharField(max_length=256)
    city = models.CharField(max_length =100)
    country = models.CharField(max_length=100)
    is_suspend = models.BooleanField(default=False)
    company_info = models.ForeignKey(Organization,models.CASCADE,related_name='company_branch')
    created_at=models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.branch_location} Company : {self.company_info}'


class DocuSignCredential(models.Model):

    docusign_id = models.AutoField(primary_key=True)
    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="docusign_credential"
    )
    
    # DocuSign API credentials
    client_id = models.CharField(max_length=128, help_text="DocuSign Integration Key (Client ID)")
    user_id = models.CharField(max_length=128, help_text="DocuSign User GUID for impersonation")
    # account_id = models.CharField(max_length=128, help_text="Account ID from DocuSign")
    auth_server = models.CharField(max_length=255, default="account-d.docusign.com")
    # base_path = models.CharField(max_length=255, default="https://demo.docusign.net")
    
    private_key_text = models.TextField(blank=True, null=True, help_text="Alternatively store private key directly")

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.organization} - {self.client_id}"

    class Meta:
        verbose_name = "DocuSign Credential"
        verbose_name_plural = "DocuSign Credentials"
        indexes = [models.Index(fields=["organization", "client_id"])]
        


class MyUser(AbstractBaseUser, PermissionsMixin):
    USER_ROLES = (
        # ('trainer', 'Trainer'),
        # ('trainee', 'Trainee'),
        # ('admin', 'Admin'),
        # ('superadmin','SuperAdmin'),
        # ('subsuperadmin','SubSuperAdmin'),
        ('recruiteradmin','recruiteradmin'),
        ('invite_user','invite_user')
    )
    GENDER_CHOICE = (
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    )
    REGISTRATION_TYPE = (
        ('email','email'),
        ('Phone_number','Phone_number')
    )

    id = models.AutoField(primary_key=True) 
    image = models.TextField(blank=True,null=True)
    emp_id = models.CharField(max_length=256, blank=True, null=True)
    name = models.CharField(max_length=256, blank=True, null=True)
    email = models.EmailField(max_length=256, blank=False, null=False)
    role = models.CharField(max_length=20, choices=USER_ROLES, default='trainee')
    address = models.TextField(blank=True, null=True)
    DOB = models.DateField(blank=True, null=True)
    registration_type = models.CharField(max_length=30,choices=REGISTRATION_TYPE,default='email')
    prev_passwords = models.JSONField(blank=True,null=True)
    Gender = models.CharField(max_length=10, choices=GENDER_CHOICE, blank=True, null=True)
    Phone_number = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    verification_code = models.CharField(max_length=10, blank=True, null=True)
    verification_code_created_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_first_login = models.BooleanField(default=True)
    is_main_user = models.BooleanField(default=False)
    is_suspend = models.BooleanField(default=False)
    assign_role = models.BooleanField(default=False)
    is_recruiter = models.BooleanField(default=False)
    is_created_by_recruiter_admin = models.BooleanField(default=False)
    company_details = models.ForeignKey(Organization, models.CASCADE, blank=True, null=True,related_name='user_company')
    branch = models.ForeignKey(Branch,models.SET_NULL,blank=True,null=True,related_name='user_branch')
    divison = models.ForeignKey(Division,on_delete=models.CASCADE,related_name='user_division', blank=True, null=True)
    allocated_token = models.IntegerField(default=0)
    utilized_token = models.IntegerField(default=0)
    objects = CustomUserManager()
    failed_login_attempts = models.IntegerField(default=0)
    lockout_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'id'
    REQUIRED_FIELDS = []  

    def __str__(self):
        return f'{self.id} -  {self.role}-{self.name} and email- {self.email}'

    def save(self, *args, **kwargs):
        # Ensure company_details is set before checking limit
        if self._state.adding and self.company_details:
            # Count current users associated with the organization
            current_user_count = MyUser.objects.only('id').filter(company_details=self.company_details).count()

            if current_user_count >= self.company_details.user_limit:
                raise ValidationError(f"User limit exceeded for organization '{self.company_details.company_name}'.")

        if self.emp_id and self.company_details:
            duplicate = MyUser.objects.filter(
                company_details=self.company_details,
                emp_id=self.emp_id
            ).exclude(id=self.id).exists()

            if duplicate:
                raise ValidationError("The employee ID already exists. Cannot proceed.")

        super().save(*args, **kwargs)


    def total_learning_time(self):
        completed = self.trainee_invites.filter(is_completed=True).select_related('enrolled_course')
        total_duration = sum([e.enrolled_course.time_allocated for e in completed if e.enrolled_course.time_allocated], timedelta())
        return round(total_duration.total_seconds() / 3600, 2) 
    

    class Meta:
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['Phone_number']),
            models.Index(fields=['role']),
            models.Index(fields=['company_details','role']),
        ]
        ordering = ['-created_at'] 

class Category(models.Model):
    category_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=256)
    company_details = models.ForeignKey(Organization, models.CASCADE,related_name='company_category')
    
    def __str__(self):
        return f'{self.category_id} {self.name}'

    # class Meta:
    #     indexes = [
    #         models.Index(fields=['company_details']),
    #     ]
    

class LastLoginDetails(models.Model):
    ip_address = models.GenericIPAddressField()
    browser = models.CharField(max_length=100)
    os = models.CharField(max_length=100)
    raw_user_agent = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(MyUser,models.CASCADE,related_name='user_login_details')
    
    def __str__(self):
        return f"{self.user} - {self.timestamp}"
    
    # class Meta:
    #     indexes = [models.Index(fields=['user'])]


class Notification(models.Model):
    title = models.CharField(max_length=256)
    message = models.TextField()
    is_read =models.BooleanField(default=False)
    user = models.ForeignKey(MyUser, models.CASCADE, related_name='notification_user')
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'{self.user.name} {self.user.email}'
    
    class Meta:
        indexes = [models.Index(fields=['user','is_read'])]



class UserActivity(models.Model):
    
    ACTION_CHOICES = [
        ('GET', 'Get'),
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    ]

    user = models.ForeignKey(MyUser, on_delete=models.CASCADE)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    description = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} {self.action} at {self.timestamp}"
    # class Meta:
    #     indexes = [
    #         models.Index(fields=['user']),
    #     ]
    


