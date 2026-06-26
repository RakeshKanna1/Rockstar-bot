import re
import os
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from database import save_code, code_exists

logger = logging.getLogger(__name__)

def get_latest_code():
    if not os.path.exists("token.json"):
        logger.error("token.json not found. Run auth.py first to authorize Google API.")
        return "❌ Error: Gmail authorization token missing. Please contact admin."

    try:
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
            return "No Rockstar emails found within the last 7 days."

        msg = service.users().messages().get(
            userId="me",
            id=messages[0]["id"]
        ).execute()

        snippet = msg.get("snippet", "")

        # Search for a 6-digit verification code
        code_match = re.search(r"\b\d{6}\b", snippet)

        if code_match:
            found_code = code_match.group()

            if not code_exists(found_code):
                save_code(found_code)

            return found_code

        return "No verification code found in the latest Rockstar email."

    except Exception as e:
        logger.error(f"Failed to fetch latest Rockstar code from Gmail: {e}", exc_info=True)
        return f"❌ Error checking verification email: {str(e)}"