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

# Column name aliases — add more variants here if needed
SKU_ALIASES = ['Variant SKU', 'model']
PRICE_ALIASES = ['Variant Price', 'price']

def detect_column(df, aliases):
    """Return the first alias found in df.columns, or None."""
    for alias in aliases:
        if alias in df.columns:
            return alias
    return None

def gold_table(gold_market: float) -> pd.DataFrame:
    multipliers = [2.1, 1.7, 1.5, 1.35, 1.25, 1.175, 1.1, 1.0683, 1]
    factors = [2, 1.8, 1.6, 1.4, 1.3, 1.2, 1.1, 1.05, 1]
    results = [gold_market / m for m in multipliers]
    return pd.DataFrame({"Gold Market": results, "Multiplier": factors})

def silver_table(silver_market: float) -> pd.DataFrame:
    multipliers_s = [2.2, 1.5573, 1.4615, 1.3571, 1.3073, 1.2025, 1.1176, 1.0555, 1]
    factors_s = [2, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.05, 1]
    results_s = [silver_market / m for m in multipliers_s]
    return pd.DataFrame({"Gold Market": results_s, "Multiplier": factors_s})

def platinum_table(platinum_market: float) -> pd.DataFrame:
    multipliers_p = [2.2, 1.5573, 1.4615, 1.3571, 1.3073, 1.2025, 1.1176, 1.0555, 1]
    factors_p = [2, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1, 1.05, 1]
    results_p = [platinum_market / m for m in multipliers_p]
    return pd.DataFrame({"Gold Market": results_p, "Multiplier": factors_p})


def lookup_multiplier(reference, gold_factor, silver_factor, platinum_factor):
    gold_factor_sorted = gold_factor.sort_values('Gold Market').reset_index(drop=True)
    silver_factor_sorted = silver_factor.sort_values('Gold Market').reset_index(drop=True)
    platinum_factor_sorted = platinum_factor.sort_values('Gold Market').reset_index(drop=True)

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
        if metal_type == 'S/S':
            return find_multiplier_above(market_value, silver_factor_sorted)
        elif metal_type == 'PLATINUM':
            return find_multiplier_above(market_value, platinum_factor_sorted)
        else:
            return find_multiplier_above(market_value, gold_factor_sorted)

    reference['Multiplier'] = reference.apply(lookup_multiplier_by_metal, axis=1)
    return reference

def update_variant_price_fixed(upload, reference, sku_col, price_col):
    """Update prices based on reference data, using detected column names."""
    result = upload.copy()

    result[sku_col] = result[sku_col].astype(str).str.strip()
    ref_clean = reference.copy()
    ref_clean['Stock ID'] = ref_clean['Stock ID'].astype(str).str.strip()

    result.loc[result[sku_col] == 'nan', sku_col] = ''
    ref_clean.loc[ref_clean['Stock ID'] == 'nan', 'Stock ID'] = ''

    price_lookup = {}
    for idx, row in ref_clean.iterrows():
        stock_id = row['Stock ID']
        new_price = row['New Price']
        if (stock_id != '' and not pd.isna(stock_id) and
                not pd.isna(new_price) and str(stock_id) != 'nan'):
            price_lookup[stock_id] = new_price

    successful_updates = 0
    skipped_blank_sku = 0
    skipped_no_match = 0

    for idx in result.index:
        variant_sku = result.loc[idx, sku_col]
        if variant_sku == '' or pd.isna(variant_sku):
            skipped_blank_sku += 1
            continue
        if variant_sku in price_lookup:
            new_price = price_lookup[variant_sku]
            if not pd.isna(new_price):
                result.loc[idx, price_col] = new_price
                successful_updates += 1
        else:
            skipped_no_match += 1

    return result, successful_updates, skipped_blank_sku, skipped_no_match

