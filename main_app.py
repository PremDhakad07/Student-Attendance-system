import os
import cv2
import face_recognition
import numpy as np
import mysql.connector
import glob
import hashlib
import time
from datetime import datetime
from flask import Flask, render_template, Response, request, redirect, url_for, session, jsonify
import webbrowser
import base64
import sys
import psutil # Required for robust process termination on Windows
import signal # Required for os.kill (though psutil is preferred for cross-platform)
import subprocess # Required for fallback taskkill on Windows (though psutil is preferred)

# --- MySQL Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'vitbpl2028',
    'database': 'project'
}

# --- Teacher Password Configuration ---
# The hash for the password 'vitbpl'
TEACHER_PASSWORD_HASH = '38c2f17ffe9cc7c7e78e962581b0e49b178f129b4e9af1a79b18d440c0338306'

# Time in seconds to wait before marking attendance for the same person again
MIN_TIME_BETWEEN_ATTENDANCE = 43200

# CORRECTED VALUE: The tolerance for face recognition. Lower is stricter.
# A value around 6 is typical. 4.5 is quite strict.
FACE_RECOGNITION_TOLERANCE = 0.5 #Don't change this value

app = Flask(__name__)
app.secret_key = 'your_super_secret_key'

# Add this line to increase the maximum request size to 16MB
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# --- Global variables for real-time attendance ---
camera = None
known_face_encodings = []
known_student_ids = []
known_student_names = []

