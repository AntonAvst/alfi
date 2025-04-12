import tabula
import pandas as pd
from bs4 import BeautifulSoup
import pdfplumber
import os
from io import StringIO

# def convert_pdf_to_csv(pdf_path):
#     # extract all tables from the PDF into a list of DataFrames.
#     tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)

#     # Save the first table with utf-8 encoding
#     if tables:
#         output_csv = "output.csv"
#         tables[0].to_csv(output_csv, index=False, encoding="windows-1255")  # Change encoding if necessary
#         print(f"Table extracted and saved to {output_csv} with UTF-8 encoding")
#     else:
#         print("No tables were found.")
    
#     return output_csv

def flip_hebrew_text(text):
    # Flip text if it contains Hebrew characters
    # Hebrew characters are in the Unicode range from U+0590 to U+05FF
    if any('\u0590' <= char <= '\u05FF' for char in text):
        return text[::-1]  # Reverse the string
    return text

def convert_pdf_to_csv(pdf_path):
    output_csv = 'output.csv'
    if os.path.exists(output_csv):
        os.remove(output_csv)
    
    with pdfplumber.open(pdf_path) as pdf:
        all_data = []
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                df = pd.DataFrame(table[1:], columns=table[0])

                # Flip Hebrew text in the entire DataFrame
                df = df.map(lambda x: flip_hebrew_text(str(x)) if isinstance(x, str) else x)                
                all_data.append(df)

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            # Ensure UTF-8 encoding for all text
            final_df = final_df.map(lambda x: x.encode('utf-8').decode('utf-8') if isinstance(x, str) else x)
            
            # Save to CSV with utf-8-sig encoding to preserve Hebrew
            final_df.to_csv(output_csv, index=False, encoding="utf-8-sig")
            print(f"Extracted {len(all_data)} tables to CSV at {output_csv}")
        else:
            print("No tables found.")
    return output_csv

def convert_xls_to_csv(xls_path):
    with open(xls_path, "r", encoding="utf-8") as file:
        soup = BeautifulSoup(file, "html.parser")
    tables = soup.find_all("table")

    if not tables:
        print("No tables found in the HTML file.")
        exit()

    largest_table = None
    max_size = 0

    for table in tables:
        df = pd.read_html(StringIO(str(table)))[0]  # Convert to DataFrame
        table_size = df.shape[0] * df.shape[1]  # Total elements (rows * columns)

        if table_size > max_size:  # Compare with the largest found so far
            max_size = table_size
            largest_table = df

    # Save the largest table to CSV
    if largest_table is not None:
        largest_table.to_csv("main_table.csv", index=False, encoding="utf-8")
        print(f"Largest table saved as main_table.csv with {largest_table.shape[0]} rows and {largest_table.shape[1]} columns.")
    else:
        print("No valid tables found.")

        print("Conversion completed successfully.")
    return 'main_table.csv'

def convert_xslx_to_csv(xslx_path):
    df_sheets = pd.read_excel(xslx_path, sheet_name=None)  # Read all sheets

    largest_sheet_name = max(df_sheets, key=lambda name:df_sheets[name].shape[0] * df_sheets[name].shape[1])
    largest_sheet = df_sheets[largest_sheet_name]
    csv_output = f"{largest_sheet_name}.csv"
    largest_sheet.to_csv(csv_output, index=False, encoding="utf-8")
    return csv_output

if __name__ == '__main__':
    convert_xslx_to_csv('כל הכרטיסים.xlsx')
