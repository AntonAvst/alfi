import sys
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import pandas as pd
import plotly.graph_objects as go
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QFileDialog, QVBoxLayout,
    QHBoxLayout, QWidget, QTabWidget, QTableWidget, QTableWidgetItem, QDialog,
    QLabel, QDateEdit, QDialogButtonBox, QComboBox, QCheckBox, QLineEdit
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, QDate, Qt
import tempfile
from data_base import DataBaseManager
from PyQt5.QtGui import QColor, QPixmap
from config_manager import config_manager
from datetime import datetime
from calendar import monthrange
import plotly.express as px
import plotly.graph_objects as go
from logger import get_logger
from pathlib import Path


log = get_logger()

def handle_exception(exc_type, exc_value, exc_traceback):
     # log all unhandled exceptions 
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    log.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception


def plot_monthly_summary(df, month):
    # Filter out rows where master_category is 'ignore'
    df = df[df["master_category"].str.lower() != "ignore"]

    # Create the plot
    fig = px.bar(
        df,
        x="master_category",
        y="amount",
        color="category",
        title=f"Monthly Summary - {month}",
        labels={"amount": "Total", "master_category": "Master Category"},
    )
    
    fig.update_layout(barmode="stack", xaxis_title="Master Category", yaxis_title="Amount")   

    # Save Plotly figure to a temporary HTML file
    temp_html_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html").name
    fig.write_html(temp_html_file)
    
    return temp_html_file

def plot_yearly_summary(df, year):
    expense_columns = [col for col in df.columns if col not in ['income', 'ignore', 'month', 'savings']]
    df[expense_columns] = df[expense_columns].apply(pd.to_numeric, errors='coerce')
    df['expenses'] = df[expense_columns].abs().sum(axis=1)
    # df['income'] = pd.to_numeric(df.get('income', 0), errors='coerce')

    # Prepare for plotting
    plot_df = df[['month', 'income', 'expenses', 'savings']].melt(
        id_vars='month', var_name='type', value_name='amount'
    )

    # Plot
    fig = px.line(
        plot_df,
        x='month',
        y='amount',
        color='type',
        title=f"Yearly Summary - {year}",
        markers=True,
        labels={'amount': 'Total Amount', 'month': 'Month', 'type': 'Type'}
    )

    # Save Plotly figure to a temporary HTML file
    temp_html_file = tempfile.NamedTemporaryFile(delete=False, suffix=".html").name
    fig.write_html(temp_html_file)
    
    return temp_html_file


class CategoryUpdateDialog(QDialog):
    """
    popup dialog for selcting category
    """
    def __init__(self, parent, row_id, current_category):
        super().__init__(parent)
        self.setWindowTitle('Update Category')
        self.setFixedSize(300, 200)

        self.row_id = row_id

        layout = QVBoxLayout(self)
        self.label = QLabel(f'select a new category for ID {row_id}')
        layout.addWidget(self.label)

        # Dropdown - master category
        layout.addWidget(QLabel('Select Master Category:'))
        self.master_dropdown = QComboBox()
        self.master_dropdown.addItems(sorted(config_manager.configs['category_config.yaml']['categories']['master']))
        self.master_dropdown.setMaxVisibleItems(len(config_manager.configs['category_config.yaml']['categories']['master']))
        layout.addWidget(self.master_dropdown)

        # Dropdown - sub category
        self.category_dropdown = QComboBox()
        self.category_dropdown.setCurrentText(current_category)
        layout.addWidget(self.category_dropdown)

        # Update subcategories based on initial master selection
        self.update_subcategories(self.master_dropdown.currentText())
        self.master_dropdown.currentTextChanged.connect(self.update_subcategories)

        # Checkbox
        self.update_entry_checkbox = QCheckBox('Update all transactions of this type')
        self.update_entry_checkbox.stateChanged.connect(self.checkbox_toggled)
        layout.addWidget(self.update_entry_checkbox)

        # Update button
        self.update_button = QPushButton('Update')
        self.update_button.clicked.connect(self.accept)
        layout.addWidget(self.update_button)

    def update_subcategories(self, selected_master):
        self.category_dropdown.clear()
        self.category_dropdown.addItems(sorted(config_manager.configs['category_config.yaml']['categories']['master'][selected_master]))

    def get_selected_category(self):
        return self.category_dropdown.currentText()
    
    def checkbox_toggled(self):
        return self.update_entry_checkbox.isChecked()
    
class AddCategoryDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('Add New Category')
        self.setFixedSize(600, 200)
        layout = QVBoxLayout(self)
        
        # Text Input
        layout.addWidget(QLabel('Enter New Category Name:'))        
        self.text_input = QLineEdit()
        layout.addWidget(self.text_input)

        # Dropdown
        layout.addWidget(QLabel('Select Master Category:'))
        self.master_dropdown = QComboBox()
        self.master_dropdown.addItems(sorted(config_manager.configs['category_config.yaml']['categories']['master']))
        self.master_dropdown.setMaxVisibleItems(len(config_manager.configs['category_config.yaml']['categories']['master']))
        layout.addWidget(self.master_dropdown)

        # Add Button
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.accept)
        layout.addWidget(self.add_button)

    def get_values(self):
        return self.text_input.text(), self.master_dropdown.currentText()
    
