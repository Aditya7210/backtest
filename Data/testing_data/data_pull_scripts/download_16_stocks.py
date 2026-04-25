import yfinance as yf
import pandas as pd
import os
import time

# Defined List of all 16 Stocks mapped to NSE Tickers
STOCK_LIST = {
    # Banking & Finance
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "State Bank of India": "SBIN.NS",
    "Bajaj Finance": "BAJFINANCE.NS",
    "Axis Bank": "AXISBANK.NS",
    
    # Defense & Tech
    "Bharat Electronics BEL": "BEL.NS",
    "MTAR Technologies": "MTARTECH.NS",
    "HAL Hindustan Aeronautics": "HAL.NS",
    "Mazagon Dock": "MAZDOCK.NS",
    
    # Adani & Power
    "Adani Enterprises": "ADANIENT.NS",
    "Adani Green Energy": "ADANIGREEN.NS",
    "Tata Power": "TATAPOWER.NS",
    
    # Conglomerate, Auto, Others
    "Reliance Industries": "RELIANCE.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "Zomato": "ZOMATO.NS",
    "Deepak Nitrite": "DEEPAKNTR.NS"
}

def download_historical_data():
    # Ensure our target directory exists
    target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data_files")
    os.makedirs(target_dir, exist_ok=True)
    
    print("==================================================")
    print("Initiating Maximum Historical Data Injection...")
    print("Source: Yahoo Finance [NSE]")
    print(f"Targeting {len(STOCK_LIST)} Heavyweight Equities")
    print("==================================================\n")

    for name, ticker in STOCK_LIST.items():
        print(f"📥 Extracting {name} ({ticker})...")
        try:
            # Download max historical data available without time restriction
            df = yf.download(ticker, period="max", progress=False)
            
            if df.empty:
                print(f"❌ Failed to fetch data for {ticker}. It might be delisted or invalid.\n")
                continue
                
            # Flatten MultiIndex columns (Fix for newer yfinance versions returning tuples)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            df.reset_index(inplace=True)
            
            # Format the output file name cleanly
            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "")
            csv_filename = f"{safe_name}_{ticker.replace('.NS', '')}.csv"
            file_path = os.path.join(target_dir, csv_filename)
            
            # Save strictly as CSV
            df.to_csv(file_path, index=False)
            print(f"✅ Saved >> {csv_filename} | Total Active Trading Days: {len(df)}\n")
            
            # 1 second delay to prevent Yahoo Finance API rate-limit bans
            time.sleep(1)
            
        except Exception as e:
            print(f"❌ ERROR processing {ticker}: {str(e)}\n")

    print("==================================================")
    print("🎉 All 16 Stock Histories Downloaded & Formatted!")
    print(f"Location: {target_dir}")
    print("==================================================")

if __name__ == "__main__":
    download_historical_data()
