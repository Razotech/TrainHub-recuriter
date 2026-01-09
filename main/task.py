from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import time
from django.db import transaction
from celery import shared_task
from main.models import *
from trainer.models import *

from PIL import Image
from django.conf import settings
from decouple import config
from django.template.loader import render_to_string
import httpagentparser
from django.core.cache import cache
from html2image import Html2Image
from django.utils import timezone
import os
from trainee.models import TraineeProgress,TraineeVideos
from botocore.exceptions import NoCredentialsError
from main.email import send_certification_email
from celery import shared_task
from sentry_sdk import capture_exception

BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')
REGION = config('AWS_DEFAULT_REGION')



def send_notification(title, message, user):
    cache.delete_pattern(f"notifiction_user_{user.id}_page_*")
    notification = Notification.objects.create(title = title,message= message , user =user)
    
    channel_layer = get_channel_layer()
    # print('channel_layer in task ',channel_layer)
    if channel_layer is None:
        print('we got a none in channel layer')
    else:
        
        async_to_sync(channel_layer.group_send)(
            f"notifications_{user.id}",
            {
                "type": "send_notification_message",
                "message": {'id':notification.id,
                            'title':title,
                            'message':message,
                            'user':user.id,
                            "notification_count":Notification.objects.filter(user=user,is_read=False).count()
                            }
            }
        )





@shared_task
def last_login_details_task(user_agent,user,ip):
    parsed_user_agent = httpagentparser.detect(user_agent)
                
    browser = parsed_user_agent.get('browser', {}).get('name', 'Unknown')
    os = parsed_user_agent.get('os', {}).get('name', 'Unknown')
    cache.delete_pattern(f"last_login_details_user_{user.id}_page_*")
    print('we are in last login details')
    LastLoginDetails.objects.create(
        ip_address=ip,
        browser=browser,
        os=os,
        raw_user_agent=user_agent,
        user = user
    )


from main.teams import create_teams_meeting
from datetime import datetime
from main.email import send_email_to_host_user
from dateutil import parser

@shared_task
def send_demo_email_to_user(data):
    name = data.get('name')
    email = data.get('email')
    phone_number = data.get('phone_number')
    organization_name = data.get('organization_name')
    time_slot_str = data.get('time_slot')
    message = data.get('message')
    
    subject = "Your Demo with Razzo Technologies is Scheduled!"
    try:
        start_time_dt = parser.isoparse(time_slot_str)
        start_time_dt = start_time_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_time_dt = start_time_dt + timedelta(hours=1)
    
    except ValueError:
        return {"status": "error", "message": "Invalid time format. Use ISO format (YYYY-MM-DDTHH:MM:SSZ)"}

    attendees = [{
        "emailAddress": {
            "address": email,
            "name": name
        },
        "type": "required"
    }]

    description = f'''
Hi {name},

✅ Your demo with Razzo Technologies has been successfully scheduled.

📅 Date & Time: {start_time_dt.strftime('%A, %d %B %Y at %I:%M %p')}
⏰ Duration: 1 Hour  

If you have any questions, feel free to reply to this email.

Regards,  
Team Razzo

'''

    response_data = create_teams_meeting(subject,description,str(start_time_dt),str(end_time_dt),attendees,"info@razzotech.in")
    email_message = f'''
Hello,

The user **{name}** from **{organization_name}** has requested a demo.

📅 Date & Time: {start_time_dt.strftime('%A, %d %B %Y at %I:%M %p')}

Here are the user details:

- Name         : {name}
- Email        : {email}
- Phone Number : {phone_number}
- Organization : {organization_name}
- Time Slot    : {start_time_dt.strftime('%A, %d %B %Y at %I:%M %p')}
- Message      : {message}
'''

    if 'id' in response_data:
        print("Email has been sent to user")
        email_message += "\n\n✅ Note: Invitation has been successfully sent.\n\nRegards,\nRazzo Team"
    else:
        email_message += f"\n\n❌ Note: Failed to send invitation.\nReason:\n{response_data}\n\nRegards,\nRazzo Team"

    send_email_to_host_user(email_message)


