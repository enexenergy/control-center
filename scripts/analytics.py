import json
import os
import sys
from datetime import datetime

# Ensure we can import common
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import common

def _fetch_invoices():
    """
    Fetch invoices from Supabase and transform to legacy format.
    """
    supabase = common.get_supabase_client()
    if not supabase:
        # Fallback to local file if Supabase fails or not configured (dev mode)
        # Or just return empty/error. Let's return empty list but log error.
        print("Error: Supabase client not initialized in analytics.")
        return []
        
    try:
        # Fetch all invoices using pagination to overcome limits (usually 1000 per request)
        all_rows = []
        offset = 0
        limit = 1000
        more = True
        
        while more:
            response = supabase.table('invoices').select('*').range(offset, offset + limit - 1).execute()
            batch = response.data
            
            if batch:
                all_rows.extend(batch)
                offset += limit
                if len(batch) < limit:
                    more = False
            else:
                more = False
                
        invoices = []
        for r in all_rows:
            # Transform YYYY-MM-DD -> DD/MM/YYYY for legacy compatibility
            date_legacy = ""
            if r.get('issue_date'):
                try:
                    date_legacy = datetime.strptime(r['issue_date'], "%Y-%m-%d").strftime("%d/%m/%Y")
                except: 
                    pass
            
            # Map fields
            inv = {
                "id": r.get('id'),
                "date": date_legacy,
                "total": float(r.get('amount') or 0),
                "consumption": float(r.get('consumption_kwh') or 0),
                "status": r.get('status'),
                "client": r.get('client_name')
            }
            invoices.append(inv)
            
        return invoices
        
    except Exception as e:
        print(f"Error fetching from Supabase: {e}")
        return []

def get_billing_data(base_dir):
    try:
        invoices = _fetch_invoices()
        
        if not invoices:
            return {"labels": [], "values": [], "last_sync": "No data (Supabase empty or error)"}
            
        # Aggregate by month
        monthly_sales = {}
        monthly_consumption = {}
        
        # Parse dates for sorting
        for inv in invoices:
            date_str = inv.get('date')
            if not date_str:
                continue
            try:
                dt = datetime.strptime(date_str, "%d/%m/%Y")
                inv['_dt'] = dt # temporary for sorting
            except ValueError:
                inv['_dt'] = datetime.min

        # Sort descending
        invoices.sort(key=lambda x: x.get('_dt'), reverse=True)

        for inv in invoices:
            dt = inv.get('_dt')
            if dt == datetime.min:
                continue
                
            month_key = dt.strftime('%Y-%m')
            
            # Sum up 'total' and 'consumption'
            # Sum up 'total' and 'consumption'
            # Remove VAT (21%) from total amount
            amount_with_iva = inv.get('total', 0)
            amount = amount_with_iva / 1.21
            
            consumo = inv.get('consumption', 0)
            
            monthly_sales[month_key] = monthly_sales.get(month_key, 0) + amount
            monthly_consumption[month_key] = monthly_consumption.get(month_key, 0) + consumo
            
        # Sort by month for chart
        sorted_keys = sorted(monthly_sales.keys())
        labels = sorted_keys
        values = [monthly_sales[k] for k in sorted_keys]
        consumption_values = [monthly_consumption.get(k, 0) for k in sorted_keys]
        
        # Calculate Accumulated Data
        acc_values = []
        acc_consumption = []
        running_total = 0
        running_consumption = 0
        
        for v, c in zip(values, consumption_values):
            running_total += v
            running_consumption += c
            acc_values.append(running_total)
            acc_consumption.append(running_consumption)
        
        # Clean up temporary field
        for inv in invoices:
            if '_dt' in inv:
                del inv['_dt']

        return {
            "labels": labels,
            "values": values,
            "consumption": consumption_values,
            "accumulated_values": acc_values,
            "accumulated_consumption": acc_consumption,
            "invoices": invoices, # Return full list for table
            "last_sync": datetime.now().strftime("%Y-%m-%d %H:%M:%S") 
        }
            
    except Exception as e:
        return {"error": str(e)}

