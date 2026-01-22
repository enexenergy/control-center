import requests
import pandas as pd
from datetime import datetime, timedelta
import io
import os
import sys

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

def convertir_a_float(valor):
    try:
        # Usamos la lógica local simple que funcionaba, o podemos usar common.clean_float
        # La original era: valor = str(valor).replace(",", ".") -> float(valor)
        # Mantendremos la lógica simple de Python standard para evitar sorpresas si no hay miles.
        if not valor: return 0.0
        valor = str(valor).replace(",", ".")
        return float(valor)
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

def generar_excel_facturas(facturas, facturas_holded):
    columnas = [
        "Num factura", "Formato de numeración", "Fecha dd/mm/yyyy", "Fecha de vencimiento dd/mm/yyyy", "Descripción", 
        "Nombre del contacto", "NIF del contacto", "Dirección", "Población", "Código postal", "Provincia", "País", 
        "Concepto", "Descripción del producto", "SKU", "Precio unidad", "Unidades", "Descuento %", "IVA %", 
        "Retención %", "Rec. de eq. %", "Operación", "Forma de pago (ID)", "Cantidad cobrada", "Fecha de cobro", 
        "Cuenta de pago", "Tags separados por -", "Nombre canal de venta", "Cuenta canal de venta", "Moneda", "Cambio de moneda", "Almacén"
    ]

    # Filtrar por prefijo 'N2026' (o el año actual dinámico si se prefiere, pero el original era hardcoded)
    # EL original decía 'N2026', asumimos que es correcto para este año.
    facturas_filtradas = []
    
    current_year = datetime.now().year
    # Detect if we should update N2026 to N{current_year} or keep strictly N2026?
    # Original code had N2026. Let's keep strict to avoid breaking logic, 
    # but maybe N2025 was intended? Let's check original.
    # Original: `if f.get("codigo_factura_cliente", "").startswith("N2026")]`
    # Warning: Current year is 2026 (per system time). So N2026 is correct.
    
    for f in facturas:
        code = f.get("codigo_factura_cliente", "")
        if not code.startswith("N2026"):
            continue
            
        if f.get("estado_factura") != "Factura cliente emitida":
            continue
            
        if code in facturas_holded:
            continue
            
        facturas_filtradas.append(f)

    datos_facturas = []
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
                
        descripcion = f"Período de medida: {fc.get('fecha_desde', '')} - {fc.get('fecha_hasta', '')}"
        
        # Unir nombre
        parts = [
            f.get("nombre_razon_social", ""), 
            f.get("nombre", ""), 
            f.get("primer_apellido", ""), 
            f.get("segundo_apellido", "")
        ]
        nombre_contacto = " ".join([p for p in parts if p and p.strip()])

        importe_total = convertir_a_float(fc.get("importe_total_cliente_euros"))
        iva_euros = convertir_a_float(fc.get("iva_euros"))
        iva_reducido = convertir_a_float(fc.get("iva_reducido_euros"))

        precio_unidad = 0
        iva_valor = 0

        # Lógica de desglose IVA inverso
        if importe_total > 0:
            if iva_euros > 0:
                iva_valor = 21
                precio_unidad = round(importe_total / (1 + iva_valor / 100), 2)
            elif iva_reducido > 0:
                iva_valor = 10
                precio_unidad = round(importe_total / (1 + iva_valor / 100), 2)

        datos_factura = {
            "Num factura": f.get("codigo_factura_cliente", ""),
            "Formato de numeración": f"{datetime.now().year}%%%%", 
            "Fecha dd/mm/yyyy": fecha_emision,
            "Fecha de vencimiento dd/mm/yyyy": fecha_venc,
            "Descripción": descripcion,
            "Nombre del contacto": nombre_contacto,
            "NIF del contacto": f.get("identificador", ""),
            "Dirección": f.get("direccion_punto_suministro", ""),
            "Población": f.get("poblacion", ""),
            "Código postal": f.get("codigo_postal", ""),
            "Provincia": f.get("provincia", ""),
            "País": f.get("pais", ""),
            "Concepto": "",
            "Descripción del producto": "",
            "SKU": "",
            "Precio unidad": precio_unidad,
            "Unidades": 1,
            "Descuento %": "",
            "IVA %": iva_valor,
            "Retención %": "",
            "Rec. de eq. %": "",
            "Operación": "",
            "Forma de pago (ID)": "",
            "Cantidad cobrada": "",
            "Fecha de cobro": "",
            "Cuenta de pago": "",
            "Tags separados por -": "",
            "Nombre canal de venta": "",
            "Cuenta canal de venta": "",
            "Moneda": "eur",
            "Cambio de moneda": 1,
            "Almacén": ""
        }
        datos_facturas.append(datos_factura)

    df = pd.DataFrame(datos_facturas, columns=columnas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name="Facturas Emitidas", index=False)
    output.seek(0)
    return output

# Alias de compatibilidad
generar_excel_emitidas = generar_excel_facturas

# === EJECUCIÓN LOCAL ===
if __name__ == "__main__":
    print("Iniciando generación de facturas emitidas...")
    
    token = common.get_orka_token()
    
    if token:
        facturas = obtener_facturas(token)
        print(f"Facturas recuperadas de ORKA: {len(facturas)}")

        if facturas:
            facturas_holded = obtener_facturas_holded()
            print(f"Facturas recuperadas de HOLDED: {len(facturas_holded)}")
            
            excel_output = generar_excel_facturas(facturas, facturas_holded)

            os.makedirs(DOWNLOADS_DIR, exist_ok=True)
            out_path = os.path.join(DOWNLOADS_DIR, f"facturas_emitidas_{_ts()}.xlsx")
            
            with open(out_path, "wb") as f:
                f.write(excel_output.read())
            print(f"✅ Archivo Excel generado con éxito: {out_path}")
        else:
            print("ℹ️ No se encontraron facturas en el rango de fechas.")
    else:
        print("❌ No se pudo obtener el token de ORKA. Verifica las credenciales en .env")

