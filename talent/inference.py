from ultralytics import YOLO
from speechbrain.inference import SpeakerRecognition
from functools import partial,lru_cache
from insightface.app import FaceAnalysis
import cv2,requests,random,torch,os,torchaudio
import numpy as np
from PIL import Image
from io import BytesIO

# --- Step 1: Init model (CPU) ---




# Allow loading old pickled models from trusted sources
torch.load = partial(torch.load, weights_only=False)

@lru_cache
def get_face_model():
    app = FaceAnalysis(providers=['CPUExecutionProvider'])
    app.prepare(ctx_id=0, det_size=(320, 320))

    # app  = FaceAnalysis(providers=['CUDAExecutionProvider'])
    # app.prepare(ctx_id=0, det_size=(320, 320))
    return app


@lru_cache
def get_yolo_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return YOLO("yolov8s.pt").to(device)


@lru_cache
def get_speaker_model():
    return SpeakerRecognition.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir="pretrained_models/spkrec-ecapa-voxceleb",
    )





def is_silent(audio_path, threshold=1e-4):
    waveform, sample_rate = torchaudio.load(audio_path)
    energy = torch.mean(waveform**2).item()
    return energy < threshold

def download_audio(url, filename):
    response = requests.get(url)
    if response.status_code == 200:
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"[+] Downloaded: {filename}")
    else:
        raise Exception(f"[!] Failed to download file: {url} (Status Code: {response.status_code})")


# Speaker matching logic
def check_speaker_match(ref_file, test_file,threshold=0.75):
    verification=get_speaker_model()
    score, prediction = verification.verify_files(ref_file, test_file)
    prediction = score > threshold
    return prediction.item(), score.item()



def preprocess_audio(file_path):
    waveform, sample_rate = torchaudio.load(file_path)

    # Convert to mono if stereo
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)

    # Apply VAD (removes non-speech / silence)
    vad_waveform = torchaudio.functional.vad(waveform, sample_rate=sample_rate)

    # If nothing left after VAD, return None
    if vad_waveform.shape[1] == 0:
        return None, sample_rate

    return vad_waveform, sample_rate

# Main function
def check_audio_proctoring(ref_url, test_url):
    ref_file_name = ref_url.split('/')[-1]
    test_file_name = test_url.split('/')[-1]
    print('ref_url',ref_url,flush=True)
    print('test_url',test_url,flush=True)

    ref_file = os.path.join('static',f'ref_file_{random.random()}_{ref_file_name}')
    test_file = os.path.join('static',f'test_file_{random.random()}_{test_file_name}')

    # Step 1: Download both files
    download_audio(ref_url, ref_file)
    download_audio(test_url, test_file)

    try:
        # ref_wave, sr = preprocess_audio(ref_file)
        # test_wave, _ = preprocess_audio(test_file)

        # if ref_wave is None or test_wave is None:
        #     print("No speech detected in one of the files")
        #     return False


        torchaudio.load(ref_file)
        torchaudio.load(test_file)

    except Exception as e:
        print(f"[!] Error processing audio: {e}")
        return False

    # Step 3: Verify speaker
    match, score = check_speaker_match(ref_file, test_file)
    print(f"Match: {match}, Score: {score}")
    
    for f in [ref_file, test_file]:
        if os.path.exists(f):
            os.remove(f)
    
    return score < 0.30




def url_to_image(url):
    """Downloads an image from a URL and returns it as a NumPy array (OpenCV format)."""
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Failed to download image: {url}")
    image_arr = np.asarray(bytearray(response.content), dtype=np.uint8)
    image = cv2.imdecode(image_arr, cv2.IMREAD_COLOR)
    return image


# ========================== Face Recorgnization detection ==========================

def get_embedding(url: str):
    img = url_to_image(url)
    app =get_face_model()
    faces = app.get(img)
    if not faces:
        raise ValueError(f"No face detected in {url}")
    # pick the largest detected face
    face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    return face.normed_embedding

# --- Step 4: Compare embeddings ---
def cosine_similarity(v1, v2):
    return float(np.dot(v1, v2))  


def face_recorgnization_detection(ref_url,curr_url):
    emb1 = get_embedding(ref_url)
    emb2 = get_embedding(curr_url)

    similarity = cosine_similarity(emb1, emb2)
    print("Face detection Cosine similarity:", similarity)

    threshold = 0.50  # adjust if needed
    return not similarity >= threshold


def face_exists(url: str) -> bool:
    img = url_to_image(url)
    app = get_face_model()
    faces = app.get(img)
    return len(faces) == 1

# ========================== object detection=========================

def load_image_from_s3_url(url):
    """Download and convert image from S3 URL to NumPy array."""
    response = requests.get(url)
    image = Image.open(BytesIO(response.content)).convert("RGB")
    return np.array(image)


def detect_object_from_mobile(url):
    model = get_yolo_model()
    image_array = load_image_from_s3_url(url)
    results = model(image_array,conf=0.30)[0]
    person_count = 0
    detect_objects = ['cell phone','laptop','monitor']
    monitor_count = 0
    laptop_count = 0
    for box in results.boxes:
        detected_class = model.names[int(box.cls[0])]
        print('detected_class',detected_class)
        if detected_class == 'person':
            if detected_class == 'person':
                person_count+=1
                if person_count>1:
                    return True

        if detected_class == 'cell phone':
            print(f"[ALERT] Cheating object detected in mobile object: {detected_class}")
            return True 
        if detected_class =='monitor_count':
            monitor_count+=1
            if monitor_count>1:
                return True
        if detected_class =='laptop':
            laptop_count +=1
            if laptop_count > 1:
                return True

    return False



def detect_cheating(image_array):
    model = get_yolo_model()
    """Run YOLO detection and return True if banned objects are detected."""

    detect_objects = ['cell phone', 'laptop', 'watch', 'remote', 'person']

    banned_ids = [k for k, v in model.names.items() if v in detect_objects]

    results = model(image_array,conf=0.30,classes=banned_ids,imgsz=416)[0]

    person_count = 0
    for box in results.boxes:

        detected_class = model.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        print(detected_class,confidence)
        if detected_class == 'person':
            person_count+=1
            if person_count>1:
                return True
        if detected_class in detect_objects:
            if detected_class == 'person':
                continue
            print(f"[ALERT] Cheating object detected: {detected_class}")
            return True  
        
    return False  

def run_proctoring_check(s3_url):
    """Main function to check cheating from S3 URL image."""
    print("Checking image from:", s3_url)
    s3_url = s3_url.replace("s3.amazonaws.com//", "s3.amazonaws.com/")

    image_array = load_image_from_s3_url(s3_url)
    is_cheating = detect_cheating(image_array)
    print("Cheating Detected:", is_cheating)
    return is_cheating