from talent.models import JobInvites
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from talent.inference import run_proctoring_check,detect_object_from_mobile,face_recorgnization_detection
from celery import current_app
import redis
from django.conf import settings
from trainer.func import delete_image_from_s3_https

# r = redis.Redis.from_url("redis://127.0.0.1:6379/0")  
r = redis.Redis.from_url("redis://:Razzotech%401@13.201.247.56:6379/0")  





@shared_task
def enforce_object_detection_to_db(invite_id, current_url, time, reply_channel_name):
    """
    Orchestrator: enqueue inference
    """
    payload = {
        "invite_id": invite_id,
        "current_url": current_url,
        "time": time,
        "reply_channel_name": reply_channel_name
    }
    # Route to GPU worker
    run_detection.delay(payload)



@shared_task
def run_detection(payload):
    invite_id = payload["invite_id"]
    url = payload["current_url"]

    invite = JobInvites.objects.get(invite_id=invite_id)

    is_object_detected = run_proctoring_check(url)
    payload["is_object_detected"] = is_object_detected
    
    counter_key = f"face_count:{invite_id}"
    count = r.get(counter_key)
    
    count = int(count) if count else 0
    
    if count % 5 == 0:
        is_face_detected = face_recorgnization_detection(invite.image, url)
    else:
        is_face_detected = False  
    
    payload["is_face_detected"] = is_face_detected
    r.incr(counter_key)

    update_invite_with_results.delay(payload)



@shared_task
def update_invite_with_results(payload):
    invite_id = payload["invite_id"]
    is_object_detected = payload["is_object_detected"] 
    is_face_detected =payload["is_face_detected"]  
    current_url = payload['current_url']
    reply_channel_name = payload['reply_channel_name']
    time = payload['time']

    channel_layer = get_channel_layer()
    if channel_layer and reply_channel_name:
        print("sending data to latop consumer ")
        try:
            async_to_sync(channel_layer.send)(reply_channel_name, {
            "type": "send_object_proctoring_result",
            "message":{
            "invite_id": invite_id,
            "is_object_detected": is_object_detected,
            'is_face_detected':is_face_detected,
            "is_proctoring_detected":False,
            }
            })
        except Exception as e:
            print(str(e))
            pass


    invite = JobInvites.objects.select_related("assessment").get(invite_id=invite_id)
    
    fields = []
    if is_object_detected:
        object_detection_json = invite.object_detection_json or []
        object_detection_json.append({"time": time, "image_url": current_url})
        invite.object_detection_json = object_detection_json
        fields.append("object_detection_json")
        
        if invite.assessment.object_detection <= invite.object_detection_count + 1:
            invite.proctoring_detected = True
            fields.append("proctoring_detected")

        invite.object_detection_count += 1
        fields.append("object_detection_count")


    if is_face_detected:
        if invite.assessment.face_detection <= invite.face_detection_count:
            invite.proctoring_detected = True
            fields.append("proctoring_detected")
        
        image_proctoring_json = invite.image_proctoring_json or []
        image_proctoring_json.append({'url':current_url,'time':time})
        invite.image_proctoring_json = image_proctoring_json
        invite.face_detection_count += 1
        fields.extend(["image_proctoring_json","face_detection_count"])

    if fields:
        try:
            with transaction.atomic():
                invite.save(update_fields=fields)
        except Exception:
            # In high contention cases, you may prefer a retry or switch to FK models
            pass
    
    if not is_object_detected and not is_face_detected:
        delete_image_from_s3_https(current_url)






@shared_task
def enforce_mobile_object_detection_to_db(invite_id, video_url, image_url,reply_channel_name):
    if video_url:
        payload = {
            "invite_id":invite_id,
            "video_url":video_url,
            }
        update_invite_with_mobile_result.delay(payload)

    else:
        payload = {
            "invite_id":invite_id,
            "image_url":image_url,
            "reply_channel_name":reply_channel_name
            }
        
        run_mobile_detection.delay(payload)
        


@shared_task
def run_mobile_detection(payload):
    invite_id = payload.get('invite_id')
    image_url = payload.get('image_url')

    invite = JobInvites.objects.select_related("assessment").only(
        "invite_id",
        "assessment__mobile_object_detection",
    ).get(invite_id=invite_id)


    if image_url and getattr(invite.assessment, "mobile_object_detection", False):
        try:
            is_object_detected = bool(detect_object_from_mobile(image_url["url"]))
        except Exception:
            # Never let detection errors crash the pipeline
            is_object_detected = False

    payload['is_object_detected'] = is_object_detected
    update_invite_with_mobile_result.delay(payload)





