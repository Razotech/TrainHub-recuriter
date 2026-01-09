from django.shortcuts import render,HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from talent.models import *
from django.shortcuts import get_object_or_404
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from decouple import config
from django.contrib.auth.hashers import make_password,check_password
import openai,re,json
from rest_framework import status
from talent.serializers import *
from main.pagination import CustomPagination
from Admin.views import generate_password
from main.email import send_job_invites,send_rejection_email
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
import requests
import cv2
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from main.views import log_user_activity
from django.db import transaction
from rest_framework import viewsets
import os
from datetime import datetime,timedelta
import random

# Create your views here.
client = openai.OpenAI(api_key=config('OPENAI_KEY'))

class GenerateJobAssessment(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Create Job Assessment with AI",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'job':openapi.Schema(type=openapi.TYPE_INTEGER),
                'description':openapi.Schema(type=openapi.TYPE_STRING),
                'qustion_details':openapi.Schema(type=openapi.TYPE_OBJECT),
                'assessment_name':openapi.Schema(type=openapi.TYPE_STRING),
                'assessment_duration':openapi.Schema(type=openapi.TYPE_STRING),
                'allocted_question':openapi.Schema(type=openapi.TYPE_INTEGER),
                'total_questions':openapi.Schema(type=openapi.TYPE_INTEGER),
                'total_marks':openapi.Schema(type=openapi.TYPE_INTEGER),
                'shortlist_percentage': openapi.Schema(type=openapi.TYPE_INTEGER),
                'review_percentage': openapi.Schema(type=openapi.TYPE_INTEGER),
                'rejected_percentage': openapi.Schema(type=openapi.TYPE_INTEGER),
                'proctoring_enable': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'face_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'voice_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'backgound_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'object_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'window_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'eye_capture_detection': openapi.Schema(type=openapi.TYPE_INTEGER),
                'exam_instruction': openapi.Schema(type=openapi.TYPE_STRING),
                'video_instruction_url': openapi.Schema(type=openapi.TYPE_STRING, format='url'),
            }
        ),
        tags=['Job Listing']
    )
    def post(self ,request):
        standard_recipes = {
        'MCQ': '[{"question_type": "MCQ", "question": "str", "options": ["a", "b", "c", "d"], "correct_answer": "str"}]',
        'MULTI_ANSWER_MCQ':'[{"question_type": "MULTI_ANSWER_MCQ", "question": "str", "options": ["a", "b", "c", "d"], "correct_answer": ["ans1","ans2","..."]}]',
        'TRUE_FALSE': '[{"question_type": "TRUE_FALSE", "question": "str", "options": ["True", "False"], "correct_answer": "str"}]',
        'FILL_IN_THE_BLANK': '[{"question_type": "FILL_IN_THE_BLANK", "question": "str", "options": null, "correct_answer": "str"}]',
        'PUZZLE': '[{"question_type": "PUZZLE", "question": "str", "correct_order": ["word1", "word2", "..."], "wrong_order": ["shuffled", "words", "..."]}]',
        'TYPE_ANSWER':'["question_type": "TYPE_ANSWER", "question": "str",correct_answer:"str"]',
        'CODING':'[{"question_type": "CODING", "question": "str","language": "str", "sample_test_case":"str"}]'
        }
        data = request.data
        job_id =data['job']
        user_description = data.pop('description')
        qustion_details = data.pop('qustion_details')
        job = get_object_or_404(JobListing,job_id=job_id)
        total_count = 0
        
        prompt= f"""
You are an AI assessment generator for evaluating candidates for a job role.

Generate an assessment containing a **mix of question types** based on the job title, job Description and Description provided by the user with format described below.
## Role:
{job.title}  

## Job Description:
{job.description}

## User Description:
{user_description}


## Coding Question Language Rule:
- If any coding language is mentioned in the job or user description, use that language.
- If not mentioned,  **any** in language.
- Created question should be in depth and allign to description.

## Question Types & Counts: 
- Generate exactly the number of questions per type as specified
"""     
        
        for q_type, count in qustion_details.items():
            if count!= None:
                prompt += f"\n- {q_type}: Exactly {count} questions (no more, no less)"
                total_count+=count
        
        prompt+= f"""
### General Rules:
- Return a **single flat JSON array** with all questions in random order.
- Each question object must include a `"question_type"` key (e.g., "MCQ","MULTIPLE_MCQ" "TRUE_FALSE", "FILL_IN_THE_BLANK", "PUZZLE").
- Follow the correct structure for each type as defined below.
- The total number of questions must be exactly {total_count}.
- Do not return fewer or more than the requested number of questions for each type.
- Failing to meet the exact count for each type will be treated as incorrect output.
- No duplication of questions or options.
- Ensure all content is age-appropriate, grammatically correct, and relevant to the topic.
- Do NOT return multiple JSON arrays.
- Do NOT wrap the output in quotes or add markdown syntax.
- Return only one valid, raw JSON array — nothing else.

### JSON Format for Each Type:
"""
        for q_type, recipe in standard_recipes.items():
            prompt += f"\n#### {q_type} Format:\n{recipe}\n"

        prompt += "\nReturn only a single valid JSON array of all questions — no explanations or markdown."
        
        try:

            response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an AI assistant specialized in creating engaging quiz games."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5
                )

            response_content = response.choices[0].message.content.strip()
            print('response_content',response_content)

            response_content = re.sub(r"```json|```", "", response_content).strip()

            parsed_content = json.loads(response_content)
            mark_for_each_question = round(int(data['total_marks'])/int(data['allocted_question']),2)
            for index,i in enumerate(parsed_content):
                i['assessment_type'] = 'MIXED_QUESTIONS'
                i['marks'] = mark_for_each_question
                i['sequence'] = index+1

            data['assessment'] = parsed_content
            serializer = JobAssessmentSerializer(data=data)
            if serializer.is_valid():
                serializer.save()

                log_user_activity(request.user,'CREATE',f'''Assessment '{data["assessment_name"]}' has been genrated using AI ''')
                return Response({'data': serializer.data,'responseMessage':'Job assessment created successfully'}, status=status.HTTP_200_OK)
            return Response({'error': serializer.errors,'responseMessage':'Something is wrong ! Please try again'}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({"responseMessage": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class AddQuestionInJobAssessmentUsingAI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Create Job Assessment with AI",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'job_assessment_id':openapi.Schema(type=openapi.TYPE_INTEGER),
                'description':openapi.Schema(type=openapi.TYPE_STRING),
                'qustion_details':openapi.Schema(type=openapi.TYPE_OBJECT),
            }
        ),
        tags=['Job Listing']
    )
    def post(self,request):
        standard_recipes = {
        'MCQ': '[{"question_type": "MCQ", "question": "str", "options": ["a", "b", "c", "d"], "correct_answer": "str"}]',
        'MULTI_ANSWER_MCQ':'[{"question_type": "MULTI_ANSWER_MCQ", "question": "str", "options": ["a", "b", "c", "d"], "correct_answer": ["ans1","ans2","..."]}]',
        'TRUE_FALSE': '[{"question_type": "TRUE_FALSE", "question": "str", "options": ["True", "False"], "correct_answer": "str"}]',
        'FILL_IN_THE_BLANK': '[{"question_type": "FILL_IN_THE_BLANK", "question": "str", "options": null, "correct_answer": "str"}]',
        'PUZZLE': '[{"question_type": "PUZZLE", "question": "str", "correct_order": ["word1", "word2", "..."], "wrong_order": ["shuffled", "words", "..."]}]',
        'TYPE_ANSWER':'["question_type": "TYPE_ANSWER", "question": "str",correct_answer:"str"]'
        }
        data = request.data
        job_assessment_id= data['job_assessment_id']

        user_description = data.pop('description')
        qustion_details = data.pop('qustion_details')
        job_assessment = get_object_or_404(JobAssessment.objects.select_related('job'),job_assessment_id=job_assessment_id)
        job = job_assessment.job
        assessment_data = job_assessment.assessment
        question_list = [question['question'] for question in assessment_data]
        total_count =0
        
        prompt= f"""
You are an AI assessment generator for evaluating candidates for a job role.

Generate an assessment containing a **mix of question types** based on the job title, job Description and Description provided by the user with format described below.
make sure the the created assessment should be apart the question list provided by below.

## Role:
{job.title}  

## Job Description:
{job.description}

## User Description:
{user_description}

## Existing Question List (Do NOT repeat)

{question_list}

## Question Types & Counts: 
- Generate exactly the number of questions per type as specified
"""     
        
        for q_type, count in qustion_details.items():
            if count!= None:
                prompt += f"\n- {q_type}: Exactly {count} questions (no more, no less)"
                total_count+=count
        
        prompt+= f"""
### General Rules:
- Return a **single flat JSON array** with all questions in random order.
- Each question object must include a `"question_type"` key (e.g., "MCQ","MULTIPLE_MCQ" "TRUE_FALSE", "FILL_IN_THE_BLANK", "PUZZLE").
- Follow the correct structure for each type as defined below.
- The total number of questions must be exactly {total_count}.
- Do not return fewer or more than the requested number of questions for each type.
- Failing to meet the exact count for each type will be treated as incorrect output.
- No duplication of questions or options.
- Do NOT repeat or reuse any question from existing question list.
- Ensure all content is age-appropriate, grammatically correct, and relevant to the topic.
- Do NOT return multiple JSON arrays.
- Do NOT wrap the output in quotes or add markdown syntax.
- Return only one valid, raw JSON array — nothing else.

### JSON Format for Each Type:
"""
        for q_type, recipe in standard_recipes.items():
            prompt += f"\n#### {q_type} Format:\n{recipe}\n"

        prompt += "\nReturn only a single valid JSON array of all questions — no explanations or markdown."
        
        try:

            response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are an AI assistant specialized in creating engaging quiz games."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5
                )

            response_content = response.choices[0].message.content.strip()
            print('response_content',response_content)

            response_content = re.sub(r"```json|```", "", response_content).strip()

            parsed_content = json.loads(response_content)
            mark_for_each_question = round(int(job_assessment.total_marks)/int(job_assessment.allocted_question),2)
            
            sequence = (
            assessment_data[-1]['sequence'] 
            if assessment_data else 1
            )     

            for index,i in enumerate(parsed_content):
                i['assessment_type'] = 'MIXED_QUESTIONS'
                i['marks'] = mark_for_each_question
                i['sequence'] =sequence + 1
                sequence += 1


            data_object = {}
            data_object['assessment'] = assessment_data + parsed_content
            data_object['total_questions'] = job_assessment.total_questions+len(parsed_content)
            
            serializer = JobAssessmentSerializer(job_assessment,data=data_object,partial=True)
            if serializer.is_valid():
                serializer.save()

                log_user_activity(request.user,'CREATE',f'''Add Question in job Assessment '{job_assessment.assessment_name}' has been genrated using AI ''')
                return Response({'data': serializer.data,'responseMessage':'Job assessment created successfully'}, status=status.HTTP_200_OK)
            return Response({'error': serializer.errors,'responseMessage':'Something is wrong ! Please try again'}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            return Response({"responseMessage": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from rest_framework.parsers import MultiPartParser,FormParser
import pandas as pd
from io import BytesIO

class ImportQuestionCSVView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    @swagger_auto_schema(
    operation_summary="Import question using csv or xlsx file",
    consumes=['multipart/form-data'],
    manual_parameters=[
        openapi.Parameter(
            name='file',
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Upload CSV or XLSX file"
        ),
        openapi.Parameter(
            'job_assessment_id',
            openapi.IN_QUERY,
            type=openapi.TYPE_INTEGER,
            required=True,
            description="Job assessment ID"
        ),
        openapi.Parameter(
            'Authorization',
            openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            description='JWT token',
            default='Bearer '
        ),
    ],
    tags=['Job Listing']
)
    
    def post(self, request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)

        file = request.FILES.get("file")
        
        if not file:
            assessment.delete()
            return Response({"error": "No file uploaded."}, status=status.HTTP_400_BAD_REQUEST)
 
        try:
            if file.name.endswith('.csv'):
                
                df = pd.read_csv(file)  # Skip first 2 rows
            elif file.name.endswith(('.xls', '.xlsx')):
                xls = pd.ExcelFile(file)
                

                df = pd.read_excel(file, sheet_name="Question Template",header=0)
            else:
                assessment.delete()
                return Response({"error": "Unsupported file format."}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e:
            assessment.delete()
            return Response({"error": f"Failed to read file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        

        try:
            assessment_details = assessment.assessment or []
            if len(assessment_details) == 0:
                seq = 1
            else:
                last_object = assessment_details[-1]
                seq = last_object['sequence'] + 1
            
            result = assessment_details
            error_list = []
            total_question = assessment.total_questions
            total_marks = assessment.total_marks


            ALLOWED_Q_TYPES = ['MCQ', 'MULTI_ANSWER_MCQ','TRUE_FALSE', 'FILL_IN_THE_BLANK', 'PUZZLE', 'TYPE_ANSWER','SHORT_ANSWER','LONG_ANSWER','UPLOAD','COADING']

            question_list = []
            for index, row in df.iterrows():
                print(row)
                print(index+2)
                q_type = row.get('Question_type')
                question = row.get('Question')
                marks = row.get('Marks')

                print(q_type)
                if not q_type or str(q_type).strip() not in ALLOWED_Q_TYPES:
                    error_list.append(
                        f"Error in row {index+2}: Invalid or missing 'Question_type'. Allowed types are {ALLOWED_Q_TYPES}."
                    )
                    continue

                # Check if question is missing or blank
                if not question or str(question).strip() == "":
                    error_list.append(f"Error in row {index+2}: 'question' field should not be blank.")
                    continue
                
                if question in question_list:
                    error_list.append(f"Error in row {index+2}: question '{question}' already exists.")
                    continue

                try:


                    required_fields = ['Question', 'Marks']

                    if q_type in ['MCQ', 'MULTI_ANSWER_MCQ']:
                        required_fields += ['Options', 'Correct_answer']
                    elif q_type == 'TRUE_FALSE':
                        required_fields += ['Correct_answer']
                    elif q_type == 'FILL_IN_THE_BLANK':
                        required_fields += ['Correct_answer']
                    elif q_type == 'PUZZLE':
                        required_fields += ['Correct_order', 'Wrong_order']
                    elif q_type in ['TYPE_ANSWER','SHORT_ANSWER','LONG_ANSWER']:
                        required_fields += ['Correct_answer']
                    
                    missing_data = False
                    for field in required_fields:
                        value = row.get(field)
                        if pd.isna(value) or str(value).strip() == "":
                            error_list.append(f"Error in row {index+2}: '{field}' is required and cannot be empty for question type '{q_type}'.")
                            missing_data = True
                    
                    if missing_data:
                        continue

    
                    marks_val = float(marks)
                    
                    if marks_val < 0:
                        error_list.append(f" Error in row {index+2}: Marks must be Zero or greater than zero.")
                
                except Exception as e:
                    error_list.append(f"Error in row {index+2}:{str(e)}")
                    continue
                
                try:
                    if q_type == 'MCQ':
                        raw_options = str(row['Options']).split(',')
                        options = [opt.strip() for opt in raw_options if opt.strip()]

                        raw_correct = str(row['Correct_answer']).strip()
                        # Normalize for matching: lowercase + remove punctuation/spaces
                        normalized_options = [re.sub(r"[^\w\s]", "", opt.lower()) for opt in options]
                        normalized_correct = [re.sub(r"[^\w\s]", "", ans.lower()) for ans in raw_correct.split(',') if ans.strip()]

                        # 1. Options must be present
                        if not options:
                            error_list.append(f"Error in row {index+2}: No valid options provided.")

                        # 2. Correct answer must be provided
                        if not normalized_correct:
                            error_list.append(f"Error in row {index+2}: No correct answer provided.")

                        # 3. Only one answer is allowed for MCQ
                        if len(normalized_correct) > 1:
                            error_list.append(f"Error in row {index+2}: Multiple answers provided, but only one is allowed.")

                        # 4. More than 8 options not allowed
                        if len(options) > 8:
                            error_list.append(f"Error in row {index+2}: More than 8 options are not allowed.")

                        # 5. Duplicate options check
                        if len(normalized_options) != len(set(normalized_options)):
                            error_list.append(f"Error in row {index+2}: Duplicate options found.")

                        # 6. Correct answer must exist in options
                        if normalized_correct:
                            correct_ans = normalized_correct[0]
                            if correct_ans not in normalized_options:
                                error_list.append(
                                    f"Error in row {index+2}: Answer '{row['Correct_answer']}' not found in options {options}."
                                )

                        # 7. Basic sanity check: at least 2 options required
                        if len(options) < 2:
                            error_list.append(f"Error in row {index+2}: At least 2 options are required for MCQ.")

                        result.append({
                            "question_type": q_type,
                            "question": row['Question'],
                            "options":[opt.strip() for opt in str(row['Options']).split(',')],
                            "correct_answer": (row['Correct_answer']) if isinstance(row['Correct_answer'],str) else (str(row['Correct_answer'])),
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                            
                        })

                    elif q_type == 'MULTI_ANSWER_MCQ':
                        raw_options = str(row['Options']).split(',')
                        options = [opt.strip() for opt in raw_options if opt.strip()]

                        raw_correct = str(row['Correct_answer']).strip()
                        correct_answers = [ans.strip() for ans in raw_correct.split(',') if ans.strip()]

                        # Normalize for comparison (case + punctuation ignored)
                        options_normalized = [re.sub(r"[^\w\s]", "", opt.lower()) for opt in options]
                        correct_normalized = [re.sub(r"[^\w\s]", "", ans.lower()) for ans in correct_answers]

                        # 1. Options must be present
                        if not options:
                            error_list.append(f"Error in row {index+2}: No valid options provided.")

                        # 2. Correct answers must be present
                        if not correct_answers:
                            error_list.append(f"Error in row {index+2}: No correct answer(s) provided.")

                        # 3. More than 8 options not allowed
                        if len(options) > 8:
                            error_list.append(f"Error in row {index+2}: More than 8 options are not allowed.")

                        # 4. Duplicates in options
                        if len(options_normalized) != len(set(options_normalized)):
                            error_list.append(f"Error in row {index+2}: Duplicate options found.")

                        # 5. Duplicates in correct answers
                        if len(correct_normalized) != len(set(correct_normalized)):
                            error_list.append(f"Error in row {index+2}: Duplicate answers provided.")

                        # 6. More answers than options
                        if len(correct_normalized) >= len(options_normalized):
                            error_list.append(f"Error in row {index+2}: Number of answers cannot be equal to or greater than the number of options.")

                        # 7. Check if all answers exist in options
                        for ans in correct_normalized:
                            if ans not in options_normalized:
                                error_list.append(
                                    f"Error in row {index+2}: Answer '{ans}' not found in options {options}."
                                )

                        # Final result
                        result.append({
                            "question_type": q_type,
                            "question": row['Question'],
                            "options": [opt.strip() for opt in raw_options if opt.strip()],
                            "correct_answer": correct_answers,  # Keep as list
                            "marks": float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence": seq
                        })

                    elif q_type == 'TRUE_FALSE':
                        raw_correct = str(row['Correct_answer']).strip().lower()

                        print(raw_correct)

                        # 2. Validate answer
                        if not raw_correct:
                            error_list.append(f"Error in row {index+2}: No correct answer provided for True/False question.")
                            correct_answer = None

                        elif raw_correct not in ["true", "false","1","2"]:
                            error_list.append(
                                f"Error in row {index+2}: Invalid answer '{row['Correct_answer']}'. "
                                f"Only 'True' or 'False' are allowed."
                            )

                            correct_answer = None
                        else:
                            correct_answer = True if raw_correct in ["true", "1"] else False

                        result.append({
                            "question_type": q_type,
                            "question": row['Question'],
                            "options": [True, False],
                            "correct_answer": correct_answer,
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                        })

                    elif q_type == 'FILL_IN_THE_BLANK':
                        result.append({
                            "question_type": q_type,
                            "question": row['Question'],
                            "options": None,
                            "correct_answer": (row['Correct_answer']),
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                        })


                    elif q_type == 'PUZZLE':
                        raw_correct = str(row['Correct_order']).strip()
                        raw_wrong = str(row['Wrong_order']).strip()

                        correct_order = [opt.strip() for opt in raw_correct.split(',') if opt.strip()]
                        wrong_order = [opt.strip() for opt in raw_wrong.split(',') if opt.strip()]

                        # Normalize (remove quotes, parentheses, *, extra chars, lowercase)
                        normalize = lambda s: re.sub(r"[^\w]", "", s).lower()
                        correct_normalized = [normalize(opt) for opt in correct_order]
                        wrong_normalized = [normalize(opt) for opt in wrong_order]

                        # 1. Correct order must not be empty
                        if not correct_order:
                            error_list.append(f"Error in row {index+2}: No valid correct order provided.")

                        # 2. Wrong order must not be empty
                        if not wrong_order:
                            error_list.append(f"Error in row {index+2}: No valid wrong order provided.")

                        # 3. Length mismatch
                        if correct_order and wrong_order and len(correct_order) != len(wrong_order):
                            error_list.append(
                                f"Error in row {index+2}: Correct order ({len(correct_order)} items) "
                                f"and wrong order ({len(wrong_order)} items) must have the same length."
                            )

                        # 4. Duplicates check
                        if len(correct_normalized) != len(set(correct_normalized)):
                            error_list.append(f"Error in row {index+2}: Duplicate values in correct order.")
                        if len(wrong_normalized) != len(set(wrong_normalized)):
                            error_list.append(f"Error in row {index+2}: Duplicate values in wrong order.")

                        # 5. Check wrong order elements exist in correct order
                        for val in wrong_normalized:
                            if val not in correct_normalized:
                                error_list.append(
                                    f"Error in row {index+2}: Wrong order contains invalid element '{val}' "
                                    f"not present in correct order {correct_order}."
                                )

                        # 6. Check missing elements in wrong order
                        for val in correct_normalized:
                            if val not in wrong_normalized:
                                error_list.append(
                                    f"Error in row {index+2}: Element '{val}' from correct order missing in wrong order."
                                )

                        # Final result
                        result.append({
                            "question_type": q_type,
                            "question": row['Question'],
                            "correct_order": correct_order,
                            "wrong_order": wrong_order,
                            "marks": float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence": seq
                        })


                    elif q_type in ['TYPE_ANSWER','SHORT_ANSWER','LONG_ANSWER']:
                        result.append({
                            "question_type": "TYPE_ANSWER",
                            "question": row['Question'],
                            "correct_answer": (row['Correct_answer']),
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                        })
                    
                    elif q_type == 'UPLOAD':
                        result.append({
                            "question_type": "UPLOAD",
                            "question": row['Question'],
                            "upload_url":None,
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                        })
                    

                    elif q_type == 'CODING':
                        result.append({
                            "question_type": "CODING",
                            "question": row['Question'],
                            "marks":float(row['Marks']) if pd.notna(row['Marks']) else 0,
                            "sequence":seq
                        })
                    seq+=1
                    total_question +=1
                    total_marks += float(row['Marks']) if pd.notna(row['Marks']) else 0
                    question_list.append(row['Question'])

                except Exception as e:
                    error_list.append(f"error in {index+2}  - str(e) ")
                    continue


            if error_list:
                assessment.delete()
                return Response({'responseMessage':'error in uploading file','error':error_list},status=status.HTTP_400_BAD_REQUEST)
            
            print(total_question)
            assessment.assessment = result
            assessment.total_marks = total_marks
            assessment.total_questions = total_question
            assessment.save(update_fields=['assessment','total_marks','total_questions'])
            log_user_activity(request.user,'CREATE',f'''Assessment '{assessment.assessment_name}' has been created by uploading file''')
            return Response({"data": result,'total_marks':total_marks,'total_questions':total_question}, status=status.HTTP_200_OK)
        
        except Exception as e:
            assessment.delete()
            print(str(e))
            return Response({'responseMessage':str(e)},status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


# ---------------- RecruiterGroup ------------------
from django.db.models import Prefetch

# Common pagination params
page_param = openapi.Parameter(
    "page", openapi.IN_QUERY, description="Page number", type=openapi.TYPE_INTEGER
)
page_size_param = openapi.Parameter(
    "page_size", openapi.IN_QUERY, description="Number of results per page", type=openapi.TYPE_INTEGER
)

authorization_param=openapi.Parameter(
    'Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer ')

search_param = openapi.Parameter(
    "search", openapi.IN_QUERY, description="Search by group name", type=openapi.TYPE_STRING
)
from rest_framework import filters
class RecruiterGroupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    filter_backends = [filters.SearchFilter] 
    search_fields = ["name"]  

    def get_queryset(self):
        """
        Return only groups that belong to the logged-in user's company_details
        """
        company = getattr(self.request.user, "company_details", None)
        if not  company:
            return RecruiterGroup.objects.none()
        return (
            RecruiterGroup.objects.filter(user__company_details=company)
            .select_related("user")  # recruiter group creator
            .prefetch_related(
                Prefetch(
                    "members",
                    queryset=RecruiterMembership.objects.select_related("user").prefetch_related("group"),
                )
            )
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        """
        Use different serializers for read vs write operations
        """
        if self.action in ["list", "retrieve"]:
            return ViewRecruiterGroupSerializer
        return RecruiterGroupSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # ---- Swagger Docs ----
    @swagger_auto_schema(
        operation_summary="List Recruiter Groups",
        operation_description="Get a paginated list of recruiter groups for the logged-in user's company.",
        manual_parameters=[page_param, page_size_param, authorization_param,search_param],
        responses={200: ViewRecruiterGroupSerializer(many=True)},
        tags=['RecruiterGroup']
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Retrieve Recruiter Group",
        operation_description="Retrieve details of a specific recruiter group by ID.",
        manual_parameters=[authorization_param],
        responses={200: ViewRecruiterGroupSerializer()},
        tags=['RecruiterGroup']
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create Recruiter Group",
        operation_description="Create a new recruiter group. Only users with role=admin are allowed.",
        manual_parameters=[authorization_param],
        request_body=RecruiterGroupSerializer,
        responses={201: RecruiterGroupSerializer()},
        tags=['RecruiterGroup']
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Update Recruiter Group",
        operation_description="Update recruiter group details.",
        manual_parameters=[authorization_param],
        request_body=RecruiterGroupSerializer,
        responses={200: RecruiterGroupSerializer()},
        tags=['RecruiterGroup']
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Delete Recruiter Group",
        operation_description="Delete a recruiter group by ID.",
        manual_parameters=[authorization_param],
        responses={204: "No Content"},
        tags=['RecruiterGroup']
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)



# ---------------- RecruiterMembership ------------------
class RecruiterMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = RecruiterMembershipSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination

    def get_queryset(self):
        """
        - Filter memberships by logged-in user's company_details
        - Optionally filter by ?group_id= in query params
        """
        company = getattr(self.request.user, "company_details", None)
        qs = RecruiterMembership.objects.filter(group__user__company_details=company)

        group_id = self.request.query_params.get("group_id")
        if group_id:
            qs = qs.filter(group__in=[group_id])

        return qs

    # Query param for swagger
    group_id_param = openapi.Parameter(
        "group_id",
        in_=openapi.IN_QUERY,
        description="Filter memberships by RecruiterGroup ID",
        type=openapi.TYPE_INTEGER,
    )

    # ---- Swagger Docs ----
    @swagger_auto_schema(
        operation_summary="List Recruiter Memberships",
        operation_description="Get a paginated list of recruiter memberships for the logged-in user's company. You can filter by group_id.",
        manual_parameters=[group_id_param,page_param,page_size_param,authorization_param],
        responses={200: RecruiterMembershipSerializer(many=True)},
        tags=['RecruiterMembership'],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Retrieve Recruiter Membership",
        operation_description="Retrieve a specific recruiter membership by ID.",
        responses={200: RecruiterMembershipSerializer()},
        manual_parameters=[authorization_param],
        tags=['RecruiterMembership'],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Create Recruiter Membership",
        operation_description="Create a new recruiter membership (only one group per user allowed).",
        manual_parameters=[authorization_param],
        request_body=RecruiterMembershipSerializer,
        responses={201: RecruiterMembershipSerializer()},
        tags=['RecruiterMembership'],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Update Recruiter Membership",
        operation_description="Update recruiter membership details.",
        manual_parameters=[authorization_param],
        request_body=RecruiterMembershipSerializer,
        responses={200: RecruiterMembershipSerializer()},
        tags=['RecruiterMembership'],
    )
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @swagger_auto_schema(
        operation_summary="Delete Recruiter Membership",
        operation_description="Delete a recruiter membership by ID.",
        manual_parameters=[authorization_param],
        responses={204: "No Content"},
        tags=['RecruiterMembership'],
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)



class JobListingView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter("page", openapi.IN_QUERY, description="Page number for pagination", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="Number of records per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('order_by_date', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('order_by_experience', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('assessment_ids',openapi.IN_QUERY,type=openapi.TYPE_STRING,description='Comma-separated JobAssessment IDs to filter job listings',),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def get(self,request):
        user = request.user
        search = request.query_params.get('search')
        order_by_date = request.query_params.get('order_by_date')
        order_by_experience = request.query_params.get('order_by_experience')
        assessment_ids = request.query_params.get('assessment_ids')  
        
        if user.role == 'trainer':
            group_membership = get_object_or_404(RecruiterMembership,user=user)
            
            job_listing = JobListing.objects.prefetch_related('Job_details').select_related('user').filter(group__in= group_membership.group.all(),archive=False).order_by('-updated_at')
        
        elif user.role in ['recruiteradmin','admin']:
            job_listing = JobListing.objects.select_related("user").prefetch_related('Job_details').filter(group__user__company_details = user.company_details,archive=False).order_by('-updated_at')
        else:
            raise ValueError("User Role is not valid role ")
        
        if search:
            job_listing = job_listing.filter(title__icontains=search)
        
        if order_by_date:
            date_order =   '-updated_at' if order_by_date == 'latest' else 'updated_at'
            job_listing = job_listing.order_by(date_order)
        
        if order_by_experience :
            experience_order = '-experience_level_from' if order_by_experience == 'max' else 'experience_level_from'
            job_listing = job_listing.order_by(experience_order)
        

        if assessment_ids:
            assessment_id_list = [int(a) for a in assessment_ids.split(",") if a.isdigit()]
            job_listing = job_listing.filter(Job_details__job_assessment_id__in=assessment_id_list).distinct()
        
        
        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(job_listing, request)
        serializer = ViewJobListingSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)
    


    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=JobListingSerializer,
        tags=['Job Listing']
    )
    def post(self,request):
        data = request.data
        user = request.user
        if user.role!= 'recruiteradmin':
            return Response({'responseMessage':'Only Recruiter admin can create a job'},status=status.HTTP_400_BAD_REQUEST)
        
        if JobListing.objects.filter(user__company_details = user.company_details, title = data.get('title')):
            return Response({'responseMessage':'Job title already exists'},status=status.HTTP_400_BAD_REQUEST)
        
        serializer = JobListingSerializer(data = data)
        if serializer.is_valid():
            serializer.save()
            log_user_activity(request.user,'CREATE',f'''New Job '{data.get("title")}' has been created ''')
            return Response({'data':serializer.data,'responseMessage':'Job Created successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong!please check job listing data'},status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter('job_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=JobListingSerializer,
        tags=['Job Listing']
    )
    def put(self,request):
        user = request.user
        
        if user.role!= 'recruiteradmin':
            return Response({'responseMessage':'Only Recruiter admin can modify a job'},status=status.HTTP_400_BAD_REQUEST)
        
        job_id = request.query_params.get('job_id')
        job = get_object_or_404(JobListing,job_id = job_id)
        data = request.data
        serializer = JobListingSerializer(job,data=data,partial=True)
        if serializer.is_valid():
            serializer.save()
            log_user_activity(request.user,'UPDATE',f'''Job '{job.title}' data updated''')

            return Response({'data':serializer.data,'responseMessage':'Data updated successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong!please check job listing data'},status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter('job_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def delete(self,request):
        user = request.user
        if user.role!= 'recruiteradmin':
            return Response({'responseMessage':'Only Recruiter admin can delete a job'},status=status.HTTP_400_BAD_REQUEST)
        
        job_id = request.query_params.get('job_id')
        job = get_object_or_404(JobListing,job_id = job_id)
        job.archive = True
        job.save(update_fields=['archive'])
        log_user_activity(request.user,'DELETE',f'''Job '{job.title}' has been archived ''')
        return Response(status=status.HTTP_204_NO_CONTENT)


import copy
class CloneJob(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Clone the job by job id",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'job_id':openapi.Schema(type=openapi.TYPE_INTEGER)
            }
        ),
        tags=['Job Listing']
    )
    def post(self,request):
        
        user = request.user
        
        if user.role!= 'recruiteradmin':
            return Response({'responseMessage':'Only Recruiter admin can clone job'},status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            job_id = request.data.get('job_id')
            org_job = get_object_or_404(JobListing,job_id=job_id)
            og_assessments = JobAssessment.objects.filter(job=org_job)
            new_job = copy.deepcopy(org_job)
            new_job.pk=None
            new_job.user=user
            new_job.created_at = timezone.now()
            new_job.title = f"{org_job.title}_copy"
            new_job.save()

            for assessment in og_assessments:
                new_assessment = copy.deepcopy(assessment)
                new_assessment.pk=None
                new_assessment.job=new_job
                new_assessment.assessment_name = f"{assessment.assessment_name}_copy"
                new_assessment.is_public=False
                new_assessment.created_at = timezone.now()
                new_assessment.save()
            
            return Response({'responseMessage':'Job clone successfully'},status=status.HTTP_200_OK)


class JobAssessmentView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="GET job Assessment",
        manual_parameters=[
            openapi.Parameter("page", openapi.IN_QUERY, description="Page number for pagination", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="Number of records per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter("job_id", openapi.IN_QUERY,type=openapi.TYPE_INTEGER),
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY,type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def get(self,request):
        job_id = request.query_params.get('job_id')
        job_assessment_id = request.query_params.get('job_assessment_id')
        if job_assessment_id:
            assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
            serializer = JobAssessmentSerializer(assessment)
            return Response({'data':serializer.data,'responseMessage':'Data retrived successfully'},status=status.HTTP_200_OK)
        
        assessment = JobAssessment.objects.filter(job__job_id = job_id,archive=False).order_by('-created_at')

        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(assessment, request)
        serializer = JobListingSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)


    @swagger_auto_schema(
        operation_summary="Create job Assessment",
        manual_parameters=[
            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=JobAssessmentSerializer,
        tags=['Job Listing']
    )
    def post(self,request):
        user = request.user
        data = request.data
        assessment_name = data.get('assessment_name')
        
        job  = data.get('job')
        
        if JobAssessment.objects.filter(assessment_name__iexact=assessment_name,job__job_id = job).exists():
            return Response({'responseMessage':'Assessment name already exists for this job'},status=status.HTTP_400_BAD_REQUEST)
        
        serializer = JobAssessmentSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save()
        
            log_user_activity(request.user,'CREATE',f'''New Assessment '{data.get("assessment_name")}' has been created.''')
        
            return Response({'data':serializer.data,'responseMessage':'Data created successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong!please check assessment data'},status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_summary="Update job Assessment",
        manual_parameters=[
            openapi.Parameter('job_assessment_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=JobAssessmentSerializer,
        tags=['Job Listing']
    )
    def put(self,request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        
        
        data = request.data
        assessment_name =  data.get('assessment_name',None)
        
        if assessment_name:
            if JobAssessment.objects.filter(assessment_name__iexact=assessment_name,job=assessment.job).exclude(job_assessment_id=job_assessment_id).exists():
                return Response({'responseMessage':'Assessment name already exists for this job'},status=status.HTTP_400_BAD_REQUEST)
        
        serializer = JobAssessmentSerializer(assessment,data=data,partial=True)
        if serializer.is_valid():
            serializer.save()
        
            log_user_activity(request.user,'UPDATE',f''' Assessment '{assessment.assessment_name}' data is updated.''')

            return Response({'data':serializer.data,'responseMessage':'Data created successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong!please check assessment data'},status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_summary="Delete job Assessment",
        manual_parameters=[
            openapi.Parameter('job_assessment_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def delete(self,request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        assessment.archive = True
        assessment.save(update_fields=['archive'])
        
        log_user_activity(request.user,'DELETE',f''' Assessment '{assessment.assessment_name}' has been archived.''')
        return Response(status=status.HTTP_204_NO_CONTENT)



class CloneJobAssessment(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Clone the assessment in job using job_id and job_assessmnt_id",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'job_id':openapi.Schema(type=openapi.TYPE_INTEGER),
                'job_assessment_id':openapi.Schema(type=openapi.TYPE_INTEGER)

            }
        ),
        tags=['Job Listing']
    )
    def post(self,request):
        user = request.user
        
        if user.role!= 'recruiteradmin':
            return Response({'responseMessage':'Only Recruiter admin can clone job'},status=status.HTTP_400_BAD_REQUEST)
        
        data = request.data
        job_id = data.get('job_id')
        job_assessment_id = data.get('job_assessment_id')
        job = get_object_or_404(JobListing,job_id=job_id)
        
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)

        new_assesment = copy.deepcopy(assessment)
        new_assesment.pk = None
        new_assesment.assessment_name = f"{assessment.assessment_name}_copy"
        new_assesment.job = job
        new_assesment.is_public = False
        new_assesment.created_at = timezone.now()
        new_assesment.save()

        return Response({'responseMessage':'Asssessment Clone successfully'},status=status.HTTP_200_OK)


from django.utils.timezone import localtime,make_aware
import pytesseract as pyt
from django.conf import settings
import io,re
from main.serializers import UserUpdateSerializer
def extract_text_from_url(file_url: str) -> str:
    pyt.pytesseract.tesseract_cmd = settings.TESSERACT_LOCATION
    
    """Download image from S3 URL and extract text using Tesseract."""
    response = requests.get(file_url)
    image = Image.open(io.BytesIO(response.content))
    text = pyt.image_to_string(image)
    return text

def verify_id_proof(file_url: str, provided_proof: str) -> bool:
    """Verify whether provided_proof exists in OCR-extracted text."""
    extracted_text = extract_text_from_url(file_url)

    # Normalize
    extracted_text_clean = re.sub(r'[^A-Za-z0-9]', '', extracted_text).lower()
    proof_clean = re.sub(r'[^A-Za-z0-9]', '', provided_proof).lower()
    
    print('provided_proof',proof_clean)
    print('extracted_text',extracted_text_clean)

    return proof_clean in extracted_text_clean


class UpdateandViewprofile(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="update Job Invites",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'name':openapi.Schema(type=openapi.TYPE_STRING),
                'email':openapi.Schema(type=openapi.TYPE_STRING),
                'address':openapi.Schema(type=openapi.TYPE_STRING),
                'Gender':openapi.Schema(type=openapi.TYPE_STRING),
                'invite_user_details':openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "image_with_id": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_URI),
                "region": openapi.Schema(type=openapi.TYPE_STRING),
                "location":openapi.Schema(type=openapi.TYPE_STRING),
                "first_gov_id_proof": openapi.Schema(type=openapi.TYPE_STRING),
                "first_gov_id_key": openapi.Schema(type=openapi.TYPE_STRING),
                "first_gov_id_upload": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_URI),
                "first_gov_id_verify": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                
                "second_gov_id_proof": openapi.Schema(type=openapi.TYPE_STRING),
                "second_gov_id_key": openapi.Schema(type=openapi.TYPE_STRING),
                "second_gov_id_upload": openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_URI),
                "second_gov_id_verify": openapi.Schema(type=openapi.TYPE_BOOLEAN),
                "resume":openapi.Schema(type=openapi.TYPE_STRING),
            }),
            }
        ),
        tags=['Job Listing']
    )
    def put(self,request):
        user = request.user
        invite_user = InviteUserDetails.objects.filter(user=user).first() 
        print('invite_user',invite_user)
        data = request.data
        invite_user_details = data.pop('invite_user_details',None)
        
        if invite_user_details:
            first_gov_id_proof = invite_user_details.get('first_gov_id_proof',None)
            second_gov_id_proof = invite_user_details.get('second_gov_id_proof',None)
            

            if first_gov_id_proof and  InviteUserDetails.objects.filter(
                first_gov_id_proof=first_gov_id_proof,
                user__company_details=user.company_details
                ).exclude(invite_user_id=invite_user.invite_user_id).exists():
                return Response({'responseMessage':f'Id proof "{first_gov_id_proof}" record already exists'},status=status.HTTP_400_BAD_REQUEST)

            if second_gov_id_proof and InviteUserDetails.objects.filter(
                second_gov_id_proof=second_gov_id_proof,
                user__company_details=user.company_details
                ).exclude(invite_user_id=invite_user.invite_user_id).exists():
                return Response({'responseMessage':f'Id proof "{second_gov_id_proof}" record already exists'},status=status.HTTP_400_BAD_REQUEST)
            
            if first_gov_id_proof and invite_user_details.get("first_gov_id_upload"):
                is_valid = verify_id_proof(
                    file_url=invite_user_details["first_gov_id_upload"],
                    provided_proof=first_gov_id_proof
                )
                invite_user_details['first_gov_id_verify'] =is_valid

            # Second ID Proof check
            if second_gov_id_proof and invite_user_details.get("second_gov_id_upload"):
                is_valid = verify_id_proof(
                    file_url=invite_user_details["second_gov_id_upload"],
                    provided_proof=second_gov_id_proof
                )
                invite_user_details['second_gov_id_verify'] =is_valid



        data['is_first_login'] =False
        
        user_serializer = UserUpdateSerializer(user,data=data,partial=True)
        
        if not user_serializer.is_valid():
            return Response({'error':user_serializer.errors,'responseMessage':'Something is wrong! please check you input'},status=status.HTTP_400_BAD_REQUEST)

        invite_user_serializer = InviteUserSeralizer(invite_user,data=invite_user_details,partial=True)
        
        if not invite_user_serializer.is_valid():
            return Response({'error':user_serializer.errors,'responseMessage':'Something is wrong! please check you input'},status=status.HTTP_400_BAD_REQUEST)
        
        invite_user_serializer.save()
        user_serializer.save()
        view_serializer = InviteUserProfileSerializer(user)
        return Response({'data':view_serializer.data,'responseMessage':'Profile updated successfully'},status=status.HTTP_200_OK)
    
    @swagger_auto_schema(
        operation_summary="Gt invite user profile ",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def get(self,request):
        serializer = InviteUserProfileSerializer(request.user)
        return Response({'data':serializer.data,'responseMessage':'Data found successfully'},status=status.HTTP_200_OK)
        
def format_datetime(value):
    """Return formatted datetime if possible, else None."""
    if not value:
        return None
    
    # If it's already a datetime, just format
    if hasattr(value, "utcoffset"):
        return localtime(value).strftime("%Y-%m-%d %H:%M")
    
    # If it's a string, try to parse
    if isinstance(value, str):
        try:
            # Adjust format string if your DB string looks different
            parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return localtime(parsed).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value  # fallback: return the raw string
    
    return None

class InviteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="GET Job Invites",
        manual_parameters=[
            openapi.Parameter("page", openapi.IN_QUERY, description="Page number for pagination", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="Number of records per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('from_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE),
            openapi.Parameter('to_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE),
            openapi.Parameter('invite_status', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['accepted','pending','rejected']),
            openapi.Parameter('order_by_date', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['latest','oldest']),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def get(self,request):

        job_assessment_id = request.query_params.get('job_assessment_id')
        invite_id = request.query_params.get('invite_id')
        search = request.query_params.get('search')
        invite_status = request.query_params.get('invite_status')
        order_by_date = request.query_params.get('order_by_date','latest')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')

        if invite_id:
            invite = get_object_or_404(JobInvites,invite_id=invite_id)
            serializer = JobInviteSerializer(invite)
            return Response({'data':serializer.data,'responseMessage':'Data found successfully'},status=status.HTTP_200_OK)
        
        invite_list = JobInvites.objects.filter(assessment__job_assessment_id = job_assessment_id)
        if invite_status:
            invite_list = invite_list.filter(invite_status=invite_status)

        if search:
            invite_list = invite_list.filter(Q(user__email__icontains = search)|Q(user__name__icontains=search))

        if from_date and to_date:
            invite_list = invite_list.filter(created_at__range=(from_date,to_date))
        
        if order_by_date:
            order = '-created_at' if order_by_date =='latest' else 'created_at'
            invite_list = invite_list.order_by(order)
           

        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(invite_list, request)
        serializer = ViewJobInviteSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)



    @swagger_auto_schema(
        operation_summary="Create Job Invites",
        manual_parameters=[      
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body = openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'job_assessment_id': openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Schema(type=openapi.TYPE_INTEGER)),
                    'emails': openapi.Schema(type=openapi.TYPE_STRING, format='email',description="Single email or comma-separated emails"),
                    'is_schduled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'schdule_start_time':openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                    'schdule_end_time':openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                    'is_reake':openapi.Schema(type=openapi.TYPE_BOOLEAN),
                    'rekate_allow':openapi.Schema(type=openapi.TYPE_INTEGER),
                    'cool_down_period':openapi.Schema(type=openapi.TYPE_INTEGER)
                },
                required=['email']  # Optional: specify required fields
                )
            ),
                tags=['Job Listing']
        )
    def post(self, request):
        from Admin.models import AssignRole
        user = request.user
        datas = request.data   # Now contains job_assessment_id as a list per object

        org = user.company_details

        # Step 1: Expand multiple job_assessment_ids and emails
        expanded_data = []
        for data in datas:
            job_assessment_ids = data.get("job_assessment_id", [])
            if not isinstance(job_assessment_ids, list):
                job_assessment_ids = [job_assessment_ids]

             
            for job_assessment_id in job_assessment_ids:
                for email in data['emails']:
                    temp = data.copy()
                    temp['email'] = email
                    temp['job_assessment_id'] = job_assessment_id
                    expanded_data.append(temp)

        # Step 2: Check plan limits
        if org.job_assessment_limit < org.job_assessment_count + len(expanded_data):
            remaining = org.job_assessment_limit - org.job_assessment_count
            return Response({
                "responseMessage": f"Invite cannot be sent. Only {remaining} assessment(s) left in your plan."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Step 3: Collect all assessments to validate
        assessment_map = {
            a.job_assessment_id: a
            for a in JobAssessment.objects.filter(job_assessment_id__in=[d['job_assessment_id'] for d in expanded_data])
        }

        invites = []
        temp_data = []
        skipped = []

        # Step 4: Process expanded invites
        for data in expanded_data:
            job_assessment_id = data['job_assessment_id']
            email = data['email']

            assessment = assessment_map.get(job_assessment_id)
            if not assessment:
                skipped.append(f"Invalid assessment {job_assessment_id} for {email}")
                continue

            if not assessment.is_public:
                return Response({'responseMessage':f'Assessment "{assessment.assessment_name}" not published'},status=status.HTTP_400_BAD_REQUEST)
                # skipped.append(f"Assessment {job_assessment_id} not published for {email}")
                # continue

            existing_invites = set(
                JobInvites.objects.filter(assessment=assessment).values_list('user__email', flat=True)
            )
            if email in existing_invites:
                continue

            
            try:
                invite_user = MyUser.objects.get(email=email, company_details=org)
                password = None
                if invite_user.role != 'invite_user':
                    return Response({'responseMessage': f'{email} already exists with role "{invite_user.role}"'},
                                    status=status.HTTP_400_BAD_REQUEST)
            except MyUser.DoesNotExist:
                password = generate_password()
                print('email',email, 'password',password)
                invite_user = MyUser.objects.create(
                    email=email,
                    password=make_password(password),
                    role="invite_user",
                    company_details=org,
                    is_verified=True
                )
                AssignRole.objects.create(user=invite_user)
                InviteUserDetails.objects.create(user=invite_user)

            is_schduled = data.get('is_schduled', False)
            is_reake = data.get('is_reake', False)

            invites.append(JobInvites(
                user=invite_user,
                assessment=assessment,
                is_schduled=is_schduled,
                schdule_start_time=data.get('schdule_start_time') if is_schduled else None,
                schdule_end_time=data.get('schdule_end_time') if is_schduled else None,
                is_reake=is_reake,
                rekate_allow=data.get('rekate_allow') if is_reake else None,
                cool_down_period=data.get('cool_down_period') if is_reake else None,
            ))

            temp_data.append({
                'email': email,
                'password': password,
                'schdule_start_time': data.get('schdule_start_time'),
                'schdule_end_time': data.get('schdule_end_time'),
                'job_assessment_id': job_assessment_id
            })

        # Step 5: Bulk create invites
        if invites:
            created_invites = JobInvites.objects.bulk_create(invites, batch_size=100)

            send_email_list = []
            for invite_obj, temp in zip(created_invites, temp_data):
                send_email_list.append({
                    'invite_id': invite_obj.invite_id,
                    'email': temp['email'],
                    'password': temp['password'],
                    'schedule_start_time': format_datetime(invite_obj.schdule_start_time),
                    'schedule_end_time': format_datetime(invite_obj.schdule_end_time),
                    'Job_title': invite_obj.assessment.job.title,
                    'user_name': invite_obj.user.name or 'user'
                })

            subject = f"You're Invited: Assessment"
            send_job_invites.delay(send_email_list, subject, user.company_details)

            log_user_activity(
                request.user,
                'CREATE',
                f"New Invites have been sent for multiple assessments."
            )

            return Response({
                'data': 'Invites sent successfully',
                'skipped': skipped
            }, status=status.HTTP_200_OK)

        return Response({'data': 'All users are already invited','skipped':skipped}, status=status.HTTP_400_BAD_REQUEST)


    @swagger_auto_schema(
        operation_summary="update Job Invites",
        manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=JobInviteSerializer,
        tags=['Job Listing']
    )
    def put(self,request):
        from talent.inference import face_exists
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites.objects.select_related('user'),invite_id=invite_id)

        data = request.data
        image = data.get('image',None)
        if image:
            check_face = face_exists(image)
            print(image)
            print('check_face',check_face)
            if not check_face:
                return Response({'responseMessage':'Please keep your entire face within the camera view'},status=status.HTTP_400_BAD_REQUEST)

        serializer = JobInviteSerializer(invite,data=data,partial=True)
        if serializer.is_valid():
            serializer.save()
            log_user_activity(request.user,'UPDATE',f'''Invite user '{invite.user.name or invite.user.name}' data has been updated for assessment '{invite.assessment.assessment_name}'.''')

            return Response({'data':serializer.data,'responseMessage':'Data updated successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong! please check you input'},status=status.HTTP_400_BAD_REQUEST)
    
    @swagger_auto_schema(
        operation_summary="delete Job Invites",
        manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def delete(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites,invite_id=invite_id)
        invite.delete()
        log_user_activity(request.user,'DELETE',f'''User Invite'{invite.name or invite.email}' has been deleted in assessment '{invite.assessment.assessment_name}'.''')

        return Response(status=status.HTTP_204_NO_CONTENT)



class JobInviteUploadView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    @swagger_auto_schema(
    operation_summary="Import question using csv or xlsx file",
    consumes=['multipart/form-data'],
    manual_parameters=[
        openapi.Parameter(
            name='file',
            in_=openapi.IN_FORM,
            type=openapi.TYPE_FILE,
            required=True,
            description="Upload XLSX file"
        ),
        openapi.Parameter(
            'job_assessment_id',
            openapi.IN_QUERY,
            type=openapi.TYPE_INTEGER,
            required=True,
            description="Job assessment ID"
        ),
        openapi.Parameter(
            'Authorization',
            openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            description='JWT token',
            default='Bearer '
        ),
    ],
    tags=['Job Listing']
    )
    def post(self, request):
        user = request.user
        job_assessment_id = request.query_params.get('job_assessment_id')
        
        # 1. Check assessment
        try:
            assessment = JobAssessment.objects.get(job_assessment_id=job_assessment_id)
        except JobAssessment.DoesNotExist:
            return Response({'responseMessage': 'Invalid assessment ID'}, status=status.HTTP_400_BAD_REQUEST)

        if not assessment.is_public:
            return Response({'responseMessage': 'Assessment is not published! Cannot send invite'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check Excel file
        excel_file = request.FILES.get("file")
        if not excel_file:
            return Response({'responseMessage': "No Excel file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(BytesIO(excel_file.read()))
        except Exception as e:
            return Response({'responseMessage': f"Invalid Excel file: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Required columns
        required_columns = ["email", "scheduled", "retake", "schdule_start_time", "schdule_end_time", "retake_allow", "cool_down_period"]
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            return Response({'responseMessage': f"Missing columns in Excel: {missing}"}, status=status.HTTP_400_BAD_REQUEST)

        # 4. Convert Excel rows to dict like request.data
        datas = df.fillna("").to_dict(orient="records")

        # ✅ Reuse your existing logic by extracting it into a helper
        return self._process_invites(request, datas, assessment)

    def _process_invites(self, request, datas, assessment):
        user = request.user
        org = user.company_details

        if org.job_assessment_limit < org.job_assessment_count + len(datas):
            remaining = org.job_assessment_limit - org.job_assessment_count
            return Response({
                "responseMessage": f"Invite cannot be sent. Only {remaining} assessment(s) left in your plan."
            }, status=status.HTTP_400_BAD_REQUEST)

        existing_invites = set(
            JobInvites.objects.filter(assessment=assessment).values_list('email', flat=True)
        )

        invites = []
        temp_data = []
        for data in datas:
            print("Row:", data)

            email = str(data.get("email", "")).strip()
            if not email or email in existing_invites:
                continue

            password = generate_password()

            # ✅ Normalize scheduled/retake fields (1.0, 0.0, '1', '0', True/False, '')
            def to_bool(val):
                if isinstance(val, (int, float)):
                    return bool(val)
                if isinstance(val, str):
                    return val.strip().lower() in ["1", "true", "yes"]
                return False

            is_schduled = to_bool(data.get("scheduled"))
            is_reake = to_bool(data.get("retake"))

            # ✅ Normalize datetime (Timestamp/NaT/string)
            def to_datetime(val):
                if pd.isna(val) or val == "":
                    return None
                if isinstance(val, pd.Timestamp):
                    return val.to_pydatetime()
                if isinstance(val, str):
                    try:
                        return datetime.fromisoformat(val)
                    except ValueError:
                        return None
                return val

            sch_start = to_datetime(data.get("schdule_start_time")) if is_schduled else None
            sch_end = to_datetime(data.get("schdule_end_time")) if is_schduled else None

            # ✅ Normalize integer fields
            def to_int(val):
                if pd.isna(val) or val == "":
                    return None
                try:
                    return int(val)
                except Exception:
                    return None

            retake_allow = to_int(data.get("retake_allow")) if is_reake else None
            cooldown = to_int(data.get("cool_down_period")) if is_reake else None

            # Build JobInvites instance
            invites.append(JobInvites(
                email=email,
                password=password,
                assessment=assessment,
                is_schduled=is_schduled,
                schdule_start_time=sch_start,
                schdule_end_time=sch_end,
                is_reake=is_reake,
                rekate_allow=retake_allow,
                cool_down_period=cooldown,
            ))

            temp_data.append({
                "email": email,
                "password": password,
                "schdule_start_time": sch_start,
                "schdule_end_time": sch_end
            })

        if invites:
            created_invites = JobInvites.objects.bulk_create(invites, batch_size=100)

            send_email_list = []
            for invite_obj, temp in zip(created_invites, temp_data):
                send_email_list.append({
                    "invite_id": invite_obj.invite_id,
                    "email": temp["email"],
                    "password": temp["password"],
                    "schedule_start_time": invite_obj.schdule_start_time,
                    "schedule_end_time": invite_obj.schdule_end_time,
                    "Job_title": invite_obj.assessment.job.title,
                    "user_name": invite_obj.name or "user"
                })

            subject = f"You're Invited: {assessment.job.title} Assessment"
            send_job_invites.delay(send_email_list, subject, request.user.company_details)
            log_user_activity(
                request.user,
                "CREATE",
                f"New Invites sent for assessment '{assessment.assessment_name}'."
            )

            return Response({"responseMessage": "Invite sent successfully"}, status=status.HTTP_200_OK)

        return Response({"responseMessage": "All users are already invited"}, status=status.HTTP_400_BAD_REQUEST)

class SendReminderEmail(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Send Reminder email",
        manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        user = request.user
        invite_obj = get_object_or_404(JobInvites,invite_id=invite_id)
        email_list =[{
                    'invite_id': invite_obj.invite_id,
                    'email': invite_obj.user.email,
                    'schedule_start_time': localtime(
                        make_aware(invite_obj.schdule_start_time)
                    ).strftime("%Y-%m-%d %H:%M") if invite_obj.schdule_start_time else None,
                    'schedule_end_time': localtime(
                        make_aware(invite_obj.schdule_end_time)
                    ).strftime("%Y-%m-%d %H:%M") if invite_obj.schdule_end_time else None,
                    'Job_title': invite_obj.assessment.job.title,
                    'user_name': invite_obj.user.name or 'user'
                }]
        subject = f"Reminder: Please Acknowledge the Assessment Invitation for {invite_obj.assessment.job.title}"

        send_job_invites(email_list,subject, user.company_details)
        log_user_activity(user,'UPDATE',f'''Reminder email sent to user Invite'{invite_obj.user.name or invite_obj.user.email}' in '{invite_obj.assessment.assessment_name}'.''')
        return Response({'responseMessage':'Reminder sent successfully'},status=status.HTTP_200_OK)
        

class ChagneInviteStatusToAccepted(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Change invite status",
        manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )
    def post(self,request):
        user = request.user
        invite_id = request.query_params.get('invite_id')
        
        invite_obj = get_object_or_404(JobInvites.objects.select_related('assessment','assessment__job'),invite_id=invite_id)
        
        invite_obj.invite_status = 'pending'
        invite_obj.save(update_fields=['invite_status'])

        email_list =[{
                    'invite_id': invite_obj.invite_id,
                    'email': invite_obj.user.email,
                    'schedule_start_time': localtime(
                        make_aware(invite_obj.schdule_start_time)
                    ).strftime("%Y-%m-%d %H:%M") if invite_obj.schdule_start_time else None,
                    'schedule_end_time': localtime(
                        make_aware(invite_obj.schdule_end_time)
                    ).strftime("%Y-%m-%d %H:%M") if invite_obj.schdule_end_time else None,
                    'Job_title': invite_obj.assessment.job.title,
                    'user_name': invite_obj.user.name or 'user'
                }]
        subject = f"Update: You've Been Reinvited to Acknowledge the '{invite_obj.assessment.job.title}' Assessment"

        send_job_invites(email_list,subject, user.company_details)
        log_user_activity(user,'UPDATE',f''' user Invite'{invite_obj.user.name or invite_obj.user.email}' in'{invite_obj.assessment.assessment_name}' invite staus has been changed and send Re-Invite email. ''')
        
        return Response({'responseMessage':'Invite sent successfully'},status=status.HTTP_200_OK)
        
        




class MultiInviteRejectAPI(APIView):
    @swagger_auto_schema(
        operation_summary="reject selected user",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'invite_ids': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(type=openapi.TYPE_INTEGER)
            )
            }
        ),
        tags=['Job Listing']
    )
    def post(self,request):
        user = request.user
        invite_ids = request.data.get('invite_ids')
        job_invites = JobInvites.objects.filter(invite_id__in = invite_ids)
        emails = list(job_invites.values_list('user__email',flat=True))
        job_invites.update(invite_status = 'rejected')
        send_rejection_email(emails,job_invites.first().assessment.job.title,user.company_details)
        log_user_activity(request.user,'UPDATE',f'''Make as rejected to invited users ''')
        return Response({'responseMessage':'User rejected successfully'},status=status.HTTP_200_OK)
    




# class CheckProctoring(APIView):
#     @swagger_auto_schema(
#         operation_summary="Check proctoring status based on image and audio",
#         manual_parameters=[
#             openapi.Parameter(
#                 name="invite_id",
#                 in_=openapi.IN_QUERY,
#                 description="Invite ID to retrieve stored reference image for comparison",
#                 type=openapi.TYPE_STRING,
#                 required=True
#             )
#         ],
#         request_body=openapi.Schema(
#             type=openapi.TYPE_OBJECT,
#             required=["current_url"],
#             properties={
#                 "current_url": openapi.Schema(type=openapi.TYPE_STRING,format="uri",
#                 description="Current video/audio/image URL (usually a frame or stream snapshot)",
#                 example="https://your-s3-bucket/image_or_audio.wav"
#                 ),
#                 "time":openapi.Schema(type=openapi.TYPE_STRING)
#             }
#         ),
#         tags=['Job Listing']            
#     )
#     def post(self,request):
#         invite_id = request.query_params.get('invite_id')
#         invite = get_object_or_404(JobInvites,invite_id=invite_id)
#         image = invite.image
#         is_proctoring_detected = False
#         is_object_detected  = False
#         is_backgound_deteted = False
#         data = request.data
#         current_url = data.get('current_url')
#         time = data.get('time',"00:00")
        

#         if not image or not current_url:
#             return Response({'responseMessage':'No url found either in record or in currnt send '},status=status.HTTP_400_BAD_REQUEST)
        
#         fields = []
        
#         job_object_count = invite.assessment.object_detection 
        
#         if job_object_count and job_object_count > 0:   
#             is_object_detected = run_proctoring_check(current_url)
            
#             if is_object_detected:
#                 object_detection_json = invite.object_detection_json or []
                
#                 object_detection_json.append({"time":time,"image_url":current_url})
#                 invite.object_detection_json =object_detection_json
                
#                 if job_object_count < invite.object_detection_count+1:
#                     is_proctoring_detected = True
#                     invite.proctoring_detected = True
#                     fields.append('proctoring_detected')
#                 invite.object_detection_count+=1
#                 fields.extend(["object_detection_json",'object_detection_count'])


#         capture = invite.capture_images if invite.capture_images else []
#         capture.append(current_url)
#         invite.capture_images = capture

#         fields.append("capture_images")
#         invite.save(update_fields=fields)
        
#         return Response({
#             'is_object_detected':is_object_detected,
#             'is_backgound_deteted':is_backgound_deteted,
#             'is_proctoring_detected':is_proctoring_detected,
#             },status=status.HTTP_200_OK)


class checkAudioProctoring(APIView):
    @swagger_auto_schema(
        operation_summary="Check proctoring status based on audio",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                description="Invite ID to retrieve stored reference image for comparison",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["current_url"],
            properties={
                "current_audio_url": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="uri",
                    description="Current video/audio/image URL (usually a frame or stream snapshot)",
                    example="https://your-s3-bucket/image_or_audio.wav"
                ),
                'time':openapi.Schema(type=openapi.TYPE_STRING)
            }
        ),
        tags=['Job Listing']            
    )
    def post(self,request):
        from talent.inference import check_audio_proctoring
        invite_id = request.query_params.get('invite_id')
        data = request.data
        
        invite = get_object_or_404(JobInvites,invite_id=invite_id)

        audio = invite.audio
        current_audio_url = data.get('current_audio_url')
        time = data.get('time','00:00')

        if not audio or not current_audio_url:
            return Response({'responseMessage':'No url found either in record or in currnt send '},status=status.HTTP_400_BAD_REQUEST)
        
        is_audio_detected = False
        fields =[]
        
        is_proctoring_detected = False
        job_audio_count = invite.assessment.voice_detection
        if job_audio_count and job_audio_count>0:
            is_audio_detected = check_audio_proctoring(audio,current_audio_url)
            
            if is_audio_detected:
                if job_audio_count <= invite.voice_detection_count+1:
                    is_proctoring_detected= True
                    invite.proctoring_detected = True
                    fields.append('proctoring_detected')

                audio_proctoring= invite.audio_proctoring_json or []
                audio_proctoring.append({'time':time,'audio_url':current_audio_url})
                invite.audio_proctoring_json = audio_proctoring
                invite.voice_detection_count+=1
                fields.extend(["audio_proctoring_json",'voice_detection_count'])


        # capture_audios = invite.capture_audios or []
        # capture_audios.append(current_audio_url)
        # invite.capture_audios = capture_audios
        # fields.append("capture_audios")
        if fields:
            invite.save(update_fields=fields)
        return Response({'is_audio_detected':is_audio_detected,'is_proctoring_detected':is_proctoring_detected},status=status.HTTP_200_OK)
    

class DetectionDataStoreAPI(APIView):
    @swagger_auto_schema(
        operation_summary="Add detected url",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                description="Invite ",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=["current_url"],
            properties={
                "detected_image_url": openapi.Schema(
                    type=openapi.TYPE_STRING,
                    format="uri",
                    description="Current video/audio/image URL (usually a frame or stream snapshot)",
                    example="https://your-s3-bucket/image_or_audio.png"
                ),
            }
        ),
        tags=['Job Listing']            
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites.objects.select_related("assessment"),invite_id=invite_id)
        is_proctoring_detected = False
        fields = []
        detected_image_url = request.data['detected_image_url']
        face_detection_count=invite.assessment.face_detection
        
        if face_detection_count and face_detection_count>0:
            if face_detection_count <= invite.face_detection_count+1:
                is_proctoring_detected = True
                invite.proctoring_detected = True
                fields.append('proctoring_detected')
        
            image_proctoring = invite.image_proctoring_json or []
            image_proctoring.append(detected_image_url)
            invite.image_proctoring_json = image_proctoring
            invite.face_detection_count+=1
            fields.extend(['image_proctoring_json','face_detection_count'])

        
        if fields:
            with transaction.atomic():
                invite.save(update_fields=fields)
        return Response({'is_proctoring_detected':is_proctoring_detected,'responseMessage':'Url added successfully'},status=status.HTTP_200_OK)        




class AddQuestionInJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
            operation_summary='Add the single question in Assessment',
            manual_parameters=[
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'question':openapi.Schema(type=openapi.TYPE_OBJECT)
            }
    ),
    tags=['Job Listing']
    )
    def post(self,request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        question = request.data['question']
        
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)

        assessment_question = assessment.assessment if assessment.assessment else []
        
        if assessment_question:
            question_list = [q['question'] for q in assessment_question]
            if question['question'] in question_list:
                return Response({'responseMessage':"The question is already exists in the assessment"},status=status.HTTP_400_BAD_REQUEST)
        
        assessment_question.append(question)
        assessment.assessment = assessment_question
        assessment.total_questions+=1
        assessment.save(update_fields=['assessment','total_questions'])
        log_user_activity(request.user,'CREATE',f'''New Question has been added in assessment '{assessment.assessment_name}' ''')

        return Response({'data':question,'responseMessage':'Qustion added successfully'},status=status.HTTP_200_OK)


    @swagger_auto_schema(
            operation_summary='Update the single question in Assessment',
            manual_parameters=[
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'question':openapi.Schema(type=openapi.TYPE_OBJECT)
            }
    ),
    tags=['Job Listing']
    )
    def put(self, request):
        try:
            job_assessment_id = request.query_params.get('job_assessment_id')
            questions = request.data.get('question')
            user = request.user

            if not job_assessment_id or not questions:
                return Response({'responseMessage': 'Assessment ID and questions are required'}, status=status.HTTP_400_BAD_REQUEST)

            sequence = questions.get('sequence')
            if sequence is None:
                return Response({'responseMessage': 'Each question must have a sequence'}, status=status.HTTP_400_BAD_REQUEST)

            assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)


            
            question_list = [q['question'] for q in assessment.assessment if q['sequence'] != sequence]
            if questions['question'] in question_list:
                return Response({'responseMessage':"The question is already exists in the assessment"},status=status.HTTP_400_BAD_REQUEST)

            # Optimized list update (maintains order)
            updated_list = [
                questions if q.get('sequence') == sequence else q
                for q in assessment.assessment
            ]

            assessment.assessment = updated_list
            assessment.save(update_fields=["assessment"])
            log_user_activity(request.user,'UPDATE',f'''Question no {sequence} has been updated in assessment '{assessment.assessment_name}' ''')

            return Response({'data': questions, 'responseMessage': 'Assessment has been updated'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'responseMessage': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class PreviewJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
            operation_summary='Preview Job Assessment',
            manual_parameters=[
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    tags=['Job Listing']
    )
    def get(self,request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        error_message=[]
        if assessment.assessment_duration <= timedelta(minutes=1):
            error_message.append('Please provide valid duration')
        

        if assessment.allocted_question == 0 :
            error_message.append("The allocated question should not be 0")
        
        if assessment.allocted_question > assessment.total_questions:
            error_message.append(f"Allocated questions must be less than or equal to total created questions.")
        
        check_assessment = assessment.assessment[:assessment.allocted_question]
        check_marks = sum(map(lambda x: x['marks'], check_assessment))
        
        print(check_marks,assessment.total_marks)

        if check_marks != assessment.total_marks:
            error_message.append(f"Sum of allocated question marks {check_marks} doesn't match total marks {assessment.total_marks}.")
                
        if not assessment.shortlist_percentage:
            error_message.append("Shortlisted percentage is required")

        if not assessment.review_percentage:
            error_message.append("On hold percentage is required")
        
        if not assessment.rejected_percentage:
            error_message.append("rejected percentage is required")
        
        if error_message:
            return Response({'responseMessage':error_message},status=status.HTTP_400_BAD_REQUEST)
        
        serializer = JobAssessmentSerializer(assessment)
        log_user_activity(request.user,'GET',f'''Preview the assessment '{assessment.assessment_name}' ''')

        return Response({'data':serializer.data,'responseMessage':'Preview generated successfully'},status=status.HTTP_200_OK)    

class PublishJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
            operation_summary='Publish Job Assessment',
            manual_parameters=[
            openapi.Parameter("job_assessment_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    tags=['Job Listing']
    )
    def post(self,request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        assessment.is_public = True
        assessment.save(update_fields=['is_public'])
        log_user_activity(request.user,'UPDATE',f'''Publish the assessment '{assessment.assessment_name}'. ''')

        return Response({'responseMessage':'Assessment Published successfully'},status=status.HTTP_200_OK)
    


# ===================================== Job Seeker Management =========================
import secrets

class InviteLogin(APIView):
    @swagger_auto_schema(
        operation_summary='Add the single question in Assessment',
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'invite_id':openapi.Schema(type=openapi.TYPE_INTEGER),
                'email':openapi.Schema(type=openapi.TYPE_INTEGER),
                'password':openapi.Schema(type=openapi.TYPE_STRING),

            }
    ),
    tags=['Job Invite']
    )
    def post(self,request):
        from main.views import get_tokens_for_user,login
        data = request.data
        invite_id = data.get('invite_id')
        email = data.get('email')
        password = data.get('password')
        # first_gov_id_proof = data.get('first_gov_id_proof')
    
        
        if not invite_id:
            return Response({'responseMessage':'Invite ID not found. Please use the link provided in your email.'},status=status.HTTP_400_BAD_REQUEST)

        print(invite_id)
        invite = get_object_or_404(JobInvites,invite_id = invite_id)
        if invite.invite_status == 'rejected':
            return Response({'responseMessage':'Access rejected by admin. Please contact admin'},status=status.HTTP_400_BAD_REQUEST)
        
        if  email!=invite.user.email or  not check_password(password,invite.user.password):
            return Response({'responseMessage':'Incorrect email or password'},status=status.HTTP_400_BAD_REQUEST)
        
        
        login(request, invite.user)

        token = get_tokens_for_user(invite.user)
        serializer = InviteUserProfileSerializer(invite.user)

        return Response({'data':serializer.data,'token':token['access'],'responseMessage':'You’re now logged in'},status=status.HTTP_200_OK)
    

class GetJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary='Get Assessment Details',
        manual_parameters=[
        openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),          
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),

        ],
    tags=['Job Invite']
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites.objects.select_related('assessment','assessment__job','assessment__job__user'),invite_id = invite_id)
        serializer = viewJobInviteSerializer(invite)
        return Response({'data':serializer.data,'responseMessage':'Data fetch successfully'},status=status.HTTP_200_OK)


class UserJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary='Get Assessment Details',
        manual_parameters=[
        openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),

        ],
    tags=['Job Invite']
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites.objects.select_related('assessment','assessment__job','assessment__job__user'),invite_id = invite_id)
        serializer = UserInviteDetailsSerializer(invite)
        return Response({'data':serializer.data,'responseMessage':'data found successfully'},status=status.HTTP_200_OK)
    

class checkJobAssessmentTime(APIView):
    @swagger_auto_schema(
        operation_summary='Get Assessment Details',
        manual_parameters=[
        openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
        ],
    tags=['Job Invite']
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites,invite_id = invite_id)
        
        if invite.invite_status == 'rejected':
            return Response({'responseMessage':'You have rejected by administrated'},status=status.HTTP_400_BAD_REQUEST)
        print(invite.schdule_start_time)
        if invite.is_schduled and invite.schdule_start_time >=datetime.now() :
            return Response({'responseMessage':'Assessment can only be started at the scheduled time'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.is_schduled and invite.schdule_end_time <= datetime.now():
            return Response({'responseMessage':'This assessment isn’t available right now. Please check your scheduled time'},status=status.HTTP_400_BAD_REQUEST)

        return Response({'responseMessage':"You can start the assessment now"},status=status.HTTP_200_OK)    

from django.core.cache import cache
class StartJobAssessment(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
            operation_summary='Start Job Assessment',
            manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    tags=['Job Invite']
    )
    def post(self,request):
        print("we are in the start job assessment")
        invite_id = request.query_params.get('invite_id')
        key = f'active:exam:{invite_id}'
        
        key_exists = cache.get(key)
        print(key_exists)

        if key_exists:
            cache.delete(key)
            # return Response({'responseMessage':'Exam already running in other tab'},status=status.HTTP_400_BAD_REQUEST)
        
        invite = get_object_or_404(JobInvites.objects.select_related('assessment','user',
        'assessment__job','assessment__job__user','assessment__job__user__company_details').prefetch_related(
            'user__invite_user_details'
        ), invite_id=invite_id)

        
        org = invite.assessment.job.user.company_details
        
        if org.job_assessment_count > org.job_assessment_limit:
            return Response({'responseMessage':'You cannot start the exam as organization has reached its assessment limit. Please contact recruiter'},status=status.HTTP_400_BAD_REQUEST)
        
        if not invite.user.invite_user_details.first_gov_id_proof or not invite.user.invite_user_details.second_gov_id_proof:
            return Response({'responseMessage':'Id proof details missing'},status=status.HTTP_400_BAD_REQUEST)
        
        if not invite.image:
            return Response({'responseMessage':'Image captureing missing'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.invite_status == 'rejected':
            return Response({'responseMessage':'You have rejected by administrated'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.submit_status in ['short_listed','review']:
            return Response({'responseMessage':'Assessment already completed'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.is_schduled and invite.schdule_start_time >=datetime.now() :
            return Response({'responseMessage':'Assessment can only be started at the scheduled time'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.is_schduled and invite.schdule_end_time <= datetime.now():
            return Response({'responseMessage':'This assessment isn’t available right now. Please check your scheduled time'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.submit_status not in  ['not_started','inprogress'] and not invite.is_reake:
            return Response({'responseMessage':'Exam already completed. Reattempt not allowed.'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.submit_status not in ['not_started','inprogress'] and invite.retake_count > invite.rekate_allow :
            return Response({'responseMessage':'Reattempt limit reached. No more retakes allowed'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.submit_status not in ['not_started','inprogress'] and invite.retake_count < invite.rekate_allow:
            if invite.cool_down_period:
                cool_down_time = invite.submit_time + timedelta(hours=invite.cool_down_period)
                if cool_down_time > timezone.now():
                    remaining_time = cool_down_time - timezone.now()
                    
                    # Convert to hours, minutes, seconds
                    total_seconds = int(remaining_time.total_seconds())
                    hours, remainder = divmod(total_seconds, 3600)
                    minutes, seconds = divmod(remainder, 60)

                    # Format the message
                    message = (
                        f"Hang tight! You can start the assessment once the cooldown is over. "
                        f"Time remaining: {hours}h {minutes}m {seconds}s."
                    )

                    return Response({'responseMessage': message}, status=status.HTTP_400_BAD_REQUEST)
                    
        if not invite.mobile_camera_is_on:
            return Response({'responseMessage':'mobile camera should on before start exam'},status=status.HTTP_400_BAD_REQUEST)
        
        if invite.submit_status != 'inprogress':
            print('we are in the new job start ')
            assessment = invite.assessment.assessment
            allocted_question = invite.assessment.allocted_question
            total_quesion = invite.assessment.total_questions

            if total_quesion != allocted_question:
                sending_assessment = random.sample(assessment,k=allocted_question)
            else:
                sending_assessment = assessment
            
            random.shuffle(sending_assessment)

            print('assessment',assessment)
            print('sending_assessment',sending_assessment)

            reset_fields = {
                "selection_questions": sending_assessment,
                "completed_assessment": None,
                "marks_scored": None,
                "percentage": None,
                "submit_status": "inprogress",
                "proctoring_detected":False,
                "start_time": timezone.now(),
                "image_proctoring_json": None,
                "face_detection_count": 0,
                "audio_proctoring_json": None,
                "voice_detection_count": 0,
                "object_detection_json": None,
                "object_detection_count": 0,
                "window_detection_json": None,
                "window_detection_count": 0,
                "mobile_detection_json": None,
                "mobile_detection_count": 0,
                "mobile_warning_json":None,
                "mobile_warning_count":0,
                "capture_mobile_videos": None,
                "capture_screen_videos": None,
            }

            if invite.submit_status != 'not_started':
                    prev_serializer  = InviteAnalyticsSerializer(invite)
                    JobInviteOldAttempt.objects.create(
                        invite = invite,
                        assessment_json = prev_serializer.data,
                        retake_no = invite.retake_count
                    )
                    reset_fields["retake_count"]= invite.retake_count+1
                    InviteSubmittedUrl.objects.filter(invite=invite).delete()
            
            save_invite_serializer = JobInviteSerializer(invite,data=reset_fields,partial=True)
            if save_invite_serializer.is_valid():
                save_invite_serializer.save()
            else:
                return Response({'error':save_invite_serializer.error_messages},status=status.HTTP_400_BAD_REQUEST)


            org.job_assessment_count+= 1
            org.save(update_fields=['job_assessment_count'])
        
        else:
            
            completed_assessment_object = list(
                SubmittedAssessmentQuestion.objects.filter(invite=invite)
                .order_by('created_at')
                .values_list('submitted_question', flat=True)
            )

            if completed_assessment_object:
                sequence_list = [obj.get('sequence') for obj in completed_assessment_object if obj]  # safely extract
                remaining_questions = [obj for obj in invite.selection_questions if obj['sequence'] not in sequence_list]
                sending_assessment = remaining_questions
            else:
                sending_assessment = invite.selection_questions

        reamaning_time = None
        if invite.is_schduled and invite.schdule_start_time and invite.schdule_end_time:
            now = timezone.now()

            available_time = (invite.schdule_end_time - now).total_seconds()

            if isinstance(invite.assessment.assessment_duration, timedelta):
                duration = invite.assessment.assessment_duration.total_seconds()
            else:
                duration = float(invite.assessment.assessment_duration)

            reamaning_time = min(available_time, duration)


        
        serializer = viewJobInviteSerializer(invite)
        serialized_data = serializer.data
        serialized_data['assessment']['assessment'] = sending_assessment
        if reamaning_time:
            hours, remainder = divmod(int(reamaning_time), 3600)
            minutes, seconds = divmod(remainder, 60)
            formatted_time = f"{hours:02}:{minutes:02}:{seconds:02}"
            serialized_data['assessment']['assessment_duration'] = formatted_time
        
        return Response({'data':serialized_data,'responseMessage':'Assessment Started successfully'},status=status.HTTP_200_OK)
    


    



def evaluate_answer(question, correct_answer, submitted_answer, total_mark):
    prompt = f"""
You are an exam evaluator. Grade the student's answer fairly based on meaning and correctness.
 
Rules:

- Award full marks ({total_mark}) only if the student's answer fully matches the meaning of the correct answer.

- If multiple valid answers exist in the correct answer (e.g., synonyms, list of options) and the student gives any one valid answer, award full marks.

- For numerical answers, allow small differences or equivalent formats (e.g., 100 vs 100.0, “one hundred” vs 100) and give full marks.

- If the student's answer is mostly correct but misses minor details, award partial marks proportionally.

- If the answer is vague, incomplete, or only tangentially related, give very low marks (close to 0).

- If the answer is completely wrong or irrelevant, give 0 marks.

- Output only a single number between 0 and {total_mark}. No words, no explanation, only the number.
 
Question: "{question}"  

Correct Answer: "{correct_answer}"  

Student's Answer: "{submitted_answer}"  
 
Score:
 
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # or "gpt-3.5-turbo"
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    score_text = response.choices[0].message.content.strip()
    print(score_text, type(score_text))
    print('evaluate_scored',score_text)
    
    try:
        return float(score_text)
    except:
        return 0



def evaluate_coading_answer(question,submitted_answer,language,total_marks):
    prompt = f"""
You are an expert coding examiner. Evaluate the student's answer for the coding question.

### Language Rule:
- Required language: "{language}"
- If the required language is **"any"**, do NOT restrict evaluation by language.
- If the required language is something else, and the student's code is clearly not written in that language:
    - Award 0 marks and explain the reason.

### Evaluation Rules:
1. If language is valid (or language = "any"):
   - Check whether the code correctly solves the problem.
   - Consider logic, completeness, correctness, efficiency, and whether the code would run successfully.

2. Grading Logic:
   - **Full Marks ({total_marks}):**
       - Code is correct, executable, complete, and solves the problem.
   - **Partial Marks:**
       - Code shows meaningful logic toward solving the problem
       - But may contain errors, missing cases, runtime issues, or incomplete logic.
   - **Zero Marks:**
       - Code is unrelated to the problem,
       - Or completely incorrect,
       - Or does not demonstrate real effort,
       - Or written in wrong language when language is not "any".

3. Provide feedback explaining:
   - Why the marks were awarded
   - What was correct
   - What needs improvement

### Output Format (JSON only):
{{
  "score": <marks_awarded>,
  "feedback": "<reason for the score>"
}}

### Question:
{question}

### Student Submitted Answer:
{submitted_answer}
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    response = response.choices[0].message.content.strip()
    json_response = json.loads(response)
    return json_response

import logging
logger = logging.getLogger(__name__)

from main.email import send_assessment_completion_email
    


class SubmitSingleAssessmentQuestion(APIView): 
    authentication_classes =[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary='Add the single question in Assessment',
        manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),

        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'question': openapi.Schema(type=openapi.TYPE_OBJECT),
                'utilized_duration': openapi.Schema(type=openapi.TYPE_STRING)
            } 
        ),
        tags=['Job Invite']
    )
    def post(self, request):
        invite_id = request.query_params.get('invite_id') 
        question = request.data['question']
        utilized_duration = request.data['utilized_duration']
        if not question:
            return Response({'responseMessage':'Blank data should not be submitted'},status=status.HTTP_400_BAD_REQUEST)
        
        if  'question' not in question:
            return Response({'responseMessage':'The question field is missing inside question data'},status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            invite = get_object_or_404(JobInvites, invite_id=invite_id)

            # Fetch existing submissions safely
            submitted_records = SubmittedAssessmentQuestion.objects.filter(invite=invite)
            # submitted_question_list = [
            #     item.submitted_question.get('question') 
            #     for item in submitted_records
            # ]
            for item in submitted_records:
                    if item.submitted_question.get('question') == question['question'] and item.submitted_question.get('sequence') == question['sequence']:
                        item.submitted_question  = question
                        item.created_at = timezone.now()
                        item.save()
                        return Response({'responseMessage': 'Question submitted successfully'}, status=status.HTTP_200_OK)



            # if question['question'] in submitted_question_list:
            #     return Response({'responseMessage': 'Question already submitted'}, status=status.HTTP_400_BAD_REQUEST)

            obj =SubmittedAssessmentQuestion.objects.create(
                invite=invite,
                submitted_question=question
            )
            print('Question has been saved in DB', obj.pk)

            invite.utilized_duration = utilized_duration
            invite.save(update_fields=['utilized_duration'])

        return Response({'responseMessage': 'Question submitted successfully'}, status=status.HTTP_200_OK)





class SubmitJobAssessment(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
            operation_summary='Add the single question in Assessment',
            manual_parameters=[
            openapi.Parameter("invite_id", openapi.IN_QUERY, type=openapi.TYPE_INTEGER),   
            openapi.Parameter('is_terminated',openapi.IN_QUERY,type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('proctor_detected',openapi.IN_QUERY,type=openapi.TYPE_BOOLEAN),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),

        ],
    tags=['Job Invite']
    )
    def post(self,request):
        from main.task import submit_job_assessment_task
        invite_id = request.query_params.get('invite_id')
        is_terminated = request.query_params.get('is_terminated',False)
        proctor_detected = request.query_params.get('proctor_detected',False)
        invite = get_object_or_404(JobInvites.objects.select_related('assessment','assessment__job','assessment__job__user','assessment__job__user__company_details'),invite_id=invite_id)
        
        completed_assessment_object = SubmittedAssessmentQuestion.objects.filter(invite=invite).order_by('created_at')
        completed_assessment = list(completed_assessment_object.values_list('submitted_question',flat=True))
        
        if not completed_assessment:
            return Response({'responseMessage':'Qestions not found'},status=status.HTTP_400_BAD_REQUEST)
         
        invite.submit_status = 'completed'
        invite.save(update_fields=['submit_status'])
        
        file_name = f"assessment_{invite_id}.json"
        
        dir_path = os.path.join("static", "submitted_json")
        os.makedirs(dir_path, exist_ok=True)  # ✅ create dir if not exists
        
        file_path = os.path.join("static","submitted_json", file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(completed_assessment, f, ensure_ascii=False, indent=4)
        
        submit_job_assessment_task.delay(invite_id,is_terminated,proctor_detected)
        return Response({'responseMessage':'Assessment submitted successfully'},status=status.HTTP_200_OK)
    
        # if not isinstance(completed_assessment,list):
        #     invite.submit_status = 'not_short_listed'
        #     invite.submit_time = timezone.now()
        #     invite.save(update_fields=['submit_status','submit_time'])
        #     serializer = JobInviteSerializer(invite)
        #     return Response({'data':serializer.data,'responseMessage':'Assessment submitted successfully'},status=status.HTTP_200_OK)
        
        # mark_scored = 0
        
        # for question in completed_assessment:
            
        #     question_type = question['question_type']
            
        #     if question_type in ['MCQ','TRUE_FALSE','FILL_IN_THE_BLANK']:
                
        #         mark_received_for_question = question['marks'] if question['correct_answer'] == question['submitted_answer'] else 0
        #         question['mark_scored']=mark_received_for_question
        #         mark_scored += mark_received_for_question

        #     if question_type == 'MULTI_ANSWER_MCQ':
        #         correct_answer = set(question['correct_answer'])
        #         submitted_answer = set(question['submitted_answer'])
        #         mark_assing_for_mcq = question['marks']

        #         # Exact match = full marks
        #         if submitted_answer == correct_answer:
        #             question['mark_scored'] = mark_assing_for_mcq
        #         else:
        #             question['mark_scored'] = 0

        #         # Update total score
        #         mark_scored += question['mark_scored']
                            
        #     if  question_type == 'PUZZLE':
        #         correct_order = question['correct_order']
        #         submitted_answer = question['submitted_answer']

        #         if submitted_answer == correct_order:
        #             mark_scored += question['marks']
        #             question['mark_scored']=question['marks']
        #         else:
        #             question['mark_scored']=0

        #     if question_type == 'TYPE_ANSWER':
        #         submitted_answer = question['submitted_answer']
        #         correct_answer = question['correct_answer']
        #         score = evaluate_answer(question['question'],correct_answer,submitted_answer,question['marks'])
        #         if score > question['marks']:
        #             score = question['marks']
        #         question['mark_scored']=score
        #         mark_scored +=score


        # data_dict={}
        
        # data_dict['completed_assessment'] = completed_assessment
        # data_dict['marks_scored'] = round(mark_scored,2)

        # total_mark  = invite.assessment.total_marks
        
        # percentage = round(mark_scored/total_mark * 100,2)
        
        # shortlist_percentage = invite.assessment.shortlist_percentage
        # review_percentage = invite.assessment.review_percentage
        
        # data_dict['mobile_camera_is_on'] = False

        # if is_terminated : 
        #     data_dict['submit_status'] = 'not_short_listed'
        
        # else:
        #     if percentage >= shortlist_percentage:
        #         data_dict['submit_status'] ='short_listed'
            
        #     elif percentage < shortlist_percentage and percentage >= review_percentage:
        #         data_dict['submit_status'] = 'review'
            
        #     else:
        #         data_dict['submit_status'] = 'not_short_listed'
        
        # data_dict['percentage'] = percentage
        # data_dict['submit_time'] = timezone.now()
        
        # serializer = JobInviteSerializer(invite,data=data_dict,partial=True)
        # if serializer.is_valid():
        #     serializer.save()
        #     completed_assessment_object.delete()

        #     email = invite.email
        #     user_name = invite.name or 'User'
        #     job_title = invite.assessment.job.title

        #     staus_Details={
        #         'review':'Under Review',
        #         'short_listed':'Shortlisted',
        #         'not_short_listed':'Rejected'
        #         }
            
        #     submission_status = staus_Details[invite.submit_status]
        #     org = invite.assessment.job.user.company_details
            
        #     send_assessment_completion_email.delay(email, user_name, job_title,submission_status, org)
        #     return Response({'data':serializer.data, 'responseMessage':'Assesment submitted successfully'},status=status.HTTP_200_OK)
        # return Response({'error':serializer.errors, 'responseMessage':'Something is wrong'},status=status.HTTP_200_OK)
        



class DeleteJobAssessmentQuestionView(APIView):
    @swagger_auto_schema(
        operation_summary="Delete a question from an Jobassessment",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
            openapi.Parameter('job_assessment_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='ID of the assessment'),
            openapi.Parameter('sequence', openapi.IN_QUERY, type=openapi.TYPE_INTEGER, description='Sequence of the question to delete')
        ],
        tags=['Job Invite']
    )
    def delete(self, request):
        job_assessment_id = request.query_params.get('job_assessment_id')
        sequence = request.query_params.get('sequence')

        if not job_assessment_id or not sequence:
            return Response({'responseMessage': 'Assessment ID and sequence are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sequence = int(sequence)
        except ValueError:
            return Response({'responseMessage': 'Sequence must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        
        if not isinstance(assessment.assessment, list):
            return Response({'responseMessage': 'Assessment data is not a valid list'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        sorted_questions = sorted(assessment.assessment, key=lambda x: x["sequence"])
        new_question_list = []
        found = False

        for question in sorted_questions:
            if question['sequence'] == sequence:
                found = True  # Mark deletion
                continue
            if found:
                question['sequence'] -= 1  # Shift sequence after deletion
            new_question_list.append(question)

        if not found:
            return Response({'responseMessage': 'Question not found in assessment'}, status=status.HTTP_404_NOT_FOUND)

        assessment.assessment = new_question_list
        assessment.total_questions -= 1
        assessment.save(update_fields=["assessment","total_questions"])
        log_user_activity(request.user,'DELETE',f'''Question has been deleted in assessment '{assessment.assessment_name}'. ''')


        return Response({'data': assessment.assessment, 'responseMessage': 'Question has been deleted'}, status=status.HTTP_200_OK)



class SubmitJobNPSAPIView(APIView):
    @swagger_auto_schema(
        operation_summary='Fetch trainee assessment progress with detailed filters and stats.',
        request_body = JobNPSSerializer,
        tags = ['Job Invite']
        )
    def post(self, request):
        try:
            data=request.data
            invite_id = data.get('invte_user')
            invite = get_object_or_404(JobInvites,invite_id=invite_id)
            data['job_assessment'] = invite.assessment.job_assessment_id
            serializer = JobNPSSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({"data": serializer.data,"responseMessage": "Feedback submitted successfully"}, status=status.HTTP_201_CREATED)
            
            return Response({"error":serializer.errors,'responseMessage':'Something is wrong'}, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.db.models import Q,Count
class JobNpsDashboard(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='Job Nps Dashboard as per the user',
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer ')
        ],
        tags=['Job Invite']
    )
    def get(self, request):
        try:
            user = request.user
            # Fetch NPS counts in a single query using aggregation
            nps_counts = JobNPSModel.objects.filter(job_assessment__job__user=user).aggregate(
                poor=Count('job_nps_id', filter=Q(rating__lte=3)),
                bad=Count('job_nps_id', filter=Q(rating__range=(4, 6))),
                good=Count('job_nps_id', filter=Q(rating__range=(7, 8))),
                excellent=Count('job_nps_id', filter=Q(rating__gte=9))
            )
            data = {**nps_counts}
            #cache.set(cache_key,data,timeout=5*60)
            return Response({'data': data, 'responseMessage': 'Data found successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

from django.db.models import F

def apply_ordering_if_present(queryset, field_name, order_type):
    if order_type:
        if order_type == 'highest':
            return queryset.order_by(F(field_name).desc(nulls_last=True))
        elif order_type == 'lowest':
            return queryset.order_by(F(field_name).asc(nulls_last=True))
    return queryset


class JobPostingSummaryAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary='',
        manual_parameters=[
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('order_by_date', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['latest','oldest']),
            openapi.Parameter('order_by_user_count', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_completed', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_pending', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_proctoring', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_shortlisted', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_review', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('order_by_rejected', openapi.IN_QUERY, type=openapi.TYPE_STRING, enum=['highest', 'lowest']),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Invite']
    )
    def get(self, request):
        user = request.user
        search = request.query_params.get('search')
        order_by_date = request.query_params.get('order_by_date','latest')
        order_by_user_count = request.query_params.get('order_by_user_count')
        order_by_completed = request.query_params.get('order_by_completed')
        order_by_pending = request.query_params.get('order_by_pending')
        order_by_proctoring = request.query_params.get('order_by_proctoring')
        order_by_shortlisted = request.query_params.get('order_by_shortlisted')
        order_by_review = request.query_params.get('order_by_review')
        order_by_rejected = request.query_params.get('order_by_rejected')
        if user.role == 'recruiteradmin':
            job_listings = JobListing.objects.filter(group__user__company_details=user.company_details).order_by('-created_at')

        else:
            group = user.recruiter_membership.group
            job_listings = JobListing.objects.filter(group__in=group.all()).order_by('-created_at')
        
        
        if search:
            job_listings = job_listings.filter(title__icontains=search)
        
        if order_by_date:
            order_status = 'created_at' if order_by_date == 'oldest' else '-created_at'
            job_listings = job_listings.order_by(order_status)

        job_listings = job_listings.annotate(
            user_count=Count('Job_details__job_assessment', distinct=True),
            completed = Count(
                'Job_details__job_assessment',
                filter=~Q(Job_details__job_assessment__submit_status='not_started'),
                distinct=True
            ),
            pending =Count(
                'Job_details__job_assessment',
                filter=Q(Job_details__job_assessment__submit_status='not_started'),
                distinct=True
            ), 
            proctoring=Count(
                'Job_details__job_assessment',
                filter=Q(Job_details__job_assessment__proctoring_detected=True),
                distinct=True
            ),
            shortlisted=Count(
                'Job_details__job_assessment',
                filter=Q(Job_details__job_assessment__submit_status='short_listed'),
                distinct=True
            ),
            review=Count(
                'Job_details__job_assessment',
                filter=Q(Job_details__job_assessment__submit_status='review'),
                distinct=True
            ),
            rejected=Count(
                'Job_details__job_assessment',
                filter=Q(Job_details__job_assessment__submit_status='not_short_listed'),
                distinct=True
            )
        )
        job_listings = apply_ordering_if_present(job_listings, 'user_count', order_by_user_count)
        job_listings = apply_ordering_if_present(job_listings, 'completed', order_by_completed)
        job_listings = apply_ordering_if_present(job_listings, 'pending', order_by_pending)
        job_listings = apply_ordering_if_present(job_listings, 'proctoring', order_by_proctoring)
        job_listings = apply_ordering_if_present(job_listings, 'shortlisted', order_by_shortlisted)
        job_listings = apply_ordering_if_present(job_listings, 'review', order_by_review)
        job_listings = apply_ordering_if_present(job_listings, 'rejected', order_by_rejected)

        job_listings = job_listings.values( 'job_id', 'title', 'created_at',
            'user_count', 'completed', 'pending',
            'proctoring', 'shortlisted', 'review', 'rejected'
            )

        return Response({'data':job_listings,'responseMessage':'Data fetch successfully'},status=status.HTTP_200_OK)
    

from dateutil import parser

class InviteAnalytics(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter("page", openapi.IN_QUERY, description="Page number for pagination", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="Number of records per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter('job_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_STRING),
            openapi.Parameter('order_by_date', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['latest','oldest']),
            openapi.Parameter('filter_by_status', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['reivew','short_listed','not_short_listed','inprogress']),
            openapi.Parameter('filter_by_score', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['highest','lowest']),
            openapi.Parameter('start_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE,),
            openapi.Parameter('end_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE),
            openapi.Parameter('filter_by_job_assessment_id',openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Listing']
    )

    def get(self,request):
        job_id = request.query_params.get('job_id')
        serach = request.query_params.get('serach')
        order_by_date = request.query_params.get('order_by_date','latest')
        filter_by_score = request.query_params.get('filter_by_score')
        filter_by_status =request.query_params.get('filter_by_status')
        filter_by_job_assessment_id =request.query_params.get('filter_by_job_assessment_id')
        start_date  = request.query_params.get('start_date')
        end_date  = request.query_params.get('end_date')


        invite_view = JobInvites.objects.select_related('assessment').filter(assessment__job__job_id= job_id).exclude(submit_status='not_started').order_by('-updated_at')
        

        if order_by_date:
            order_format = '-updated_at' if order_by_date == 'latest' else 'updated_at'
            invite_view = invite_view.order_by(order_format)
        

        if serach:
            invite_view = invite_view.filter(Q(name__icontains=serach)|Q(email__icontains=serach)|Q(assessment__assessment_name = serach))
        
        if filter_by_status:
            invite_view = invite_view.filter(submit_status=filter_by_status)
        
        if filter_by_score:
            percentage_status='-percentage'if filter_by_score =='highest' else 'percentage' 
            invite_view = invite_view.order_by(percentage_status)

        if filter_by_job_assessment_id:
            invite_view = invite_view.filter(assessment__job_assessment_id = filter_by_job_assessment_id)

        date_filters = {}
        # try:
        if start_date:
            print('we are in the start_date')
            start_date_obj = parser.parse(start_date).date()
            date_filters["submit_time__date__gte"] = start_date_obj

        if end_date:
            end_date_obj = parser.parse(end_date).date()
            date_filters["submit_time__date__lte"] = end_date_obj


        if date_filters:
            invite_view = invite_view.filter(**date_filters)
        
        
        # except ValueError:
        #     pass  # ignore invalid dates
        
        
        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(invite_view, request)
        serializer = InviteAnalyticsSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)
    

        
class AcknowledgeInvite(APIView):
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites,invite_id = invite_id)
        if invite.invite_status != 'pending':
            return HttpResponse('')
        invite.invite_status = 'accepted'
        invite.save(update_fields=['invite_status'])
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Thank You</title>
            <style>
                body {
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background-color: #f9f9f9;
                    font-family: Arial, sans-serif;
                }
                img {
                    width: 500px;
                    height: auto;
                    margin-bottom: 20px;
                }
                h1 {
                    color: #2c3e50;
                    font-size: 2rem;
                }
            </style>
        </head>
        <body>
            <img src="https://openmoji.org/data/color/svg/1F44D.svg" alt="Thumbs Up" />
            <h1>Thank you for acknowledging the invite!</h1>
        </body>
        </html>
        """


        return HttpResponse(html_content)




from main.email import send_custom_email
class SendCustomEmail(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get credit usage data by role",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
                request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'invite_id':openapi.Schema(type=openapi.TYPE_INTEGER),
                'subject':openapi.Schema(type=openapi.TYPE_STRING),
                'message':openapi.Schema(type=openapi.TYPE_OBJECT)
            }
        ),
        tags=['Job Listing']
    )

    def post(self,request):
        user = request.user
        data = request.data
        subject = data.get('subject')
        invite_id = data.get('invite_id')
        message = data.get('message')

        invite = get_object_or_404(JobInvites,invite_id=invite_id)
        send_custom_email(subject,message,user.email,invite.user.email,user.company_details)
        log_user_activity(request.user,'CREATE',f'''Custom email has been send to invite user '{invite.name or invite.email}'. ''')
        
        return Response({'responseMessage':'Email sent successfully'},status=status.HTTP_200_OK)




class OnOffMobileCameraOfInvite(APIView):
    @swagger_auto_schema(
        operation_summary="Toggle mobile camera status for a specific invite",
        operation_description=(
            "Toggles the `mobile_camera_is_on` flag for a given Job Invite.\n\n"
            "**Example:** If it's ON, this will turn it OFF, and vice versa."
        ),
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            ),
        ],
         request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'mobile_status':openapi.Schema(type=openapi.TYPE_BOOLEAN),
            }
        ),
        tags=['Job Invite']
    )
    def post(self, request):
        invite_id = request.query_params.get('invite_id')
        mobile_status = request.data.get('mobile_status')
        if not invite_id:
            return Response(
                {"error": "invite_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        
        invite = get_object_or_404(JobInvites, invite_id=invite_id)
        if mobile_status and  invite.submit_status not in ['not_started','inprogress','not_short_listed']:
            return Response({'responseMessage':'Assessment already completed'},status=status.HTTP_400_BAD_REQUEST)
    
        invite.mobile_camera_is_on = mobile_status
    
        invite.save(update_fields=['mobile_camera_is_on'])

        return Response(
            {
                "invite_id": invite.invite_id,
                "mobile_camera_is_on": invite.mobile_camera_is_on
            },
            status=status.HTTP_200_OK
        )
    


class AddScreenRecordingVideos(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Add the screen recording videos in the invite",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            ),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'screen_url':openapi.Schema(type=openapi.TYPE_STRING),
                'time':openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        tags=['Job Invite']
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        data = request.data

        with transaction.atomic():
            invite = get_object_or_404(JobInvites,invite_id=invite_id)
            InviteSubmittedUrl.objects.create(invite=invite,url_json=data,url_type = 'screen_recording')
            # capture_screen_videos =  invite.capture_screen_videos or []
            # capture_screen_videos.append(data)
            # invite.capture_screen_videos = capture_screen_videos
            # invite.save(update_fields=['capture_screen_videos'])
        return Response({'responseMessage':'Screen video added successfully'},status=status.HTTP_200_OK)
    


class AddWindowDetectionRecords(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Add the web detection records in the invite",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            ),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),

        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'image_url':openapi.Schema(type=openapi.TYPE_STRING),
                'time':openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        tags=['Job Invite']
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites,invite_id=invite_id)

        data = request.data
        with transaction.atomic():
            window_detection_json =  invite.window_detection_json or []
            window_detection_json.append(data)
            invite.window_detection_json = window_detection_json
            invite.window_detection_count+=1
            invite.save(update_fields=['window_detection_json','window_detection_count'])
        return Response({'responseMessage':'Screen video added successfully'},status=status.HTTP_200_OK)
    

class AddMobileWarningDetectionRecords(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Add the Add mobile warning  in the invite",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            ),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),

        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'image_url':openapi.Schema(type=openapi.TYPE_STRING),
                'time':openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        tags=['Job Invite']
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        data = request.data
        with transaction.atomic():
            invite = get_object_or_404(JobInvites,invite_id=invite_id)
            mobile_warning_json = invite.mobile_warning_json or []
            mobile_warning_json.append(data)
            invite.mobile_warning_json =mobile_warning_json
            invite.mobile_warning_count+=1 
            invite.save(update_fields=['mobile_warning_json','mobile_warning_count'])
        return Response({'responseMessage':'Mobile Warning records added successfully'},status=status.HTTP_200_OK)


class AddMobileRecordingChunks(APIView):
    @swagger_auto_schema(
        operation_summary="Add the Add mobile warning  in the invite",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            ),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'video_url':openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        tags=['Job Invite']
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        video_url = request.data['video_url']
        invite = get_object_or_404(JobInvites.objects.select_related('assessment'),invite_id=invite_id)
        with transaction.atomic():
            videos = invite.capture_mobile_videos or []
            videos.append(video_url)
            invite.capture_mobile_videos = videos
            invite.save(update_fields=['capture_mobile_videos'])

        return Response({'responseMessage':'Mobile recording chunks updated successfully'},status=status.HTTP_200_OK)




class LiveUserDetails(APIView):
    @swagger_auto_schema(
        operation_summary="LiveUserDetails",
        manual_parameters=[
            openapi.Parameter(name="job_assessment_id",in_=openapi.IN_QUERY,type=openapi.TYPE_STRING,description="Unique Job assessment ID "),
            openapi.Parameter("user_status",openapi.IN_QUERY,type=openapi.TYPE_STRING,enum=['online','offline'],default='online'),
            openapi.Parameter("date_filter",openapi.IN_QUERY,type=openapi.TYPE_STRING,enum=['latest','oldest'],default='latest'),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        tags=['Job Invite']
    )
    def get(self,request):
        
        job_assessment_id = request.query_params.get('job_assessment_id')
        search = request.query_params.get('search')
        user_status = request.query_params.get('user_status','online')
        date_filter = request.query_params.get('date_filter','latest')
        
        if not job_assessment_id:
            return Response({'responseMessage':'Asessment not found'},status=status.HTTP_200_OK)
        
        filter_dict = {
            "assessment__job_assessment_id":job_assessment_id,
            "mobile_camera_is_on" : False if user_status == 'offline' else True
        }
        invites = JobInvites.objects.select_related('assessment').filter(**filter_dict)

        if date_filter:
            order_status = (
                ('-created_at' if date_filter == 'latest' else 'created_at')
                if user_status == 'offline'
                else ('-start_time' if date_filter == 'latest' else 'start_time')
            )

            invites = invites.order_by(order_status)
        if search:
            invites = invites.filter(assessment__assessment_name__icontains = search)
        
        serializer = LiveIniviteUserDetails(invites,many=True)
        return Response({'data':serializer.data},status=status.HTTP_200_OK)
    

import urllib

class CheckSurroundingWithObjectDetection(APIView):
    @swagger_auto_schema(
        operation_summary="Add the web detection records in the invite",
        manual_parameters=[
            openapi.Parameter(
                name="invite_id",
                in_=openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                required=True,
                description="Unique invite ID of the Job Invite"
            )
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'video_url':openapi.Schema(type=openapi.TYPE_STRING),
            }
        ),
        tags=['Job Invite']
    )
    def post(self, request):
        
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites, invite_id=invite_id)

        video_url = request.data.get('video_url')
        if not video_url:
            return Response({"error": "video_url is required"}, status=status.HTTP_400_BAD_REQUEST)

        if invite.submit_status not in ['not_started', 'inprogress', 'not_short_listed']:
            return Response({'responseMessage': 'Assessment already completed'}, status=status.HTTP_400_BAD_REQUEST)

        if invite.submit_status == 'not_short_listed':
            if not invite.is_reake or invite.retake_count >= invite.rekate_allow:
                return Response({'responseMessage': 'Assessment already completed'}, status=status.HTTP_400_BAD_REQUEST)
        # Handle spaces in URL
        video_url = video_url.replace(" ", "_")

        # Download video to static folder
        static_dir = os.path.join(os.getcwd(), "static")
        os.makedirs(static_dir, exist_ok=True)
        file_name = os.path.basename(urllib.parse.urlparse(video_url).path)
        file_path = os.path.join(static_dir, file_name)

        try:
            r = requests.get(video_url, stream=True)
            r.raise_for_status()
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Process video
            is_object_detected = self.process_video(file_path)

            # Save result in DB
            invite.capture_surrounding = video_url
            invite.save(update_fields=['capture_surrounding'])
            if is_object_detected:
                return Response({"is_object_detected": is_object_detected}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({"is_object_detected": is_object_detected}, status=status.HTTP_200_OK)


        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        finally:
            # Clean up file
            if os.path.exists(file_path):
                os.remove(file_path)

    def process_video(self, file_path):
        from talent.inference import get_yolo_model
        model = get_yolo_model()
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise Exception("Cannot open video file")

        detect_objects = {"cell phone", "person"}
        detection_found = False
        frame_skip = 10  # process every 10th frame for speed

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1

            if frame_count % frame_skip != 0:
                continue

            # Skip invalid or black frames
            if frame is None or frame.mean() < 5:
                continue

            # Resize frame (higher resolution helps detect phones)
            frame = cv2.resize(frame, (960, 960))

            # Run YOLO only on person (0) and cell phone (67)
            results = model(frame, conf=0.15, classes=[0, 67], agnostic_nms=True)[0]

            for box in results.boxes:
                cls_name = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                # Apply per-class confidence threshold
                if cls_name == "person" and conf > 0.50:
                    detection_found = True
                    break
                # if cls_name == "cell phone" and conf > 0.3:
                #     detection_found = True
                #     break

            if detection_found:
                break

        cap.release()
        return detection_found


from collections import defaultdict
class JobAssessmentDetails(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @swagger_auto_schema(
        operation_summary="Get Job Assessment List",
        operation_description="Fetch a list of job assessments for the authenticated user.",
        manual_parameters=[
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),

        ],
    )
    def get(self, request):
        user = request.user
        
        if user.role == 'recruiteradmin':
            qs = JobAssessment.objects.filter(
                job__user__company_details=user.company_details
            ).values(
                'job__job_id',
                'job__title',
                'job_assessment_id',
                'assessment_name'
            ).order_by('-job__created_at')
        else:
            qs = JobAssessment.objects.filter(
                job__group=user.recruiter_membership.group.all()
            ).values(
                'job__job_id',
                'job__title',
                'job_assessment_id',
                'assessment_name'
            ).order_by('-job__created_at')

        grouped = defaultdict(lambda: {"job_id": None, "job_title": None, "job_assessment": []})

        for item in qs:
            job_id = item['job__job_id']

            grouped[job_id]["job_id"] = job_id
            grouped[job_id]["job_title"] = item['job__title']
            grouped[job_id]["job_assessment"].append({
                "job_assessment_id": item['job_assessment_id'],
                "assessment_name": item['assessment_name']
            })

        return Response({"data": list(grouped.values())}, status=status.HTTP_200_OK)
        


class ChatMessagesView(APIView):
    @swagger_auto_schema(
        operation_summary="Get Job Assessment List",
        operation_description="Fetch a list of job assessments for the authenticated user.",
        manual_parameters=[
        openapi.Parameter('user_type', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['trainer','invite']),
        openapi.Parameter('id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER,description='triner user id'),
        openapi.Parameter('job_assessment_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        ],
    )
    def get(self,request):
        user_type = request.query_params.get('user_type')
        id = request.query_params.get('id')
        job_assessment_id = request.query_params.get('job_assessment_id')
        invite_id = request.query_params.get('invite_id')

        if user_type == 'trainer':
            chat_details = ChatMessages.objects.filter(assessment__job_assessment_id=job_assessment_id,trainer__id = id,invite__invite_id = invite_id).order_by('created_at')
        else:
            chat_details = ChatMessages.objects.filter(assessment__job_assessment_id=job_assessment_id,invite__invite_id = invite_id).order_by('created_at')

        serializer = chatMessageSerializer(chat_details,many=True)
        return Response({'data':serializer.data,'responseMessage':'Messages retrived successfully'},status=status.HTTP_200_OK)


class CustomMessageView(APIView):
    @swagger_auto_schema(
        operation_summary="Get Custom message api",
        operation_description="Get custom message api information details",
        manual_parameters=[
        openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        ],
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        custom_message = (
        JobInvites.objects
        .filter(invite_id=invite_id)
        .select_related("assessment__job")
        .values_list("assessment__job__custom_message", flat=True)
        .first()
        )
        if custom_message is None:
            return Response(
                {"responseMessage": "Invalid invite ID"},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        return Response({"data": custom_message}, status=status.HTTP_200_OK)


class UpdateInviteAssessmentMarks(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Get Custom message api",
        operation_description="Get custom message api information details",
        manual_parameters=[
        openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
        openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token',default='Bearer '),

        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'sequence':openapi.Schema(type=openapi.TYPE_INTEGER),
                'updated_marks':openapi.Schema(type=openapi.TYPE_INTEGER)
            }
        )
    )
    def post(self,request):
        invite_id = request.query_params.get('invite_id')
        data = request.data
        sequence  = data.get('sequence')
        updated_marks = data.get('updated_marks')

        invite = get_object_or_404(JobInvites.objects.select_related(
            'assessment','assessment__job','assessment__job__user','assessment__job__user__company_details'),
            invite_id=invite_id
            )

        total_updated_marks = 0
        sequence_detected = False
        updated_assessment=[]
        for question in invite.completed_assessment:
            if sequence == question.get('sequence'):
                sequence_detected = True
                question['mark_scored'] = updated_marks
                total_updated_marks += updated_marks
                question['is_edited']=True
                updated_assessment.append(question)
            else:
                updated_assessment.append(question)
                total_updated_marks+= question['mark_scored']
        
        if not sequence_detected:
            return Response({'responseMessage':'Question sequence not found'},status=status.HTTP_400_BAD_REQUEST)
        
        print(updated_marks)
        invite.completed_assessment = updated_assessment
        invite.marks_scored = float(total_updated_marks)
        total_marks = float(invite.assessment.total_marks)
        print(total_marks)
        percentage = round(float(total_updated_marks)/total_marks* 100,2)
        print(percentage)
        invite.percentage = percentage

        if percentage >= invite.assessment.shortlist_percentage:
                user_submit_status ='short_listed'
            
        elif percentage < invite.assessment.shortlist_percentage and percentage >= invite.assessment.review_percentage:
            user_submit_status = 'review'
        
        else:
            user_submit_status = 'not_short_listed'

        if invite.submit_status!= user_submit_status:
            invite.submit_status = user_submit_status

            email = invite.user.email
            user_name = invite.user.name or 'User'
            job_title = invite.assessment.job.title

            staus_Details={
                'review':'On Hold',
                'short_listed':'Shortlisted',
                'not_short_listed':'Rejected'
                        }
            
            submission_status = staus_Details[user_submit_status]
            org = invite.assessment.job.user.company_details

            subject = f"Update Status: Assessment status updated for {job_title}"
            if user_submit_status == 'short_listed':
                message = (
                    f"Hi {user_name},\n\n"
                    f"Great news! 🎉 Your assessment for the role of '{job_title}' "
                    f"has been reviewed and you have been **Shortlisted**.\n\n"
                    "Our team will reach out to you with the next steps soon.\n\n"
                    f"Best regards,\n{org}"
                )
            elif user_submit_status == 'review':
                message = (
                    f"Hi {user_name},\n\n"
                    f"Your assessment for the role of '{job_title}' is currently **On Hold**.\n\n"
                    "This means that your submission is under further review. "
                    "We will notify you once a final decision is made.\n\n"
                    f"Best regards,\n{org}"
                )
            else:  # not_short_listed
                message = (
                    f"Hi {user_name},\n\n"
                    f"Thank you for completing the assessment for the role of '{job_title}'.\n\n"
                    "After careful consideration, we regret to inform you that "
                    "you have not been shortlisted at this time.\n\n"
                    "We truly appreciate the effort you put into the process and "
                    "encourage you to apply for future opportunities with us.\n\n"
                    f"Best regards,\n{org}"
                )
            send_assessment_completion_email.delay(email, user_name, job_title,submission_status, org,subject,message)

        
        invite.save(update_fields=['submit_status','percentage','marks_scored','completed_assessment'])

        return Response({'responseMessage':'marks updated successfully'},status=status.HTTP_200_OK)
    



class GroupDropdownList(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Create Job Assessment with AI",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        user = request.user
        queryset = RecruiterGroup.objects.filter(user__company_details= user.company_details)
        serializer = RecruiterGroupSerializer(queryset,many=True)
        return Response({'data':serializer.data},status=status.HTTP_200_OK)
    
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class TerminateExam(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Terminate the user exam",
        manual_parameters=[
            openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')
        invite = get_object_or_404(JobInvites,invite_id=invite_id)
        
        if invite.submit_status != 'inprogress':
            return Response({'responseMessage':'Only inprogress assessment can terminate'},status=status.HTTP_400_BAD_REQUEST)
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"proctoring_{invite_id}",
            {
                "type": "send_termination",
                "invite_id": invite_id,
                "is_terminated": True
            }
        )
        invite.submit_status = 'not_short_listed'
        invite.save(update_fields=['submit_status'])
        return Response({'responseMessage': 'Exam terminated successfully'}, status=status.HTTP_200_OK)
    



class InviteAssessmentList(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="invite user job assessment list",
        manual_parameters=[
            
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):

        if request.user.role != 'invite_user':
            return Response({'responseMessage':'Only job seeker have access'},status=status.HTTP_400_BAD_REQUEST)
        
        invite_list = JobInvites.objects.filter(user = request.user).order_by('-created_at')
        
        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(invite_list, request)
        serializer = viewJobInviteSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)
     

class ViewOldAssessmentDetails(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        manual_parameters=[
            openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        invite_id = request.query_params.get('invite_id')

        attempts = JobInviteOldAttempt.objects.filter(invite__invite_id=invite_id).order_by('-created_at')
        
        serializer = JobInviteOldAttemptSerializer(attempts,many=True)
        
        return Response({'data':serializer.data,'responseMessag':'Data found successfully'},status=status.HTTP_200_OK)
    



# ========================= Application user Management ================================


class ApplicationUserManagementView(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        manual_parameters=[
            openapi.Parameter("page", openapi.IN_QUERY, description="Page number for pagination", type=openapi.TYPE_INTEGER),
            openapi.Parameter("page_size", openapi.IN_QUERY, description="Number of records per page", type=openapi.TYPE_INTEGER),
            openapi.Parameter('job_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('search', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('from_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE),
            openapi.Parameter('to_date', openapi.IN_QUERY, type=openapi.FORMAT_DATE),
            openapi.Parameter('application_status', openapi.IN_QUERY, type=openapi.TYPE_STRING,enum=['pending','invited','rejected']),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        job_id = request.query_params.get('job_id')
        search = request.query_params.get('search')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        filter_status = request.query_params.get('application_status')
        application_list = ApplicationUserList.objects.filter(job__job_id=job_id).order_by('-created_at')
        
        if filter_status:
            application_list = application_list.filter(application_status=filter_status)

        if search:
            application_list = application_list.filter(name__icontains=search)

        if from_date and to_date:
                
            application_list = application_list.filter(
                created_at__range=(from_date, to_date)
            ) 
        paginator = CustomPagination()
        paginated_querySet = paginator.paginate_queryset(application_list, request)
        serializer = ApplicationUserListSerializer(paginated_querySet, many=True)

        response_data = {
            "next": paginator.get_next_link(),
            "previous": paginator.get_previous_link(),
            "results": {
                "total_pages": paginator.page.paginator.num_pages,
                "data": serializer.data,
                "responseMessage": "Data found successfully"
            }
        }
        return Response(response_data, status=status.HTTP_200_OK)
     
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        manual_parameters=[
            openapi.Parameter('application_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def delete(self,request):
        application_id = request.query_params.get('application_id')    
        ApplicationUserList.objects.filter(application_id=application_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
class MultiApplicationReject(APIView):

    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type= openapi.TYPE_OBJECT,
            properties={
                'application_ids':openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Schema(type=openapi.TYPE_INTEGER)),
            }
        )
    )
    def put(self,request):
        user = request.user
        application_ids = request.data['application_ids']
        application_list = ApplicationUserList.objects.filter(application_id__in =application_ids)
        emails = list(application_list.values_list('email', flat=True))
        print('the email list',emails)
        application_list.update(application_status='rejected')
        send_rejection_email(emails,application_list.first().job.title,user.company_details)
        return Response({'responseMessage':'application rejected successfully'},status=status.HTTP_200_OK)
    

class MultiApplicationInvite(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type= openapi.TYPE_OBJECT,
            properties={
                'application_ids':openapi.Schema(type=openapi.TYPE_ARRAY,items=openapi.Schema(type=openapi.TYPE_INTEGER)),
                'job_assessment_id':openapi.Schema(type=openapi.TYPE_INTEGER),
                'is_schduled': openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'schdule_start_time':openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                'schdule_end_time':openapi.Schema(type=openapi.TYPE_STRING, format=openapi.FORMAT_DATETIME),
                'is_reake':openapi.Schema(type=openapi.TYPE_BOOLEAN),
                'rekate_allow':openapi.Schema(type=openapi.TYPE_INTEGER),
                'cool_down_period':openapi.Schema(type=openapi.TYPE_INTEGER)
            }
        )
    )
    def put(self,request):
        from Admin.models import AssignRole
        user = request.user
        data = request.data
        application_ids = data['application_ids']
        job_assessment_id = data['job_assessment_id']
        is_schduled = data.get('is_schduled', False)
        is_reake = data.get('is_reake', False)

        org = user.company_details
        if org.job_assessment_limit < org.job_assessment_count + len(application_ids):
            remaining = org.job_assessment_limit - org.job_assessment_count
            
            return Response({
                "responseMessage": f"Invite cannot be sent. Only {remaining} assessment(s) left in your plan."
            }, status=status.HTTP_400_BAD_REQUEST)
        

        assessment = get_object_or_404(JobAssessment,job_assessment_id=job_assessment_id)
        
        if not assessment.is_public:
            return Response({'responseMessage':f'Assessment "{assessment.assessment_name}" not published'},status=status.HTTP_400_BAD_REQUEST)
        
        applications = ApplicationUserList.objects.filter(application_id__in =application_ids)
        
        existing_invites = set(
                JobInvites.objects.filter(assessment=assessment).values_list('user__email', flat=True)
            )
        invites = []
        temp_data = []
        
        for application in applications:
            email = application.email
            
            if email in existing_invites:
                continue

            try:
                invite_user = MyUser.objects.get(email=email, company_details=org)
                password = None
                if invite_user.role != 'invite_user':
                    return Response({'responseMessage': f'{email} already exists with role "{invite_user.role}"'},
                                    status=status.HTTP_400_BAD_REQUEST)
            except MyUser.DoesNotExist:
                password = generate_password()
                print('email',email, 'password',password)
                invite_user = MyUser.objects.create(
                    email=email,
                    name = application.name,
                    password=make_password(password),
                    role="invite_user",
                    company_details=org,
                    is_verified=True
                )
                AssignRole.objects.create(user=invite_user)
                InviteUserDetails.objects.create(
                    user=invite_user,
                    region = application.region,
                    resume=application.resume_url,
                    first_gov_id_proof = application.first_gov_id_proof,
                    first_gov_id_key = application.first_gov_id_key,
                    first_gov_id_upload=application.first_gov_id_upload,
                    first_gov_id_verify=application.first_gov_id_verify,
                    second_gov_id_proof= application.second_gov_id_proof,
                    second_gov_id_key=application.second_gov_id_key,
                    second_gov_id_upload=application.second_gov_id_upload,
                    second_gov_id_verify=application.second_gov_id_verify
                    )

            invites.append(JobInvites(
                user=invite_user,
                assessment=assessment,
                is_schduled=is_schduled,
                schdule_start_time=data.get('schdule_start_time') if is_schduled else None,
                schdule_end_time=data.get('schdule_end_time') if is_schduled else None,
                is_reake=is_reake,
                rekate_allow=data.get('rekate_allow') if is_reake else None,
                cool_down_period=data.get('cool_down_period') if is_reake else None,
            ))

            temp_data.append({
                'email': email,
                'password': password,
                'schdule_start_time': data.get('schdule_start_time'),
                'schdule_end_time': data.get('schdule_end_time'),
                'job_assessment_id': job_assessment_id
            })

        # Step 5: Bulk create invites
        if invites:
            created_invites = JobInvites.objects.bulk_create(invites, batch_size=100)

            send_email_list = []
            for invite_obj, temp in zip(created_invites, temp_data):
                send_email_list.append({
                    'invite_id': invite_obj.invite_id,
                    'email': temp['email'],
                    'password': temp['password'],
                    'schedule_start_time': format_datetime(invite_obj.schdule_start_time),
                    'schedule_end_time': format_datetime(invite_obj.schdule_end_time),
                    'Job_title': invite_obj.assessment.job.title,
                    'user_name': invite_obj.user.name or 'user'
                })

            subject = f"You're Invited: Assessment"
            send_job_invites.delay(send_email_list, subject, user.company_details)

            log_user_activity(
                request.user,
                'CREATE',
                f"New Invites have been sent for from apply user list."
            )

            applications.update(application_status='invited')

            return Response({
                'data': 'Invites sent successfully',
            }, status=status.HTTP_200_OK)

        return Response({'data': 'All users are already invited'}, status=status.HTTP_400_BAD_REQUEST)



class ApplicationUserSubmitForm(APIView):
    @swagger_auto_schema(
        operation_summary="View old Job Assessment attempts of invite user",
        request_body=ApplicationUserListSerializer,
    )
    def post(self,request):
        from main.task import calculate_resume_score_task
        data = request.data

        if ApplicationUserList.objects.filter(email=data['email'],job__job_id = data['job']).exists():
            return Response({'responseMessage':'Application alreday submitted'},status=status.HTTP_400_BAD_REQUEST)
        
        first_gov_id_proof = data.get('first_gov_id_proof',None)
        second_gov_id_proof = data.get('second_gov_id_proof',None)

        if first_gov_id_proof and  InviteUserDetails.objects.filter(
                first_gov_id_proof=first_gov_id_proof,
                ).exclude(email=data['email']).exists():
                return Response({'responseMessage':f'Id proof "{first_gov_id_proof}" record already exists'},status=status.HTTP_400_BAD_REQUEST)

        if second_gov_id_proof and InviteUserDetails.objects.filter(
            second_gov_id_proof=second_gov_id_proof,
            ).exclude(email=data['email']).exists():
            return Response({'responseMessage':f'Id proof "{second_gov_id_proof}" record already exists'},status=status.HTTP_400_BAD_REQUEST)
        
        if first_gov_id_proof :
            is_valid = verify_id_proof(
                file_url=data["first_gov_id_upload"],
                provided_proof=first_gov_id_proof
            )
            data['first_gov_id_verify'] =is_valid

        # Second ID Proof check
        if second_gov_id_proof :
            is_valid = verify_id_proof(
                file_url=data["second_gov_id_upload"],
                provided_proof=second_gov_id_proof
            )
            data['second_gov_id_verify'] =is_valid
            

        serializer = ApplicationUserListSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            serialized_data = serializer.data
            print(serialized_data)
            calculate_resume_score_task.delay(serialized_data['application_id'])

            return Response({'data':serialized_data,'responseMessage':'Application submitted successfully'},status=status.HTTP_200_OK)
        return Response({'error':serializer.errors,'responseMessage':'Something is wrong! please check the input'},status=status.HTTP_400_BAD_REQUEST)


class JobDropdown(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Job dropdown",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self, request):
        user = request.user

        if user.role == 'recruiteradmin':
            job_view = JobListing.objects.filter(
                user__company_details=user.company_details
            ).values('job_id', 'title').order_by('-created_at')
        else:
            recruiter = RecruiterMembership.objects.filter(user=user).first()
            if not recruiter:
                return Response({"responseMessage": "Recruiter membership not found."}, status=status.HTTP_404_NOT_FOUND)

            groups = recruiter.group.all()  # ✅ ManyToMany relation
            job_view = JobListing.objects.filter(
                user__company_details=user.company_details,
                group__in=groups
            ).values('job_id', 'title').order_by('-created_at')

        return Response({'data':job_view,'responseMessage':'Data found successfully'}, status=status.HTTP_200_OK)



class SaveJobLink(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Job dropdown",
        manual_parameters=[
            openapi.Parameter('job_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type = openapi.TYPE_OBJECT,
            properties={
                'job_link':openapi.Schema(type=openapi.TYPE_STRING),
            }
    )
    )
    def post(self,request):
        job_id = request.query_params.get('job_id')
        job_link = request.data.get('job_link')
        job = get_object_or_404(JobListing,job_id=job_id)
        job.job_link = job_link
        job.save(update_fields=['job_link'])
        return Response({'responseMessage':'Job link saved successfully'},status=status.HTTP_200_OK)
    


class ExtractJobSeeker(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Extract job seeker details",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        user = request.user
        user_details = InviteUserDetails.objects.filter(user__company_details=user.company_details).values('user__name','user__email','first_gov_id_proof','first_gov_id_key','second_gov_id_proof','second_gov_id_key','region')

        return Response({'data':user_details})



class BackgoundDetectionFromDesktop(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
    operation_summary="Extract job seeker details",
    manual_parameters=[
        openapi.Parameter(
            'invite_id',
            openapi.IN_QUERY,
            type=openapi.TYPE_INTEGER,
            description='Invite ID',
        ),
        openapi.Parameter(
            'Authorization',
            openapi.IN_HEADER,
            type=openapi.TYPE_STRING,
            description='JWT token (format: Bearer <token>)',
            default='Bearer ',
        ),
    ],
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            's3_urls': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Schema(  # ✅ must be a Schema, not a type constant
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'current_url': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='S3 URL of the uploaded file',
                        ),
                        'time': openapi.Schema(
                            type=openapi.TYPE_STRING,
                            description='Timestamp when file was uploaded',
                        ),
                    },
                ),
            ),
        },
    ),
    )
    def post(self,request):
        from main.task import backgound_detection_from_desktop
        invite_id = request.query_params.get('invite_id')
        s3_urls = request.data.get('s3_urls')
        backgound_detection_from_desktop.delay(s3_urls,invite_id)
        return Response({'responseMessage':'backgound detection started successfully'},status=status.HTTP_200_OK)


class ImageProctoringDetection(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Extract job seeker details",
        manual_parameters=[
            openapi.Parameter('invite_id', openapi.IN_QUERY, type=openapi.TYPE_INTEGER),
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'current_url':openapi.Schema(type=openapi.TYPE_STRING),
                'time':openapi.Schema(type=openapi.TYPE_STRING)

            }
        ),
    )
    def post(self,request):

        invite_id = requests.query_params.get('invite_id')
        data = request.data

        invite = JobInvites.objects.get(invite_id=invite_id)
        image_proctoring_json = invite.image_proctoring_json or []
        image_proctoring_json.append(data)
        invite.image_proctoring_json = image_proctoring_json
        invite.save(update_fields=['image_proctoring_json'])
        return Response({'responseMessage':'Data saved successfully'},status=status.HTTP_200_OK)
    


class JobAssessmentDropDown(APIView):
    authentication_classes=[JWTAuthentication]
    permission_classes = [IsAuthenticated]
    @swagger_auto_schema(
        operation_summary="Job assessment dropdown",
        manual_parameters=[
            openapi.Parameter('Authorization', openapi.IN_HEADER, type=openapi.TYPE_STRING, description='JWT token', default='Bearer '),
        ],
    )
    def get(self,request):
        user = request.user

        if user.role == 'recruiteradmin':
            assessment_view = list(JobAssessment.objects.filter(
                job__user__company_details=user.company_details
            ).values('job_assessment_id','assessment_name'))
        else:
            recruiter = RecruiterMembership.objects.filter(user=user).first()
            if not recruiter:
                return Response({"responseMessage": "Recruiter membership not found."}, status=status.HTTP_404_NOT_FOUND)

            groups = recruiter.group.all()  # ✅ ManyToMany relation
            assessment_view = list(JobAssessment.objects.filter(
                job__user__company_details=user.company_details,
                job__group__in=groups
            ).values('job_assessment_id','assessment_name'))
        
        return Response({'data':assessment_view,'responseMessage':'Data found successfully'}, status=status.HTTP_200_OK)

