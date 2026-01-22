import csv
import json
import zipfile
import requests
import os
import re
import sys
import openpyxl

# Ensure we can import common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import common

# Cargar variables de entorno
common.load_config()

# ==== CONFIGURACIÓN ====
HOLD_API_URL = "https://api.holded.com/api/invoicing/v1/documents/purchase?contactid=665574e36c21a403930ada24"
HOLD_API_KEY = os.getenv("HOLDED_API_KEY") 
GENERAR_FILTRANDO_HOLDED = True  # pon False si no quieres filtrar duplicados
CARPETA_DESCARGAS = common.get_downloads_dir()
PREFIJO_ARCHIVO = "FO_enex_"

# ==== COLUMNAS DEL EXCEL ====
COLUMNAS = [
    "Num factura", "Fecha dd/mm/yyyy", "Fecha de vencimiento dd/mm/yyyy", "Descripción", "Nombre del contacto",
    "NIF", "Dirección", "Población", "Código postal", "Provincia", "País", "Concepto", "Descripción del producto",
    "SKU", "Precio unidad", "Unidades", "Descuento %", "IVA %", "Retención %", "Inv. Suj. Pasivo (1/0)",
    "Operación", "Cantidad cobrada", "Fecha de cobro", "Cuenta de pago", "Tags separados por -",
    "Nombre cuenta de gasto", "Num. Cuenta de gasto", "Moneda", "Cambio de moneda"
]

# ==== FUNCIONES ====
def limpiar_y_convertir(valor):
    if valor is None:
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
        
    val_str = str(valor).strip()
    if not val_str:
        return 0.0
        
    result = 0.0
    try:
        # Try standard float first (handles 123.45)
        result = float(val_str)
    except ValueError:
        # Try Spanish format (1.234,56)
        try:
            # Remove dots, replace comma
            clean_s = val_str.replace('.', '').replace(',', '.')
            result = float(clean_s)
        except ValueError:
             print(f"⚠️ No se pudo convertir a numero: '{val_str}'")
             return 0.0
    
    # Debug log (Remove later if too noisy, but needed now)
    # print(f"DEBUG: '{val_str}' -> {result}") 
    return result

def encontrar_zip_mas_reciente():
    try:
        # Check if directory exists
        if not os.path.exists(CARPETA_DESCARGAS):
             raise FileNotFoundError(f"La carpeta {CARPETA_DESCARGAS} no existe.")

        archivos = [
            f for f in os.listdir(CARPETA_DESCARGAS)
            if f.startswith(PREFIJO_ARCHIVO) and f.endswith(".zip")
        ]
    except FileNotFoundError:
        raise FileNotFoundError(f"La carpeta {CARPETA_DESCARGAS} no existe.")

    if not archivos:
        raise FileNotFoundError(f"No se encontró ningún archivo ZIP que empiece por {PREFIJO_ARCHIVO} en {CARPETA_DESCARGAS}.")
    
    def extraer_numero(nombre):
        match = re.search(r"FO_enex_(\d+)", nombre)
        return int(match.group(1)) if match else -1

    archivos.sort(key=extraer_numero, reverse=True)
    return os.path.join(CARPETA_DESCARGAS, archivos[0])