def get_db_connection():
    """Establishes and returns a MySQL database connection."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def load_known_faces():
    """Loads face embeddings from the database for the attendance system."""
    global known_face_encodings, known_student_ids, known_student_names
    known_face_encodings.clear()
    known_student_ids.clear()
    known_student_names.clear()
    
    conn = get_db_connection()
    if not conn:
        print("Error: Could not connect to database to load known faces.")
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT registration_number, name, face_embedding FROM students")
        results = cursor.fetchall()
        
        for reg_no, name, embedding_blob in results:
            known_student_ids.append(reg_no)
            known_student_names.append(name)
            # Ensure the embedding is converted back to a numpy array
            embedding_array = np.frombuffer(embedding_blob, dtype=np.float64)
            known_face_encodings.append(embedding_array)
            
        print(f"Loaded {len(known_student_ids)} student faces from the database.")
        return True
    except mysql.connector.Error as err:
        print(f"Error loading faces from database: {err}")
        return False
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def mark_attendance(student_id):
    """
    Marks attendance for a given student ID in the database.
    Returns the attendance status string.
    """
    try:
        conn = get_db_connection()
        if not conn: return "DB Error"
        cursor = conn.cursor()
        
        cursor.execute("SELECT name, last_attendance_time FROM students WHERE registration_number = %s", (student_id,))
        result = cursor.fetchone()
        
        if not result:
            return "Not Registered"
            
        student_name, last_time_str = result
        
        can_mark = True
        if last_time_str:
            last_time = datetime.strptime(str(last_time_str), "%Y-%m-%d %H:%M:%S")
            seconds_elapsed = (datetime.now() - last_time).total_seconds()
            if seconds_elapsed < MIN_TIME_BETWEEN_ATTENDANCE:
                can_mark = False
        
        if can_mark:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            update_sql = "UPDATE students SET total_attendance = total_attendance + 1, last_attendance_time = %s WHERE registration_number = %s"
            cursor.execute(update_sql, (current_time, student_id))
            insert_sql = "INSERT INTO attendance (student_reg_no, check_in_time) VALUES (%s, %s)"
            cursor.execute(insert_sql, (student_id, current_time))
            
            conn.commit()
            print(f" Attendance marked for student: {student_id}")
            return "Marked"
        else:
            return "Already Marked"
            
    except mysql.connector.Error as err:
        print(f" Error marking attendance: {err}")
        return "DB Error"
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

def get_embedding_from_image(image_path):
    """Generates a face embedding from an image file."""
    try:
        image = face_recognition.load_image_file(image_path)
        face_encodings = face_recognition.face_encodings(image)
        if len(face_encodings) == 1:
            return face_encodings[0]
        else:
            return None
    except Exception as e:
        print(f"Error processing image: {e}")
        return None

def show_registered_students():
    students = []
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT registration_number, name, major, year, starting_year, total_attendance FROM students")
            students = cursor.fetchall()
        finally:
            if conn.is_connected():
                cursor.close()
                conn.close()
    return students


# --- Flask Routes ---
@app.route('/')
def main_menu():
    return render_template('main_menu.html')

@app.route('/attendance')
def attendance():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def gen_frames():
    """
    Generator function to create a live video stream with face recognition.
    """
    global camera
    if camera is None:
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            print("Error: Camera failed to open.")
            return

    while True:
        # Important: Check if the camera object is still valid before reading
        if camera is None or not camera.isOpened():
            print("Video stream stopped.")
            break
            
        success, frame = camera.read()
        if not success:
            break
        else:
            small_frame = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
            
            for face_encoding, face_location in zip(face_encodings, face_locations):
                display_name = "Unknown"
                display_reg_no = ""
                display_status = "Not Registered"
                frame_color = (0, 0, 255)
                
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                
                if face_distances.size > 0:
                    best_match_index = np.argmin(face_distances)
                    if face_distances[best_match_index] < FACE_RECOGNITION_TOLERANCE:
                        student_id = known_student_ids[best_match_index]
                        student_name = known_student_names[best_match_index]
                        
                        status = mark_attendance(student_id)
                        
                        display_name = student_name
                        display_reg_no = f"Reg No: {student_id}"
                        display_status = status
                        
                        if status == "Marked":
                            frame_color = (0, 255, 0)
                        elif status == "Already Marked":
                            frame_color = (0, 255, 255)
                
                y1, x2, y2, x1 = [v * 4 for v in face_location]
                cv2.rectangle(frame, (x1, y1), (x2, y2), frame_color, 2)
                cv2.putText(frame, display_name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, frame_color, 2)
                cv2.putText(frame, display_status, (x1, y2 + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, frame_color, 2)

            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# NEW ROUTE: This route will release the camera object
@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    global camera
    if camera:
        print("Releasing camera...")
        camera.release()
        camera = None
        return jsonify({'message': 'Camera stopped successfully'}), 200
    return jsonify({'message': 'Camera was not running'}), 200

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        password = request.form['password']
        entered_hash = hashlib.sha256(password.encode()).hexdigest()
        if entered_hash == TEACHER_PASSWORD_HASH:
            session['logged_in'] = True
            return redirect(url_for('teacher_menu'))
        else:
            return "Incorrect password.", 401
    return render_template('teacher_login.html')

@app.route('/teacher_menu')
def teacher_menu():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))
    return render_template('teacher_menu.html')

@app.route('/manage_students')
def manage_students():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))
    
    students = show_registered_students()
    return render_template('manage_students.html', students=students)

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))

    if request.method == 'POST':
        reg_no = request.form['reg_no']
        name = request.form['name']
        major = request.form['major']
        year = request.form['year']
        starting_year = request.form['starting_year']
        
        embedding = None
        temp_path = None
        
        # Option 1: Handle camera capture data
        if 'camera_image_data' in request.form and request.form['camera_image_data']:
            image_data_uri = request.form['camera_image_data']
            # Decode the base64 string
            image_data = base64.b64decode(image_data_uri.split(',')[1])
            temp_path = os.path.join("temp_uploads", f"{reg_no}.png")
            os.makedirs("temp_uploads", exist_ok=True)
            with open(temp_path, "wb") as f:
                f.write(image_data)
            embedding = get_embedding_from_image(temp_path)
            
        # Option 2: Handle file upload
        elif 'face_image' in request.files and request.files['face_image'].filename != '':
            file = request.files['face_image']
            temp_path = os.path.join("temp_uploads", file.filename)
            os.makedirs("temp_uploads", exist_ok=True)
            file.save(temp_path)
            embedding = get_embedding_from_image(temp_path)

        if embedding is None:
            # Clean up the temp file if it was created
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            return "Error: Could not find a single face in the image. Please try again.", 400

        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                sql = """
                    INSERT INTO students (registration_number, name, face_embedding, major, year, starting_year)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                cursor.execute(sql, (reg_no, name, embedding.tobytes(), major, year, starting_year))
                conn.commit()
                # Clean up the temp file after successful database insert
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                return redirect(url_for('manage_students'))
            except mysql.connector.Error as err:
                # Clean up the temp file if an error occurred
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                return f"Database error: {err}", 500
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

    return render_template('add_student.html')

