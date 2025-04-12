import sqlite3
from transactions import process_statement
import pandas as pd
from config_manager import config_manager


class DataBaseManager:
    def __init__(self, db_path='financial_data.db'):
        self.db_path = db_path
        self.connection, self.cursor = self.connect_to_database(self.db_path)
        for schema in config_manager.configs['schema.yaml']:
            self.initialize_database(schema=config_manager.configs['schema.yaml'][schema], table_name=schema)

    def connect_to_database(self, db_path):
        # Connect to SQLite database (or create it if it doesn't exist)
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        return connection, cursor

    def initialize_database(self, schema, table_name):
        # Initialize the Database (Create Table if Not Exists)
        # SQL command to create a table for storing financial statements

        schema_string = ''
        for k,v in schema.items():
            schema_string = schema_string + f'{k} {v},\n'
        schema_string = schema_string[:-2]

        create_table_query = f'CREATE TABLE IF NOT EXISTS {table_name} ({schema_string});'

        try:
            self.cursor.execute(create_table_query)
            self.connection.commit()
            print('db created successfully')
        except Exception as e:
            print(f'failed to create db: {e}')

    def insert_df_to_table(self, df, table_name):
        # insert to db
        try:
            df.to_sql(table_name, self.connection, if_exists='append', index=False)
        except Exception as e:
            print(f'failed to preocess statment: {e}')

    def fetch_table(self, table_name):         
         """Fetches all rows from the given table """
         df = pd.read_sql(f'SELECT * FROM {table_name}', self.connection)
         return df
    
    def batch_upload(self, file_list):
        """
        receive a file list of statements - process statements and upload each statement to the corresponding table in db
        """
        for file in file_list:
            df, table_name = process_statement(file)
            self.insert_df_to_table(df, table_name)

    def get_table_names(self):
        query = "SELECT name FROM sqlite_master WHERE type='table';"
        self.cursor.execute(query)
        tables = [table[0] for table in self.cursor.fetchall()]
        return tables
    
    def get_categories_total(self, start_date, end_date):
        query = """
                SELECT category, SUM(total) AS grand_total
                FROM (
                    SELECT category, SUM(COALESCE(debit, 0) + COALESCE(credit, 0)) AS total
                    FROM kibutz
                    WHERE category IS NOT NULL
                    AND DATE(date) BETWEEN ? AND ?
                    GROUP BY category

                    UNION ALL

                    SELECT category, SUM(credit_bill) AS total
                    FROM credit_card
                    WHERE category IS NOT NULL
                    AND transaction_date BETWEEN ? AND ?
                    GROUP BY category

                    UNION ALL

                    SELECT category, SUM(COALESCE(debit, 0) + COALESCE(credit, 0)) AS total
                    FROM bank
                    WHERE category IS NOT NULL
                    AND date BETWEEN ? AND ?
                    GROUP BY category
                ) AS all_data
                GROUP BY category
                ORDER BY grand_total DESC;
                """
        df = pd.read_sql_query(query, self.connection, params=(start_date, end_date, start_date, end_date, start_date, end_date))
        return df
    
    def get_category_totals_by_month(self, start_date, end_date):
        query = """
                SELECT master_category, category, SUM(total) AS amount
                FROM (
                    SELECT master_category, category, SUM(COALESCE(debit, 0) + COALESCE(credit, 0)) AS total
                    FROM kibutz
                    WHERE category IS NOT NULL
                    AND DATE(date) BETWEEN ? AND ?
                    GROUP BY master_category, category

                    UNION ALL

                    SELECT master_category, category, SUM(credit_bill) AS total
                    FROM credit_card
                    WHERE category IS NOT NULL
                    AND DATE(transaction_date) BETWEEN ? AND ?
                    GROUP BY master_category, category

                    UNION ALL

                    SELECT master_category, category, SUM(COALESCE(debit, 0) + COALESCE(credit, 0)) AS total
                    FROM bank
                    WHERE category IS NOT NULL
                    AND DATE(date) BETWEEN ? AND ?
                    GROUP BY master_category, category
                ) AS combined
                GROUP BY master_category, category
                ORDER BY master_category, amount DESC;
                """

        df = pd.read_sql_query(query, self.connection, params=(
            start_date, end_date,  # for kibutz
            start_date, end_date,  # for credit_card
            start_date, end_date   # for bank
        ))
        return df
    
    def get_monthly_summary_all_tables_by_master_category(self, year):
        query = """
                SELECT month, master_category, SUM(total) AS grand_total
                FROM (
                    -- Kibutz table
                    SELECT 
                        strftime('%m', date) AS month,
                        master_category,
                        SUM(COALESCE(debit, 0) - COALESCE(credit, 0)) AS total
                    FROM kibutz
                    WHERE master_category IS NOT NULL
                    AND strftime('%Y', date) = ?
                    GROUP BY month, master_category

                    UNION ALL

                    -- Credit card table
                    SELECT 
                        strftime('%m', transaction_date) AS month,
                        master_category,
                        SUM(-credit_bill) AS total
                    FROM credit_card
                    WHERE master_category IS NOT NULL
                    AND strftime('%Y', transaction_date) = ?
                    GROUP BY month, master_category

                    UNION ALL

                    -- Bank table
                    SELECT 
                        strftime('%m', date) AS month,
                        master_category,
                        SUM(COALESCE(debit, 0) + COALESCE(credit, 0)) AS total
                    FROM bank
                    WHERE master_category IS NOT NULL
                    AND strftime('%Y', date) = ?
                    GROUP BY month, master_category
                ) AS all_data
                GROUP BY month, master_category
                ORDER BY month, grand_total DESC
                """

        df = pd.read_sql_query(query, self.connection, params=(year, year, year))
        pivot = df.pivot_table(index="month", columns="master_category", values="grand_total", fill_value=0)
        pivot.index = pd.to_datetime(pivot.index, format='%m').strftime('%B')
        return pivot.reset_index()
    
    def update_transaction_category(self, table, id, category):
        query = f""" 
                UPDATE {table}
                SET category = ?, master_category = ?
                WHERE id = ?
                """
        for master, subcategories in config_manager.configs['category_config.yaml']['categories']['master'].items():
            if category in subcategories:
                master_category = master
        try:
            self.cursor.execute(query, (category, master_category, id))
            self.connection.commit()
        except Exception as e:
            print(f'unable to update category - {e}')
        


# # Utility: Logging Errors
# def log_error(error):
#     # Implement logging to a file or console
#     print("Database Error:", error)

# if __name__ == "__main__":
#     db = DataBaseManager()
#     df = db.get_monthly_summary_all_tables_by_category('2025')
#     print(df)