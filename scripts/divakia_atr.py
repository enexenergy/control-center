import os
import sys
import base64
import logging
import csv
import requests
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

# Ensure we can import common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import common

# Load configuration first
common.load_config()

# Configuración de Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Constantes y Configuración
API_BASE_URL = "https://www.orkamanager.com/orkapi"
FACTURAS_URL = f"{API_BASE_URL}/facturas/find"
HOLDED_API_URL = "https://api.holded.com/api/invoicing/v1/documents/purchase"

# Mapeo de prefijos de facturas a contactos
PROVEEDORES = {
    "17": {"nombre": "EDISTRIBUCION REDES DIGITALES SL", "nif": "B82846817"},
    "03": {"nombre": "I-DE Redes Eléctricas Inteligentes, S.A.U", "nif": "A95075578"},
    "J":  {"nombre": "UFD Distribución Electricidad, S.A.", "nif": "A63222533"},
}
PROVEEDOR_DEFAULT = {"nombre": "Desconocido", "nif": "NA"}

# IVA fijo solicitado
IVA_PORCENTAJE = Decimal("21")
IVA_FACTOR = Decimal("1") + (IVA_PORCENTAJE / Decimal("100"))

def obtener_facturas(token):
    """Obtiene las facturas paginadas desde el API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "limite": 1000,
        "offset": 0
    }
    
    try:
        response = requests.post(FACTURAS_URL, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        logger.info("Facturas obtenidas exitosamente.")
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al obtener las facturas: {e}")
        try:
            logger.debug(f"Detalle error: {response.text}")
        except:
            pass
        return None

def obtener_compras_holded(api_key):
    """Obtiene el listado de compras (expenses) desde Holded y retorna un set de números de documento."""
    if not api_key:
        logger.warning("No se configuró HOLDED_API_KEY. No se filtrarán duplicados.")
        return set()

    headers = {
        "key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        tres_meses_atras = datetime.now() - timedelta(days=90)
        timestamp_inicio = int(tres_meses_atras.timestamp())
        
        hoy = datetime.now()
        fin_dia = hoy.replace(hour=23, minute=59, second=59, microsecond=0)
        timestamp_fin = int(fin_dia.timestamp())

        params = {
            "starttmp": timestamp_inicio,
            "endtmp": timestamp_fin
        }

        response = requests.get(HOLDED_API_URL, headers=headers, params=params, timeout=20)
        
        if response.status_code == 400:
            logger.warning("Fallo con timestamp en segundos. Intentando con milisegundos...")
            params["starttmp"] = timestamp_inicio * 1000
            params["endtmp"] = timestamp_fin * 1000
            response = requests.get(HOLDED_API_URL, headers=headers, params=params, timeout=20)

        response.raise_for_status()
        
        data = response.json()
        if isinstance(data, list):
            numeros_existentes = {doc.get("docNumber") for doc in data if doc.get("docNumber")}
            logger.info(f"Se encontraron {len(numeros_existentes)} compras en Holded.")
            return numeros_existentes
        else:
            logger.warning("Formato de respuesta de Holded inesperado (no es lista).")
            return set()

    except requests.exceptions.RequestException as e:
        logger.error(f"Error al obtener compras de Holded: {e}")
        return set()

def safe_decimal(value, default=Decimal("0.0")):
    """Convierte un valor a Decimal de forma segura, manejando comas como decimales."""
    if not value:
        return default
    try:
        if isinstance(value, str):
            cleaned_value = value.replace(",", ".").strip()
            return Decimal(cleaned_value)
        return Decimal(value)
    except (ValueError, TypeError, ArithmeticError):
        logger.warning(f"No se pudo convertir '{value}' a Decimal. Usando valor por defecto {default}.")
        return default

def procesar_datos(data):
    """Procesa los datos crudos y genera un DataFrame limpio."""
    registros = []
    lista_facturas = data.get("facturas", [])
    
    if not lista_facturas:
        logger.warning("No se encontraron facturas en la respuesta.")
        return []

    for factura in lista_facturas:
        factura_atr = factura.get("factura_atr", {})
        
        importe_raw = factura_atr.get("importe_total_atr_euros", "0")
        importe_total = safe_decimal(importe_raw)
        
        num_factura = factura.get("codigo_factura_atr", "")
        datos_contacto = PROVEEDOR_DEFAULT
        
        for prefijo, datos in PROVEEDORES.items():
            if num_factura.startswith(prefijo):
                datos_contacto = datos
                break
        
        precio_unidad = (importe_total / IVA_FACTOR).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)

        registro = {
            "Num factura": num_factura,
            "Fecha dd/mm/yyyy": factura_atr.get("fecha_emision", ""),
            "Fecha de vencimiento dd/mm/yyyy": factura_atr.get("fecha_limite_pago", ""),
            "Descripción": factura_atr.get("motivo_facturacion", ""),
            "Nombre del contacto": datos_contacto["nombre"],
            "NIF": datos_contacto["nif"],
            "Dirección": "",
            "Población": "",
            "Código postal": "",
            "Provincia": "",
            "País": "",
            "Concepto": factura.get("cups", ""),
            "Descripción del producto": "",
            "SKU": "",
            "Precio unidad": precio_unidad,
            "Unidades": 1,
            "Descuento %": "",
            "IVA %": IVA_PORCENTAJE,
            "Retención %": "",
            "Inv. Suj. Pasivo (1/0)": "",
            "Operación": "",
            "Cantidad cobrada": "",
            "Fecha de cobro": "",
            "Cuenta de pago": "",
            "Tags separados por -": "",
            "Nombre cuenta de gasto": "Compras ATR",
            "Num. Cuenta de gasto": "60000001",
            "Moneda": "Eur",
            "Cambio de moneda": 1,
        }
        registros.append(registro)
        
    return registros

def guardar_en_csv(datos, archivo_salida):
    """Guarda los datos en un archivo CSV."""
    if not datos:
        logger.warning("Lista de datos vacía, no se generará archivo CSV.")
        return

    try:
        output_dir = os.path.dirname(archivo_salida)
        os.makedirs(output_dir, exist_ok=True)

        # Obtener columnas del primer registro o definir fijas
        if datos:
            columnas = list(datos[0].keys())
        else:
            return

        with open(archivo_salida, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=columnas, delimiter=';')
            writer.writeheader()
            writer.writerows(datos)
            
        logger.info(f"Archivo CSV guardado exitosamente en: {archivo_salida}")

    except Exception as e:
        logger.error(f"Error al guardar el archivo CSV: {e}")

def main():
    logger.info("Iniciando proceso de extracción de facturas ATR...")
    
    # 1. Configuración de Salida
    # 1. Configuración de Salida
    archivo_salida = os.path.join(common.get_downloads_dir(), "facturas_resultados.xlsx")

    # 5. Procesamiento
    registros = procesar_datos(data_facturas)
    
    if registros:
        logger.info("Filtrando facturas antiguas (más de 3 meses de antigüedad)...")
        fecha_limite = datetime.now() - timedelta(days=90)
        inicial_cnt = len(registros)
        
        registros_filtrados = []
        for r in registros:
            d_str = r.get("Fecha dd/mm/yyyy", "")
            try:
                # Intentar parsear fecha
                if d_str:
                    dt = datetime.strptime(d_str, "%d/%m/%Y")
                    if dt >= fecha_limite:
                        registros_filtrados.append(r)
                else:
                    # Sin fecha, ¿guardamos o descartamos? Pandas coerce -> NaT -> False. Descartamos.
                    pass
            except:
                pass
        
        registros = registros_filtrados
        final_cnt = len(registros)
        
        logger.info(f"Se descartaron {inicial_cnt - final_cnt} facturas anteriores a {fecha_limite.strftime('%d/%m/%Y')}.")

    if registros and facturas_holded:
        logger.info("Filtrando facturas ya existentes en Holded...")
        inicial_cnt = len(registros)
        registros = [r for r in registros if r["Num factura"] not in facturas_holded]
        final_cnt = len(registros)
        logger.info(f"Se filtraron {inicial_cnt - final_cnt} facturas que ya existían en Holded.")

    # 6. Guardado (cambiar extensión a csv)
    archivo_salida = archivo_salida.replace(".xlsx", ".csv")
    guardar_en_csv(registros, archivo_salida)

    # 2. Configuración Holded
    holded_key = os.getenv("HOLDED_API_KEY")

    # 3. Datos Holded
    facturas_holded = set()
    if holded_key:
        logger.info("Obteniendo facturas de Holded (últimos 3 meses)...")
        facturas_holded = obtener_compras_holded(holded_key)
    else:
        logger.info("No se configuró HOLDED_API_KEY. Se omitirá el filtrado.")

    # 4. Obtención de Datos Divakia con common
    token = common.get_orka_token()
    
    if not token:
        logger.error("No se pudo obtener token de ORKA. Verifica credenciales en .env.")
        sys.exit(1)

    data_facturas = obtener_facturas(token)
    
    if not data_facturas:
        logger.error("No se obtuvieron datos de facturas. Abortando.")
        sys.exit(1)

    # 6. Guardado eliminado en el bloque anterior

    
    logger.info("Proceso finalizado.")

if __name__ == "__main__":
    main()

