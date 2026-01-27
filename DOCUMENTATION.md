# Enex Antigravity - Panel de Control

Este proyecto es un **Panel de Control y Automatización** diseñado para gestionar la facturación y operativa energética de Enex. Combina un backend en Python (Flask) con scripts de automatización para sincronizar datos entre **Orka Manager** (ERP Sectorial) y **Holded** (Contabilidad), además de ofrecer visualizaciones clave.

## 📋 Características Principales

1.  **Dashboard Central (`/`)**: Interfaz unificada para ejecutar scripts de automatización.
2.  **Visualización de Ventas (`/billing`)**: Gráficos interactivos de facturación y consumo energético mensual/acumulado.
3.  **Ranking de Competencia (`/ranking`)**: Comparativa de cuota de mercado vs. competidores utilizando datos reales de ventas.
4.  **Consulta SIPS (`/sips`)**: Herramienta para consultar datos técnicos de puntos de suministro (CUPS) directamente desde la API de Orka.
4.  **Consulta SIPS (`/sips`)**: Herramienta para consultar datos técnicos de puntos de suministro (CUPS) directamente desde la API de Orka.
5.  **Automatización de Scripts**: Ejecución de tareas programadas o bajo demanda para generación de ficheros contables.

## 🛠 Estructura del Proyecto

*   **`api/index.py`**: Entry point Flask (Vercel Serverless Function). Gestiona rutas, API y orquesta la ejecución de scripts.
*   **`scripts/`**: Lógica de negocio y automatización.
    *   `analytics.py`: Lógica para procesamiento de datos de Billing y Ranking (Lee desde **Supabase**).
    *   `sync_divakia_sales.py`: Sincronización de ventas Bidireccional (Orka API -> **Supabase**).
    *   `common.py`: Funciones compartidas (logging, config, cliente Supabase).
*   **`templates/`**: Vistas HTML (Frontend).
*   **`static/`**: Estilos CSS y Assets.
*   **Base de Datos (Supabase)**: Almacenamiento persistente de facturas y datos históricos.

## 🚀 Instalación y Requisitos

### Prerrequisitos
*   **Python 3.9+**
*   Cuenta de **Supabase** (PostgreSQL) para almacenamiento.

### Configuración
1.  **Clonar el repositorio**.
2.  **Instalar dependencias**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configurar Variables de Entorno (.env)**:
    ```ini
    ORKA_USER="tu_usuario"
    ORKA_PASSWORD="tu_password"
    HOLDED_API_KEY="tu_api_key_holded"
    LOG_LEVEL=INFO
    
    # Base de Datos (Supabase)
    SUPABASE_URL="https://tu-proyecto.supabase.co"
    SUPABASE_KEY="tu_service_role_key" # Clave 'service_role' (starts with ey...)
    ```
4.  **Inicializar Base de Datos**:
    Ejecutar el script SQL de migración en el panel de Supabase para crear la tabla `invoices` con todos los campos extendidos.

## ▶️ Uso y Ejecución

### Iniciar el Servidor Web
```bash
python api/index.py
```
Acceder a: `http://127.0.0.1:5000`

### APIs Disponibles
*   `GET /api/billing-data`: Retorna datos agregados de facturación (Fuente: Supabase).
*   `POST /api/sips/search`: Consulta datos de un CUPS.

## 🔄 Flujos de Automatización

### 1. Sincronización de Ventas (Cloud Database)
Ejecutar `sync_divakia_sales.py`.
*   Conecta a la API de Orka Manager.
*   Descarga el historial completo de facturas.
*   Procesa y mapea **todos los campos de facturación** (CUPS, potencias, costes desglosados, batería virtual, etc.).
*   Realiza un "Upsert" en la tabla `invoices` de Supabase.

### 2. Contabilización de Facturas (Holded)
*   **Ventas**: Ejecutar `facturas_emitidas.py` genera un Excel para importación.
*   **Compras (ATR)**: Ejecutar `divakia_atr.py`.
*   **Compras (OMIE)**: Ejecutar `omie_holded.py`.
