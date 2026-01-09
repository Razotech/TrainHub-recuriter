import json,uuid
from channels.generic.websocket import AsyncWebsocketConsumer,AsyncJsonWebsocketConsumer

from asgiref.sync import sync_to_async
import traceback

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        """Connect user to their notification group based on user_id from the URL."""
        self.user_id = self.scope["url_route"]["kwargs"].get("id")
        
        if self.user_id:
            self.group_name = f"notifications_{self.user_id}"  # Unique channel group per user
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            
            await self.accept()
            # await self.send(text_data=json.dumps({"message": "Connection established"}))

        else:
            await self.close()


    async def disconnect(self, close_code):
        """Disconnect user from the notification group."""
        if self.user_id:
            # await self.send(text_data=json.dumps({"message": "Connection disconeected"}))
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            await self.close()

    async def receive(self, text_data):
        """Receive message from WebSocket (optional)"""
        pass

    async def send_notification_message(self, event):
        """Send notification to WebSocket."""
        await self.send(text_data=json.dumps(event["message"]))


# consumers.py
from channels.db import database_sync_to_async

from talent.models import JobInvites,ChatMessages,JobAssessment
from main.models import MyUser
from main.task import enforce_object_detection_to_db,enforce_mobile_object_detection_to_db
from django.core.cache import cache
import traceback


REQUESTS_PER_WINDOW = 25        # allow 20 messages...
WINDOW_SECONDS = 60   
ACTIVE_EXAM_KEY= 'active:exam:{invite_id}' 

class ProctoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.invite_id = self.scope['url_route']['kwargs']['invite_id']
        self.room_group_name = f"proctoring_{self.invite_id}"
        cache.incr(ACTIVE_EXAM_KEY.format(invite_id=self.invite_id), ignore_key_check=True)
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            invite_id = data.get("invite_id")
            current_url = data.get("current_url")
            time = data.get("time")


            if await self._is_rate_limited(invite_id):
                await self.send(json.dumps({
                    "invite_id": invite_id,
                    "status": "throttled",
                    "detail": f"Too many messages; try again in {WINDOW_SECONDS}s window."
                }))
                return
            print('current_url',current_url)
            if current_url:
                # Offload heavy detection to Celery
                print("we are sending the image detection to celery")
                enforce_object_detection_to_db.delay(
                    invite_id,
                    current_url,
                    time,
                    self.channel_name,
                )
            else:
                await self.send(json.dumps({
                    "invite_id": invite_id,
                    "error": "please provide image url"
                }))

        except Exception as e:
            traceback.print_exc()
            await self.send(text_data=json.dumps({"error": str(e)}))

    async def send_object_proctoring_result(self,event):
        event = event['message']
        await self.send(text_data=json.dumps({
            "invite_id": event['invite_id'],
            "is_object_detected": event['is_object_detected'],
            "is_face_detected":event['is_face_detected'],
            "is_proctoring_detected": event['is_proctoring_detected']
        }))

    
    async def send_termination(self,event):
        await self.send(text_data=json.dumps(
            {
            "invite_id":event['invite_id'],
            "is_terminated":event['is_terminated']
            }
        ))
    
    async def object_detection_result(self, event):
        await self.send(text_data=json.dumps({
            "invite_id": event["invite_id"],
            "is_object_detected": event["is_object_detected"],
            "is_proctoring_detected":event["is_proctoring_detected"],
            "source": "ScreenRecordingConsumer"
        }))
    
    async def start_mobile_disconnection_loop(self, event):
        invite_id = event["invite_id"]

        async def loop_task():
            while True:
                # ⏳ Wait first 10 seconds before checking
                await asyncio.sleep(20)
                

                # ✅ Refetch invite each time
                invite = await database_sync_to_async(
                    lambda: JobInvites.objects.select_related('assessment').get(invite_id=invite_id)
                )()

                if invite.mobile_camera_is_on:
                    print("📱 Mobile camera reconnected, stopping loop.")
                    break

                # Send update to trainer
                print("sending mobile monotirng is off to laptop consumer")
                await self.channel_layer.group_send(
                    f"proctoring_{invite_id}",
                    {
                        "type": "mobile_disconnection_update",
                        "invite_id": invite_id,
                    }
                )
                await asyncio.sleep(2)


        # Run background loop
        asyncio.create_task(loop_task())

    async def mobile_disconnection_update(self, event):
        await self.send(text_data=json.dumps({
            "invite_id": event["invite_id"],
            "mobile_proctoring_off": True,
            "type": "mobile_off",
            "source": "ProctoringConsumer"
        }))

    async def disconnect(self, close_code):
        try:
            remaning = cache.decr(ACTIVE_EXAM_KEY.format(invite_id=self.invite_id))
        except ValueError:
            remaning = 0

        if remaning<= 0:
            cache.delete(ACTIVE_EXAM_KEY.format(invite_id=self.invite_id))

        print(f"Socket disconnected with code {close_code}")


    async def _is_rate_limited(self, invite_id: str) -> bool:
        """
        Fixed-window rate limiter backed by Django cache (Redis recommended).
        """
        RATE_LIMIT_KEY = "screenProctoring:invite:{invite_id}:rate"
        key = RATE_LIMIT_KEY.format(invite_id=invite_id)
        try:
            current = cache.get(key)
            if current is None:
                cache.set(key, 1, timeout=WINDOW_SECONDS)
                return False
            if current >= REQUESTS_PER_WINDOW:
                return True
            cache.incr(key)
            return False
        except Exception:
            # fail open if cache is down
            return False


