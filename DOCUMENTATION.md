# Enex Antigravity - Panel de Control

Este proyecto es un **Panel de Control y Automatización** diseñado para gestionar la facturación y operativa energética de Enex. Combina un backend en Python (Flask) con scripts de automatización para sincronizar datos entre **Orka Manager** (ERP Sectorial) y **Holded** (Contabilidad), además de ofrecer visualizaciones clave.

## 📋 Características Principales

1.  **Dashboard Central (`/`)**: Interfaz unificada para ejecutar scripts de automatización.
2.  **Visualización de Ventas (`/billing`)**: Gráficos interactivos de facturación y consumo energético mensual/acumulado.
3.  **Ranking de Competencia (`/ranking`)**: Comparativa de cuota de mercado vs. competidores utilizando datos reales de ventas.
4.  **Consulta SIPS (`/sips`)**: Herramienta para consultar datos técnicos de puntos de suministro (CUPS) directamente desde la API de Orka.
5.  **Automatización de Scripts**: Ejecución de tareas programadas o bajo demanda para generación de ficheros contables.

## 🛠 Estructura del Proyecto

*   **`app.py`**: Servidor Web Flask. Gestiona las rutas, la API interna y la ejecución de scripts.
*   **`scripts/`**: Lógica de negocio y automatización.
    *   `common.py`: Funciones compartidas (autenticación Orka, logging).
    *   `divakia_atr.py`: Descarga facturas de Peajes (ATR) de Orka y genera Excel para importación en Holded.
    *   `facturas_emitidas.py`: Descarga facturas de clientes de Orka y genera Excel para Holded.
    *   `omie_holded.py`: Procesa ficheros ZIP de OMIE y los convierte a formato compatible con Holded.
    *   `sync_divakia_sales.py`: Sincroniza el histórico de ventas desde Orka a un JSON local (`divakia_sales_data.json`) para el dashboard.
*   **`templates/`**: Vistas HTML (Frontend).
*   **`static/`**: Estilos CSS y Assets.
*   **`competitors_ranking.json`**: Datos estáticos de competidores para el ranking.
*   **`divakia_sales_data.json`**: Cache local de ventas (generado por `sync_divakia_sales.py`).

## 🚀 Instalación y Requisitos

### Prerrequisitos
*   **Python 3.8+**
*   Acceso a internet (para conectar con Orka y Holded).

### Configuración
1.  **Clonar el repositorio** o descomprimir el proyecto.
2.  **Crear el entorno virtual** (opcional pero recomendado):
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
3.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Configurar Variables de Entorno**:
    Crear un archivo `.env` en la raíz con el siguiente contenido:
    ```ini
    ORKA_USER="tu_usuario"
    ORKA_PASSWORD="tu_password"
    HOLDED_API_KEY="tu_api_key_holded"
    LOG_LEVEL=INFO
    ```

## ▶️ Uso y Ejecución

### Iniciar el Servidor Web
Ejecutar el siguiente comando en la terminal:
```bash
python app.py
```
Acceder en el navegador a: `http://127.0.0.1:5000`

### Uso del Dashboard
*   Desde la página de inicio, puede lanzar los scripts de automatización haciendo clic en los botones correspondientes.
*   El sistema mostrará el log de ejecución en tiempo real.

### APIs Disponibles
*   `GET /api/billing-data`: Retorna datos agregados de facturación.
*   `GET /api/ranking-data`: Retorna datos comparativos de mercado.
*   `POST /api/sips/search`: Consulta datos de un CUPS (`{ "cups": "ES..." }`).

## 🔄 Flujos de Automatización

### 1. Sincronización de Ventas
Ejecutar `sync_divakia_sales.py`. Esto descargará todas las facturas de clientes de Orka de los últimos 2 años y actualizará `divakia_sales_data.json`. El gráfico de `/billing` se actualizará automáticamente.

### 2. Contabilización de Facturas (Holded)
*   **Ventas**: Ejecutar `facturas_emitidas.py` genera un Excel en Descargas listo para importar en Holded.
*   **Compras (ATR)**: Ejecutar `divakia_atr.py` descarga facturas de distribuidoras, normaliza proveedores y genera el Excel.
*   **Compras (OMIE)**: Ejecutar `omie_holded.py` procesa los ZIPs descargados del mercado y genera el Excel.
