import pandas as pd
import re
from config_manager import config_manager
import os
from convert_to_csv import convert_pdf_to_csv
from convert_to_csv import convert_xls_to_csv
from convert_to_csv import convert_xslx_to_csv
import csv
import hashlib
from logger import get_logger


log = get_logger()


def assign_category(row):
    text = " ".join(str(row[col]).lower() for col in ['description', 'details'] if col in row and pd.notna(row[col]))
    for keyword, category in config_manager.configs['local_config.yaml']['categories']['sub'].items():
        if keyword in text:
            return category
    return 'uncategorized'

def assign_master_category(category):
    """Return the master category for a given subcategory"""
    for master, subcategories in config_manager.configs['category_config.yaml']['categories']['master'].items():
        if category in subcategories:
            return master
    return "uncategorized"

def process_statement(file_path):
    log.info(f'processing - {file_path}')
    mapping = {'kibutz': ['כלבו', 'חיוב חשמל לחודש', 'חדר אוכל', 'חיוב מים'],
               'credit_card': ['שם כרטיס', 'ארבע ספרות אחרונות', 'ויזה', 'מסתיים ב', 'קורפוריט', 'מסטרקארד'],
               'bank': ['יתרה בחשבון', 'מסגרת אשראי', 'תנועות אחרונות']
               }
    matches = {key: [] for key in mapping}  # Store matches found
    if os.path.splitext(file_path)[1] == '.pdf':
        file_path = convert_pdf_to_csv(file_path) # change pointer to new (csv) file
    elif os.path.splitext(file_path)[1] == '.xls':
        file_path = convert_xls_to_csv(file_path)
    elif os.path.splitext(file_path)[1] == '.xlsx':
        file_path = convert_xslx_to_csv(file_path)
    elif os.path.splitex(file_path)[1] != '.csv':
        log.info(f'unsupported file format - {os.path.splitex(file_path)[1]}')
        return None

    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)

        for row in reader:
            row_text = ' '.join(row)

            for category, phrases in mapping.items():
                for phrase in phrases:
                    if re.search(phrase.lower(), row_text.lower()):
                        matches[category].append(phrase)
    for match, phrases in matches.items():
        if len(phrases) >= 2: # found at least 2 matching phrases in statement
            statement_type = match
            log.info(f'statement identified as {statement_type}')
    if statement_type == 'kibutz':
        return process_kibutz_statement(file_path)
    elif statement_type == 'credit_card':
        return process_credit_card_statement(file_path)
    elif statement_type == 'bank':
        return process_bank_statement(file_path)

    log.info('something went wrong during process_statement()')
    return None

def generate_id(date, val_list):
    """
    generate an int10 unique id by given values from a transaction.
    must include transaction date.
    """
    raw_string = str(date)
    for val in val_list:
        val = str(val).replace(',', '').replace(' ', '')
        raw_string = f'{raw_string}|{val}'

    hash_val = hashlib.md5(raw_string.encode("utf-8")).hexdigest() # encode by hashing (string -> hex)
    return int(hash_val, 16) % (10**10) # (hex -> int16 -> int10)

def ensure_unique_ids(df):
    """ this is a protection against transaction with similar variables (to prevent duplicate ids -> ignored transactions by db) """
    seen = set()
    new_ids = []

    for id in df['id']:
        original = id
        while id in seen:
            id += 1
        seen.add(id)
        new_ids.append(id)
    df['id'] = new_ids
    return df

def process_bank_statement(csv_path):
    column_mapping = config_manager.configs['column_mapping.yaml']['bank']
    # payment_days = ['10', '02']
    
    # Load CSV without setting headers initially
    df = pd.read_csv(csv_path, header=None, dtype=str)  # Load all as strings to avoid conversion issues
    df = pd.DataFrame(df)
    # perliminary cleaning
    df = df.iloc[6:] # remove first n rows # TODO: this is very fregile, replace with more robust logic, mabey automatic header detection?
    new_headers = list(df.iloc[0])  # Get first row as column headers    
    df.columns = new_headers  # Set headers
    df = df.iloc[1:].reset_index(drop=True)
    df = df.dropna(axis=1, how="all")  # Drops columns where all values are NaN
    df = df.drop(columns=['יתרה בש"ח', 'תאריך ערך'])

    # Rename columns based on the mapping
    df.rename(columns=lambda x: column_mapping.get(x.strip(), x.strip().lower()), inplace=True)

    # add categories
    df["category"] = df.apply(assign_category, axis=1)

    # convert data types
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format='%d/%m/%y')
    df = df.dropna(subset=['date'])  # Remove NaT values (invalid dates)
    df["debit"] = df["debit"].astype(str).str.replace(",", "").astype(float)
    df["credit"] = df["credit"].astype(str).str.replace(",", "").astype(float)
    df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
    df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
    df["reference"] = pd.to_numeric(df["reference"], errors="coerce").fillna(0)

    # parsing logic 
    dates_tolerance = 4 # TODO: move to config
    dates_range = list(range(10 - dates_tolerance, 10 + dates_tolerance)) # TODO: add this as feature to all future parsing logic?
    df.loc[(df['category'] == 'check') & (df['date'].dt.day.isin(dates_range)), 'category'] = 'rent'
    df["master_category"] = df["category"].apply(lambda c: assign_master_category(c))

    df['id'] = df.apply(lambda row: generate_id(row['date'],[
        row.get('source'), row.get('category'), row.get('debit'), row.get('credit'), row.get('reference'), row.get('description'),
    ]), axis=1)
    df = ensure_unique_ids(df)

    return df, 'bank'

