from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return {"status": "Sarah backend running"}

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/lead", methods=["POST"])
def lead():
    data = request.get_json()

    return jsonify({
        "status": "lead received",
        "name": data.get("name"),
        "phone": data.get("phone"),
        "message": data.get("message")
    })

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
