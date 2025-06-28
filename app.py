from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import google.generativeai as genai
import re
import requests
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from werkzeug.utils import secure_filename
from datetime import datetime
from docx import Document
import io

def extract_docx_text(file):
    try:
        doc = Document(io.BytesIO(file.read()))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return text[:8000]  
    except Exception as e:
        return f"[Error reading .docx file: {str(e)}]"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = 'super-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)

class DailyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.String(20))  
    medications_done = db.Column(db.Boolean, default=False)
    water_intake = db.Column(db.Integer)
    exercise_done = db.Column(db.Boolean, default=False)
    sleep_good = db.Column(db.Boolean, default=False)

    patient = db.relationship("User", backref="daily_logs")

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100))
    filename = db.Column(db.String(200))
    upload_date = db.Column(db.String(50))

    patient = db.relationship("User", backref="reports")


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fullname = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)  
    specialization = db.Column(db.String(200))
    profile_pic_url = db.Column(db.String(300))
    phone_number = db.Column(db.String(50))
    experience_years = db.Column(db.Integer)
    notifications = db.Column(db.String(50))

    
    age = db.Column(db.Integer)
    gestational_age = db.Column(db.Integer)
    trimester = db.Column(db.String(10))
    due_date = db.Column(db.String(20))
    risk_status = db.Column(db.String(20))
    weight = db.Column(db.Float)
    blood_pressure = db.Column(db.String(20))
    blood_sugar = db.Column(db.Float)

# create appointment table 
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    date = db.Column(db.String(20))
    time = db.Column(db.String(20))
    reason = db.Column(db.String(200))

    patient = db.relationship("User", foreign_keys=[patient_id], backref="appointments_made")
    doctor = db.relationship("User", foreign_keys=[doctor_id], backref="appointments_received")

# for booking appointments
@app.route('/book-appointment', methods=['POST'])
def book_appointment():
    patient_id = request.form.get('patient_id')
    doctor_id = request.form.get('doctor_id')
    date = request.form.get('date')
    time = request.form.get('time')
    reason = request.form.get('reason')

    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        date=date,
        time=time,
        reason=reason
    )
    db.session.add(appointment)
    db.session.commit()
    flash("Appointment booked successfully!", "success")
    return redirect(url_for('patient_dashboard'))


with app.app_context():
    db.create_all()

# direct to the landing page
@app.route('/')
def home():
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        submit_type = request.form.get('submit')
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if submit_type == 'Sign Up':
            fullname = request.form.get('fullname')
            role = request.form.get('role')

            specialization = request.form.get('specialization') if role == 'Doctor' else None
            profile_pic_url = request.form.get('profile_pic_url') if role == 'Doctor' else None
            phone_number = request.form.get('phone_number') if role == 'Doctor' else None
            experience_years = request.form.get('experience_years') if role == 'Doctor' else None

            if user:
                flash(" Email already registered.", "error")

            else:

                hashed_pw = generate_password_hash(password)
                new_user = User(
                    fullname=fullname,
                    email=email,
                    password=hashed_pw,
                    role=role,
                    specialization=specialization,
                    profile_pic_url=profile_pic_url,
                    phone_number=phone_number,
                    experience_years=int(experience_years) if experience_years else None
                )
                db.session.add(new_user)
                db.session.commit()
                flash("Registration successful. Please log in.", "success")
                return redirect(url_for('login'))

        elif submit_type == 'Login':
            if user and check_password_hash(user.password, password):
                flash(f"Welcome {user.role} {user.fullname}!", "success")
                session["user_id"] = user.id
                session["user_role"] = user.role
                if user.role == 'Doctor':
                    return redirect(url_for('doctor_dashboard'))
                elif user.role == 'Patient':
                    return redirect(url_for('patient_dashboard'))
                else:
                    flash("Unknown role!", "error")
            else:
                flash("Invalid credentials.", "error")

    return render_template('login.html')