@app.route('/edit_student/<string:reg_no>', methods=['GET', 'POST'])
def edit_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))
    
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor(dictionary=True)
        try:
            if request.method == 'POST':
                # Handle form submission to update student data
                name = request.form['name']
                major = request.form['major']
                year = request.form['year']
                starting_year = request.form['starting_year']

                update_sql = "UPDATE students SET name = %s, major = %s, year = %s, starting_year = %s WHERE registration_number = %s"
                cursor.execute(update_sql, (name, major, year, starting_year, reg_no))
                conn.commit()

                # Reload faces in case student data was updated
                load_known_faces()
                return redirect(url_for('manage_students'))
            
            else:
                # Handle GET request to show the edit form
                cursor.execute("SELECT * FROM students WHERE registration_number = %s", (reg_no,))
                student = cursor.fetchone()
                if student:
                    return render_template('edit_student.html', student=student)
                else:
                    return "Student not found", 404
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    return "Database connection error.", 500

@app.route('/delete_student/<string:reg_no>', methods=['POST'])
def delete_student(reg_no):
    if not session.get('logged_in'):
        return redirect(url_for('teacher_login'))
    
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Step 1: Delete all attendance records for this student first
            cursor.execute("DELETE FROM attendance WHERE student_reg_no = %s", (reg_no,))
            
            # Step 2: Now that child records are gone, delete the student
            cursor.execute("DELETE FROM students WHERE registration_number = %s", (reg_no,))
            conn.commit()

            # Reload faces to remove the deleted student's face embedding
            load_known_faces()
            return redirect(url_for('manage_students'))
        except mysql.connector.Error as err:
            print(f"Error during student deletion: {err}")
            return "An error occurred while trying to delete the student.", 500
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    return "Database connection error.", 500

# This is the route that shuts down the application
@app.route('/shutdown', methods=['POST'])
def shutdown():
    # Stop the child process first
    func = request.environ.get('werkzeug.server.shutdown')
    if func is not None:
        func()
    
    print("Server shutdown initiated. Attempting to terminate parent process...")
    
    parent_pid = os.getppid()
    try:
        parent = psutil.Process(parent_pid)
        if parent:
            parent.terminate() # Request termination
            parent.wait(timeout=3) # Wait for parent to terminate (optional timeout)
            print(f"Parent process with PID {parent_pid} terminated successfully using psutil.")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        print(f"Parent process with PID {parent_pid} not found or access denied. It may have already terminated.")
    except psutil.TimeoutExpired:
        print(f"Parent process with PID {parent_pid} did not terminate within timeout. Forcing kill.")
        try:
            parent.kill() # Force kill if terminate didn't work
            print(f"Parent process with PID {parent_pid} forcefully terminated.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            print(f"Could not forcefully terminate parent process with PID {parent_pid}.")
    except Exception as e:
        print(f"An unexpected error occurred during termination: {e}")
        
    print("Goodbye!") # Your goodbye message here

    # Now, exit the child process
    sys.exit(0)
    
    # This return statement will likely not be reached due to sys.exit(0)
    return "Server is shutting down..."

if __name__ == '__main__':
    # Only open the browser if this is the main process, not the reloader.
    # This prevents duplicate browser tabs when debug=True.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        print("Starting Flask server and opening browser...")
        # A small delay helps ensure the server is ready before the browser opens
        time.sleep(2)
        webbrowser.open('http://127.0.0.1:5000')

    # Load faces for the attendance system
    load_known_faces()
    
    # Run the Flask application with debug mode enabled
    app.run(host='0.0.0.0', debug=True)