class DateSelectionDialog(QDialog):
    def __init__(self, parent, scope):
        super().__init__(parent)
        self.setWindowTitle('Select Date')
        self.setFixedSize(600, 200)
        layout = QVBoxLayout(self)
        self.scope = scope

        year_list = ['2022', '2023', '2024', '2025'] # TODO: get available dates dynamicaly
        month_list = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

        # Dropdowns
        layout.addWidget(QLabel('Select Year:'))
        self.year_dropdown = QComboBox()
        self.year_dropdown.addItems(sorted(year_list))
        self.year_dropdown.setMaxVisibleItems(len(year_list))
        layout.addWidget(self.year_dropdown)

        if self.scope == 'month':
            layout.addWidget(QLabel('Select Month:'))
            self.month_dropdown = QComboBox()
            self.month_dropdown.addItems(sorted(month_list))
            self.month_dropdown.setMaxVisibleItems(len(month_list))
            layout.addWidget(self.month_dropdown)

        # Confirmation Button
        self.confirm_button = QPushButton('Load Summary')
        self.confirm_button.clicked.connect(self.accept)
        layout.addWidget(self.confirm_button)

    def get_selected_dates(self):
        year = self.year_dropdown.currentText()
        if self.scope == 'month':
            month = self.month_dropdown.currentText()
        else:
            month = 'Jan'
        return year, month


class TableSelectionDialog(QDialog):
    def __init__(self, parent, table_list):
        super().__init__(parent)
        self.setWindowTitle('Select Table')
        self.setFixedSize(300, 100)
        self.selected_table = None
        layout = QVBoxLayout(self)
        self.label = QLabel('Choose a table:')
        layout.addWidget(self.label)

        # Dropdown
        self.table_dropdown = QComboBox()
        self.table_dropdown.addItems(table_list)
        layout.addWidget(self.table_dropdown)

        # Confirm button
        self.confirm_button = QPushButton('Load Table')
        self.confirm_button.clicked.connect(self.accept)
        layout.addWidget(self.confirm_button)

    def get_selected_table(self):
        return self.table_dropdown.currentText()