# direct you to the doct dashboard
@app.route('/doctor')
def doctor_dashboard():
    if session.get("user_role") != "Doctor":
        flash("Access denied. Please log in as Doctor.", "error")
        return redirect(url_for("login"))

    user_id = session.get("user_id")
    doctor = User.query.get(user_id)

    patients = User.query.filter_by(role="Patient").all()

    appointments = Appointment.query.filter_by(doctor_id=doctor.id).all()

    return render_template("doctor.html", doctor=doctor, patients=patients, appointments=appointments)

# direct to the patient dashboard
from datetime import datetime  # Make sure this is at the top of your file

@app.route('/patient')
def patient_dashboard():
    user_id = session.get('user_id')
    if not user_id:
        flash("Please login first.", "error")
        return redirect(url_for('login'))

    patient = User.query.filter_by(id=user_id, role='Patient').first()
    doctors = User.query.filter_by(role='Doctor').all()

    # ✅ Fetch today's health log (this is what was missing)
    today = datetime.now().strftime("%Y-%m-%d")
    daily_log = DailyLog.query.filter_by(patient_id=user_id, date=today).first()

    # ✅ Pass daily_log to the template
    return render_template('patient.html', patient=patient, doctors=doctors, daily_log=daily_log)


# signin as a patient
@app.route('/update-profile', methods=['POST'])
def update_profile():
    if session.get("user_role") != "Patient":
        return redirect(url_for("login"))

    patient = User.query.get(session["user_id"])

    patient.fullname = request.form.get("fullname") or patient.fullname
    patient.age = request.form.get("age") or patient.age
    patient.gestational_age = request.form.get("gestational_age") or patient.gestational_age
    patient.trimester = request.form.get("trimester") or patient.trimester
    patient.due_date = request.form.get("due_date") or patient.due_date
    patient.risk_status = request.form.get("risk_status") or patient.risk_status

    db.session.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for("patient_dashboard"))


@app.route('/update-health', methods=['POST'])
def update_health():
    if session.get("user_role") != "Patient":
        return redirect(url_for("login"))

    patient = User.query.get(session["user_id"])

    patient.weight = request.form.get("weight") or patient.weight
    patient.blood_pressure = request.form.get("blood_pressure") or patient.blood_pressure
    patient.blood_sugar = request.form.get("blood_sugar") or patient.blood_sugar

    db.session.commit()
    flash("Health data updated successfully!", "success")
    return redirect(url_for("patient_dashboard"))


# logout 
@app.route('/logout')
def logout():
    session.clear()  
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))

# this funtc is for appointments
@app.route('/update-appointment-status', methods=['POST'])
def update_appointment_status():
    if session.get("user_role") != "Doctor":
        flash("Access denied.", "error")
        return redirect(url_for('login'))

    appt_id = request.form.get("appointment_id")
    status = request.form.get("status")

    appointment = Appointment.query.get(appt_id)
    if appointment:
        appointment.status = status
        db.session.commit()
        flash(f"Appointment {status.lower()} successfully.", "success")
    else:
        flash("Appointment not found.", "error")

    return redirect(url_for('doctor_dashboard'))

# gets or fetch the patient data form the db 
@app.route('/api/patient/<int:patient_id>/health')
def get_patient_health(patient_id):
    patient = User.query.filter_by(id=patient_id, role='Patient').first()
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    health_data = {
        "blood_pressure": patient.blood_pressure if hasattr(patient, 'blood_pressure') else "120/80",
        "blood_sugar": patient.blood_sugar if hasattr(patient, 'blood_sugar') else 95,
        "weight": patient.weight if hasattr(patient, 'weight') else 68.0,
    }
    return jsonify(health_data)

