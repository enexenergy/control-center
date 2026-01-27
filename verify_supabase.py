import os
import sys

# Ensure we can import scripts.common
sys.path.append(os.getcwd())
from scripts import common

def verify():
    print("--- Verificando conexión a Supabase ---")
    
    # Load env
    common.load_config()
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("❌ Faltan credenciales en .env (SUPABASE_URL / SUPABASE_KEY)")
        return
        
    print(f"URL: {url}")
    print(f"KEY: {'*' * 5} (Oculta)")
    
    supabase = common.get_supabase_client()
    if not supabase:
        print("❌ Error inicializando cliente.")
        return
        
    try:
        # Try a lightweight query
        print("Intentando consultar tabla 'invoices'...")
        response = supabase.table("invoices").select("count", count="exact").limit(1).execute()
        
        print(f"✅ Conexión exitosa. Filas actuales en tabla 'invoices': {response.count}")
        
        # Check for bad dates
        bad_dates = supabase.table("invoices").select("id").is_("issue_date", "null").execute()
        if len(bad_dates.data) > 0:
            print(f"⚠️ ATENCIÓN: Hay {len(bad_dates.data)} facturas con fecha inválida (NULL).")
            print("   -> Tip: Ejecuta de nuevo el script de sincronización para corregirlas.")
        else:
            print("✅ Todas las facturas tienen fecha válida.")
            
        print("La integración parece correcta.")
        
    except Exception as e:
        print(f"❌ Error consultando Supabase: {e}")
        print("Verifica si creaste la tabla 'invoices' en el Editor SQL de Supabase.")

if __name__ == "__main__":
    verify()
