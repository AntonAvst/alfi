import sys
from PyQt5.QtWidgets import QApplication 
from gui import DataVisualizer
from config_manager import config_manager

if __name__ == "__main__":
    # startup:
    pass    
    app = QApplication(sys.argv)
    window = DataVisualizer()
    window.show()
    sys.exit(app.exec_())