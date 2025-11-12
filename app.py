import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime

# Set page config
st.set_page_config(
    page_title="💰 Precious Metals Processor",
    page_icon="💰",
    layout="wide"
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        text-align: center;
        background: linear-gradient(90deg, #ffd700, #ffed4e);
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .stFileUploader {
        border: 2px dashed #ffd700;
        border-radius: 10px;
        padding: 1rem;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 5px;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

def gold_table(gold_market: float) -> pd.DataFrame:
    """Generate gold multiplier table"""
    multipliers = [2.1, 1.7, 1.5, 1.35, 1.25, 1.175, 1.1, 1.0683, 1]
    factors = [2, 1.8, 1.6, 1.4, 1.3, 1.2, 1.1, 1.05, 1]
    results = [gold_market / m for m in multipliers]
    return pd.DataFrame({"Gold Market": results, "Multiplier": factors})

def silver_table(silver_market: float) -> pd.DataFrame:
    """Generate silver multiplier table"""
    multipliers_s = [2.2, 1.5573, 1.4615, 1.3571, 1.3073, 1.2025, 1.1176, 1.0555, 1]
    factors_s = [2, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.05, 1]
    results_s = [silver_market / m for m in multipliers_s]
    return pd.DataFrame({"Gold Market": results_s, "Multiplier": factors_s})

def lookup_multiplier(reference, gold_factor, silver_factor):
    """Lookup multiplier from appropriate factor table based on Metal type"""
    gold_factor_sorted = gold_factor.sort_values('Gold Market').reset_index(drop=True)
    silver_factor_sorted = silver_factor.sort_values('Gold Market').reset_index(drop=True)
    
    def find_multiplier_above(value, factor_df, market_col='Gold Market'):
        if pd.isna(value):
            return pd.NA
        valid_matches = factor_df[factor_df[market_col] > value]
        if valid_matches.empty:
            return factor_df.iloc[-1]['Multiplier']
        else:
            return valid_matches.iloc[0]['Multiplier']
    
    def lookup_multiplier_by_metal(row):
        market_value = row['Gold Market']
        metal_type = row['Metal']
        
        if pd.isna(market_value) or pd.isna(metal_type):
            return pd.NA
        
        if metal_type == 'S/S':  # Silver
            return find_multiplier_above(market_value, silver_factor_sorted)
        else:  # Gold or any other metal
            return find_multiplier_above(market_value, gold_factor_sorted)
    
    reference['Multiplier'] = reference.apply(lookup_multiplier_by_metal, axis=1)
    return reference

def update_variant_price_fixed(upload, reference):
    """Update variant prices based on reference data"""
    result = upload.copy()
    
    # Clean and prepare both datasets
    result['Variant SKU'] = result['Variant SKU'].astype(str).str.strip()
    ref_clean = reference.copy()
    ref_clean['Stock ID'] = ref_clean['Stock ID'].astype(str).str.strip()
    
    # Remove 'nan' strings
    result.loc[result['Variant SKU'] == 'nan', 'Variant SKU'] = ''
    ref_clean.loc[ref_clean['Stock ID'] == 'nan', 'Stock ID'] = ''
    
    # Create lookup dictionary
    price_lookup = {}
    for idx, row in ref_clean.iterrows():
        stock_id = row['Stock ID']
        new_price = row['New Price']
        
        if (stock_id != '' and not pd.isna(stock_id) and 
            not pd.isna(new_price) and str(stock_id) != 'nan'):
            price_lookup[stock_id] = new_price
    
    # Track updates
    successful_updates = 0
    skipped_blank_sku = 0
    skipped_no_match = 0
    
    # Process each row individually
    for idx in result.index:
        variant_sku = result.loc[idx, 'Variant SKU']
        
        if variant_sku == '' or pd.isna(variant_sku):
            skipped_blank_sku += 1
            continue
        
        if variant_sku in price_lookup:
            new_price = price_lookup[variant_sku]
            if not pd.isna(new_price):
                result.loc[idx, 'Variant Price'] = new_price
                successful_updates += 1
        else:
            skipped_no_match += 1
    
    return result, successful_updates, skipped_blank_sku, skipped_no_match

def process_precious_metals_data(reference_file, upload_file, gold_price, silver_price):
    """Main processing function implementing your exact Colab logic"""
    
    try:
        # Read reference file
        reference = pd.read_csv(reference_file, encoding='latin1')
        
        # Read upload file  
        upload = pd.read_csv(upload_file, encoding='latin1')
        
        # Process reference data (following your Colab logic)
        reference["Date Created"] = pd.to_datetime(reference["Date Created"], errors="coerce")
        reference["Date Last Price Change"] = pd.to_datetime(reference["Date Last Price Change"], errors="coerce")
        reference["Last Stocked"] = pd.to_datetime(reference["Last Stocked"], errors="coerce")
        
        reference["Max Date"] = reference[
            ["Date Created", "Date Last Price Change", "Last Stocked"]
        ].max(axis=1)
        
        reference = reference.sort_values(by="Max Date", ascending=False).reset_index(drop=True)
        
        # Remove specific columns
        columns_to_drop = ["Date Created", "Date Last Price Change", "Last Stocked", 
                          "Bar Code ID", "Department", "Description", "Qty On Hand", 
                          "Type", "Vendor Name", "UID", "Vendor UID", "Photo"]
        
        # Only drop columns that exist
        columns_to_drop = [col for col in columns_to_drop if col in reference.columns]
        reference = reference.drop(columns=columns_to_drop)
        
        # Filter and clean data
        today = pd.Timestamp.today().normalize()
        reference = reference[reference["Max Date"] <= today].reset_index(drop=True)
        
        # Clean Stock ID and Metal columns - handle NaN values
        reference["Stock ID"] = reference["Stock ID"].fillna("").astype(str).str.replace(" ", "", regex=False)
        reference["Metal"] = reference["Metal"].fillna("").astype(str).str.replace(" ", "", regex=False)
        reference["Metal"] = reference["Metal"].str.replace("SS", "S/S", regex=False)
        reference = reference.drop_duplicates(subset=["Stock ID"]).reset_index(drop=True)
        
        # Clean Gold Market column - more robust handling
        if "Gold Market" in reference.columns:
            reference["Gold Market"] = reference["Gold Market"].fillna("")
            reference["Gold Market"] = reference["Gold Market"].astype(str).str.replace(",", "", regex=False)
            reference["Gold Market"] = reference["Gold Market"].str.replace("-", "", regex=False)
            reference["Gold Market"] = reference["Gold Market"].str.replace(" ", "", regex=False)
            reference["Gold Market"] = pd.to_numeric(reference["Gold Market"], errors="coerce")
        
        # Ensure Price Per Unit is numeric
        if "Price Per Unit" in reference.columns:
            reference["Price Per Unit"] = pd.to_numeric(reference["Price Per Unit"], errors="coerce")
            reference["Price Per Unit"] = reference["Price Per Unit"].fillna(0)
        
        # Generate multiplier tables using current market prices
        gold_factor = gold_table(gold_price)
        silver_factor = silver_table(silver_price)
        
        # Lookup and assign multipliers
        reference = lookup_multiplier(reference, gold_factor, silver_factor)
        
        # Create new price column - ensure both columns are numeric
        reference['Multiplier'] = pd.to_numeric(reference['Multiplier'], errors='coerce').fillna(1.0)
        reference['New Price'] = reference['Price Per Unit'] * reference['Multiplier']
        reference['New Price'] = reference['New Price'].round(2)
        
        # Ensure Variant Price column exists and is numeric in upload file
        if "Variant Price" not in upload.columns:
            upload["Variant Price"] = 0.0
        else:
            upload["Variant Price"] = pd.to_numeric(upload["Variant Price"], errors="coerce")
        
        # Ensure Variant SKU column exists
        if "Variant SKU" not in upload.columns:
            upload["Variant SKU"] = ""
        
        # Update variant prices in upload data
        upload_updated, successful_updates, skipped_blank_sku, skipped_no_match = update_variant_price_fixed(upload, reference)
        
        # Round variant prices to 2 decimal places
        upload_updated['Variant Price'] = pd.to_numeric(upload_updated['Variant Price'], errors='coerce')
        upload_updated['Variant Price'] = upload_updated['Variant Price'].round(2)
        
        # Remove special characters from all string columns in final output
        # Special focus on Body (HTML) column
        for col in upload_updated.columns:
            if upload_updated[col].dtype == 'object':
                upload_updated[col] = upload_updated[col].apply(
                    lambda x: str(x).replace('‚', '').replace('ƒ', '').replace('Ã', '').replace('Â', '').replace('Ã‚', '') if pd.notna(x) else x
                )
        
        # Additional cleaning specifically for Body (HTML) column if it exists
        if 'Body (HTML)' in upload_updated.columns:
            upload_updated['Body (HTML)'] = upload_updated['Body (HTML)'].str.replace('‚', '', regex=False)
            upload_updated['Body (HTML)'] = upload_updated['Body (HTML)'].str.replace('ƒ', '', regex=False)
            upload_updated['Body (HTML)'] = upload_updated['Body (HTML)'].str.replace('Ã', '', regex=False)
            upload_updated['Body (HTML)'] = upload_updated['Body (HTML)'].str.replace('Â', '', regex=False)
            upload_updated['Body (HTML)'] = upload_updated['Body (HTML)'].str.replace('Ã‚', '', regex=False)
        
        return upload_updated, {
            'successful_updates': successful_updates,
            'skipped_blank_sku': skipped_blank_sku,
            'skipped_no_match': skipped_no_match,
            'total_rows': len(upload_updated),
            'reference_rows': len(reference)
        }
        
    except Exception as e:
        st.error(f"Processing error: {str(e)}")
        st.error("Please check that your CSV files have the required columns:")
        st.error("- Reference file: Stock ID, Metal, Price Per Unit, Gold Market")
        st.error("- Product file: Variant SKU, Variant Price")
        return None, None

# Main App
def main():
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>💰 Precious Metals Processor</h1>
        <p>Upload your documents and get processed results with current market prices</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Create columns for layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Upload Reference Data")
        reference_file = st.file_uploader(
            "Upload your 'test for price updates.csv' file",
            type=['csv'],
            key="reference_file",
            help="This is your reference data file with pricing information"
        )
    
    with col2:
        st.subheader("📦 Upload Product Export")
        upload_file = st.file_uploader(
            "Upload your 'products_export.csv' file",
            type=['csv'],
            key="upload_file",
            help="This is your product export file that will be updated with new prices"
        )
    
    # Market prices section
    st.subheader("💰 Current Market Prices")
    col3, col4 = st.columns(2)
    
    with col3:
        gold_price = st.number_input(
            "🥇 Gold Price (per oz)",
            min_value=0.0,
            value=2000.0,
            step=0.01,
            format="%.2f"
        )
    
    with col4:
        silver_price = st.number_input(
            "🥈 Silver Price (per oz)",
            min_value=0.0,
            value=25.0,
            step=0.01,
            format="%.2f"
        )
    
    # Process button
    if st.button("🚀 Process Documents", type="primary", use_container_width=True):
        if reference_file is None or upload_file is None:
            st.error("Please upload both files before processing.")
        elif gold_price <= 0 or silver_price <= 0:
            st.error("Please enter valid gold and silver prices.")
        else:
            with st.spinner("Processing your documents..."):
                # Process the data
                result_df, stats = process_precious_metals_data(
                    reference_file, upload_file, gold_price, silver_price
                )
                
                if result_df is not None and stats is not None:
                    # Show success message
                    st.success("✅ Processing completed successfully!")
                    
                    # Show statistics
                    st.subheader("📊 Processing Statistics")
                    col5, col6, col7, col8 = st.columns(4)
                    
                    with col5:
                        st.metric("Total Rows", stats['total_rows'])
                    with col6:
                        st.metric("Successfully Updated", stats['successful_updates'])
                    with col7:
                        st.metric("Blank SKUs", stats['skipped_blank_sku'])
                    with col8:
                        st.metric("No Match Found", stats['skipped_no_match'])
                    
                    # Show preview of results
                    st.subheader("📋 Preview of Updated Data")
                    st.dataframe(result_df.head(10))
                    
                    # Download section
                    st.subheader("📥 Download Results")
                    
                    # Convert DataFrame to CSV
                    csv_buffer = io.StringIO()
                    result_df.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()
                    
                    # Create download button
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"processed_precious_metals_{timestamp}.csv"
                    
                    st.download_button(
                        label="📥 Download Processed Data",
                        data=csv_data,
                        file_name=filename,
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
                    
                    st.markdown(f"""
                    <div class="success-box">
                        <h4>🎉 Success!</h4>
                        <p>Your processed file is ready for download. The file contains all your original data with updated prices based on current market rates.</p>
                        <p><strong>Filename:</strong> {filename}</p>
                    </div>
                    """, unsafe_allow_html=True)

# Sidebar with instructions
with st.sidebar:
    st.header("📋 Instructions")
    st.markdown("""
    ### How to use:
    1. **Upload Reference Data**: Your pricing reference CSV file
    2. **Upload Product Export**: Your product export CSV file
    3. **Enter Market Prices**: Current gold and silver prices per ounce
    4. **Process**: Click the process button
    5. **Download**: Get your updated file with new prices
    
    ### File Requirements:
    - **Reference file** should contain: Stock ID, Metal, Price Per Unit, Gold Market
    - **Product file** should contain: Variant SKU, Variant Price
    - Files must be in CSV format
    
    ### Processing Logic:
    - Creates multiplier tables based on current market prices
    - Matches products by SKU/Stock ID
    - Updates prices using metal type (Gold/Silver) multipliers
    - Rounds all prices to 2 decimal places
    - Removes special encoding characters from final output
    """)
    
    st.header("💡 Tips")
    st.markdown("""
    - Make sure your CSV files use UTF-8 encoding
    - Remove any special characters from filenames
    - Check that Stock IDs match between files
    - Verify gold and silver prices before processing
    """)

if __name__ == "__main__":
    main()
