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

        # Date Parsing for DB (Try multiple formats)
        date_str = fc.get("fecha_emision", "")
        issue_date = None
        if date_str:
            for fmt in ["%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"]:
                try:
                    issue_date = datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                    break
                except: continue


        # Helper for helpers
        def _f(val):
             return float(str(val).replace(",", ".")) if val else 0.0
             
        def _d(date_val):
            if not date_val: return None
            for fmt_ in ["%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"]:
                try: return datetime.strptime(date_val, fmt_).strftime("%Y-%m-%d")
                except: continue
            return None

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
            "raw_data": f,
            "updated_at": datetime.now().isoformat(),

            # --- Expanded Schema Fields ---
            
            # Suministro
            "cnae": f.get("cnae"),
            "cups": f.get("cups"),
            "price_type": f.get("precio"),
            "payment_method": f.get("forma_pago"),
            "access_tariff": f.get("tarifa_atr"),
            "self_consumption_type": f.get("autoconsumo"),
            "distributor": f.get("distribuidor"),
            "fiscal_address": f.get("direccion_fiscal"),
            "shipping_address": f.get("direccion_envio"),
            
            # Contratos Ref
            "contract_reference_atr": f.get("codigo_contrato_atr"),
            "contract_reference": f.get("codigo_contrato_cliente"),
            "invoice_reference_atr": f.get("codigo_factura_atr"),
            "contract_end_date": _d(f.get("fecha_finalizacion_contrato")),

            # Potencias
            "p1_kw": _f(f.get("potencia_p1_kW")),
            "p2_kw": _f(f.get("potencia_p2_kW")),
            "p3_kw": _f(f.get("potencia_p3_kW")),
            "p4_kw": _f(f.get("potencia_p4_kW")),
            "p5_kw": _f(f.get("potencia_p5_kW")),
            "p6_kw": _f(f.get("potencia_p6_kW")),

            # Factura Cliente (Desglose)
            "fc_start_date": _d(fc.get("fecha_desde")),
            "fc_end_date": _d(fc.get("fecha_hasta")),
            "fc_days": int(fc.get("numero_dias_facturacion", 0)) if fc.get("numero_dias_facturacion") else 0,
            
            "fc_invoice_type": fc.get("tipo_factura_cliente"),
            "fc_energy_cost": _f(fc.get("importe_energia_euros")),
            "fc_power_cost": _f(fc.get("importe_potencia_euros")),
            "fc_rental_cost": _f(fc.get("alquileres_euros")),
            "fc_tax_electricity": _f(fc.get("importe_impuesto_electrico_euros")),
            "fc_iva_cost": _f(fc.get("iva_euros")),
            
            # Totales y Extras
            "fc_total_energy": _f(fc.get("importe_total_energia_euros")),
            "fc_total_power": _f(fc.get("importe_total_potencia_euros")),
            "fc_excess_power": _f(fc.get("excesos_potencia_euros")),
            "fc_excess_reactive": _f(fc.get("excesos_reactiva_euros")),
            "fc_surplus_energy": _f(fc.get("autoconsumo_excedentes_euros")),
            "fc_surplus_compens": _f(fc.get("autoconsumo_compensacion_euros")),
            "fc_virtual_battery": _f(fc.get("descuento_aplicacion_bateria_virtual_euros")),
            "fc_social_bonus": _f(fc.get("importe_financiacion_bono_social_euros")),
            "fc_other_services": _f(fc.get("otros_servicios_euros")),
            "fc_invoice_total": _f(fc.get("importe_factura_euros"))
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
