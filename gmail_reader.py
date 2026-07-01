import base64
import json
import logging
import os
import re

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from database import code_exists, save_code

logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def load_credential_options():
    credentials = []
    token_env = os.environ.get("GOOGLE_TOKEN")
    if token_env:
        try:
            cleaned_env = re.sub(r"[\x00-\x1f\x7f]", "", token_env.strip())
            token_data = json.loads(cleaned_env)
            logger.info("Loaded Google token from environment variables.")
            credentials.append((
                "GOOGLE_TOKEN",
                Credentials.from_authorized_user_info(token_data, GMAIL_SCOPES)
            ))
        except Exception as e:
            logger.error(f"Failed to load Google token from environment: {e}")
            if not os.path.exists("token.json"):
                raise ValueError(f"Failed to parse GOOGLE_TOKEN: {str(e)}") from e

    if os.path.exists("token.json"):
        credentials.append((
            "token.json",
            Credentials.from_authorized_user_file("token.json", GMAIL_SCOPES)
        ))

    if not credentials:
        logger.error("token.json not found. Run auth.py first to authorize Google API.")
        raise FileNotFoundError("Gmail authorization token missing. Please contact admin.")

    return credentials


def get_message_body(part):
    if "parts" in part:
        for subpart in part["parts"]:
            body = get_message_body(subpart)
            if body:
                return body
    else:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")
        if mime_type in ["text/plain", "text/html"] and data:
            try:
                return base64.urlsafe_b64decode(data.encode("ASCII")).decode("utf-8")
            except Exception:
                pass
    return ""


def fetch_latest_code(creds):
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

    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    subject = ""
    for header in headers:
        if header.get("name", "").lower() == "subject":
            subject = header.get("value", "")
            break

    snippet = msg.get("snippet", "")
    body = get_message_body(payload)

    code_match = re.search(r"\b\d{6}\b", subject)
    if not code_match:
        code_match = re.search(r"\b\d{6}\b", snippet)
    if not code_match:
        code_match = re.search(r"\b\d{6}\b", body)

    if code_match:
        found_code = code_match.group()

        if not code_exists(found_code):
            save_code(found_code)

        return found_code

    return "No verification code found in the latest Rockstar email."


def get_latest_code():
    last_error = None

    try:
        credential_options = load_credential_options()
    except Exception as e:
        logger.error(f"Failed to load Gmail credentials: {e}", exc_info=True)
        return f"Error checking verification email: {str(e)}"

    for source, creds in credential_options:
        try:
            return fetch_latest_code(creds)
        except Exception as e:
            last_error = e
            logger.error(f"Failed to fetch latest Rockstar code using {source}: {e}", exc_info=True)

    if last_error:
        if "invalid_grant" in str(last_error):
            return "Gmail authorization expired. Please regenerate GOOGLE_TOKEN or token.json with auth.py."
        return f"Error checking verification email: {str(last_error)}"

    return "Error checking verification email: Gmail authorization unavailable."