def process_precious_metals_data(reference_file, upload_file, gold_price, silver_price, platinum_price):
    try:
        reference = pd.read_csv(reference_file, encoding='latin1')
        upload = pd.read_csv(upload_file, encoding='latin1')

        # Detect SKU and Price columns
        sku_col = detect_column(upload, SKU_ALIASES)
        price_col = detect_column(upload, PRICE_ALIASES)

        if sku_col is None:
            st.error(f"Could not find a SKU column. Expected one of: {SKU_ALIASES}")
            return None, None
        if price_col is None:
            st.error(f"Could not find a Price column. Expected one of: {PRICE_ALIASES}")
            return None, None

        st.info(f"Detected columns → SKU: **{sku_col}** | Price: **{price_col}**")

        # Process reference data
        reference["Date Created"] = pd.to_datetime(reference["Date Created"], errors="coerce")
        reference["Date Last Price Change"] = pd.to_datetime(reference["Date Last Price Change"], errors="coerce")
        reference["Last Stocked"] = pd.to_datetime(reference["Last Stocked"], errors="coerce")

        reference["Max Date"] = reference[
            ["Date Created", "Date Last Price Change", "Last Stocked"]
        ].max(axis=1)

        reference = reference.sort_values(by="Max Date", ascending=False).reset_index(drop=True)

        columns_to_drop = ["Date Created", "Date Last Price Change", "Last Stocked",
                           "Bar Code ID", "Department", "Description", "Qty On Hand",
                           "Type", "Vendor Name", "UID", "Vendor UID", "Photo"]
        columns_to_drop = [col for col in columns_to_drop if col in reference.columns]
        reference = reference.drop(columns=columns_to_drop)

        today = pd.Timestamp.today().normalize()
        reference = reference[reference["Max Date"] <= today].reset_index(drop=True)

        reference["Stock ID"] = reference["Stock ID"].fillna("").astype(str).str.replace(" ", "", regex=False)
        reference["Metal"] = reference["Metal"].fillna("").astype(str).str.replace(" ", "", regex=False)
        reference["Metal"] = reference["Metal"].str.replace("SS", "S/S", regex=False)
        reference = reference.drop_duplicates(subset=["Stock ID"]).reset_index(drop=True)

        if "Gold Market" in reference.columns:
            reference["Gold Market"] = reference["Gold Market"].fillna("")
            reference["Gold Market"] = reference["Gold Market"].astype(str).str.replace(",", "", regex=False)
            reference["Gold Market"] = reference["Gold Market"].str.replace("-", "", regex=False)
            reference["Gold Market"] = reference["Gold Market"].str.replace(" ", "", regex=False)
            reference["Gold Market"] = pd.to_numeric(reference["Gold Market"], errors="coerce")

        if "Price Per Unit" in reference.columns:
            reference["Price Per Unit"] = pd.to_numeric(reference["Price Per Unit"], errors="coerce")
            reference["Price Per Unit"] = reference["Price Per Unit"].fillna(0)

        gold_factor = gold_table(gold_price)
        silver_factor = silver_table(silver_price)
        platinum_factor = platinum_table(platinum_price)

        reference = lookup_multiplier(reference, gold_factor, silver_factor, platinum_factor)

        reference['Multiplier'] = pd.to_numeric(reference['Multiplier'], errors='coerce').fillna(1.0)
        reference['New Price'] = reference['Price Per Unit'] * reference['Multiplier']
        reference['New Price'] = reference['New Price'].round(2)

        # Ensure price column exists and is numeric
        if price_col not in upload.columns:
            upload[price_col] = 0.0
        else:
            upload[price_col] = pd.to_numeric(upload[price_col], errors="coerce")

        # Ensure SKU column exists
        if sku_col not in upload.columns:
            upload[sku_col] = ""

        upload_updated, successful_updates, skipped_blank_sku, skipped_no_match = update_variant_price_fixed(
            upload, reference, sku_col, price_col
        )

        upload_updated[price_col] = pd.to_numeric(upload_updated[price_col], errors='coerce')
        upload_updated[price_col] = upload_updated[price_col].round(2)

        for col in upload_updated.columns:
            if upload_updated[col].dtype == 'object':
                upload_updated[col] = upload_updated[col].apply(
                    lambda x: str(x).replace('‚', '').replace('ƒ', '').replace('Ã', '').replace('Â', '').replace('Ã‚', '') if pd.notna(x) else x
                )

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
            'reference_rows': len(reference),
            'sku_col': sku_col,
            'price_col': price_col,
        }

    except Exception as e:
        st.error(f"Processing error: {str(e)}")
        st.error("Please check that your CSV files have the required columns:")
        st.error(f"- Reference file: Stock ID, Metal, Price Per Unit, Gold Market")
        st.error(f"- Product file: one of {SKU_ALIASES} and one of {PRICE_ALIASES}")
        return None, None