from django.core.cache import cache

ACTIVE_CONNECTIONS_KEY = "mobileProctoring:{invite_id}:connections"

class ScreenRecordingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            print("Mobile Connect Called")
            self.invite_id = self.scope['url_route']['kwargs']['invite_id']
            self.room_group_name = f"screen_recording_{self.invite_id}"
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

            # mark mobile camera on
            self.invite = await database_sync_to_async(
                JobInvites.objects.select_related('assessment').get
            )(invite_id=self.invite_id)
            
            cache.incr(ACTIVE_CONNECTIONS_KEY.format(invite_id=self.invite_id), ignore_key_check=True)
            self.invite.mobile_camera_is_on = True
            await database_sync_to_async(self.invite.save)()
            print("Mobile Connect Called successfully")
            await self.accept()

        except Exception as e:
            traceback.print_exc()  
            print("WebSocket connect error:", e)
            await self.close()

    async def receive(self, text_data=None, bytes_data=None):
        try:
            if not text_data:
                return

            data = json.loads(text_data)

            invite_id = data.get("invite_id") or self.invite_id
            image_url = data.get("image_url")     # {"url": "..."} or None
            video_url = data.get("video_url",None)     # "https://..." or None
        

            # OPTIONAL: simple per-invite rate limit (protects Celery & DB)
            # allows REQUESTS_PER_WINDOW per WINDOW_SECONDS
            if await self._is_rate_limited(invite_id):
                await self.send(json.dumps({
                    "invite_id": invite_id,
                    "status": "throttled",
                    "detail": f"Too many messages; try again in {WINDOW_SECONDS}s window."
                }))
                return

            # Offload detection + DB to Celery (send back to THIS channel)
            
            enforce_mobile_object_detection_to_db.delay(
                invite_id,
                video_url,
                image_url,
                self.channel_name,
            )


        except Exception as e:
            print("Receive error:", e)
            await self.close()


    async def send_result(self,event):
        event = event['message']
        await self.channel_layer.group_send(
            f"proctoring_{event['invite_id']}",
            {
                "type": "object_detection_result",
                "invite_id": event['invite_id'],
                "is_object_detected": event['is_object_detected'],
                "is_proctoring_detected":event['is_proctoring_detected'],
            }
        )
        

        
    async def disconnect(self, close_code):
        print("Mobile called disconnect ")
        try:
            invite = await database_sync_to_async(
                JobInvites.objects.select_related('assessment').get
            )(invite_id=self.invite_id)
            
            key = ACTIVE_CONNECTIONS_KEY.format(invite_id=self.invite_id)
            remaining = cache.decr(key)
            if remaining <= 0:
                invite.mobile_camera_is_on = False
                await database_sync_to_async(invite.save)()
                cache.delete(key)
                print("no new connection found monitoring off ")

            await self.channel_layer.group_send(
                f"proctoring_{self.invite_id}",
                {
                    "type": "start_mobile_disconnection_loop",
                    "invite_id": self.invite_id,
                }
            )
            print("Mobile called disconnect successfully")

        except Exception as e:
            print("Disconnect error:", e)

        # Always clean group
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def _is_rate_limited(self, invite_id: str) -> bool:
        """
        Simple fixed-window rate limiter backed by Django cache (use Redis).
        """
        RATE_LIMIT_KEY = "mobileProctoring:invite:{invite_id}:rate"
        key = RATE_LIMIT_KEY.format(invite_id=invite_id)
        try:
            current = cache.get(key)
            if current is None:
                cache.set(key, 1, timeout=WINDOW_SECONDS)
                return False
            if current >= REQUESTS_PER_WINDOW:
                return True
            cache.incr(key)
            return False
        except Exception:
            # If cache is down, fail open to avoid breaking the flow
            return False

