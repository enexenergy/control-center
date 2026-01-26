import requests
import json
import os
import sys
from datetime import datetime, timedelta

# Ensure we can import common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import common

# Load config
common.load_config()

def obtener_facturas(token):
    """Consulta todas las facturas emitidas (cliente) con paginación."""
    url = "https://www.orkamanager.com/orkapi/facturas/find"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Rango amplio para traer historial (ajustar segun necesidad, aqui ponemos ~2 años)
    hoy = datetime.today()
    hace_dias = hoy - timedelta(days=730) 
    fecha_desde = hace_dias.strftime("%d/%m/%Y")
    fecha_hasta = hoy.strftime("%d/%m/%Y")

    all_facturas = []
    offset = 0
    limit = 1000
    more_available = True
    
    print(f"Consultando facturas desde {fecha_desde} hasta {fecha_hasta}...")

    while more_available:
        payload = {
            "fecha_emision_factura_cliente_desde": fecha_desde,
            "fecha_emision_factura_cliente_hasta": fecha_hasta,
            "limite": limit, 
            "offset": offset
        }
        
        try:
            print(f"  Solicitando offset={offset} limit={limit}...")
            response = requests.post(url, headers=headers, json=payload, timeout=45)
            
            if response.status_code == 200:
                data = response.json()
                page_results = data.get("facturas", [])
                
                if not page_results:
                    more_available = False
                else:
                    all_facturas.extend(page_results)
                    print(f"  Recibidas {len(page_results)} facturas. Total acumulado: {len(all_facturas)}")
                    
                    if len(page_results) < limit:
                        more_available = False # Less than limit means last page
                    else:
                        offset += limit # Next page
            else:
                print(f"Error al consultar facturas: {response.status_code} - {response.text}")
                more_available = False # Stop on error
                
        except Exception as e:
            print(f"Excepción obteniendo facturas: {e}")
            more_available = False
            
    return all_facturas

def procesar_facturas(facturas):
    datos_export = []
    
    for f in facturas:
        if f.get("estado_factura") != "Factura cliente emitida":
            continue
            
        fc = f.get("factura_cliente", {})
        
        # Unify Name Logic
        # User requested: concatenation of nombre_razon_social + primer_apellido + segundo_apellido
        nombre_razon = f.get("nombre_razon_social", "").strip()
        apellido1 = f.get("primer_apellido", "").strip()
        apellido2 = f.get("segundo_apellido", "").strip()
        
        full_name_parts = []
        if nombre_razon: full_name_parts.append(nombre_razon)
        if apellido1: full_name_parts.append(apellido1)
        if apellido2: full_name_parts.append(apellido2)
        
        full_name = " ".join(full_name_parts)
            
        # Fallback if empty
        if not full_name:
            full_name = f.get("nombre", "").strip() or "Desconocido"
            
        # Clean amounts
        try:
            total = float(str(fc.get("importe_total_cliente_euros", 0)).replace(",", "."))
        except: total = 0.0
        
        try:
            # Extract consumption from 'consumo_total_kWh'
            consumo_raw = fc.get("consumo_total_kWh", "0")
            consumption = float(str(consumo_raw).replace(",", "."))
        except: consumption = 0.0

        record = {
            "id": f.get("codigo_factura_cliente", ""),
            "date": fc.get("fecha_emision", ""),
            "total": total,
            "consumption": consumption,
            "client": full_name or "Desconocido",
            "status": f.get("estado_factura", "")
        }
        datos_export.append(record)
        
    return datos_export

def main():
    print("Iniciando sincronización de ventas (Divakia > JSON)...")
    
    token = common.get_orka_token()
    if token:
        facturas = obtener_facturas(token)
        print(f"Facturas obtenidas: {len(facturas)}")
        
        if facturas:
            data = procesar_facturas(facturas)
            
            # Save to JSON
            out_file = "divakia_sales_data.json" # Saved in root
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            print(f"✅ Datos guardados en {out_file}")
        else:
            print("No se encontraron facturas.")
            
    else:
        print("❌ Error de autenticación.")

if __name__ == "__main__":
    main()