def main():
    st.markdown("""
    <div class="main-header">
        <h1>💰 Precious Metals Processor</h1>
        <p>Upload your documents and get processed results with current market prices</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Upload Reference Data")
        reference_file = st.file_uploader(
            "Upload your 'test for price updates.csv' file",
            type=['csv'],
            key="reference_file",
            help="Reference data file with pricing information"
        )

    with col2:
        st.subheader("📦 Upload Product Export")
        upload_file = st.file_uploader(
            "Upload your 'products_export.csv' file",
            type=['csv'],
            key="upload_file",
            help="Product export file that will be updated with new prices"
        )

    st.subheader("💰 Current Market Prices")
    col3, col4, col5 = st.columns(3)

    with col3:
        gold_price = st.number_input("🥇 Gold Price (per oz)", min_value=0.0, value=2000.0, step=0.01, format="%.2f")
    with col4:
        silver_price = st.number_input("🥈 Silver Price (per oz)", min_value=0.0, value=25.0, step=0.01, format="%.2f")
    with col5:
        platinum_price = st.number_input("⬜ Platinum Price (per oz)", min_value=0.0, value=1000.0, step=0.01, format="%.2f")

    if st.button("🚀 Process Documents", type="primary", use_container_width=True):
        if reference_file is None or upload_file is None:
            st.error("Please upload both files before processing.")
        elif gold_price <= 0 or silver_price <= 0 or platinum_price <= 0:
            st.error("Please enter valid gold, silver, and platinum prices.")
        else:
            with st.spinner("Processing your documents..."):
                result_df, stats = process_precious_metals_data(
                    reference_file, upload_file, gold_price, silver_price, platinum_price
                )

                if result_df is not None and stats is not None:
                    st.success("✅ Processing completed successfully!")

                    st.subheader("📊 Processing Statistics")
                    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)

                    with stat_col1:
                        st.metric("Total Rows", stats['total_rows'])
                    with stat_col2:
                        st.metric("Successfully Updated", stats['successful_updates'])
                    with stat_col3:
                        st.metric("Blank SKUs", stats['skipped_blank_sku'])
                    with stat_col4:
                        st.metric("No Match Found", stats['skipped_no_match'])

                    st.subheader("📋 Preview of Updated Data")
                    st.dataframe(result_df.head(10))

                    st.subheader("📥 Download Results")

                    csv_buffer = io.StringIO()
                    result_df.to_csv(csv_buffer, index=False)
                    csv_data = csv_buffer.getvalue()

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
                        <p>Your processed file is ready for download with updated prices based on current market rates.</p>
                        <p><strong>SKU column used:</strong> {stats['sku_col']} &nbsp;|&nbsp; <strong>Price column used:</strong> {stats['price_col']}</p>
                        <p><strong>Filename:</strong> {filename}</p>
                    </div>
                    """, unsafe_allow_html=True)


with st.sidebar:
    st.header("📋 Instructions")
    st.markdown("""
    ### How to use:
    1. **Upload Reference Data**: Your pricing reference CSV file
    2. **Upload Product Export**: Your product export CSV file
    3. **Enter Market Prices**: Current gold, silver, and platinum prices per ounce
    4. **Process**: Click the process button
    5. **Download**: Get your updated file with new prices

    ### File Requirements:
    - **Reference file** should contain: Stock ID, Metal, Price Per Unit, Gold Market
    - **Product file** should contain a SKU column (`Variant SKU` or `model`) and a price column (`Variant Price` or `Price`)
    - Files must be in CSV format

    ### Metal Types Supported:
    - **Gold**: Uses gold multiplier table
    - **S/S (Silver)**: Uses silver multiplier table
    - **PLATINUM**: Uses platinum multiplier table

    ### Processing Logic:
    - Creates multiplier tables based on current market prices
    - Matches products by SKU/Stock ID
    - Updates prices using metal type multipliers
    - Rounds all prices to 2 decimal places
    - Removes special encoding characters from final output
    """)

    st.header("💡 Tips")
    st.markdown("""
    - Make sure your CSV files use UTF-8 encoding
    - Remove any special characters from filenames
    - Check that Stock IDs match between files
    - Verify gold, silver, and platinum prices before processing
    - Accepted SKU column names: `Variant SKU`, `model`
    - Accepted Price column names: `Variant Price`, `Price`
    """)

if __name__ == "__main__":
    main()
