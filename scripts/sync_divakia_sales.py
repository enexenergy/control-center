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
    
    # Extend to tomorrow to include full current day if API is exclusive
    manana = hoy + timedelta(days=1)
    fecha_hasta = manana.strftime("%d/%m/%Y")

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
        nombre_razon = f.get("nombre_razon_social", "").strip()
        apellido1 = f.get("primer_apellido", "").strip()
        apellido2 = f.get("segundo_apellido", "").strip()
        
        full_name_parts = []
        if nombre_razon: full_name_parts.append(nombre_razon)
        if apellido1: full_name_parts.append(apellido1)
        if apellido2: full_name_parts.append(apellido2)
        
        full_name = " ".join(full_name_parts)
            
        if not full_name:
            full_name = f.get("nombre", "").strip() or "Desconocido"
            
        # Clean amounts
        try:
            total = float(str(fc.get("importe_total_cliente_euros", 0)).replace(",", "."))
        except: total = 0.0
        
        try:
            consumo_raw = fc.get("consumo_total_kWh", "0")
            consumption = float(str(consumo_raw).replace(",", "."))
        except: consumption = 0.0

        # Date Parsing for DB (DD/MM/YYYY -> YYYY-MM-DD)
        date_str = fc.get("fecha_emision", "")
        issue_date = None
        if date_str:
            try:
                issue_date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except: pass

        record = {
            "id": f.get("codigo_factura_cliente", ""),
            "issue_date": issue_date,
            "amount": total,
            "consumption_kwh": consumption,
            "client_name": full_name or "Desconocido",
            "nif": f.get("identificador"),
            "address": f.get("direccion_punto_suministro"),
            "municipality": f.get("poblacion"),
            "province": f.get("provincia"),
            "status": f.get("estado_factura", ""),
            "raw_data": f, # STORE FULL API RESPONSE
            "updated_at": datetime.now().isoformat()
        }
        datos_export.append(record)
        
    return datos_export

def main():
    print("Iniciando sincronización de ventas (Divakia > Supabase)...")
    
    token = common.get_orka_token()
    if not token:
        print("❌ Error de autenticación Orka.")
        return

    supabase = common.get_supabase_client()
    if not supabase:
        print("❌ Error de configuración Supabase (SUPABASE_URL/KEY faltantes).")
        return

    facturas = obtener_facturas(token)
    print(f"Facturas obtenidas: {len(facturas)}")
    
    if facturas:
        data = procesar_facturas(facturas)
        
        if not data:
             print("No hay facturas procesables.")
             return

        print(f"Upserting {len(data)} facturas a Supabase...")
        
        # Supabase upsert batching
        BATCH_SIZE = 100
        for i in range(0, len(data), BATCH_SIZE):
            batch = data[i:i+BATCH_SIZE]
            try:
                # upsert matches on PRIMARY KEY (id)
                supabase.table("invoices").upsert(batch).execute()
                print(f"  Lote {i}-{i+len(batch)} enviado.")
            except Exception as e:
                print(f"❌ Error enviando lote {i}: {e}")
                
        print(f"✅ Sincronización completada.")
    else:
        print("No se encontraron facturas.")

if __name__ == "__main__":
    main()
