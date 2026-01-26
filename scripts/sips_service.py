import os
import requests
import base64
import time
from dotenv import load_dotenv

# Cache for token
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
        raise Exception("Credenciales ORKA no configuradas en entorno (ORKA_USER/ORKA_PASSWORD)")

    # Orka requires base64 encoded credentials in body
    user_b64 = base64.b64encode(username.encode()).decode()
    pass_b64 = base64.b64encode(password.encode()).decode()

    payload = {
        "user": user_b64,
        "password": pass_b64
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        resp = requests.post("https://www.orkamanager.com/orkapi/login", data=payload, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
         raise Exception(f"Error de conexión con Orka: {e}")

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

def search_cups_data(cups):
    if not cups:
        return {"error": "CUPS no proporcionado"}, 400

    try:
        token = get_orka_token()
    except Exception as e:
        return {"error": str(e)}, 500
    
    url = f"https://www.orkamanager.com/orkapi/cups/{cups}"
    headers = {
       "Authorization": f"Bearer {token}",
       "User-Agent": "Enex-Control-Center/1.0" 
    }
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión con Orka: {e}"}, 502

    if resp.status_code == 404:
         return {"error": "CUPS no encontrado"}, 404
         
    if not resp.ok:
        return {"error": f"Error upstream: {resp.text}"}, resp.status_code
        
    raw_data = resp.json()
    
    try:
        # --- Processing Logic ---
        
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
                })

        # Calculate Totals
        total_anual = sum(consumo_anual_periodo.values())
        total_consumos["consumo_anual_kWh"] = total_consumos["consumo_total_kWh"] 
        
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
        
        return transformed, 200

    except Exception as e:
        return {"error": f"Error procesando datos: {str(e)}"}, 500
