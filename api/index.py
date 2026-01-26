from flask import Flask, render_template, Response, request, jsonify
import requests
import base64
import time
import subprocess
import os
import sys
import json
from datetime import datetime, timedelta

# Determine the project root directory
# api/index.py is in /api, so root is one level up
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Prepend root to path so we can import local modules if needed (though we are moving everything here)
sys.path.append(BASE_DIR)

# Initialize Flask with explicit folder paths relative to api/index.py
app = Flask(__name__, 
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

# Helper to execute script and stream output
import importlib.util
import io
import contextlib

# Helper to execute script and stream output (In-Process)
def generate_output(script_name):
    # Updated to look in scripts/ folder using BASE_DIR
    script_path = os.path.join(BASE_DIR, 'scripts', script_name)
    
    if not os.path.exists(script_path):
        yield f"Error: Script {script_name} not found at {script_path}.\n"
        return

    # In-process execution to avoid subprocess issues on Vercel
    yield f"Iniciando {script_name} (in-process)...\n"
    
    # Add scripts dir to sys.path so internal imports (like `import common`) work
    scripts_dir = os.path.dirname(script_path)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        
    # Capture Stdout
    output_capture = io.StringIO()
    
    try:
        # Load Module Dynamically
        spec = importlib.util.spec_from_file_location("dynamic_script", script_path)
        module = importlib.util.module_from_spec(spec)
        
        # Redirect stdout/stderr
        with contextlib.redirect_stdout(output_capture), contextlib.redirect_stderr(output_capture):
            try:
                spec.loader.exec_module(module)
                
                # Check if it has a main() function
                if hasattr(module, 'main'):
                    module.main()
                else:
                    print("⚠️ El script no tiene una función main(). Ejecutando nivel módulo solamente.")
                    
            except SystemExit as e:
                print(f"Script finalizó con SystemExit: {e}")
            except Exception as e:
                print(f"Error ejecutando script: {e}")
                import traceback
                traceback.print_exc()
        
        # Yield result
        yield output_capture.getvalue()
        yield "\n[EXITO] Proceso finalizado."

    except Exception as e:
        yield f"\n[EXCEPCION CRITICA] Fallo al cargar el script: {str(e)}"
    finally:
        output_capture.close()

@app.route('/debug-files')
def debug_files():
    output = []
    output.append(f"Current Working Directory: {os.getcwd()}")
    output.append(f"Base Directory: {BASE_DIR}")
    output.append("--- Recursive File Listing ---")
    
    for root, dirs, files in os.walk(BASE_DIR):
        for name in files:
            path = os.path.join(root, name)
            rel_path = os.path.relpath(path, BASE_DIR)
            size = os.path.getsize(path)
            output.append(f"{rel_path} ({size} bytes)")
            
    return "<pre>" + "\n".join(output) + "</pre>"

# === AUTHENTICATION ===
app.secret_key = os.environ.get("SECRET_KEY", "super_secret_key_123") # USE ENV VAR IN PROD
USER_CREDENTIALS = {
    "username": os.environ.get("APP_USERNAME", "Alvaro"),
    "password": os.environ.get("APP_PASSWORD", "123456")
}

from flask import session, redirect, url_for

@app.before_request
def require_login():
    allowed_rutes = ['login', 'static']
    if request.endpoint and request.endpoint not in allowed_rutes and 'user' not in session:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Simple check
        if username and username.lower() == USER_CREDENTIALS['username'].lower() and password == USER_CREDENTIALS['password']:
            session['user'] = USER_CREDENTIALS['username']
            return redirect(url_for('index'))
        else:
            error = "Credenciales incorrectas"
            
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/run/<script_name>')
def run_script(script_name):
    # Security check: only allow specific scripts to be run to prevent command injection
    ALLOWED_SCRIPTS = ['omie_holded.py', 'divakia_atr.py', 'facturas_emitidas.py', 'test_debug.py', 'sync_holded_sales.py', 'sync_divakia_sales.py']
    
    if script_name not in ALLOWED_SCRIPTS:
        return f"Error: {script_name} is not allowed.", 403

    return Response(generate_output(script_name), mimetype='text/plain')

@app.route('/run-upload/<script_name>', methods=['POST'])
def run_upload_script(script_name):
    # Security check
    ALLOWED_SCRIPTS = ['omie_holded.py', 'divakia_atr.py', 'facturas_emitidas.py', 'test_debug.py', 'sync_holded_sales.py', 'sync_divakia_sales.py']
    
    if script_name not in ALLOWED_SCRIPTS:
        return f"Error: {script_name} is not allowed.", 403

    if 'file' not in request.files:
        return "Error: No file part", 400
        
    file = request.files['file']
    if file.filename == '':
        return "Error: No selected file", 400

    if file:
        # Save to /tmp (Vercel writable dir)
        temp_dir = "/tmp"
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir, exist_ok=True)
            
        filename = file.filename
        # Sanitize filename if needed, but for now trust internal usage
        file_path = os.path.join(temp_dir, filename)
        file.save(file_path)
        
        # Set ENV var for the script to pick up
        os.environ['INPUT_FILE_PATH'] = file_path
        
        # Generator wrapper to clean up env/file?
        # Ideally we restore env, but for now just running it is fine.
        
        return Response(generate_output(script_name), mimetype='text/plain')

