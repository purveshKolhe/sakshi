from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import firebase_admin
from firebase_admin import credentials, auth as admin_auth, db
import requests
import re
import html
import json
from config import firebase_config, firebase_admin_config, gemini_api_key, flask_secret_key
from string import Template
import google.generativeai as genai
import traceback

# Initialize Firebase Admin SDK
cred = credentials.Certificate(firebase_admin_config)
firebase_admin.initialize_app(cred, {
    'databaseURL': firebase_config['databaseURL']
})

# Get a reference to the database service
db_ref = db.reference('/')

# Configure Gemini
genai.configure(api_key=gemini_api_key)
flash_model = genai.GenerativeModel('gemini-2.5-flash')
pro_model = genai.GenerativeModel('gemini-2.5-pro')

app = Flask(__name__)
app.secret_key = flask_secret_key

# Security helper functions
def sanitize_input(text):
    if not text:
        return ""
    return html.escape(text.strip())

def validate_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"

def is_doctor_linked_to_patient(doctor_uid, patient_uid):
    try:
        patient_data = db_ref.child("users").child(patient_uid).get()
        if not patient_data:
            return False
        return patient_data.get('linkedDoctorUID') == doctor_uid
    except Exception:
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/patient/signup', methods=['GET', 'POST'])
def patient_signup():
    if request.method == 'POST':
        email = sanitize_input(request.form.get('email', ''))
        password = request.form.get('password', '')
        fullname = sanitize_input(request.form.get('fullname', ''))
        username = sanitize_input(request.form.get('username', ''))
        phone = sanitize_input(request.form.get('phone', ''))
        invite_code = sanitize_input(request.form.get('invite_code', ''))

        if not all([email, password, fullname, username, phone, invite_code]):
            return "All required fields must be filled", 400
        if not validate_email(email):
            return "Invalid email format", 400
        is_valid, password_msg = validate_password(password)
        if not is_valid:
            return password_msg, 400
        
        try:
            user = admin_auth.create_user(email=email, password=password)
            uid = user.uid
            data = { "fullname": fullname, "username": username, "email": email, "phone": phone, "invite_code": invite_code }
            doctors_ref = db_ref.child("doctors").order_by_child("inviteCode").equal_to(invite_code).get()
            if doctors_ref:
                doctor_uid = list(doctors_ref.keys())[0]
                data['linkedDoctorUID'] = doctor_uid
            db_ref.child("users").child(uid).set(data)
            return redirect(url_for('patient_login'))
        except admin_auth.EmailAlreadyExistsError:
            return "An account with this email already exists. Please log in.", 409
        except Exception as e:
            traceback.print_exc()
            return "An unexpected error occurred during registration. Please try again.", 500
    return render_template('patient_signup.html')

def sign_in_with_firebase(email, password):
    rest_api_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={firebase_config['apiKey']}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    response = requests.post(rest_api_url, json=payload)
    response.raise_for_status()
    return response.json()

