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
    text = " ".join(str(row[col]) for col in ['description', 'details'] if col in row and pd.notna(row[col]))
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

def smart_parse_dates(df, column_name):
    # Check if the first non-null value contains a time (:) or not
    sample_value = df[column_name].dropna().iloc[0]    
    if isinstance(sample_value, str) and ':' in sample_value:
        df[column_name] = pd.to_datetime(df[column_name], errors='coerce').dt.date
    else:
        df[column_name] = pd.to_datetime(df[column_name], errors='coerce', format='%d/%m/%Y').dt.date    
    return df

def check_triggers(row, process_triggers, card_triggers, billing_date_triggers):
    identified_process = None
    identified_card = None
    identified_billing_date = None

    if any(bill_phrase in (row if isinstance(row, str) else ''.join(row)) for bill_phrase in billing_date_triggers): # check for billing date 
        for bill_phrase in billing_date_triggers:
            match = re.search(r'\b\d{2}/\d{2}/(\d{2}|\d{4})\b', str(row))
            if match:
                identified_billing_date = match.group()

    if any(logic in row for logic in process_triggers): # if any row contains process type
        for process in process_triggers:
            if process in str(row):
                identified_process = process
                break
    if any(card in str(row) for card in card_triggers):  # If row contains a credit card number
            for card in card_triggers:
                # Match card name followed by optional space and digits
                for col in row:
                    match = re.search(rf"{card}.*?(\d+)", col)              
                    if match:
                        identified_card = match.group(1)  # Return only the digits after the card
                        break

    return identified_card, identified_process, identified_billing_date

def format_credit_card_statement(csv_path):
    """ 
    split all sub-tables in csv table to different df chunks 
    assumptions: 
    1. each statement comes partitioned to cards and processes (card number, local - international)
    We create each chunk when we detect a trigger - credit card type or process type
    """
    def flush_chunk():
        nonlocal current_chunk
        if current_chunk:
            all_chunks.append(pd.DataFrame(current_chunk))
            current_chunk = []


    # Load CSV without setting headers initially
    df = pd.read_csv(csv_path, header=None, dtype=str)  # Load all as strings to avoid conversion issues

    # Initialize variables
    current_credit_card = None
    current_billing_date = None
    card_types = ['ויזה', 'קורפוריט', 'מסטרקארד']
    process_types = ['עסקאות בארץ', 'עסקאות בחו˝ל']
    billing_phrases = ['מועד חיוב', 'עסקאות לחיוב ב-']
    rows_to_ignore = ['סך חיוב בש"ח:', 'TOTAL FOR DATE']
    current_chunk = []
    all_chunks = []

    for _, row in df.iterrows():
        row_data = row.dropna().tolist()  # Remove NaN values from row 
        identified_card, identified_process, billing_date = check_triggers(row_data, process_types, card_types, billing_phrases)

        if billing_date:
            current_billing_date = billing_date
            billing_date = None

        if identified_card:
            current_credit_card = identified_card            
            identified_card = None
            flush_chunk()
            continue

        if identified_process:
            identified_process = None
            flush_chunk()
            continue

        if len(row_data) > 1 and current_credit_card and not any(phrase in row_data for phrase in rows_to_ignore):
            row_dict = row.to_dict()
            if not current_chunk:
                row_dict[len(row_dict)] = 'card'
                row_dict[len(row_dict)] = 'billing_date'
            else:
                row_dict[len(row_dict)] = current_credit_card
                row_dict[len(row_dict)] = current_billing_date
            current_chunk.append(row_dict)
    flush_chunk()
    return all_chunks

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

    df_list = format_credit_card_statement(csv_path)
    processed_dfs = []

    for df in df_list:
        # Convert the cleaned transactions into a DataFrame
        df = pd.DataFrame(df)

        # Set the first row as column names and remove it from data
        new_headers = list(df.iloc[0])  # Get first row as column headers
        
        df.columns = new_headers  # Set headers
        df = df.iloc[1:].reset_index(drop=True)
        df = df.dropna(axis=1, how='all')
        df.columns = [col.replace("\n", " ").strip() for col in df.columns]
        # Rename columns based on the mapping
        df = df.rename(columns=lambda x: column_mapping.get(x.strip(), None))
        # df.rename(columns=lambda x: column_mapping.get(x.strip(), x.strip().lower()), inplace=True)
        df = df[[col for col in df.columns if col is not None]] # drop columns that where not renamed

        df["category"] = df.apply(assign_category, axis=1)
        df["master_category"] = df["category"].apply(lambda c: assign_master_category(c))
        df['source'] = 'credit card'

        # convert data types 
        df = smart_parse_dates(df, 'transaction_date')
        df = df.dropna(subset=['transaction_date'])  # Remove NaT values (invalid dates)
        df["credit_bill"] = df["credit_bill"].astype(str).str.replace(",", "").astype(float)
        df["credit_bill"] = pd.to_numeric(df["credit_bill"], errors="coerce").fillna(0)
        df["card"] = pd.to_numeric(df["card"], errors="coerce")   

        df['id'] = df.apply(lambda row: generate_id(row['transaction_date'],[
            row.get('source'), row.get('category'), row.get('card'), row.get('credit_bill'), row.get('details'), row.get('billing_date')
        ]), axis=1)
        df = ensure_unique_ids(df)

        processed_dfs.append(df)

    return pd.concat(processed_dfs, ignore_index=True), 'credit_card'

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


def split_by_card_and_process_type(csv_path):
    df = pd.read_csv(csv_path, header=None, dtype=str)  # Load all as strings

    card_types = ['ויזה', 'קורפוריט', 'מסטרקארד']
    proccess_types = ['עסקאות בארץ', 'עסקאות בחו"ל']

    current_credit_card = None
    current_process_type = None
    current_chunk = []
    all_chunks = []

    def flush_chunk():
        nonlocal current_chunk
        if current_chunk:
            all_chunks.append(pd.DataFrame(current_chunk))
            current_chunk = []

    for _, row in df.iterrows():
        row_data = row.dropna().tolist()
        text = " ".join(row_data)

        # Detect process type
        for proc in proccess_types:
            if proc in text:
                if proc != current_process_type:
                    flush_chunk()
                    current_process_type = proc
                break

        # Detect card number
        for card in card_types:
            if card in text:
                for col in row_data:
                    match = re.search(rf"{card}.*?(\d+)", col)
                    if match:
                        new_card_number = match.group(1)
                        if new_card_number != current_credit_card:
                            flush_chunk()
                            current_credit_card = new_card_number
                        break
                break

        if len(row_data) > 1 and current_credit_card:
            row_dict = row.to_dict()
            row_dict['card'] = current_credit_card
            row_dict['process_type'] = current_process_type
            current_chunk.append(row_dict)

    flush_chunk()
    return all_chunks