@app.route('/billing')
def billing():
    return render_template('billing.html')

@app.route('/ranking')
def ranking():
    return render_template('ranking.html')

@app.route('/api/billing-data')
def billing_data():
    try:
        # Changed to Divakia Data, using BASE_DIR
        data_path = os.path.join(BASE_DIR, 'divakia_sales_data.json')
        if not os.path.exists(data_path):
            return {"labels": [], "values": [], "last_sync": "No data found"}
        
        with open(data_path, 'r', encoding='utf-8') as f:
            invoices = json.load(f)
            
        # Aggregate by month
        # Aggregate by month
        monthly_sales = {}
        monthly_consumption = {}
        
        # We also want to return the raw list, perhaps sorted by date
        # Parse dates for sorting
        for inv in invoices:
            date_str = inv.get('date')
            if not date_str:
                continue
            try:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
                inv['_dt'] = dt # temporary for sorting
            except ValueError:
                inv['_dt'] = datetime.min

        # Sort descending
        invoices.sort(key=lambda x: x.get('_dt'), reverse=True)

        for inv in invoices:
            dt = inv.get('_dt')
            if dt == datetime.min:
                continue
                
            month_key = dt.strftime('%Y-%m')
            
            # Sum up 'total' and 'consumption'
            amount = inv.get('total', 0)
            consumo = inv.get('consumption', 0)
            
            monthly_sales[month_key] = monthly_sales.get(month_key, 0) + amount
            monthly_consumption[month_key] = monthly_consumption.get(month_key, 0) + consumo
            
        # Sort by month for chart
        sorted_keys = sorted(monthly_sales.keys())
        labels = sorted_keys
        values = [monthly_sales[k] for k in sorted_keys]
        consumption_values = [monthly_consumption.get(k, 0) for k in sorted_keys]
        
        # Calculate Accumulated Data
        acc_values = []
        acc_consumption = []
        running_total = 0
        running_consumption = 0
        
        for v, c in zip(values, consumption_values):
            running_total += v
            running_consumption += c
            acc_values.append(running_total)
            acc_consumption.append(running_consumption)
        
        return {
            "labels": labels,
            "values": values,
            "consumption": consumption_values,
            "accumulated_values": acc_values,
            "accumulated_consumption": acc_consumption,
            "invoices": invoices, # Return full list for table
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        }
            
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/ranking-data')
def ranking_data():
    try:
        # 1. Load Competitors using BASE_DIR
        ranking_path = os.path.join(BASE_DIR, 'competitors_ranking.json')
        if not os.path.exists(ranking_path):
            return {"error": "Ranking data not found"}, 404
            
        with open(ranking_path, 'r', encoding='utf-8') as f:
            competitors = json.load(f)
            
        # 2. Load User Data using BASE_DIR
        user_data_path = os.path.join(BASE_DIR, 'divakia_sales_data.json')
        user_invoices = []
        if os.path.exists(user_data_path):
             with open(user_data_path, 'r', encoding='utf-8') as f:
                user_invoices = json.load(f)

        # 3. Process Invoices into Monthly Buckets
        monthly_map = {}
        min_date = datetime.now()
        max_date = datetime.min
        
        has_data = False
        
        for inv in user_invoices:
            try:
                kwh = inv.get('consumption', 0)
                date_str = inv.get('date')
                if date_str:
                    dt = datetime.strptime(date_str, "%d/%m/%Y")
                    # Track min/max for timeline
                    if dt < min_date: min_date = dt
                    if dt > max_date: max_date = dt
                    has_data = True
                    
                    month_key = dt.strftime('%Y-%m')
                    monthly_map[month_key] = monthly_map.get(month_key, 0) + kwh
            except:
                pass
                
        if not has_data:
            # Fallback if no invoices
            min_date = datetime.now()
            max_date = datetime.now()

        # 4. Generate Continuous Timeline (Month by Month)
        # Normalize min_date to start of month
        current_dt = min_date.replace(day=1)
        # Normalize max_date to start of month
        end_dt = max_date.replace(day=1)
        
        timeline_months = []
        # Safety limit for loop
        loop_limit = 0
        while current_dt <= end_dt and loop_limit < 1000:
            timeline_months.append(current_dt.strftime('%Y-%m'))
            # Add one month
            next_month = current_dt.month % 12 + 1
            next_year = current_dt.year + (current_dt.month // 12)
            current_dt = current_dt.replace(year=next_year, month=next_month)
            loop_limit += 1
            
        # 5. Calculate Rolling 12M for each point in timeline
        evolution_labels = []
        evolution_gwh = []
        evolution_rank = []
        
        for i, month_str in enumerate(timeline_months):
            # Calculate window: [month_str and previous 11 months]
            # Since timeline is continuous, we can just look back 11 indices
            window_sum = 0
            start_idx = max(0, i - 11)
            
            for j in range(start_idx, i + 1):
                m = timeline_months[j]
                window_sum += monthly_map.get(m, 0)
            
            # Convert to GWh
            rolling_val = window_sum / 1_000_000
            
            # Find Simulated Rank (User Rolling vs Approx Competitor Static)
            better_competitors = [c for c in competitors if c.get('sales_2024', 0) > rolling_val]
            rank = len(better_competitors) + 1
            
            evolution_labels.append(month_str)
            evolution_gwh.append(rolling_val)
            evolution_rank.append(rank)

        # 6. Current Metrics (Last point in evolution should be "Current Rolling 12M")
        current_gwh = evolution_gwh[-1] if evolution_gwh else 0
        current_rank = evolution_rank[-1] if evolution_rank else 0
        
        # 2023 Metric (Fixed Calendar Year Sum)
        sales_2023 = 0
        for m_key, val in monthly_map.items():
            if m_key.startswith('2023'):
                sales_2023 += val
        gwh_2023 = sales_2023 / 1_000_000
        
        # Change %
        pct_change = 0
        if gwh_2023 > 0:
            pct_change = ((current_gwh - gwh_2023) / gwh_2023) * 100
        elif current_gwh > 0:
            pct_change = 100.0

        # 7. Insert User into Ranking Table
        user_entry = {
            "name": "ENEX (Tu Empresa)",
            "sales_gwh": current_gwh,
            "sales_2024": current_gwh, # Display rolling 12m
            "sales_2023": gwh_2023,
            "change_pct": round(pct_change, 2),
            "is_user": True,
            "rank": 0 # Will be calc below
        }
        
        all_entities = competitors + [user_entry]
        all_entities.sort(key=lambda x: x.get('sales_2024', 0), reverse=True)
        
        final_ranking = []
        user_rank_table = 0
        
        for i, entity in enumerate(all_entities):
            rank = i + 1
            entity['rank'] = rank
            final_ranking.append(entity)
            if entity.get('is_user'):
                user_rank_table = rank

        return {
            "user_stats": {
                "rank": user_rank_table,
                "gwh": current_gwh,
                "gwh_prev": gwh_2023,
                "change_pct": pct_change,
                "total_competitors": len(competitors)
            },
            "ranking_table": final_ranking, 
            "evolution": {
                "labels": evolution_labels,
                "gwh": evolution_gwh,
                "rank": evolution_rank
            }
        }


    except Exception as e:
        return {"error": str(e)}, 500

# --- SIPS / Orka Logic ---

# --- Environment Setup ---
from dotenv import load_dotenv

# Load environment variables from .env file securely
env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    try:
        load_dotenv(env_path)
    except Exception as e:
        print(f"Warning: Failed to load .env file: {e}")

orka_token_cache = {
    "token": None,
    "expires_at": 0
}

def get_orka_token():
    now = time.time()
    if orka_token_cache["token"] and orka_token_cache["expires_at"] > now:
        return orka_token_cache["token"]

    username = os.environ.get("ORKA_USER")
    password = os.environ.get("ORKA_PASSWORD")

    if not username or not password:
        raise Exception("Credenciales ORKA no configuradas en .env")

    # Orka requires base64 encoded credentials in body
    user_b64 = base64.b64encode(username.encode()).decode()
    pass_b64 = base64.b64encode(password.encode()).decode()

    # Changed from manual string formatting to dictionary to ensure proper URL encoding
    # of base64 characters (like + and =)
    payload = {
        "user": user_b64,
        "password": pass_b64
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    resp = requests.post("https://www.orkamanager.com/orkapi/login", data=payload, headers=headers)
    
    if not resp.ok:
        raise Exception(f"Login fallido: {resp.text}")

    data = resp.json()
    if not data.get("access_token"):
        raise Exception("Token no recibido en login")

    # Helper for safety
    expires_in = data.get("expires_in", 86400)
    
    orka_token_cache["token"] = data["access_token"]
    orka_token_cache["expires_at"] = now + (expires_in / 1000) - 60 
    
    return orka_token_cache["token"]

@app.route('/sips')
def sips_page():
    return render_template('sips.html')

@app.route('/api/sips/search', methods=['POST'])
def sips_search_api():
    try:
        data = request.get_json()
        cups = data.get('cups')
        
        if not cups:
            return jsonify({"error": "CUPS no proporcionado"}), 400

        token = get_orka_token()
        
        url = f"https://www.orkamanager.com/orkapi/cups/{cups}"
        headers = {
           "Authorization": f"Bearer {token}",
           "User-Agent": "Enex-Control-Center/1.0" 
        }
        
        resp = requests.get(url, headers=headers)
        
        if resp.status_code == 404:
             return jsonify({"error": "CUPS no encontrado"}), 404
             
        if not resp.ok:
            return jsonify({"error": f"Error upstream: {resp.text}"}), resp.status_code
            
        raw_data = resp.json()
        
        # --- Porting Logic from index.ts ---
        
        # 1. Extract Consumptions
        consumos = []
        consumo_anual_periodo = {}
        penalizaciones_reactiva = {}
        total_consumos = {
            "consumo_total_kWh": 0,
            "consumo_anual_kWh": 0,
            "consumo_anual_porcentaje": 0
        }
        
        # Gather all consumption sources
        sources = [
            raw_data.get('puntos_suministro', []),
            raw_data.get('consumos', []),
            raw_data.get('consumos_historicos', []),
            raw_data.get('lecturas', [])
        ]
        
        all_consumos_data = []
        # Handle puntos_suministro separately as it wraps consumos
        if isinstance(sources[0], list):
             for p in sources[0]:
                 if isinstance(p.get('consumos'), list):
                     all_consumos_data.extend(p['consumos'])

        # Add others
        for s in sources[1:]:
             if isinstance(s, list):
                 all_consumos_data.extend(s)

        # Process
        for c in all_consumos_data:
            fecha_inicio = c.get('fecha_lectura_inicio') or c.get('fecha_desde') or c.get('fecha')
            fecha_fin = c.get('fecha_lectura_fin') or c.get('fecha_hasta') or c.get('fecha')
            
            # Active Energy
            energia_data = c.get('energia_activa_kWh') or c.get('energia_activa') or c.get('consumo_periodos') or {}
            if not isinstance(energia_data, dict): 
                # Sometimes it might not be a dict?
                energia_data = {}

            consumo_total_record = 0
            consumo_detallado = {}
            
            for periodo, valor in energia_data.items():
                val_num = 0
                if isinstance(valor, str):
                    try: val_num = float(valor.replace(',', '.'))
                    except: val_num = 0
                elif isinstance(valor, (int, float)):
                    val_num = valor
                
                if val_num > 0:
                    consumo_total_record += val_num
                    consumo_detallado[periodo] = val_num
                    consumo_anual_periodo[periodo] = consumo_anual_periodo.get(periodo, 0) + val_num

            # Reactive Penalties
            pen_data = c.get('penalizacion_reactiva_euros') or c.get('penalizaciones') or {}
            pen_record = {}
            if isinstance(pen_data, dict):
                for p, v in pen_data.items():
                     val_num = 0
                     if isinstance(v, str):
                        try: val_num = float(v.replace(',', '.'))
                        except: val_num = 0
                     elif isinstance(v, (int, float)):
                        val_num = v
                     
                     if val_num > 0:
                         pen_record[p] = val_num
                         penalizaciones_reactiva[p] = penalizaciones_reactiva.get(p, 0) + val_num

            if consumo_total_record > 0:
                total_consumos["consumo_total_kWh"] += consumo_total_record
                consumos.append({
                    "fecha": fecha_fin or fecha_inicio,
                    "consumo": consumo_total_record,
                    "consumo_detallado": consumo_detallado,
                    "penalizacion_reactiva_euros": pen_record
                    # Add others if needed
                })

        # Calculate Totals
        total_anual = sum(consumo_anual_periodo.values())
        total_consumos["consumo_anual_kWh"] = total_consumos["consumo_total_kWh"] # Logic from TS seems to equate them roughly
        
        # Potencias Contratadas parsing
        potencias_raw = raw_data.get('potencias_contratadas', {}).get('potencias_kW', {})
        potencias_clean = {}
        for k, v in potencias_raw.items():
             if isinstance(v, str):
                 try: potencias_clean[k] = float(v.replace(',', '.'))
                 except: pass
             else:
                 potencias_clean[k] = v

        # Construct Response
        transformed = {
            "cups": raw_data.get('cups', cups),
            "direccion": raw_data.get('localizacion', {}).get('direccion', "No disponible"),
            "municipio": raw_data.get('localizacion', {}).get('municipio', "No disponible"),
            "provincia": raw_data.get('localizacion', {}).get('provincia', "No disponible"),
            "codigo_postal": raw_data.get('localizacion', {}).get('codigo_postal', "No disponible"),
            "tarifa": raw_data.get('potencias_contratadas', {}).get('tarifa', "No disponible"),
            
            "potencia_contratada": potencias_clean.get("periodo_1"), 
            "potencias_contratadas": potencias_clean,
            
            "consumo_anual_total": total_anual,
            "distribuidor": raw_data.get("distribuidor", "No disponible"),
            
            "titular": {
                "tipo_actividad": raw_data.get("titular", {}).get("tipo_actividad"),
                "tipo_identificador": raw_data.get("titular", {}).get("tipo_identificador")
            },
            
            "datos_tecnicos": raw_data.get("datos", {}), # Pass mostly as is
            "fechas": raw_data.get("fechas", {}),
            
            "consumos": consumos,
            "consumos_anuales_periodo": consumo_anual_periodo,
            "penalizaciones_reactiva": penalizaciones_reactiva,
            "total_consumos": total_consumos,
            "raw_data": raw_data
        }
        
        return jsonify(transformed)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=5000)