@app.route('/patient/login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'POST':
        email = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        try:
            user = sign_in_with_firebase(email, password)
            session['user'] = user['idToken']
            session['role'] = 'patient'
            return redirect(url_for('patient_dashboard'))
        except requests.exceptions.HTTPError as e:
            return "Invalid credentials", 401
        except Exception as e:
            return "An error occurred during login. Please try again.", 500
    return render_template('patient_login.html')

@app.route('/doctor/login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        email = sanitize_input(request.form.get('username', ''))
        password = request.form.get('password', '')
        try:
            user = sign_in_with_firebase(email, password)
            doctor_ref = db_ref.child("doctors").order_by_child("email").equal_to(email).get()
            if not doctor_ref:
                return "Not a doctor account", 403
            session['user'] = user['idToken']
            session['role'] = 'doctor'
            return redirect(url_for('doctor_dashboard'))
        except requests.exceptions.HTTPError as e:
            return "Invalid credentials", 401
        except Exception as e:
            return "An error occurred during login. Please try again.", 500
    return render_template('doctor_login.html')

@app.route('/patient/dashboard')
def patient_dashboard():
    if 'user' in session and session.get('role') == 'patient':
        return render_template('patient_dashboard.html')
    return redirect(url_for('patient_login'))

@app.route('/doctor/dashboard')
def doctor_dashboard():
    if 'user' in session and session.get('role') == 'doctor':
        try:
            user_info = admin_auth.verify_id_token(session['user'])
            doctor_uid = user_info['uid']
            # Primary: patients explicitly linked to this doctor
            patients = db_ref.child("users").order_by_child("linkedDoctorUID").equal_to(doctor_uid).get() or {}

            # Fallback: if no explicit linkage yet, link via invite code match
            if not patients:
                invite_code = db_ref.child("doctors").child(doctor_uid).child("inviteCode").get()
                if invite_code:
                    via_code = db_ref.child("users").order_by_child("invite_code").equal_to(invite_code).get() or {}
                    # Backfill linkage so future queries are fast and authorization works
                    for uid in via_code.keys():
                        try:
                            db_ref.child("users").child(uid).update({"linkedDoctorUID": doctor_uid})
                        except Exception:
                            pass
                    if via_code:
                        patients = via_code
            return render_template('doctor_dashboard.html', patients=patients)
        except Exception as e:
            session.clear()
            return redirect(url_for('doctor_login'))
    return redirect(url_for('doctor_login'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/chat', methods=['POST'])
def chat():
    if 'user' not in session or session.get('role') != 'patient':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_message = sanitize_input(request.json.get('message', ''))
        user_info = admin_auth.verify_id_token(session['user'])
        uid = user_info['uid']
        chat_history = db_ref.child("chats").child(uid).get() or []
        prompt = f"You are a friendly AI assistant. Patient: {user_message}\nAI:"
        response = flash_model.generate_content(prompt)
        ai_message = response.text
        chat_history.append({"user": user_message, "ai": ai_message})
        db_ref.child("chats").child(uid).set(chat_history)
        return jsonify({"response": ai_message})
    except Exception as e:
        return jsonify({"error": "An error occurred. Please try again."}), 500

@app.route('/analyze-chats/<patient_uid>')
def analyze_chats(patient_uid):
    if 'user' not in session or session.get('role') != 'doctor':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_info = admin_auth.verify_id_token(session['user'])
        doctor_uid = user_info['uid']
        if not is_doctor_linked_to_patient(doctor_uid, patient_uid):
            return jsonify({"error": "Access denied"}), 403
        chat_history = db_ref.child("chats").child(patient_uid).get()
        if not chat_history:
            return jsonify({
                "summary": "No chat history.",
                "moodTimeline": {"labels": [], "data": []},
                "activity": {"labels": [], "data": []},
                "urgencyDistribution": {"labels": ["Low", "Medium", "High"], "data": [0,0,0]},
                "emotionRadar": {"labels": ["Joy","Anger","Sadness","Anxiety","Surprise"], "data": [0,0,0,0,0]},
                "highlights": [],
                "criticalFlags": [],
                "keywords": [],
                "emojiCloud": []
            })

        chat_history_json = json.dumps(chat_history, ensure_ascii=False)
        prompt_tpl = Template(
            """
You are assisting a clinician by analyzing a patient's chat conversation with an AI support assistant.
Output a single JSON object with EXACTLY these keys and shapes:

- "summary": string – a concise, professional summary (5-8 sentences) focusing on emotional state, risks, and guidance for clinician follow-up.

- "moodTimeline": object – line chart of mood over time
  {"labels": ["2025-08-09T10:01:00Z", "2025-08-09T11:07:00Z"], "data": [-0.2, 0.4]}

- "activity": object – messages per day
  {"labels": ["2025-08-08", "2025-08-09"], "data": [3, 7]}

- "urgencyDistribution": object – doughnut chart
  {"labels": ["Low","Medium","High"], "data": [70, 25, 5]}

- "emotionRadar": object – radar chart
  {"labels": ["Joy","Anger","Sadness","Anxiety","Surprise"], "data": [6, 2, 4, 5, 3]}

- "highlights": array of 5-10 key messages
  [{"message": "text", "reason": "why notable", "timestamp": "2025-08-09T10:01:00Z"}]

- "criticalFlags": array of messages needing attention (self-harm, suicidal ideation, panic, severe depression, withdrawal)
  [{"message": "text", "category": "Self-harm", "severity": 85, "timestamp": "2025-08-09T11:07:00Z"}]

- "keywords": array – common terms/phrases
  [{"term": "sleep", "count": 5}]

- "emojiCloud": array – emojis and counts
  [{"emoji": "😊", "count": 4}]

IMPORTANT:
- Return ONLY the JSON (no commentary, code fences, or markdown).
- If something is unavailable, return an empty array/object for that field.

Chat Conversation (oldest first):
$CHAT
"""
        )
        prompt = prompt_tpl.substitute(CHAT=chat_history_json)
        response = pro_model.generate_content(prompt)
        raw = response.text.strip()
        # Remove accidental code fences
        if raw.startswith('```'):
            raw = raw.strip('`')
            raw = raw.replace('json', '', 1).strip()
        analysis_data = json.loads(raw)
        db_ref.child("analysis").child(patient_uid).set(analysis_data)
        return jsonify(analysis_data)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "An error occurred during analysis."}), 500

@app.route('/send-direct-message/<patient_uid>', methods=['POST'])
def send_direct_message(patient_uid):
    if 'user' not in session or session.get('role') != 'doctor':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_info = admin_auth.verify_id_token(session['user'])
        doctor_uid = user_info['uid']
        if not is_doctor_linked_to_patient(doctor_uid, patient_uid):
            return jsonify({"error": "Access denied"}), 403
        message = sanitize_input(request.json.get('message', ''))
        if not message:
            return jsonify({"error": "Message cannot be empty"}), 400
        message_data = {"from": doctor_uid, "message": message, "timestamp": {".sv": "timestamp"}}
        db_ref.child("direct_messages").child(patient_uid).push(message_data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": "An error occurred while sending the message."}), 500

@app.route('/send-message-to-doctor', methods=['POST'])
def send_message_to_doctor():
    if 'user' not in session or session.get('role') != 'patient':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_info = admin_auth.verify_id_token(session['user'])
        patient_uid = user_info['uid']
        message = sanitize_input(request.json.get('message', ''))
        if not message:
            return jsonify({"error": "Message cannot be empty"}), 400
        # Lookup linked doctor
        user_record = db_ref.child("users").child(patient_uid).get() or {}
        doctor_uid = user_record.get('linkedDoctorUID')
        if not doctor_uid:
            return jsonify({"error": "No linked doctor found for this patient."}), 400
        # Store message in the same thread under patient's node
        db_ref.child("direct_messages").child(patient_uid).push({
            'from': patient_uid,
            'message': message,
            'timestamp': {'.sv': 'timestamp'}
        })
        return jsonify({"success": True})
    except Exception:
        return jsonify({"error": "An error occurred while sending the message."}), 500
@app.route('/get-direct-messages')
def get_direct_messages():
    if 'user' not in session or session.get('role') != 'patient':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_info = admin_auth.verify_id_token(session['user'])
        patient_uid = user_info['uid']
        # Be defensive: result can be dict keyed by push-id or a list
        raw = db_ref.child("direct_messages").child(patient_uid).get()
        message_list = []
        if isinstance(raw, dict):
            for _, msg in raw.items():
                if isinstance(msg, dict):
                    msg.setdefault('timestamp', 0)
                    message_list.append(msg)
        elif isinstance(raw, list):
            for msg in raw:
                if isinstance(msg, dict):
                    msg.setdefault('timestamp', 0)
                    message_list.append(msg)
        # Sort ascending by timestamp
        message_list.sort(key=lambda m: m.get('timestamp', 0))
        return jsonify(message_list)
    except Exception as e:
        return jsonify({"error": "An error occurred while fetching messages."}), 500


@app.route('/chat/history')
def get_chat_history():
    if 'user' not in session or session.get('role') != 'patient':
        return jsonify({"error": "Unauthorized"}), 401
    try:
        user_info = admin_auth.verify_id_token(session['user'])
        uid = user_info['uid']
        chat_history = db_ref.child("chats").child(uid).get() or []
        # Ensure array of {user, ai} objects
        if isinstance(chat_history, dict):
            # If stored as dict (by index), convert to list preserving order
            chat_history = [chat_history[k] for k in sorted(chat_history.keys(), key=lambda x: int(x) if str(x).isdigit() else x)]
        # Sanitize to only allow 'user' and 'ai' keys
        clean = []
        for item in chat_history:
            if isinstance(item, dict):
                clean.append({k: item.get(k) for k in ['user', 'ai'] if k in item})
        return jsonify(clean)
    except Exception:
        return jsonify({"error": "An error occurred while fetching chat history."}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