# upload the reports
@app.route('/upload-report', methods=['POST'])
def upload_report():
    user_id = session.get("user_id")
    patient = User.query.get(user_id)

    if 'report_file' not in request.files:
        logging.warning(f"[UPLOAD] Patient {user_id} submitted upload with no file.")
        flash("No file part in the form", "error")
        return redirect(url_for('patient_dashboard'))

    file = request.files['report_file']
    title = request.form.get('title')

    if file.filename == '':
        logging.warning(f"[UPLOAD] Patient {user_id} submitted with empty filename.")
        flash("No selected file", "error")
        return redirect(url_for('patient_dashboard'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        full_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(full_path)

        report = Report(
            patient_id=user_id,
            title=title,
            filename=filename,
            upload_date=datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        db.session.add(report)
        db.session.commit()

        logging.info(f"[UPLOAD] Patient {patient.fullname} (ID: {user_id}) uploaded '{filename}' titled '{title}'")
        flash("Report uploaded successfully!", "success")
    else:
        logging.error(f"[UPLOAD] Patient {user_id} tried to upload invalid file: {file.filename}")
        flash("Invalid file type. Please upload PDF or DOC.", "error")

    return redirect(url_for('patient_dashboard'))
# Analysing the uploaded reports
@app.route('/api/patient/<int:patient_id>/history')
def get_patient_history(patient_id):
    patient = User.query.get(patient_id)
    if not patient:
        return jsonify({"error": "Patient not found"}), 404

    # Placeholder: in future, fetch real historical data
    systolic_bp = int(patient.blood_pressure.split('/')[0]) if patient.blood_pressure else 120
    sugar = int(patient.blood_sugar) if patient.blood_sugar else 90

    return jsonify({
        "bp": [systolic_bp - 5, systolic_bp, systolic_bp + 2],
        "sugar": [sugar - 5, sugar, sugar + 3]
    })
@app.route('/update-health-log', methods=['POST'])
def update_health_log():
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))

    today = datetime.now().strftime("%Y-%m-%d")
    log = DailyLog.query.filter_by(patient_id=user_id, date=today).first()

    if not log:
        log = DailyLog(patient_id=user_id, date=today)

    log.medications_done = bool(request.form.get('medications_done'))
    log.water_intake = int(request.form.get('water_intake') or 0)
    log.exercise_done = bool(request.form.get('exercise_done'))
    log.sleep_good = bool(request.form.get('sleep_good'))

    db.session.add(log)
    db.session.commit()

    flash("Health log saved for today.", "success")
    return redirect(url_for('patient_dashboard'))


@app.route('/analyze-chat', methods=['POST'])
def analyze_chat():
    file = request.files.get('file')
    message = request.form.get('message')
    prompt = ""

    if file:
        try:
            if file.filename.endswith('.docx'):
                content = extract_docx_text(file)
            else:
                content = file.read().decode('utf-8', errors='ignore')[:8000]   # works for .txt/.doc, not PDF
            prompt += f"User uploaded a report:\n{content}\n"
        except Exception as e:
            return jsonify({'reply': f'Error reading file: {str(e)}'})

    if message:
        prompt += f"\nUser message: {message}"
    if len(prompt) > 8000:
        prompt = prompt[:8000] + "\n\n[Note: The report was too long. Some content was truncated.]"
    if not prompt.strip():
        return jsonify({'reply': 'No input received.'})

    try:
        reply = chat.send_message(prompt).text
    except Exception as e:
        return jsonify({'reply': f'Assistant error: {str(e)}'})

    return jsonify({'reply': reply})



UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if not exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


API_KEY = "GEMINI_API"
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
chat = model.start_chat()

chat.send_message(
"""
your name is MatraAi
You are a maternity care assistant AI and you only have to work around maternity do not response other responses.
keep english as default
Your only job is to help pregnant women with trusted, real medical advice.

Help pregnant women in their own language (Hindi,Marathi etc.), based on what language they use.

You respond to:
- Blood pressure, blood sugar, pain, nausea, bleeding, anxiety, dizziness
- Diet, fetal movement, sleep, water intake, breathing
- Emergency warning signs

When a user shares a symptom:
- Give 1–2 helpful **remedies or medicines** (if safe, like paracetamol, iron, folic acid, etc.)
- OR tell them to **call the doctor immediately** if it's serious

Do NOT:
- Make jokes
- Say things like "I'm an AI" or "I don't know"
- Talk about unrelated stuff

Use a serious, warm tone. Every response should be short, clear, and patient-friendly.
Examples:

User: I have a headache and blurry vision  
Bot: These could be signs of high BP or preeclampsia. Contact your doctor immediately.

User: I have light cramps in the evening  
Bot: Mild cramps are common. Drink warm water. If it worsens, ask your doctor.

User: I feel dizzy in the morning  
Bot: You might be low on sugar or iron. Eat something light and rest. If it keeps happening, tell your doctor.
"""
)

@app.route('/update_settings', methods=['POST'])
def update_settings():
    if session.get("user_role") != "Doctor":
        flash("Access denied.", "error")
        return redirect(url_for('login'))

    doctor = User.query.get(session["user_id"])
    

    doctor.fullname = request.form.get('fullname')
    doctor.email = request.form.get('email')
    doctor.notifications = request.form.get('notifications')

    db.session.commit()
    session['doctor_name'] = doctor.fullname
    session['doctor_email'] = doctor.email

    flash('Settings updated successfully!', 'success')
    return redirect(url_for('doctor_dashboard'))


# ========== SOS System ==========
sos_messages = []

@app.route('/api/sos', methods=['POST'])
def sos():
    data = request.get_json()
    print("SOS Received:", data)
    sos_messages.append(data)
    return {"message": "Doctor notified"}, 200

@app.route('/api/sos-feed', methods=['GET'])
def sos_feed():
    return jsonify(sos_messages)

# ========== Chat Endpoint ==========
chat_history = []


@app.route('/api/send', methods=['POST'])
def receive_message():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"reply": "Unauthorized"}), 401

    patient = User.query.filter_by(id=user_id, role='Patient').first()
    if not patient:
        return jsonify({"reply": "Patient not found"}), 404

    message = request.get_json().get("message")

    sys_bp, dia_bp = extract_bp(message)
    bp_status = check_bp_status(sys_bp, dia_bp)

    sos_triggered = False
    if bp_status in ["high", "low"]:
        sos_triggered = True
        bp_str = f"{sys_bp}/{dia_bp if dia_bp else '--'}"
        send_realtime_sos(patient.fullname, bp_str, bp_status)

    response = chat.send_message(message)
    reply = response.text

    return jsonify({
        "reply": reply,
        "sos": sos_triggered
    })


def extract_bp(text):
    numbers = re.findall(r'\d{2,3}', text)
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
    elif len(numbers) == 1:
        return int(numbers[0]), None
    return None, None

# ========== BP Status Check 
def check_bp_status(sys_bp, dia_bp):
    if sys_bp is None:
        return "normal"
    if sys_bp < 90 or (dia_bp is not None and dia_bp < 60):
        return "low"
    elif sys_bp > 140 or (dia_bp is not None and dia_bp > 90):
        return "high"
    return "normal"

def check_sugar_status(sugar):
    try:
        sugar = float(sugar)
        if sugar < 70:
            return "low"
        elif sugar > 140:
            return "high"
    except:
        pass
    return "normal"

# ========== SOS Sender ==========
def send_realtime_sos(patient_name, bp, status):
    payload = {
        "patient": patient_name,
        "bp": bp,
        "status": status,
        "message": f"{status.upper()} BP ALERT: {bp} for patient {patient_name}"
    }
    try:
        requests.post("http://localhost:5000/api/sos", json=payload)
    except Exception as e:
        print("Failed to send SOS:", e)

# ================= Run Flask App =================

if __name__ == '__main__':
    app.run(debug=True)
