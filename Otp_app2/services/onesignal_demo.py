import httpx
import asyncio

# -------------------------------------------------------------------
# OneSignal Configuration
# Get these from your OneSignal Dashboard -> Settings -> Keys & IDs
# -------------------------------------------------------------------
ONESIGNAL_APP_ID = "YOUR_ONESIGNAL_APP_ID"
ONESIGNAL_API_KEY = "YOUR_ONESIGNAL_REST_API_KEY"

async def send_onesignal_notification(
    user_ids: list[str], 
    title: str, 
    message: str, 
    data: dict = None
):
    """
    Sends a push notification via OneSignal REST API.
    
    Args:
        user_ids: List of external user IDs (the IDs you use in your DB).
                  OneSignal maps these to device tokens if you use setExternalUserId on client.
        title: Notification Title
        message: Notification Body
        data: Optional dictionary of extra data (e.g., {"type": "exam_result"})
    """
    
    url = "https://onesignal.com/api/v1/notifications"
    
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Basic {ONESIGNAL_API_KEY}"
    }
    
    payload = {
        "app_id": ONESIGNAL_APP_ID,
        "include_external_user_ids": user_ids,  # Target specific users by your DB ID
        "headings": {"en": title},
        "contents": {"en": message},
        "data": data or {},
        # "included_segments": ["All"]  # Use this to send to EVERYONE instead of specific users
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"✅ OneSignal Notification Sent: {response.json()}")
                return response.json()
            else:
                print(f"❌ OneSignal Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Request Failed: {e}")
            return None

# -------------------------------------------------------------------
# Example Usage (Async)
# -------------------------------------------------------------------
async def main():
    # Example: Sending to a student with ID "student_123"
    await send_onesignal_notification(
        user_ids=["student_123"],
        title="Exam Graded!",
        message="Your Physics exam has been graded. Click to view results.",
        data={"type": "exam_result", "exam_id": "physics_01"}
    )

if __name__ == "__main__":
    asyncio.run(main())
