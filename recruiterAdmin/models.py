from django.db import models
from main.models import MyUser

class Recruiter(models.Model):
    recruiter_id = models.AutoField(primary_key=True)
    user = models.OneToOneField(MyUser,models.CASCADE,related_name='recuriter_user')
    suspend = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"recruiter Id : {self.recruiter_id} : user : {self.user} "