import time, asyncio

class StreamConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.stream_id = self.scope['url_route']['kwargs']['stream_id']
        self.room_group_name = f"stream_{self.stream_id}"

        # Target FPS
        self.frame_interval = 1 / 15
        self.frame_queue = asyncio.Queue(maxsize=30)  # avoid memory blow-up

        # Add to group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Background sender task
        self.sender_task = asyncio.create_task(self.frame_sender())

        print(f"[Connected] {self.channel_name} in stream {self.stream_id}")

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        if self.sender_task:
            self.sender_task.cancel()
        print(f"[Disconnected] {self.channel_name}")

    async def receive(self, text_data=None, bytes_data=None):
        if text_data:
            
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError:
                data = {"raw_text": text_data}

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'send_to_group',
                    'message': data,
                }
            )

        if bytes_data:

            # Drop oldest frame if queue is full
            if self.frame_queue.full():
                _ = await self.frame_queue.get()  # remove oldest
            await self.frame_queue.put(bytes_data)

    async def frame_sender(self):
        """
        Continuously sends frames from queue at target FPS.
        """
        try:
            while True:
                frame = await self.frame_queue.get()
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'send_binary',
                        'bytes_data': frame,
                    }
                )
                await asyncio.sleep(self.frame_interval)
        except asyncio.CancelledError:
            pass

    async def send_to_group(self, event):
        await self.send(text_data=json.dumps(event['message']))

    async def send_binary(self, event):
        try:
            
            await self.send(bytes_data=event['bytes_data'])
        except Exception as e:
            print(f"[Send Error] {e}")


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']  # assessment_id
        self.room_group_name = f"chat_{self.room_name}"

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        print('chat recived data',data)
        message = data.get("message")
        sender = data.get("sender")  # "trainer" or "invite"
        trainer_id = data.get("trainer_id")
        invite_id = data.get("invite_id")
        assessment_id = self.room_name  # from URL

        # Save the message and get unread counts
        unread_counts = await self.save_message_and_get_counts(
            trainer_id, invite_id, assessment_id,message, sender
        )


        # Broadcast with unread counts
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "sender": sender,
                "invite_id":invite_id,
                "unread_counts": unread_counts,
                
            }
        )

    async def chat_message(self, event):
        
        await self.send(text_data=json.dumps({
            "sender": event["sender"],
            "message": event["message"],
            "invite_id":event['invite_id'],
            "unread_counts": event.get("unread_counts", {})
        }))

    @database_sync_to_async
    def save_message_and_get_counts(self, trainer_id, invite_id, assessment_id,message, sender):
        invite = JobInvites.objects.get(invite_id=invite_id)
        trainer = MyUser.objects.get(id=trainer_id)
        assessment = JobAssessment.objects.get(job_assessment_id=assessment_id)

        # Save the message
        ChatMessages.objects.create(
            trainer=trainer,
            invite=invite,
            assessment=assessment,
            message = message,
            sender=sender,
            is_trainer_read=(sender != "trainer"),  # if trainer sent, invite unread
            is_invite_read=(sender != "invite")    # if invite sent, trainer unread
        )

        # Calculate unread counts
        unread_for_trainer = ChatMessages.objects.filter(
            assessment=assessment,
            is_trainer_read=False
        ).count()

        unread_for_invite = ChatMessages.objects.filter(
            assessment=assessment,
            is_invite_read=False
        ).count()

        return {
            "trainer": unread_for_trainer,
            "invite": unread_for_invite
        }
    


# class SignallingConsumer(AsyncJsonWebsocketConsumer):
#     async def connect(self):
#         self.room_name = self.scope['url_route']['kwargs']['invite_id']
#         self.room_group_name = f"webrtc_room_{self.room_name}"
#         # assign a random peer id
#         self.peer_id = str(uuid.uuid4())

#         await self.channel_layer.group_add(self.room_group_name, self.channel_name)
#         await self.accept()

