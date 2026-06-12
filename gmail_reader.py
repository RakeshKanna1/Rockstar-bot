from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from database import save_code
from database import save_code, code_exists
import re

def get_latest_code():

    creds = Credentials.from_authorized_user_file(
        "token.json",
        ["https://www.googleapis.com/auth/gmail.readonly"]
    )

    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(
        userId="me",
        q="from:noreply@rockstargames.com newer_than:7d",
        maxResults=1
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        return "No Rockstar emails found"

    msg = service.users().messages().get(
        userId="me",
        id=messages[0]["id"]
    ).execute()

    snippet = msg["snippet"]

    code = re.search(r"\b\d{6}\b", snippet)

    if code:
        found_code = code.group()

        if not code_exists(found_code):
            save_code(found_code)

        return found_code

    return "No verification code found in latest email"