@shared_task
def update_invite_with_mobile_result(payload):
    video_url = payload.get('video_url')
    invite_id = payload.get('invite_id')
    image_url = payload.get('image_url')
    reply_channel_name = payload.get('reply_channel_name')
    is_object_detected = payload.get("is_object_detected")


    channel_layer = get_channel_layer()
    if channel_layer and reply_channel_name:
        print("sending data to latop consumer ")
        try:
            async_to_sync(channel_layer.send)(reply_channel_name, {
            "type": "send_result",
            "message":{
            "invite_id": invite_id,
            "is_object_detected": is_object_detected,
            "is_proctoring_detected":False,
            }
            })
        except Exception as e:
            print(str(e))
            pass


    invite = JobInvites.objects.get(invite_id=invite_id)

    fields = []

    if video_url:
        videos = invite.capture_mobile_videos or []
        videos.append(video_url)
        invite.capture_mobile_videos = videos
        fields.append("capture_mobile_videos")

    if is_object_detected:
        detections = invite.mobile_detection_json or []
        detections.append(image_url)  # keep the original dict
        invite.mobile_detection_json = detections
        invite.mobile_detection_count = (invite.mobile_detection_count or 0) + 1
        fields.extend(["mobile_detection_json", "mobile_detection_count"])

        # If threshold exceeded, flag proctoring
        threshold = getattr(invite.assessment, "mobile_object_detection", 0) or 0
        if invite.mobile_detection_count >= threshold:
            if not invite.proctoring_detected:
                invite.proctoring_detected = True
                fields.append("proctoring_detected")
    
    if fields:
        try:
            with transaction.atomic():
                invite.save(update_fields=fields)
        except Exception:
            # In high contention cases, you may prefer a retry or switch to FK models
            pass
    if not is_object_detected and image_url:
        delete_image_from_s3_https(image_url["url"])


from django.shortcuts import get_object_or_404
from talent.models import SubmittedAssessmentQuestion,InviteSubmittedUrl
from talent.serializers import JobInviteSerializer
from main.email import send_assessment_completion_email

