import requests
import csv
from datetime import datetime, timedelta
import os
import sys
import unicodedata

# Ensure we can import common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import common

# === CONFIGURACIÓN ===
# Load config from .env
common.load_config()
holded_api_key = os.getenv("HOLDED_API_KEY")

# Carpeta de salida
DOWNLOADS_DIR = common.get_downloads_dir()

def _ts():
    # timestamp seguro para nombres de archivo en Windows
    return datetime.now().strftime("%Y%m%d_%H-%M-%S")

# === FUNCIONES ===

def normalize_text(text):
    """Normalize text to ASCII (remove accents/diacritics)."""
    if not text:
        return ""
    # Normalize unicode characters to closest ASCII equivalent
    return ''.join(c for c in unicodedata.normalize('NFD', str(text))
                   if unicodedata.category(c) != 'Mn')

def convertir_a_float(valor):
    try:
        if not valor: return 0.0
        # Assume Spanish format: 1.234,56
        # Remove thousands separator (.) first
        val_str = str(valor).replace('.', '')
        # Replace decimal separator (,) with (.)
        val_str = val_str.replace(',', '.')
        return float(val_str)
    except (ValueError, TypeError):
        return 0.0

def obtener_facturas(token):
    """Consulta solo las facturas emitidas en los últimos 7 días (ajustable)."""
    url = "https://www.orkamanager.com/orkapi/facturas/find"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    hoy = datetime.today()
    # PRECAUCION: El código original decía 'timedelta(days=25)' aunque el docstring decía '7 días'.
    # Mantendremos 25 días por seguridad para cubrir el rango esperado.
    hace_dias = hoy - timedelta(days=25)
    fecha_desde = hace_dias.strftime("%d/%m/%Y")
    fecha_hasta = hoy.strftime("%d/%m/%Y")

    payload = {
        "fecha_emision_factura_cliente_desde": fecha_desde,
        "fecha_emision_factura_cliente_hasta": fecha_hasta,
        "limite": 1000,
        "offset": 0
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code == 200:
            return response.json().get("facturas", [])
        else:
            print(f"Error al consultar facturas: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Excepción obteniendo facturas: {e}")
        return []

def obtener_facturas_holded():
    if not holded_api_key:
        print("Warning: HOLDED_API_KEY no definida. No se filtrarán facturas existentes.")
        return set()

    # URL original tenía starttmp fijo en 1526979494. 
    # Podríamos hacerlo dinámico, pero si funciona así, mejor no tocar demasiado la lógica de negocio remota.
    url = "https://api.holded.com/api/invoicing/v1/documents/invoice?starttmp=1526979494&endtmp=2000000000"
    headers = {"accept": "application/json", "key": holded_api_key}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            facturas_holded = response.json()
            # Asegurar que es lista
            if isinstance(facturas_holded, list):
                return {factura.get('docNumber', '') for factura in facturas_holded if 'docNumber' in factura}
            return set()
        else:
            print(f"Error al consultar facturas en Holded: {response.status_code}")
            return set()
    except Exception as e:
        print(f"Excepción conectando a Holded: {e}")
        return set()

def generar_csv_facturas(facturas, facturas_holded, output_path):
    columnas = [
        "Num factura", "Formato de numeracion", "Fecha dd/mm/yyyy", "Fecha de vencimiento dd/mm/yyyy", "Descripcion", 
        "Nombre del contacto", "NIF del contacto", "Direccion", "Poblacion", "Codigo postal", "Provincia", "Pais", 
        "Concepto", "Descripcion del producto", "SKU", "Precio unidad", "Unidades", "Descuento %", "IVA %", 
        "Retencion %", "Rec. de eq. %", "Operacion", "Forma de pago (ID)", "Cantidad cobrada", "Fecha de cobro", 
        "Cuenta de pago", "Tags separados por -", "Nombre canal de venta", "Cuenta canal de venta", "Moneda", "Cambio de moneda", "Almacen"
    ]

    # Filtrar facturas
    facturas_filtradas = []
    
    current_year = datetime.now().year
    
    for f in facturas:
        code = f.get("codigo_factura_cliente", "")
        # Mantener filtro estricto por ahora, asumiendo N{current_year} o N2026?
        # Original code was "N2026". 
        if not code.startswith("N2026"):
            continue
            
        if f.get("estado_factura") != "Factura cliente emitida":
            continue
            
        if code in facturas_holded:
            continue
            
        facturas_filtradas.append(f)

    # Escribir CSV
    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columnas, delimiter=';') # Excel friendly delimiter
            writer.writeheader()
            
            for f in facturas_filtradas:
                fc = f.get("factura_cliente", {})
                fecha_emision = fc.get("fecha_emision", "")
                
                # Calculo vencimiento +5 dias
                fecha_venc = ""
                if fecha_emision:
                    try:
                        dt_emision = datetime.strptime(fecha_emision, "%d/%m/%Y")
                        fecha_venc = (dt_emision + timedelta(days=5)).strftime("%d/%m/%Y")
                    except:
                        pass
                        
                descripcion = f"Periodo de medida: {fc.get('fecha_desde', '')} - {fc.get('fecha_hasta', '')}"
                
                # Unir nombre
                parts = [
                    f.get("nombre_razon_social", ""), 
                    f.get("nombre", ""), 
                    f.get("primer_apellido", ""), 
                    f.get("segundo_apellido", "")
                ]
                nombre_contacto = " ".join([p for p in parts if p and p.strip()])
                nombre_contacto = normalize_text(nombre_contacto) # Normalize name

                importe_total = convertir_a_float(fc.get("importe_total_cliente_euros"))
                iva_euros = convertir_a_float(fc.get("iva_euros"))
                iva_reducido = convertir_a_float(fc.get("iva_reducido_euros"))

                precio_unidad = 0.0
                iva_valor = 0

                # Lógica de desglose IVA inverso
                if importe_total > 0:
                    if iva_euros > 0:
                        iva_valor = 21
                        precio_unidad = round(importe_total / (1 + iva_valor / 100.0), 2)
                    elif iva_reducido > 0:
                        iva_valor = 10
                        precio_unidad = round(importe_total / (1 + iva_valor / 100.0), 2)

                row = {
                    "Num factura": f.get("codigo_factura_cliente", ""),
                    "Formato de numeracion": "2025%%%%", 
                    "Fecha dd/mm/yyyy": fecha_emision,
                    "Fecha de vencimiento dd/mm/yyyy": fecha_venc,
                    "Descripcion": descripcion,
                    "Nombre del contacto": nombre_contacto,
                    "NIF del contacto": f.get("identificador", ""),
                    "Direccion": normalize_text(f.get("direccion_punto_suministro", "")),
                    "Poblacion": normalize_text(f.get("poblacion", "")),
                    "Codigo postal": f.get("codigo_postal", ""),
                    "Provincia": normalize_text(f.get("provincia", "")),
                    "Pais": normalize_text(f.get("pais", "")),
                    "Concepto": "",
                    "Descripcion del producto": "",
                    "SKU": "",
                    "Precio unidad": f"{precio_unidad:.2f}", # Dot decimal format
                    "Unidades": "1",
                    "Descuento %": "",
                    "IVA %": str(iva_valor),
                    "Retencion %": "",
                    "Rec. de eq. %": "",
                    "Operacion": "",
                    "Forma de pago (ID)": "",
                    "Cantidad cobrada": "",
                    "Fecha de cobro": "",
                    "Cuenta de pago": "",
                    "Tags separados por -": "",
                    "Nombre canal de venta": "",
                    "Cuenta canal de venta": "",
                    "Moneda": "eur",
                    "Cambio de moneda": "1",
                    "Almacen": ""
                }
                writer.writerow(row)
        return True
    except Exception as e:
        print(f"Error escribiendo CSV: {e}")
        return False

# Alias de compatibilidad


def main():
    print("Iniciando generación de facturas emitidas...")
    
    token = common.get_orka_token()
    
    if token:
        facturas = obtener_facturas(token)
        print(f"Facturas recuperadas de ORKA: {len(facturas)}")

        if facturas:
            facturas_holded = obtener_facturas_holded()
            print(f"Facturas recuperadas de HOLDED: {len(facturas_holded)}")
            
            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            out_path = os.path.join(DOWNLOADS_DIR, f"facturas_emitidas_{_ts()}.csv")
            
            if generar_csv_facturas(facturas, facturas_holded, out_path):
                print(f"✅ Archivo CSV generado con éxito: {out_path}")
                common.trigger_download_via_stdout(out_path)
            else:
                print("❌ Fallo al generar el archivo CSV")
        else:
            print("ℹ️ No se encontraron facturas en el rango de fechas.")
    else:
        print("❌ No se pudo obtener el token de ORKA. Verifica las credenciales en .env")

# === EJECUCIÓN LOCAL ===
if __name__ == "__main__":
    main()

