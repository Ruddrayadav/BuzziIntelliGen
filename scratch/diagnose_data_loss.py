import pandas as pd
from services.cleaning_service import clean_dataframe
from services.mapping_service import suggest_mapping, apply_mapping

def diagnose_file(filepath: str, file_type: str):
    print(f"--- Diagnosing {file_type.upper()} File: {filepath} ---")
    
    # 1. Load Raw
    try:
        raw_df = pd.read_csv(filepath)
    except FileNotFoundError:
        print(f"File not found: {filepath}. Note: If the sample files have 60/34 rows instead of 727, this might just use the old small sample files.")
        return
        
    print(f"1. RAW DATA")
    print(f"   Raw Row count: {len(raw_df)}")
    print(f"   Raw Exact duplicates: {raw_df.duplicated().sum()}")
    print("   Null counts per column:")
    for col, count in raw_df.isnull().sum().items():
        print(f"     - {col}: {count}")
    
    # 2. Map Columns (to standard schema) so we can run calculations
    mapping = suggest_mapping(raw_df.columns.tolist(), file_type, use_llm=False)
    std_df = apply_mapping(raw_df, mapping.to_rename_dict())
    
    # 3. Clean Data to standardize numeric formats before summing raw sums
    # We do a basic manual conversion for summing since raw data might have "₹25,000"
    def parse_money_raw(val):
        if pd.isna(val): return 0.0
        s = str(val).replace("₹", "").replace(",", "").strip()
        try: return float(s)
        except: return 0.0
        
    if file_type == "sales":
        raw_sum = std_df["revenue"].apply(parse_money_raw).sum()
        print(f"   Raw Revenue Sum (manual compute): ₹{raw_sum:,.2f}")
    else:
        raw_sum = std_df["amount"].apply(parse_money_raw).sum()
        print(f"   Raw Expense Sum (manual compute): ₹{raw_sum:,.2f}")

    print("\n2. CLEANING PIPELINE")
    result = clean_dataframe(std_df, file_type)
    print(f"   Rows read: {result.raw_count}")
    print(f"   Rows saved: {result.clean_count}")
    print(f"   Duplicates removed: {result.duplicates_removed}")
    print(f"   Invalid removed: {result.invalid_removed}")
    
    if file_type == "sales":
        clean_sum = result.clean_df["revenue"].sum()
        print(f"   Clean Revenue Sum: ₹{clean_sum:,.2f}")
    else:
        clean_sum = result.clean_df["amount"].sum()
        print(f"   Clean Expense Sum: ₹{clean_sum:,.2f}")
        
    print(f"\n   LOSS SUMMARY: {result.raw_count - result.clean_count} rows lost.")
    print(f"   Difference in sum: ₹{(raw_sum - clean_sum):,.2f}")
    
    # Let's find exactly which rows were lost by looking at the diff
    # We can use pd.merge indicator
    if file_type == "sales":
        # Temporary standardized raw df for comparison
        std_df["revenue"] = std_df["revenue"].apply(parse_money_raw)
        merged = std_df.merge(result.clean_df, on=["date", "product", "revenue"], how="left", indicator=True)
        dropped = merged[merged["_merge"] == "left_only"]
        print("\n   SAMPLE OF DROPPED ROWS:")
        print(dropped.head(10)[["date", "product", "revenue"]])
    print("\n")

if __name__ == "__main__":
    diagnose_file("data/samples/sample_sales.csv", "sales")
    diagnose_file("data/samples/sample_expenses.csv", "expenses")
