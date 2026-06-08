import os
import datetime
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

CAL_API_KEY = os.environ.get("CAL_API_KEY", "")
CAL_EVENT_TYPE_ID = os.environ.get("CAL_EVENT_TYPE_ID", "")
CAL_BASE_URL = "https://api.cal.com/v1"

@app.route("/")
def home():
    return {"status": "Sarah backend running"}

@app.route("/health")
def health():
    return {"status": "ok"}

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
            dt_str = args.get("dateTime", "")
            dt = datetime.datetime.fromisoformat(dt_str)
            date_str = dt.strftime("%Y-%m-%d")

            resp = requests.get(
                f"{CAL_BASE_URL}/slots",
                params={
                    "apiKey": CAL_API_KEY,
                    "eventTypeId": CAL_EVENT_TYPE_ID,
                    "startTime": f"{date_str}T00:00:00+10:00",
                    "endTime": f"{date_str}T23:59:00+10:00",
                    "timeZone": "Australia/Sydney"
                },
                timeout=8
            )
            slots_data = resp.json()
            all_slots = []
            for day_slots in slots_data.get("slots", {}).values():
                for slot in day_slots:
                    all_slots.append(slot.get("time", ""))

            requested_time = dt.strftime("%H:%M")
            available = any(requested_time in s for s in all_slots)

            if available:
                return jsonify({"result": "available", "slots": all_slots[:5]}), 200
            else:
                return jsonify({"result": "unavailable", "slots": all_slots[:5]}), 200

        except Exception as e:
            return jsonify({"result": f"error: {str(e)}"}), 200

    elif fn_name == "createEvent":
        try:
            dt_str = args.get("dateTime", "")
            dt = datetime.datetime.fromisoformat(dt_str)

            payload = {
                "eventTypeId": int(CAL_EVENT_TYPE_ID),
                "start": dt.isoformat(),
                "responses": {
                    "name": args.get("name", "Customer"),
                    "email": args.get("email", "noreply@smithsplumbing.com.au"),
                    "phone": args.get("phone", ""),
                    "notes": args.get("description", "")
                },
                "timeZone": "Australia/Sydney",
                "language": "en",
                "metadata": {}
            }

            resp = requests.post(
                f"{CAL_BASE_URL}/bookings",
                params={"apiKey": CAL_API_KEY},
                json=payload,
                timeout=8
            )
            result = resp.json()

            if resp.status_code in [200, 201]:
                return jsonify({"result": "booked", "bookingId": result.get("id")}), 200
            else:
                return jsonify({"result": f"booking failed: {result}"}), 200

        except Exception as e:
            return jsonify({"result": f"error: {str(e)}"}), 200

    return jsonify({"result": "unknown tool"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