#         # announce join to room
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {"type": "signal.message",
#              "message": {"type": "new-peer", "peer_id": self.peer_id}}
#         )

#         # tell the joining client its own id
#         await self.send_json({"type": "id", "peer_id": self.peer_id})

#     async def disconnect(self, close_code):
#         # announce leaving
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {"type": "signal.message",
#              "message": {"type": "peer-left", "peer_id": self.peer_id}}
#         )
#         await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

#     async def receive_json(self, content, **kwargs):
#         """
#         Expected messages from client:
#         - {type: "offer", target: "<peerId>", offer: {...}}
#         - {type: "answer", target: "<peerId>", answer: {...}}
#         - {type: "candidate", target: "<peerId>", candidate: {...}}
#         - {type: "join"} (optional — we already announce on connect)
#         """
#         print('content',content)
#         message_type = content.get("type")
#         payload = content.copy()
#         payload["from"] = self.peer_id

#         # broadcast to group (clients filter by .target)
#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {"type": "signal.message", "message": payload}
#         )

#     async def signal_message(self, event):
#         # pushes event["message"] to the client
#         await self.send_json(event["message"])


# your_app/consumers.py

import json
import logging
import uuid
from channels.generic.websocket import AsyncJsonWebsocketConsumer 
logger = logging.getLogger(__name__)

ROOM_OFFERS = {}  # room_id -> last offer message 
 
class SignallingConsumer(AsyncJsonWebsocketConsumer):

    """

    WebSocket signaling consumer for peer-to-peer WebRTC negotiation.
 
    Behavior:

    - Clients connect to: /ws/SignallingConsumer/<invite_id>/

    - On connect:

        - A random peer_id is created and returned to the connecting client as {"type": "id", "peer_id": "<uuid>"}.

        - A "new-peer" message is broadcast to the room so others may notice a join.

    - When a client sends JSON via the socket, it is broadcast to the room, augmented with:

        - "from": the peer_id assigned on connect (so recipients know the sender)

    - Receiving clients SHOULD filter messages locally:

        - If message contains "to": only the client whose peer_id equals message["to"] should act on it.

        - If message has no "to": treat as broadcast/room message.

    - This consumer intentionally does NOT attempt to route by channel name or maintain a central peer map

      because Channels may run multiple workers. Clients must include `to` where necessary.

    """
 
    async def connect(self):

        # room (invite) id from URL route kwargs

        self.room_name = self.scope['url_route']['kwargs']['invite_id']

        self.room_group_name = f"webrtc_room_{self.room_name}"
 
        # assign a stable random peer id for this connection

        self.peer_id = str(uuid.uuid4())
 
        # join room group

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        await self.accept()
 
        logger.info("WS connect peer_id=%s room=%s", self.peer_id, self.room_name)
 
        # announce join to the group (optional)

        await self.channel_layer.group_send(

            self.room_group_name,

            {

                "type": "signal.message",

                "message": {"type": "new-peer", "peer_id": self.peer_id}

            }

        )
 
        # tell the joining client its own id (client should store this)

        await self.send_json({"type": "id", "peer_id": self.peer_id})
 
    async def disconnect(self, close_code):

        # announce leaving

        try:

            await self.channel_layer.group_send(

                self.room_group_name,

                {"type": "signal.message", "message": {"type": "peer-left", "peer_id": self.peer_id}}

            )

            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

            logger.info("WS disconnect peer_id=%s room=%s", self.peer_id, self.room_name)

        except Exception:

            logger.exception("Error during disconnect cleanup for peer_id=%s", self.peer_id)
 

 
    async def receive_json(self, content, **kwargs):

        try:

            if not isinstance(content, dict):

                return
    
            payload = content.copy()

            payload["from"] = self.peer_id
    
            # ✅ If it's an offer, save it for late-joining admins

            if payload.get("type") == "offer":

                ROOM_OFFERS[self.room_name] = payload
    
            await self.channel_layer.group_send(

                self.room_group_name,

                {"type": "signal.message", "message": payload}

            )

        except Exception:

            logger.exception("Error in receive_json for peer_id=%s", self.peer_id)

 
 
    async def signal_message(self, event):

        """

        Called when the channel layer sends a message to this consumer.

        event["message"] is the original payload we broadcast above.

        We forward it to the WebSocket **only if**:

         - it has no 'to' field (public to room), OR

         - the 'to' matches this connection's peer_id.

        Also, don't re-send a message back to its sender (optional but usually desired).

        """

        try:

            message = event.get("message", {})

            if not isinstance(message, dict):

                return
 
            # If message has a 'to' field, deliver only to matching peer_id

            message_to = message.get("to")

            message_from = message.get("from")
 
            # Ignore messages sent by this same connection (so sender doesn't get its own offer back)

            if message_from == self.peer_id:

                return
 
            # If 'to' exists and doesn't match this consumer's peer_id, skip

            if message_to and message_to != self.peer_id:

                return
 
            # Optionally: filter out internal-only messages (if you want)

            # e.g. if message.get("type") == "internal", skip
 
            await self.send_json(message)

        except Exception:

            logger.exception("Error in signal_message for peer_id=%s", self.peer_id)

 