def procesar_zip(ruta_zip):
    with zipfile.ZipFile(ruta_zip, 'r') as zip_ref:
        json_filename = next((name for name in zip_ref.namelist() if name.endswith('.json')), None)
        if not json_filename:
            raise FileNotFoundError("No se encontró ningún archivo JSON en el ZIP.")

        with zip_ref.open(json_filename) as json_file:
            data = json.load(json_file)

    facturas_data = []
    lista_facturas = data.get('facturas_omie', []) 
    if not lista_facturas:
        print("Advertencia: No se encontraron facturas en 'facturas_omie'.")
        
    for factura in lista_facturas:
        if factura.get("tipo_factura_omie") == "Factura de venta":
            continue

        num_factura = factura.get('cod_factura', '')
        fecha_emision = factura.get('fecha_emision', '')
        fecha_vencimiento = factura.get('fecha_pago', '')
        
        # Safe get access
        importe = factura.get('importe', {})
        if not importe: importe = {}
            
        iva_porcentaje = limpiar_y_convertir(importe.get('porcentaje_impuesto_%', ''))
        
        precio_unidad = limpiar_y_convertir(
            importe.get('base_imponible_€') or 
            importe.get("base_imponible_\u00e2\u201a\u00ac", '')
        )

        # Concepto
        conceptos = factura.get("conceptos", [{}])
        concepto_str = ""
        if conceptos and isinstance(conceptos, list):
            concepto_str = conceptos[0].get("concepto", "")

        datos_factura = {
            "Num factura": num_factura,
            "Fecha dd/mm/yyyy": fecha_emision,
            "Fecha de vencimiento dd/mm/yyyy": fecha_vencimiento,
            "Descripción": "Compra energía",
            "Nombre del contacto": "OMI POLO ESPAÑOL (OMI-POLO ESPAÑOL, S.A.)",
            "NIF": "A86025558",
            "Dirección": "",
            "Población": "",
            "Código postal": "",
            "Provincia": "",
            "País": "",
            "Concepto": concepto_str,
            "Descripción del producto": "",
            "SKU": "",
            "Precio unidad": precio_unidad, # KEEP AS FLOAT/NUMBER
            "Unidades": 1,
            "Descuento %": "",
            "IVA %": iva_porcentaje, # KEEP AS FLOAT/NUMBER
            "Retención %": "",
            "Inv. Suj. Pasivo (1/0)": "",
            "Operación": "general",
            "Cantidad cobrada": "",
            "Fecha de cobro": "",
            "Cuenta de pago": "",
            "Tags separados por -": "",
            "Nombre cuenta de gasto": "Compras OMIE",
            "Num. Cuenta de gasto": "60000002",
            "Moneda": "EUR",
            "Cambio de moneda": 1
        }
        facturas_data.append(datos_factura)

    return facturas_data

def guardar_en_excel(datos, archivo_salida):
    """Guarda los datos en un archivo XLSX usando openpyxl."""
    if not datos:
        print("Lista de datos vacía, no se generará archivo XLSX.")
        return

    try:
        output_dir = os.path.dirname(archivo_salida)
        os.makedirs(output_dir, exist_ok=True)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Facturas OMIE"
        
        # Headers
        ws.append(COLUMNAS)
        
        for row_data in datos:
            row_values = []
            for h in COLUMNAS:
                val = row_data.get(h, "")
                row_values.append(val)
            ws.append(row_values)
            
        wb.save(archivo_salida)
        print(f"Archivo XLSX guardado exitosamente en: {archivo_salida}")

    except Exception as e:
        print(f"Error al guardar el archivo XLSX: {e}")

def obtener_facturas_holded():
    headers = {"accept": "application/json", "key": HOLD_API_KEY}
    try:
        response = requests.get(HOLD_API_URL, headers=headers, timeout=20)
        if response.status_code == 200:
            holded_data = response.json()
            if isinstance(holded_data, list):
                return {factura.get('docNumber', '') for factura in holded_data if 'docNumber' in factura}
            return set()
        else:
            print(f"Error al obtener datos de Holded: {response.status_code}")
            return set()
    except Exception as e:
        print(f"Excepción obteniendo facturas Holded: {e}")
        return set()

# ==== PROGRAMA PRINCIPAL ====
def main():
    try:
        # Check if file was provided via upload (env var)
        uploaded_file = os.getenv('INPUT_FILE_PATH')
        
        if uploaded_file and os.path.exists(uploaded_file):
            ruta_zip = uploaded_file
            print(f"📥 Usando archivo subido: {ruta_zip}")
        else:
            try:
                ruta_zip = encontrar_zip_mas_reciente()
            except FileNotFoundError:
                 print("❌ No se encontró archivo ZIP. Asegúrate de cargarlo.")
                 return


        print(f"📂 Procesando archivo: {ruta_zip}")

        facturas = procesar_zip(ruta_zip)

        if GENERAR_FILTRANDO_HOLDED and HOLD_API_KEY:
            facturas_holded = obtener_facturas_holded()
            inicial_count = len(facturas)
            facturas = [f for f in facturas if f["Num factura"] not in facturas_holded]
            print(f"🔍 Facturas nuevas tras filtrar: {len(facturas)} (de {inicial_count})")
        elif not HOLD_API_KEY:
            print("⚠️ HOLDED_API_KEY no configurado. No se filtrarán duplicados.")

        if facturas:
            output_filename = os.path.join(CARPETA_DESCARGAS, "compras_omie.xlsx")
            
            guardar_en_excel(facturas, output_filename)
                
            common.trigger_download_via_stdout(output_filename)
        else:
            print("ℹ️ No hay facturas nuevas para procesar.")
            
    except FileNotFoundError as e:
        print(f"❌ Error archivo no encontrado: {e}")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")

# ==== PROGRAMA PRINCIPAL ====
if __name__ == "__main__":
    main()

