from django.shortcuts import render
from main.models import MyUser
from recruiterAdmin.models import Recruiter
from main.serializers import UserUpdateSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from talent.models import *
from drf_yasg.utils import swagger_auto_schema
from main.views import log_user_activity
from main.task import send_notification
from drf_yasg import openapi
from Admin.tasks import user_generation_task
from django.shortcuts import get_object_or_404
from recruiterAdmin.serializers import *
from main.pagination import CustomPagination
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated



class MarkUserAsRecruiter(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Assign a User as Recruiter",
        operation_description="Assigns an existing user to the recruiter role and adds them to a recruiter group.",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["user_id", "group_id"],
            properties={
                "user_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the user to make recruiter"),
                "group_id": openapi.Schema(type=openapi.TYPE_INTEGER, description="ID of the recruiter group"),
            },
        ),
        tags=["Recruiter-admin"],
    )
    def post(self,request):
        data = request.data
        user_id = data.get('user_id')
        group_id = data.get('group_id')
        
        user = get_object_or_404(MyUser,id=user_id)
        group = get_object_or_404(RecruiterGroup,group_id=group_id)
        
        try:
            Recruiter.objects.create(user=user)
            recuriter_member = RecruiterMembership.objects.create(user=user)
            recuriter_member.group.set(group_id)

        except Exception as e :
            return Response({'responseMessage':str(e)},status=status.HTTP_400_BAD_REQUEST)
        
        
        user.is_recruiter = True
        user.save(update_fields = ['is_recruiter'])
        log_user_activity(user, 'UPDATE', f'USer {user.name} has marked as recuriter')
        return Response({'responseMessage':'User set as recruiter'},status=status.HTTP_200_OK)
    


class RecuriterProfile(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Recuriter profile",
        operation_description="",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=["Recruiter-admin"],
    )
    def get(self,request):
        user = request.user
        recuriter = Recruiter.objects.filter(user = user).first()
        if recuriter:
            serializer = ViewRecriterSerializer(recuriter)
            return Response({'data':serializer.data,'responseMessage':'Profile Retrive successfully'},status=status.HTTP_200_OK)
        return Response({'responseMessage':'Recuriter profile not found'},status=status.HTTP_400_BAD_REQUEST)
        

