import os
import datetime
import json
import requests
from flask import Flask, request, jsonify, redirect
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

app = Flask(__name__)

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
CALENDAR_ID = "getveronica.ai@gmail.com"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
REDIRECT_URI = "https://sarah-backend-eipx.onrender.com/oauth/callback"
TOKEN_FILE = "google_token.json"

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
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    return redirect(auth_url)

@app.route("/oauth/callback")
def oauth_callback():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [REDIRECT_URI]
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=request.args.get("code"))
    creds = flow.credentials
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes)
    }
    return jsonify({
        "message": "Auth successful! Copy this token and add it to Render as GOOGLE_TOKEN",
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

    if fn_name == "capture_lead":
        return jsonify({"result": "Lead captured successfully"}), 200

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