def process_credit_card_statement(csv_path):
    column_mapping = config_manager.configs['column_mapping.yaml']['credit_card']

    # Load CSV without setting headers initially
    df = pd.read_csv(csv_path, header=None, dtype=str)  # Load all as strings to avoid conversion issues

    # Initialize variables
    current_credit_card = None
    transactions = []

    # Loop through rows to process transactions
    for index, row in df.iterrows():
        row_data = row.dropna().tolist()  # Remove NaN values from row

        if (len(row_data) == 1 or index == 0) and any(char.isdigit() for char in row_data[0]):  # If row contains a credit card number
            credit_card_number = "".join(re.findall(r"\d+", row_data[0]))
            if credit_card_number:  # If a valid number is found, store it
                current_credit_card = credit_card_number
        elif len(row_data) > 1:  # If row is a transaction (multiple columns)
            row_dict = row.to_dict()
            if not transactions:
                row_dict[len(row_dict)] = 'card'
            else:
                row_dict[len(row_dict)] = current_credit_card  # Assign credit card number
            transactions.append(row_dict)

    # Convert the cleaned transactions into a DataFrame
    df = pd.DataFrame(transactions)

    # Set the first row as column names and remove it from data
    new_headers = list(df.iloc[0])  # Get first row as column headers
    
    df.columns = new_headers  # Set headers
    df = df.iloc[1:].reset_index(drop=True)

    # Drop rows that dont contain a date (not transactions)
    df["תאריך חיוב"] = pd.to_datetime(df["תאריך חיוב"], errors="coerce")  # Invalid dates become NaT
    df = df.dropna(subset=["תאריך חיוב"])  # Remove NaT values (invalid dates)

    # Rename columns based on the mapping
    df.rename(columns=lambda x: column_mapping.get(x.strip(), x.strip().lower()), inplace=True)

    # add category
    df["category"] = df.apply(assign_category, axis=1)
    df["master_category"] = df["category"].apply(lambda c: assign_master_category(c))

    # add source
    df['source'] = 'credit card'

     # convert data types
    df["billing_date"] = pd.to_datetime(df["billing_date"], errors="coerce", format="%d/%m/%Y")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce", format="%d/%m/%Y")
    df["credit_bill"] = df["credit_bill"].astype(str).str.replace(",", "").astype(float)
    df["credit_bill"] = pd.to_numeric(df["credit_bill"], errors="coerce").fillna(0)
    df["card"] = pd.to_numeric(df["card"], errors="coerce")   

    df['id'] = df.apply(lambda row: generate_id(row['transaction_date'],[
        row.get('source'), row.get('category'), row.get('card'), row.get('credit_bill'), row.get('billing_date'),
    ]), axis=1)
    df = ensure_unique_ids(df)

    return df, 'credit_card'

def process_kibutz_statement(csv_path):
    column_mapping = config_manager.configs['column_mapping.yaml']['kibutz']
    phrases_to_remove = ["העברה לבנק", 'סה"כ כללי', "יתרת סגירה"]

    try:
        df = pd.read_csv(
                            csv_path,
                            delimiter=",",          # can also be - ';' or '\t'
                            encoding="utf-8",       
                            skipinitialspace=True,  # Removes leading/trailing spaces
                            dtype=str               # Load all as strings initially to avoid conversion issues
                        )
    except Exception as e:
        log.error(f'failed to read csv - {e}')
        return None
    
    # Identify and remove the first row containing "Unnamed"
    df = df[df.apply(lambda row: not row.astype(str).str.contains("Unnamed", na=False, regex=True).all(), axis=1)]

    # Reset index after removing the unwanted row
    df.reset_index(drop=True, inplace=True)

    # Set the first remaining row as the new header
    df.columns = df.iloc[0]  # Set first row as column names
    df = df[1:].reset_index(drop=True)  # Drop the new header row from data

    # remove all columns with nan headers
    df = df.loc[:, ~df.columns.isna()]
    df = df.dropna(axis=0, how='all') # remove nan rows

    # Convert all columns to string type for safe searching
    df = df.astype(str)

    # Create regex pattern from the list (joins phrases with '|')
    pattern = "|".join(map(re.escape, phrases_to_remove))  # `re.escape` ensures special characters don't break regex

    # Remove rows where ANY column contains one of the phrases
    df = df[~df.apply(lambda row: row.str.contains(pattern, case=False, na=False, regex=True).any(), axis=1)]

    # Rename columns based on the mapping
    df.rename(columns=lambda x: column_mapping.get(x.strip(), x.strip().lower()), inplace=True)

    # add category
    df["category"] = df.apply(assign_category, axis=1)
    df["master_category"] = df["category"].apply(lambda c: assign_master_category(c))


    #add source
    df['source'] = 'kibutz'

    # convert data types
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="%d/%m/%y").dt.date
    df["debit"] = df["debit"].astype(str).str.replace(",", "").astype(float)
    df["debit"] = pd.to_numeric(df["debit"], errors="coerce").fillna(0)
    df["credit"] = df["credit"].astype(str).str.replace(",", "").astype(float)
    df["credit"] = pd.to_numeric(df["credit"], errors="coerce").fillna(0)
    df["amount"] = df["amount"].astype(str).str.replace(",", "").astype(float)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    
    df['id'] = df.apply(lambda row: generate_id(row['date'],[
        row.get('source'), row.get('category'), row.get('sub_id'), row.get('debit'), row.get('credit'),
    ]), axis=1)
    df = ensure_unique_ids(df)

    return df, 'kibutz'

def reverse_text(text):
    return text[::-1] if isinstance(text, str) else text