from collections import defaultdict
@shared_task
def submit_job_assessment_task(invite_id,is_terminated,proctor_detected):
    exam_key =f"active:exam:{invite_id}"
    if cache.get(exam_key):
        cache.delete(exam_key)
    
    from talent.views import evaluate_answer,evaluate_coading_answer
    invite = get_object_or_404(JobInvites.objects.select_related('assessment','assessment__job','assessment__job__user','assessment__job__user__company_details'),invite_id=invite_id)
    
    completed_assessment_object = SubmittedAssessmentQuestion.objects.filter(invite=invite).order_by('created_at')
    completed_assessment = list(completed_assessment_object.values_list('submitted_question',flat=True))


    mark_details_dict = defaultdict(lambda: {"total_marks": 0, "marks_scored": 0,"total_question":0})


    if not isinstance(completed_assessment,list):
        print('completed assessment data not found or not a list')
        invite.submit_status = 'not_short_listed'
        invite.submit_time = timezone.now()
        invite.save(update_fields=['submit_status','submit_time'])
        return
    
    mark_scored = 0
    
    for question in completed_assessment:
        
        question_type = question['question_type']
        
        if question_type in ['MCQ','TRUE_FALSE','FILL_IN_THE_BLANK']:
            
            mark_received_for_question = question['marks'] if question['correct_answer'] == question['submitted_answer'] else 0
            question['mark_scored']=mark_received_for_question
            mark_scored += mark_received_for_question

            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += mark_received_for_question
            mark_details_dict[question_type]["total_question"] += 1


        if question_type == 'MULTI_ANSWER_MCQ':
            correct_answer = set(question['correct_answer'])
            submitted_answer = set(question['submitted_answer'])
            mark_assing_for_mcq = question['marks']

            # Exact match = full marks
            if submitted_answer == correct_answer:
                question['mark_scored'] = mark_assing_for_mcq
            else:
                question['mark_scored'] = 0

            # Update total score
            mark_scored += question['mark_scored']
            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += question['mark_scored']
            mark_details_dict[question_type]["total_question"] += 1
                        
        if  question_type == 'PUZZLE':
            correct_order = question['correct_order']
            submitted_answer = question['submitted_answer']

            if submitted_answer == correct_order:
                mark_scored += question['marks']
                question['mark_scored']=question['marks']
            else:
                question['mark_scored']=0

            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += question['mark_scored']
            mark_details_dict[question_type]["total_question"] += 1

        if question_type == 'TYPE_ANSWER':
            submitted_answer = question['submitted_answer']
            correct_answer = question['correct_answer']
            score = evaluate_answer(question['question'],correct_answer,submitted_answer,question['marks'])
            if score > question['marks']:
                score = question['marks']
            question['mark_scored']=score
            mark_scored +=score

            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += score
            mark_details_dict[question_type]["total_question"] += 1
        
        if question_type == 'UPLOAD':
            question['mark_scored'] = 0
            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += 0
            mark_details_dict[question_type]["total_question"] += 1

        if question_type == 'CODING':
            submitted_answer = question['submitted_answer']
            response_data = evaluate_coading_answer(question['question'],submitted_answer,question['language'],question['marks'])
            score = response_data['score']
            feedback =response_data['feedback']
            question['mark_scored']=score
            question['feedback'] = feedback
            mark_scored +=score

            mark_details_dict[question_type]["total_marks"] += question['marks']
            mark_details_dict[question_type]["marks_scored"] += score
            mark_details_dict[question_type]["total_question"] += 1

    data_dict={}
    
    data_dict['marks_details'] = mark_details_dict
    data_dict['completed_assessment'] = completed_assessment
    data_dict['marks_scored'] = round(mark_scored,2)

    total_mark  = invite.assessment.total_marks
    
    percentage = (mark_scored / total_mark) * 100
    percentage = int(percentage + 0.5)
    
    shortlist_percentage = invite.assessment.shortlist_percentage
    review_percentage = invite.assessment.review_percentage
    
    data_dict['mobile_camera_is_on'] = False

    if is_terminated : 
        data_dict['submit_status'] = 'not_short_listed'
    
    else:
        if percentage >= shortlist_percentage:
            data_dict['submit_status'] ='short_listed'
        
        elif percentage < shortlist_percentage and percentage >= review_percentage:
            data_dict['submit_status'] = 'review'
        
        else:
            data_dict['submit_status'] = 'not_short_listed'
    
    if proctor_detected==True:
        data_dict['proctoring_detected'] = True

    data_dict['percentage'] = percentage
    data_dict['submit_time'] = timezone.now()
    
    serializer = JobInviteSerializer(invite,data=data_dict,partial=True)
    if serializer.is_valid():
        serializer.save()
        print('submit job assessment data saved successfully to db\n\n')
        print(serializer.data)
        print('\n\n')

        email = invite.user.email
        user_name = invite.user.name or 'User'
        job_title = invite.assessment.job.title

        staus_Details={
            'review':'Under Review',
            'short_listed':'Shortlisted',
            'not_short_listed':'Rejected'
            }
        
        submission_status = staus_Details[invite.submit_status]
        org = invite.assessment.job.user.company_details
        convert_laptop_chunks_to_video.delay(invite_id)
        convert_mobile_chunks_to_video.delay(invite_id)
        send_assessment_completion_email.delay(email, user_name, job_title,submission_status, org)
        completed_assessment_object.delete()
    else:
        print('error in submit serializer\n\n',serializer.errors)    

import tempfile
import requests
# from moviepy.editor import VideoFileClip, concatenate_videoclips
from trainer.views import upload_video_to_s3
import subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed

def download_chunk_with_index(index_url_pair):
    """Download a chunk and return (index, temp_file_path)."""
    index, url = index_url_pair
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm")
    for chunk in resp.iter_content(chunk_size=8192):
        temp_file.write(chunk)
    temp_file.close()
    return index, temp_file.name


