from flask import Flask, render_template, Response, request, jsonify, session, redirect, url_for
import os
import sys
import importlib.util
import io
import contextlib
import logging
from dotenv import load_dotenv

# Determine the project root directory
# api/index.py is in /api, so root is one level up
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Prepend root to path so we can import local modules
sys.path.append(BASE_DIR)

# Import services
from scripts import analytics
from scripts import sips_service

# Load environment variables
env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

# Initialize Flask
app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

app.secret_key = os.environ.get("SECRET_KEY", "default-dev-key") # Change in PROD

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EnexAPI")

# === AUTHENTICATION ===
USER_CREDENTIALS = {
    "username": os.environ.get("APP_USERNAME"),
    "password": os.environ.get("APP_PASSWORD")
}

if not USER_CREDENTIALS["username"] or not USER_CREDENTIALS["password"]:
    logger.warning("⚠️ CREDENTIALS NOT SET: APP_USERNAME or APP_PASSWORD missing. Login disabled or insecure.")

@app.before_request
def require_login():
    allowed_routes = ['login', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'user' not in session:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check against env vars
        valid_user = USER_CREDENTIALS['username']
        valid_pass = USER_CREDENTIALS['password']
        
        if valid_user and valid_pass:
            if username == valid_user and password == valid_pass:
                session['user'] = username
                return redirect(url_for('index'))
            else:
                error = "Credenciales incorrectas"
        else:
             error = "Error de configuración de servidor (Credenciales no establecidas)"
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# === ROUTES ===

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/billing')
def billing():
    return render_template('billing.html')

@app.route('/ranking')
def ranking():
    return render_template('ranking.html')

@app.route('/sips')
def sips_page():
    return render_template('sips.html')

# === API ENDPOINTS (Delegated to Services) ===

@app.route('/api/billing-data')
def billing_data():
    result = analytics.get_billing_data(BASE_DIR)
    return jsonify(result)

@app.route('/api/ranking-data')
def ranking_data():
    result = analytics.get_ranking_data(BASE_DIR)
    return jsonify(result)

@app.route('/api/sips/search', methods=['POST'])
def sips_search_api():
    data = request.get_json()
    cups = data.get('cups')
    
    result, status_code = sips_service.search_cups_data(cups)
    return jsonify(result), status_code

# === SCRIPT EXECUTION (Legacy/Admin) ===

@app.route('/run/<script_name>')
def run_script(script_name):
    ALLOWED_SCRIPTS = ['omie_holded.py', 'divakia_atr.py', 'facturas_emitidas.py', 'sync_holded_sales.py', 'sync_divakia_sales.py']
    
    if script_name not in ALLOWED_SCRIPTS:
        return f"Error: {script_name} is not allowed.", 403

    return Response(generate_output(script_name), mimetype='text/plain')

@app.route('/run-upload/<script_name>', methods=['POST'])
def run_upload_script(script_name):
    ALLOWED_SCRIPTS = ['omie_holded.py', 'divakia_atr.py', 'facturas_emitidas.py', 'sync_holded_sales.py', 'sync_divakia_sales.py']
    
    if script_name not in ALLOWED_SCRIPTS:
        return f"Error: {script_name} is not allowed.", 403

    if 'file' not in request.files:
        return "Error: No file part", 400
        
    file = request.files['file']
    if file.filename == '':
        return "Error: No selected file", 400

    if file:
        temp_dir = "/tmp"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir, exist_ok=True)
            
        filename = file.filename
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        os.environ['INPUT_FILE_PATH'] = file_path
        
        return Response(generate_output(script_name), mimetype='text/plain')

def generate_output(script_name):
    script_path = os.path.join(BASE_DIR, 'scripts', script_name)
    
    if not os.path.exists(script_path):
        yield f"Error: Script {script_name} not found.\n"
        return

    yield f"Iniciando {script_name}...\n"
    
    scripts_dir = os.path.dirname(script_path)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    output_capture = io.StringIO()
    
    try:
        spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
        module = importlib.util.module_from_spec(spec)
        
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            try:
                spec.loader.exec_module(module)
                if hasattr(module, 'main'):
                    module.main()
                else:
                    print("⚠️ Script execution: main() function not found.")
            except SystemExit:
                pass
            except Exception as e:
                print(f"Error executing script: {e}")
                import traceback
                traceback.print_exc()
        
        yield output_capture.getvalue()
        yield "\n[EXITO] Proceso finalizado."

    except Exception as e:
        yield f"\n[CRITICAL FAIL] {str(e)}"
    finally:
        output_capture.close()

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)