class RecuriterUserManagement(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Recuriter list ",
        operation_description="",
        manual_parameters=[
            openapi.Parameter('page', openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER),
            openapi.Parameter('page_size', openapi.IN_QUERY, description="Number of items per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter('search', openapi.IN_QUERY, description="Search by user name", type=openapi.TYPE_STRING),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=["Recruiter-admin"],
    )
    def get(self,request):
        user = request.user
        search = request.query_params.get('search')

        recuriter_user  = Recruiter.objects.filter(user__company_details = user.company_details).order_by('-created_at')

        if search:
            recuriter_user = recuriter_user.filter(user__name__icontains = search)
        
        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(recuriter_user, request)
        serializer = ViewRecriterSerializer(paginated_querySet,many =True)
        
        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data,status=status.HTTP_200_OK)

    @swagger_auto_schema(
        operation_summary='This API allows an admin to create multiple users and associate them with the same company as the requesting user',
        manual_parameters=[
            openapi.Parameter('registration_type', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['email','Phone_number']),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        request_body=openapi.Schema(
        type=openapi.TYPE_ARRAY,
        description="Array of user/recruiter objects to be created",
        items=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING),
                "Phone_number":openapi.Schema(type=openapi.TYPE_INTEGER),
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "role": openapi.Schema(type=openapi.TYPE_STRING, enum=["trainer", "trainee", "admin"]),
                "emp_id": openapi.Schema(type=openapi.TYPE_STRING),
                "password":openapi.Schema(type=openapi.TYPE_STRING),            
                "group_id": openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Schema(type=openapi.TYPE_INTEGER)),     
            },
            required=["name", "email", "emp_id", "role"],
        ),
    ),
    tags=["Recruiter-admin"],
    )
    def post(self,request):

        user = request.user
        data = request.data.copy()
        email_list =[]

        current_user_count = MyUser.objects.filter(company_details=user.company_details).count()
        user_limit = user.company_details.user_limit


        if user_limit is not None and (current_user_count + len(data)) > user_limit:
            return Response(
                {
                    'responseMessage': f'Cannot create users. Limit of {user_limit} would be exceeded.'},
                status=status.HTTP_403_FORBIDDEN
            )

        for obj in data:
            registration_type = obj['registration_type']
            required_fields = {"emp_id", "name", "role",f"{registration_type}"}
            
            if not all(field in obj and obj[field] for field in required_fields):
                return Response(
                    {"error": f"All objects must contain emp_id, name, '{registration_type}', and role with values"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            obj['company_details'] = user.company_details
            obj['is_verified'] = True
            obj['is_recruiter'] = True
            obj['is_created_by_recruiter_admin']= True

            if 'email' in obj and obj['email'] and obj['registration_type'] == 'email':
                email_list.append(obj['email'].strip().lower())

            existing_emails = list(MyUser.objects.filter(email__in=email_list,company_details=user.company_details).values_list('email', flat=True))

            if existing_emails:
            
                return Response({
                    'responseMessage': 'One or more users already exist with the provided email or phone number.',
                    'existing_emails': existing_emails,
                }, status=status.HTTP_400_BAD_REQUEST)
            
        user_generation_task.delay(data,user)
        
        title = "User Creation"
        message = "New user(s) have been created and credentials are sent."
        send_notification(title, message, user)
        log_user_activity(user, 'CREATE', f'New User(s) have been created')
        return Response({'responseMessage':'User created successfully & Credentials sent to registered emails.'},status=status.HTTP_200_OK)


    @swagger_auto_schema(
        operation_summary='update user',
        manual_parameters=[
        openapi.Parameter('user_id', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='User id of user '),
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "name": openapi.Schema(type=openapi.TYPE_STRING),
                "Phone_number":openapi.Schema(type=openapi.TYPE_INTEGER),
                "email": openapi.Schema(type=openapi.TYPE_STRING),
                "emp_id": openapi.Schema(type=openapi.TYPE_STRING),            
                "group_id": openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Schema(type=openapi.TYPE_INTEGER)),     
            },
    ),    
    tags=['Recruiter-admin'],
    )
    def put(self,request):
        user_id = request.query_params.get('user_id')

        user = get_object_or_404(MyUser,id = user_id)
        data = request.data.copy()
        group_ids = data.pop('group_id',None)
        filter_data = {k: v for k, v in data.items() if v not in ['null', '', None]}
        
        serializer = UserUpdateSerializer(user, data=filter_data, partial=True)
        if serializer.is_valid():
            serializer.save()
            if group_ids:
                group_membership= get_object_or_404(RecruiterMembership.objects.prefetch_related('group'),user=user)
                # for group_id in group_ids:
                #     if group_id not in  group_membership.group.all():
                #         # group = get_object_or_404(RecruiterGroup,group_id=group_id)
                group_membership.group.set(group_ids)
                        # group_membership.save(update_fields=['group'])

            title = "User Update"
            message = f'User "{user.email}" has been updated successfully.'
            send_notification(title, message, request.user)
            log_user_activity(request.user, 'UPDATE', f'User {user.name} have been updated')
            return Response({'data':serializer.data, 'responseMessage':'User updated successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors, 'responseMessage':'something is wrong'},status=status.HTTP_400_BAD_REQUEST)
    

    @swagger_auto_schema(
        operation_summary='delete user/recruiter',
        manual_parameters=[
        openapi.Parameter('recruiter_id', openapi.IN_QUERY, type=openapi.TYPE_STRING, description='recruiter_id of user '),
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=['Recruiter-admin']
    )
    def delete(self,request):
        recruiter_id = request.query.params.get('recruiter_id')

        recruiter = get_object_or_404(Recruiter,recruiter_id=recruiter_id)
        if recruiter.user.is_recruiter and recruiter.user.is_created_by_recruiter_admin:
            recruiter.user.delete()
            log_user_activity(request.user, 'DELETE', f'Recruiter "{recruiter.user.name}" has been removed ')
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'responseMessage':'You can delete LMS users'},status=status.HTTP_400_BAD_REQUEST)


class RemoveRecuriter(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Remove Recruiter",
        operation_description="Remove a recruiter by recruiter_id. If the user was created by a recruiter admin, the user will also be deleted. Otherwise, only recruiter role is removed.",
        manual_parameters=[
            openapi.Parameter("recruiter_id",openapi.IN_QUERY,description="Recruiter ID to be removed",type=openapi.TYPE_INTEGER,required=True),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin"],
    )
    def get(self,request):
        recruiter_id = request.query_params.get('recruiter_id')
        recruiter = get_object_or_404(Recruiter,recruiter_id=recruiter_id) 
        user = recruiter.user

        RecruiterMembership.objects.filter(user=user).delete()
        if user.is_created_by_recruiter_admin:
            user.delete()
        else:
            user.is_recruiter = False
            user.save(update_fields = ['is_recruiter'])
            recruiter.delete()
        
        log_user_activity(request.user, 'DELETE', f'Recruiter "{recruiter.user.name}" has been removed ')

        return Response(status=status.HTTP_204_NO_CONTENT)


class UpdateSuspendRecuriter(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Update Recruiter Suspend Status",
        operation_description="Suspend or unsuspend a recruiter by recruiter_id. Pass `true` or `false` in the suspend field.",
        manual_parameters=[
            openapi.Parameter("recruiter_id",openapi.IN_QUERY,description="Recruiter ID to be removed",type=openapi.TYPE_INTEGER,required=True),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin"],
    )
    def post(self,request):
        recruiter_id = request.query_params.get('recruiter_id')
        

        recruiter = get_object_or_404(Recruiter,recruiter_id=recruiter_id)
        recruiter.suspend = not recruiter.suspend
        recruiter.save()
        log_user_activity(request.user, 'UPDATE', f'Recruiter user "{recruiter.user.name}" suspend status updated and marked as "{recruiter.suspend}"')
        return Response({'responseMessage':'Recruiter Status updated'},status=status.HTTP_200_OK)



class DeleteInviteOldRecord(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Delete old records of job invites.",
        operation_description="",
        manual_parameters=[

            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin"],
    )
    def get(self,request):
        from main.task import delete_old_invite_record
        user = request.user
        delete_old_invite_record.delay()

        return Response({'responseMessage':'Deletion process has been started'},status=status.HTTP_200_OK)
    




#  ==================================== Dashboard ========================================
from django.db.models import Count, Case, When, IntegerField
from django.db.models import Count
from django.db.models.functions import TruncDate


class RecuriterOverview(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Recuriter dashboard overview.",
        operation_description="",
        manual_parameters=[

            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin / Dashboard"],
    )
    def get(self, request):
        user = request.user

        if user.role == 'trainer':
            group_membership = get_object_or_404(RecruiterMembership, user=user)

            job_listing = (
                JobListing.objects.filter(
                    group__in=group_membership.group.all(),
                    archive=False
                )
                .order_by('-updated_at')
            )

        elif user.role in ['recruiteradmin', 'admin']:
            job_listing = (
                JobListing.objects
                .filter(
                    group__user__company_details=user.company_details,
                    archive=False
                )
                .order_by('-updated_at')
            )

        else:
            return Response({"responseMessage":"User role not allowed"},status=status.HTTP_400_BAD_REQUEST)

        total_jobs = job_listing.count()

        job_seekers = JobInvites.objects.filter(
            assessment__job__in=job_listing
        ).aggregate(
            not_started=Count(
                Case(When(submit_status='not_started', then=1), output_field=IntegerField())
            ),
            inprogress=Count(
                Case(When(submit_status='inprogress', then=1), output_field=IntegerField())
            ),
            under_review=Count(
                Case(When(submit_status='review', then=1), output_field=IntegerField())
            ),
            short_listed=Count(
                Case(When(submit_status='short_listed', then=1), output_field=IntegerField())
            ),
            not_short_listed=Count(
                Case(When(submit_status='not_short_listed', then=1), output_field=IntegerField())
            ),
            completed=Count(
                Case(When(submit_status='completed', then=1), output_field=IntegerField())
            ),
        )

        job_seekers['total_jobs'] = total_jobs

        return Response({'data':job_seekers,'responseMessage':'Data found successfully'},
                        status=status.HTTP_200_OK
                        )



class StatusDestribution(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Recuriter distribution status for pie chart.",
        operation_description="",
        manual_parameters=[

            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin / Dashboard"],
    )
    def get(self,request):
        
        user = request.user
        job_assessment_id = request.query_params.get('job_assessment_id')

        if user.role == 'trainer':
            group_membership = get_object_or_404(RecruiterMembership, user=user)

            Job_assessment =  JobAssessment.objects.filter(job__group__in=group_membership.group.all(),job__archive=False)
            
            if not job_assessment_id:
                Job_assessment = Job_assessment.latest()
            
            else:
                Job_assessment = Job_assessment.get(job_assessment_id=job_assessment_id)
            

        elif user.role in ['recruiteradmin', 'admin']:

            Job_assessment =  JobAssessment.objects.filter(job__group__user__company_details=user.company_details,job__archive=False)
            
            if not job_assessment_id:
                Job_assessment = Job_assessment.latest()
            
            else:
                Job_assessment = Job_assessment.get(job_assessment_id=job_assessment_id)
            
        else:
            return Response({"responseMessage":"User role not allowed"},status=status.HTTP_400_BAD_REQUEST)

        job_seekers = JobInvites.objects.filter(
            assessment = Job_assessment
        ).aggregate(
            not_started=Count(
                Case(When(submit_status='not_started', then=1), output_field=IntegerField())
            ),
            inprogress=Count(
                Case(When(submit_status='inprogress', then=1), output_field=IntegerField())
            ),
            under_review=Count(
                Case(When(submit_status='review', then=1), output_field=IntegerField())
            ),
            short_listed=Count(
                Case(When(submit_status='short_listed', then=1), output_field=IntegerField())
            ),
            not_short_listed=Count(
                Case(When(submit_status='not_short_listed', then=1), output_field=IntegerField())
            ),
            completed=Count(
                Case(When(submit_status='completed', then=1), output_field=IntegerField())
            ),
        )

        return Response({'data':job_seekers,'responseMessage':'Data found successfully'},
                        status=status.HTTP_200_OK
                        )


class InvitationAnalytics(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="The list chart shows invites by count weekly.",
        operation_description="",
        manual_parameters=[

            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        tags=["Recruiter-admin / Dashboard"],
    )
    def get(self, request):
        user = request.user
        today = timezone.now().date()
        last_7_days = today - timedelta(days=6)

        if user.role == 'trainer':
            group_membership = get_object_or_404(RecruiterMembership, user=user)

            job_invites = JobInvites.objects.filter(
                assessment__job__group__in=group_membership.group.all(),
                created_at__date__range=[last_7_days, today]
            )

        elif user.role in ['recruiteradmin', 'admin']:
            job_invites = JobInvites.objects.filter(
                assessment__job__group__user__company_details=user.company_details,
                created_at__date__range=[last_7_days, today]
            )

        else:
            return Response(
                {"responseMessage": "User role not allowed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        analytics = (
            job_invites
            .annotate(date=TruncDate('created_at'))
            .values('date')
            .annotate(invited_users=Count('id'))
            .order_by('date')
        )

        return Response({"data":analytics,'responseMessage':'Data found successfully'},status=status.HTTP_200_OK)
    
class Jobseekeranalytics(APIView):
    def get(self, request):
        user = request.user

        if user.role == 'trainer':
            group_membership = get_object_or_404(RecruiterMembership, user=user)

            job_invites = JobInvites.objects.filter(
                assessment__job__group__in=group_membership.group.all()
            )

        elif user.role in ['recruiteradmin', 'admin']:
            job_invites = JobInvites.objects.filter(
                assessment__job__group__user__company_details=user.company_details
            )

        else:
            return Response(
                {"responseMessage": "User role not allowed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        analytics = (
            job_invites
            .values(
                'assessment__job__job_id',
                'assessment__job__title'
            )
            .annotate(total_invites=Count('id'))
            .order_by('-created_at')
        )

        response = [
            {
                "job_id": row['assessment__job__job_id'],
                "job_title": row['assessment__job__title'],
                "total_invites": row['total_invites']
            }
            for row in analytics
        ]

        return Response({'data':response,'responseMessage':'Data found successfully'})