@shared_task
def convert_laptop_chunks_to_video(invite_id):
    lock_id = f"video_lock_{invite_id}"
    if not cache.add(lock_id, True, timeout=180):
        print("Task already running")
        return 
    time.sleep(10)

    video_list = list(
        InviteSubmittedUrl.objects.filter(invite__invite_id=invite_id)
        .values_list("url_json", flat=True)
        .order_by("created_at")
    )
    print('no of videos ', len(video_list))
    if not video_list:
        print("the video list empty stopping final video recording")
        return

    invite = get_object_or_404(JobInvites, invite_id=invite_id)

    # Collect detection times
    timing_json = []
    for json_list in [
        invite.image_proctoring_json,
        invite.object_detection_json,
        invite.window_detection_json,
        invite.mobile_warning_json,
    ]:
        if json_list:
            for i in json_list:
                timing_json.append({"time": i.get("time")})

    # Download chunks in parallel
    indexed_urls = list(enumerate([v["screen_url"] for v in video_list]))
    temp_files = [None] * len(video_list)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(download_chunk_with_index, pair) for pair in indexed_urls]
        for future in as_completed(futures):
            index, temp_path = future.result()
            print('video index ', index , 'video temp path', temp_path)
            temp_files[index] = temp_path

    # Prepare output path
    assessment_name = invite.assessment.assessment_name.replace(" ", "_")
    output_file_name = f"{assessment_name}_{invite_id}_{random.random()}"
    output_path = os.path.abspath(os.path.join("static", f"{output_file_name}.mp4"))
    print("Output path:", output_path)

    # Re-encode each chunk to uniform format using GPU
    reencoded_files = []
    for i, f_path in enumerate(temp_files):
        temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".ts").name  # transport stream
        cmd = [
            "ffmpeg",
            "-i", f_path,
            "-c:v", "h264_nvenc",
            "-preset", "llhp",
            "-c:a", "aac",
            "-b:a", "192k",
            "-vf", "scale=1280:720,fps=24",
            "-y", temp_out
        ]
        subprocess.run(cmd, check=True)
        print('file is reencoded',f_path)
        reencoded_files.append(temp_out)

    # Create concat file for FFmpeg
    concat_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    with open(concat_file, "w") as f:
        for f_path in reencoded_files:
            f.write(f"file '{f_path}'\n")

    # Concatenate all re-encoded chunks without re-encoding
    cmd_concat = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        "-y", output_path
    ]
    subprocess.run(cmd_concat, check=True)
    # Upload to S3
    print('final file created')
    s3_url = upload_video_to_s3(output_path, output_file_name)
    InviteSubmittedUrl.objects.create(
        invite=invite,
        url_json={"screen_url": s3_url, "detectd_object_time": timing_json},
    )

    # Cleanup temp files
    for f in temp_files + reencoded_files:
        try:
            os.remove(f)
        except OSError:
            pass
    os.remove(concat_file)
    os.remove(output_path)
    cache.delete(lock_id)


    return s3_url


