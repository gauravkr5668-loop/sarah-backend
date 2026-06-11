import os
import datetime
import json
import requests
from flask import Flask, request, jsonify, redirect
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
CALENDAR_ID = "getveronica.ai@gmail.com"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
REDIRECT_URI = "https://sarah-backend-eipx.onrender.com/oauth/callback"

CLIENT_CONFIG = {
    "web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [REDIRECT_URI]
    }
}

def get_calendar_service():
    token_json = os.environ.get("GOOGLE_TOKEN", "")
    if not token_json:
        raise Exception("No Google token found")
    token_data = json.loads(token_json)
    creds = Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)

@app.route("/")
def home():
    return {"status": "Sarah backend running"}

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/oauth/start")
def oauth_start():
    flow = Flow.from_client_config(
        CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.code_verifier = None
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent"
    )
    return redirect(auth_url)

@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    token_response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code"
        }
    )
    token_data = token_response.json()
    return jsonify({
        "message": "Auth successful! Copy the token below and add to Render as GOOGLE_TOKEN",
        "token": json.dumps(token_data)
    })

@app.route("/vapi-tool", methods=["POST"])
def vapi_tool():
    data = request.get_json(silent=True) or {}
    tool_calls = data.get("message", {}).get("toolCalls", [])

    if not tool_calls:
        return jsonify({"result": "no tool calls found"}), 200

    tool = tool_calls[0]
    fn_name = tool.get("function", {}).get("name", "")
    args = tool.get("function", {}).get("arguments", {})
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except:
            args = {}

    if fn_name == "capture_lead":
        try:
            NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
            NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
            payload = {
                "parent": {"database_id": NOTION_DATABASE_ID},
                "properties": {
                    "Caller name": {
                        "title": [{"text": {"content": args.get("name", "Unknown")}}]
                    },
                    "Phone number": {
                        "phone_number": args.get("phone", args.get("number", ""))
                    },
                    "Suburb": {
                        "rich_text": [{"text": {"content": args.get("suburb", args.get("location", ""))}}]
                    },
                    "Job type": {
                        "select": {"name": args.get("problem", args.get("issue", "General"))}
                    },
                    "Notes": {
                        "rich_text": [{"text": {"content": args.get("urgency", "normal")}}]
                    },
                    "Call time": {
                        "date": {"start": datetime.datetime.now().isoformat()}
                    },
                    "Status": {
                        "select": {"name": "New lead"}
                    }
                }
            }
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=10
            )
            if response.status_code == 200:
                return jsonify({"result": "Lead captured successfully"}), 200
            else:
                return jsonify({"result": f"Notion error: {response.text}"}), 200
        except Exception as e:
            return jsonify({"result": f"Lead capture error: {str(e)}"}), 200

    elif fn_name == "checkAvailability":
        try:
            service = get_calendar_service()
            dt_str = args.get("dateTime", "")
            dt = datetime.datetime.fromisoformat(dt_str)
            dt_end = dt + datetime.timedelta(hours=1)
            body = {
                "timeMin": dt.isoformat() + "+10:00",
                "timeMax": dt_end.isoformat() + "+10:00",
                "timeZone": "Australia/Sydney",
                "items": [{"id": CALENDAR_ID}]
            }
            result = service.freebusy().query(body=body).execute()
            busy = result["calendars"][CALENDAR_ID]["busy"]
            if busy:
                return jsonify({"result": "unavailable"}), 200
            else:
                return jsonify({"result": "available"}), 200
        except Exception as e:
            return jsonify({"result": f"error: {str(e)}"}), 200

    elif fn_name == "createEvent":
        try:
            service = get_calendar_service()
            dt_str = args.get("dateTime", "")
            dt = datetime.datetime.fromisoformat(dt_str)
            dt_end = dt + datetime.timedelta(hours=1)
            event = {
                "summary": args.get("title", "Plumbing Job"),
                "description": args.get("description", ""),
                "start": {"dateTime": dt.isoformat() + "+10:00", "timeZone": "Australia/Sydney"},
                "end": {"dateTime": dt_end.isoformat() + "+10:00", "timeZone": "Australia/Sydney"},
            }
            created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            return jsonify({"result": "booked", "eventId": created.get("id")}), 200
        except Exception as e:
            return jsonify({"result": f"error: {str(e)}"}), 200

    return jsonify({"result": "unknown tool"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