# Main GUI Window
class DataVisualizer(QMainWindow):
    def __init__(self):
        log.info("starting alfi app")

        super().__init__()

        self.setWindowTitle("Data Visualizer")
        self.setGeometry(100, 100, 1000, 600)
        
        self.db = DataBaseManager()
        self.table_pointer = None

        # Main Layout (Sidebar + Content Area)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # Left Panel
        sidebar = QVBoxLayout()

        self.load_table_button = QPushButton("Load Table")
        self.load_table_button.clicked.connect(self.show_table_selection_popup)
        sidebar.addWidget(self.load_table_button)

        self.open_file_button = QPushButton("Select Files")
        self.open_file_button.clicked.connect(self.open_file_dialog)
        sidebar.addWidget(self.open_file_button)

        self.update_button = QPushButton('Update Category')
        self.update_button.clicked.connect(self.show_category_popup)
        sidebar.addWidget(self.update_button)

        self.add_category_button = QPushButton('Add New Category')
        self.add_category_button.clicked.connect(self.add_category_popup)
        sidebar.addWidget(self.add_category_button)

        self.view_month_summary_button = QPushButton('View Monthly Summary')
        self.view_month_summary_button.clicked.connect(lambda: self.spending_summary_by_date_popup('month'))
        sidebar.addWidget(self.view_month_summary_button)

        self.view_year_summary_button = QPushButton('View Yearly Summary')
        self.view_year_summary_button.clicked.connect(lambda: self.spending_summary_by_date_popup('year'))
        sidebar.addWidget(self.view_year_summary_button)

        # logo
        logo_label = QLabel()
        icon_path = Path(__file__).parent / "graphics" / "alfi_icon.png"
        pixmap = QPixmap(str(icon_path)).scaled(100, 100, Qt.KeepAspectRatio) 
        logo_label.setPixmap(pixmap)
        logo_label.setAlignment(Qt.AlignCenter) 
        sidebar.addWidget(logo_label)
        
        sidebar.addStretch()  # Push buttons to the top

        # Tabbed Interface for Charts & Tables
        self.tabs = QTabWidget()

        # Tables Tab
        self.table_tab = QWidget()
        table_layout = QVBoxLayout(self.table_tab)
        self.table_widget = QTableWidget()
        table_layout.addWidget(self.table_widget)
        self.tabs.addTab(self.table_tab, "Tables")

        # Charts Tab 
        self.chart_tab = QWidget()
        chart_layout = QVBoxLayout(self.chart_tab)
        self.plotly_view = QWebEngineView(self)
        chart_layout.addWidget(self.plotly_view)
        self.tabs.addTab(self.chart_tab, "Charts")

        # Add to Main Layout
        main_layout.addLayout(sidebar, 1)  # Sidebar (Left)
        main_layout.addWidget(self.tabs, 4)  # Tabs (Right)

    def show_category_popup(self):
        selected_row = self.table_widget.currentRow()
        if selected_row == -1:
            print('No row selected')
            return
        
        row_id = self.table_widget.item(selected_row, 0).text() # TODO: get row id dynamiclly
        current_category = self.table_widget.item(selected_row, 2).text() # TODO: get category dynamically
        details = self.table_widget.item(selected_row, 7).text() # TODO: get details dynamiclly

        # Open category selection dialog
        dialog = CategoryUpdateDialog(self, row_id, current_category)
        if dialog.exec_():
            new_category = dialog.get_selected_category()
            update_config = dialog.checkbox_toggled()
            self.update_category(selected_row, row_id, new_category, details, update_config)

    def update_category(self, row_index, row_id, new_value, details, update_config):
        self.table_widget.setItem(row_index, 2, QTableWidgetItem(new_value)) # TODO: Column 2= category               
        if update_config:
            self.db.update_all_transaction_category_by_details(table=self.table_pointer, category=new_value, details=details)
            config_manager.add_value_to_subcategory(new_value, details)
        else:
            self.db.update_transaction_category(self.table_pointer, row_id, new_value) 
        self.load_table(self.table_pointer)

    def add_category_popup(self):
        dialog = AddCategoryDialog(self)
        if dialog.exec_():
            sub, master = dialog.get_values()
            config_manager.add_new_category(sub, master)
        
    def load_summary(self, start_date, end_date, scope): # TODO: load_summary() and load_table are very similar, maybe merge them to prevent duplicate code
        if scope == 'month':
            log.info(f'loading financial summary for {start_date[5:7]}')
            df = self.db.get_category_totals_by_month(start_date, end_date)
            chart_file = plot_monthly_summary(df, start_date[:7])
        if scope == 'year':
            log.info(f'loading financial summary for {start_date[:4]}')
            df = self.db.get_monthly_summary_all_tables_by_master_category(start_date[:4])
            chart_file = plot_yearly_summary(df, start_date[:4])            
        self.plotly_view.setUrl(QUrl.fromLocalFile(chart_file))

        try:
            self.table_widget.setRowCount(df.shape[0])
            self.table_widget.setColumnCount(df.shape[1])
            self.table_widget.setHorizontalHeaderLabels(df.columns)

            # target_column = 'category'
            # highlight_value = 'uncategorized'

            for row_idx, row_data in df.iterrows():
                for col_idx, value in enumerate(row_data):
                    item = QTableWidgetItem(str(value))
                    # if row_data[target_column] == highlight_value:
                    #     item.setBackground(QColor(255, 200, 200))
                    self.table_widget.setItem(row_idx, col_idx, item)
        except Exception as e:
            log.error(f'unable to load summary: {e}')

    def load_table(self, table_name):
        log.info(f'Loading table: {table_name}')

        df = self.db.fetch_table(table_name)
        self.table_widget.setRowCount(df.shape[0])
        self.table_widget.setColumnCount(df.shape[1])
        self.table_widget.setHorizontalHeaderLabels(df.columns)

        self.table_widget.setSortingEnabled(False)  # Disable during population to avoid glitches

        target_column = 'category'
        highlight_value = 'uncategorized'

        for row_idx, row_data in df.iterrows():
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                if row_data[target_column] == highlight_value:
                    item.setBackground(QColor(255, 200, 200))
                self.table_widget.setItem(row_idx, col_idx, item)
        self.table_widget.setSortingEnabled(True)

    def convert_selected_date_to_range(self, year, month):
        " convert selected year+month to date range of that month  "        
        dt = datetime.strptime(f'{year}-{month}', '%Y-%b') # dt=datetime
        start_date = dt.replace(day=1)
        end_date = dt.replace(day=monthrange(dt.year, dt.month)[1])
        return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

    def show_table_selection_popup(self):
        table_list = self.db.get_table_names()
        dialog = TableSelectionDialog(self, table_list)
        if dialog.exec_():
            self.table_pointer = dialog.get_selected_table()
            self.load_table(self.table_pointer)

    def spending_summary_by_date_popup(self, scope):
        dialog = DateSelectionDialog(self, scope)
        if dialog.exec_():
            selected_year, selected_month = dialog.get_selected_dates()
            start_date, end_date = self.convert_selected_date_to_range(selected_year, selected_month)
            self.load_summary(start_date, end_date, scope)

    def open_file_dialog(self):
        """Opens a file dialog and prints selected file paths."""
        log.info('selecting statement files for parsing')
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "", "All Files (*.*)"
        )
        if file_paths:
            log.info(f"Selected Files:, {file_paths}")
            self.db.batch_upload(file_paths)
        else:
            log.info('no files selected')

    def closeEvent(self, event):
        log.info('closing alfi app...')
        self.db.close_connection()
        log.info('app closed gracefully')
        event.accept()


# Run the Application
if __name__ == "__main__":    
    # TODO: uncategorizing english keys
    app = QApplication(sys.argv)
    window = DataVisualizer()
    window.show()
    sys.exit(app.exec_())