@shared_task
def convert_mobile_chunks_to_video(invite_id):
    lock_id = f"mobile_video_lock_{invite_id}"
    if not cache.add(lock_id, True, timeout=180):
        print("Mobile Task already running")
        return 
    
    time.sleep(20)

    invite = get_object_or_404(JobInvites, invite_id=invite_id)
    
    video_list = invite.capture_mobile_videos
    if not video_list:
        print("the video list empty stopping final mobile video recording")
        return
    # Collect detection times
    timing_json = []
    for json_list in [
        invite.image_proctoring_json,
        invite.object_detection_json,
        invite.window_detection_json,
        invite.mobile_warning_json,
    ]:
        if json_list:
            for i in json_list:
                timing_json.append({"time": i.get("time")})

    # Download chunks in parallel
    indexed_urls = list(enumerate([v for v in video_list]))
    temp_files = [None] * len(video_list)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(download_chunk_with_index, pair) for pair in indexed_urls]
        for future in as_completed(futures):
            index, temp_path = future.result()
            temp_files[index] = temp_path

    # Prepare output path
    assessment_name = invite.assessment.assessment_name.replace(" ", "_")
    output_file_name = f"{assessment_name}_{invite_id}_mobile_recording_{random.random()}"
    output_path = os.path.abspath(os.path.join("static", f"{output_file_name}.mp4"))
    print("Output path:", output_path)

    # Re-encode each chunk to uniform format using GPU
    reencoded_files = []
    for i, f_path in enumerate(temp_files):
        temp_out = tempfile.NamedTemporaryFile(delete=False, suffix=".ts").name  # transport stream
        cmd = [
            "ffmpeg",
            "-i", f_path,
            "-c:v", "h264_nvenc",
            "-preset", "llhp",
            "-c:a", "aac",
            "-b:a", "192k",
            "-vf", "scale=1280:720,fps=24",
            "-y", temp_out
        ]
        subprocess.run(cmd, check=True)
        reencoded_files.append(temp_out)

    # Create concat file for FFmpeg
    concat_file = tempfile.NamedTemporaryFile(delete=False, suffix=".txt").name
    with open(concat_file, "w") as f:
        for f_path in reencoded_files:
            f.write(f"file '{f_path}'\n")

    # Concatenate all re-encoded chunks without re-encoding
    cmd_concat = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_file,
        "-c", "copy",
        "-y", output_path
    ]
    subprocess.run(cmd_concat, check=True)
    # Upload to S3
    s3_url = upload_video_to_s3(output_path, output_file_name)
    capture_mobile_videos = invite.capture_mobile_videos or []
    capture_mobile_videos.append(s3_url)
    invite.capture_mobile_videos = capture_mobile_videos
    invite.save(update_fields=['capture_mobile_videos'])


    # Cleanup temp files
    for f in temp_files + reencoded_files:
        try:
            os.remove(f)
        except OSError:
            pass
    os.remove(concat_file)
    os.remove(output_path)
    cache.delete(lock_id)
    return s3_url

@shared_task
def calculate_resume_score_task(application_id):
    from AIManagement.views import calculate_resume_score_openai
    calculate_resume_score_openai(application_id)


@shared_task
def backgound_detection_from_desktop(s3_urls,invite_id):
    
    invite = JobInvites.objects.get(invite_id=invite_id)
    image_proctoring_json = invite.image_proctoring_json or []
    
    for url in s3_urls:
        
        is_object_detected = run_proctoring_check(url['current_url'])
        
        if is_object_detected:
            image_proctoring_json.append(url)
            invite.face_detection_count+=1
        else:
            delete_image_from_s3_https(url['current_url'])
        
    invite.image_proctoring_json = image_proctoring_json
    invite.save(update_fields=['image_proctoring_json','face_detection_count'])



def delete_old_invite_record():
    six_months_ago = timezone.now() - timedelta(days=6*30)  # approx 6 months
    invites = JobInvites.objects.filter(created_at__lt=six_months_ago)

    url_list = []
    if invites.exists():
        for invite in invites:
            image_proctoring_json = invite.image_proctoring_json
            object_detection_json = invite.object_detection_json
            window_detection_json = invite.window_detection_json
            mobile_detection_json = invite.mobile_detection_json
            capture_mobile_videos = invite.capture_mobile_videos
            mobile_warning_json=invite.mobile_warning_json

            if image_proctoring_json:
                for i in image_proctoring_json:
                    url_list.append(i.get('url'))
            
            if object_detection_json:
                for i in object_detection_json:
                    url_list.append(i.get('image_url'))
            
            if window_detection_json:
                for i in window_detection_json:
                    url_list.append(i.get('image_url'))

            if capture_mobile_videos:
                url_list.extend(capture_mobile_videos)
            
            if mobile_detection_json:
                for i in mobile_detection_json:
                    url_list.append(i.get('url'))
            
            if mobile_warning_json:
                for i in mobile_warning_json:
                    url_list.append(i.get('url'))

            if invite.image:
                url_list.append(invite.image)
            if invite.capture_surrounding:
                url_list.append(invite.capture_surrounding)
            
            submitted_urls = list(InviteSubmittedUrl.objects.filter(invite=invite).values_list('url_json',flat=True))
            if submitted_urls:
                for i in submitted_urls:
                    url_list.append(i.get('screen_url'))

        
        for url in url_list:    
                delete_image_from_s3_https(url)

        invites.delete()
        print("invites deleted successfuly")