def get_ranking_data(base_dir):
    try:
        # 1. Load Competitors using BASE_DIR
        ranking_path = os.path.join(base_dir, 'competitors_ranking.json')
        if not os.path.exists(ranking_path):
            return {"error": "Ranking data not found"}
            
        with open(ranking_path, 'r', encoding='utf-8') as f:
            competitors = json.load(f)
            
        # 2. Load User Data using Supabase Helper
        user_invoices = _fetch_invoices()
        
        # 3. Process Invoices into Monthly Buckets
        monthly_map = {}
        min_date = datetime.now()
        max_date = datetime.min
        
        has_data = False
        
        for inv in user_invoices:
            try:
                kwh = inv.get('consumption', 0)
                date_str = inv.get('date')
                if date_str:
                    dt = datetime.strptime(date_str, "%d/%m/%Y")
                    # Track min/max for timeline
                    if dt < min_date: min_date = dt
                    if dt > max_date: max_date = dt
                    has_data = True
                    
                    month_key = dt.strftime('%Y-%m')
                    monthly_map[month_key] = monthly_map.get(month_key, 0) + kwh
            except:
                pass
                
        if not has_data:
            # Fallback if no invoices
            min_date = datetime.now()
            max_date = datetime.now()

        # 4. Generate Continuous Timeline (Month by Month)
        # Normalize min_date to start of month
        current_dt = min_date.replace(day=1)
        # Normalize max_date to start of month
        end_dt = max_date.replace(day=1)
        
        timeline_months = []
        # Safety limit for loop
        loop_limit = 0
        while current_dt <= end_dt and loop_limit < 1000:
            timeline_months.append(current_dt.strftime('%Y-%m'))
            # Add one month
            next_month = current_dt.month % 12 + 1
            next_year = current_dt.year + (current_dt.month // 12)
            current_dt = current_dt.replace(year=next_year, month=next_month)
            loop_limit += 1
            
        # 5. Calculate Rolling 12M for each point in timeline
        evolution_labels = []
        evolution_gwh = []
        evolution_rank = []
        
        for i, month_str in enumerate(timeline_months):
            # Calculate window: [month_str and previous 11 months]
            # Since timeline is continuous, we can just look back 11 indices
            window_sum = 0
            start_idx = max(0, i - 11)
            
            for j in range(start_idx, i + 1):
                m = timeline_months[j]
                window_sum += monthly_map.get(m, 0)
            
            # Convert to GWh
            rolling_val = window_sum / 1_000_000
            
            # Find Simulated Rank (User Rolling vs Approx Competitor Static)
            better_competitors = [c for c in competitors if c.get('sales_2024', 0) > rolling_val]
            rank = len(better_competitors) + 1
            
            evolution_labels.append(month_str)
            evolution_gwh.append(rolling_val)
            evolution_rank.append(rank)

        # 6. Current Metrics (Last point in evolution should be "Current Rolling 12M")
        current_gwh = evolution_gwh[-1] if evolution_gwh else 0
        current_rank = evolution_rank[-1] if evolution_rank else 0
        
        # 2023 Metric (Fixed Calendar Year Sum)
        sales_2023 = 0
        for m_key, val in monthly_map.items():
            if m_key.startswith('2023'):
                sales_2023 += val
        gwh_2023 = sales_2023 / 1_000_000
        
        # Change %
        pct_change = 0
        if gwh_2023 > 0:
            pct_change = ((current_gwh - gwh_2023) / gwh_2023) * 100
        elif current_gwh > 0:
            pct_change = 100.0

        # 7. Insert User into Ranking Table
        user_entry = {
            "name": "ENEX (Tu Empresa)",
            "sales_gwh": current_gwh,
            "sales_2024": current_gwh, # Display rolling 12m
            "sales_2023": gwh_2023,
            "change_pct": round(pct_change, 2),
            "is_user": True,
            "rank": 0 # Will be calc below
        }
        
        all_entities = competitors + [user_entry]
        all_entities.sort(key=lambda x: x.get('sales_2024', 0), reverse=True)
        
        final_ranking = []
        user_rank_table = 0
        
        for i, entity in enumerate(all_entities):
            rank = i + 1
            entity['rank'] = rank
            final_ranking.append(entity)
            if entity.get('is_user'):
                user_rank_table = rank

        return {
            "user_stats": {
                "rank": user_rank_table,
                "gwh": current_gwh,
                "gwh_prev": gwh_2023,
                "change_pct": pct_change,
                "total_competitors": len(competitors)
            },
            "ranking_table": final_ranking, 
            "evolution": {
                "labels": evolution_labels,
                "gwh": evolution_gwh,
                "rank": evolution_rank
            }
        }

    except Exception as e:
        return {"error": str(e)}
