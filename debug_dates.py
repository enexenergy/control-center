import os
import sys
from collections import Counter
from datetime import datetime

# Ensure we can import scripts.common
sys.path.append(os.getcwd())
from scripts import common

def analyze_dates():
    print("--- Analyzing Invoice Dates in Supabase ---")
    
    common.load_config()
    supabase = common.get_supabase_client()
    
    if not supabase:
        print("❌ Connect failed.")
        return

    try:
        # Fetch only issue_date field to avoid huge payload
        print("Fetching issue_dates...")
        res = supabase.table("invoices").select("issue_date").limit(5000).execute()
        
        dates = [r['issue_date'] for r in res.data if r['issue_date']]
        
        print(f"Total Rows with Date: {len(dates)}")
        
        if not dates:
            print("No dates found.")
            return

        # Analyze distribution by YYYY-MM
        months = []
        for d in dates:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                months.append(dt.strftime("%Y-%m"))
            except:
                pass
                
        ctr = Counter(months)
        
        print("\nDistribution by Month:")
        for k in sorted(ctr.keys()):
            print(f"{k}: {ctr[k]} invoices")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    analyze_dates()
