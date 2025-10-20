# -----------------------------
# Environment settings (suppress Qt warnings)
# -----------------------------
import os
os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"  # suppress QVector<int> console warnings

# -----------------------------
# Standard libraries
# -----------------------------
import sys
import time
import json
import csv
import shutil
import uuid
import re
import threading
import sqlite3
from datetime import date, datetime, timedelta

# -----------------------------
# Third-party libraries
# -----------------------------
import numpy as np
import cv2
from PIL import Image
import pytesseract
import pyperclip
import pyautogui
import keyboard
import pandas as pd

# -----------------------------
# Google API libraries (if used)
# -----------------------------
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError

# -----------------------------
# Local utilities
# -----------------------------
from utils import resource_path, user_resource_path, get_tesseract_path, ensure_user_file

# -----------------------------
# PyQt5 imports (after QT_LOGGING_RULES)
# -----------------------------
from PyQt5 import QtCore
from PyQt5.QtCore import (
    Qt, QPoint, QSize, QRect, QSettings, QTime, QTimer,
    pyqtSignal, QObject, QThreadPool, QRunnable, pyqtSlot, QThread, QEvent, QPointF,
    QStandardPaths
)
from PyQt5.QtGui import (
    QKeySequence, QBrush, QPainter, QPen, QColor, QFont, QPixmap, QIcon, QMovie, QRadialGradient
)
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QVBoxLayout, QCheckBox, QStyledItemDelegate,
    QDoubleSpinBox, QFileDialog, QTableWidget, QTableWidgetItem, QLineEdit, QMenu, QDialog,
    QProgressBar, QDialogButtonBox, QHBoxLayout, QTabWidget, QGroupBox, QGridLayout,
    QTextEdit, QShortcut, QMessageBox, QSplashScreen, QInputDialog
)
from support.RedBorderOverlay import RedBorderOverlay
from support.blacklistdb import blacklistdb
from support.DriveUploadThread import DriveUploadThread,ProfileDialog
from support.RoundCheckboxDelegate import RoundCheckboxDelegate 
from support.CSVLoader import CSVLoader, CSVLoaderSignals, LoadingOverlay
from support.Settings import Settings, SettingsDialog
from support.DraggableWidget import DraggableWidget, Overlay

VERSION= 1.4
# === Static Settings ===
SCOPES = ['https://www.googleapis.com/auth/drive.file']
#CREDENTIALS_PATH = resource_path('resources/credentials.json')
#TOKEN_PATH = resource_path('resources/token.json')
BASE_FOLDER = "pyqt whatsapp"
MAC_ID = ""
COMPANY_NAME = ""

# DATA_FILE = resource_path('resources/layout_data.json')
# SETTINGS_FILE = resource_path("resources/profilesettings.json")

# SETTINGS = resource_path("resources/settings.json")

#pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Dynamic user-specific resources
# DATA_FILE = user_resource_path("layout_data.json")  
# SETTINGS_FILE = user_resource_path("profilesettings.json")
# SETTINGS = user_resource_path("settings.json")
# TOKEN_PATH = user_resource_path("token.json")
CREDENTIALS_PATH = ensure_user_file('credentials.json')
DATA_FILE = ensure_user_file("layout_data.json")
SETTINGS_FILE = ensure_user_file("profilesettings.json")
SETTINGS = ensure_user_file("settings.json")
TOKEN_PATH = ensure_user_file("token.json")

pytesseract.pytesseract.tesseract_cmd = get_tesseract_path()

pyautogui.FAILSAFE = False      



skipped_contacts = []  # 📝 Store skipped names
# Add this class at the top with other imports
class PauseController(QObject):
    paused_signal = pyqtSignal()
    resumed_signal = pyqtSignal()
    stopped_signal = pyqtSignal()
    

    def __init__(self):
        super().__init__()
        self._typing_active = False
        self._paused = False
        self._skip_requested = False
        self._stop_requested = False
        self._lock = threading.Lock()

    def stop(self):
        """Request to stop the automation immediately"""
        with self._lock:
            self._stop_requested = True
            self._paused = False  # force-unpause so wait exits
        self.stopped_signal.emit()
        print("🛑 Stop requested")

    @property
    def stop_requested(self):
        with self._lock:
            return self._stop_requested

    def reset_stop(self):
        with self._lock:
            self._stop_requested = False

    def typing_block(self, operation):
        with self._lock:
            self._typing_active = True
        try:
            return operation()
        finally:
            with self._lock:
                self._typing_active = False
                if self._skip_requested:
                    raise InterruptedError("Skip requested during typing")

    def start_typing(self):
        with self._lock:
            self._typing_active = True

    def finish_typing(self):
        with self._lock:
            self._typing_active = False

    @property
    def paused(self):
        with self._lock:
            return self._paused

    @property
    def skip_requested(self):
        with self._lock:
            return self._skip_requested

    def pause(self):
        with self._lock:
            self._paused = True
        self.paused_signal.emit()
        print("⏸️ Automation paused")

    def resume(self):
        with self._lock:
            self._paused = False
        self.resumed_signal.emit()
        print("▶️ Automation resumed")

    def skip(self):
        with self._lock:
            self._skip_requested = True
        print("⏭️ Skip requested")

    def reset_skip(self):
        with self._lock:
            self._skip_requested = False

    # ✅ KEEP ONLY THIS VERSION (delete the duplicate further down)
    def wait_if_paused(self):
        while True:
            with self._lock:
                if self._stop_requested:
                    raise InterruptedError("Stop requested")
                if not self._paused and not self._typing_active:
                    break
                if self._skip_requested:
                    self._skip_requested = False
                    raise InterruptedError("Skip requested during pause")
            time.sleep(0.05)


    def reset_all(self):
        with self._lock:
            self._typing_active = False
            self._paused = False
            self._skip_requested = False
            self._stop_requested = False
        print("🔄 All pause controller flags reset")


#overlay red border sending msg

# from PyQt5.QtWidgets import QTableWidgetItem, QCheckBox, QWidget, QHBoxLayout
# from PyQt5.QtCore import Qt, QThread, pyqtSignal
# #import pandas as pd

# from PyQt5.QtCore import QThread, pyqtSignal
# import pandas as pd
# import re

#DB_PATH = "messages.db"

                
# In WhatsAppAutomationUI class, replace pause-related code with:
class WhatsAppAutomationUI(QWidget):
    #campaign_finished_signal = pyqtSignal()
    campaign_finished_signal = pyqtSignal(int, int, int, list)  
# total_clients, messages_sent, skipped, skipped_contacts

    stop_complete_signal = pyqtSignal()
    update_stats_signal = pyqtSignal(int, str, int, int, str)
      # loads from JSON if exists, otherwise defaults

    
    def __init__(self):
        super().__init__()
        
        self.setStyleSheet("""
    QMessageBox QLabel {
        color: #333;
        font-size: 13px;
        padding: 8px;
    }

    /* Button styling inside QMessageBox */
    QMessageBox QPushButton {
        background-color: #0078d7;
        color: white;
        padding: 6px 12px;
        border: none;
        border-radius: 4px;
        min-width: 80px;
    }

    QMessageBox QPushButton:hover {
        background-color: #005ea6;
    }

    QMessageBox QPushButton:pressed {
        background-color: #004c87;
    }

    /* Optional: center align the buttons */
    QMessageBox {
        qproperty-textInteractionFlags: 5; /* Enable selectable text */
    }
            QWidget, QMessagebox {
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }

            QTableWidget {
                border: 1px solid #ccc;
                border-radius: 4px;
                gridline-color: #ccc;
                selection-background-color: #0078d7;
                alternate-background-color: #f9f9f9;
            }

            QTabWidget::pane {
                border: 1px solid #aaa;
                border-radius: 6px;
                padding: 4px;
            }

            QTabBar::tab {
                background: #ddd;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }

            QTabBar::tab:selected {
                background: #ffffff;
                border: 1px solid #aaa;
                border-bottom-color: transparent;
            }

            QPushButton {
                background-color: #0078d7;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
            }

            QPushButton:hover {
                background-color: #005ea6;
            }

            QPushButton:pressed {
                background-color: #004c87;
            }

            QLabel {
                font-weight: bold;
            }

            QLineEdit, QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                background-color: #fff;
            }

            QGroupBox {
                border: 1px solid #aaa;
                border-radius: 6px;
                margin-top: 10px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 6px;
                background-color: #f0f0f0;
                border-radius: 3px;
            }
        """)


        self.initialize_database()
        
        self.add_blacklist = blacklistdb()
        self.add_blacklist.create_blacklist_table()
        
        self.blacklist = self.add_blacklist.load_blacklist()
        
        
        #self.stop_complete_signal = pyqtSignal()

        self.automation_thread = None
        self.is_automation_running = False
        self.stop_requested = False

        self.campaign_finished_signal.connect(self.show_campaign_success_dialog)
        self.stop_complete_signal.connect(self.on_stop_complete)
        
        self.pause_controller = PauseController()  # Replace old pause attributes
        self.pause_controller.paused_signal.connect(self.on_paused)
        self.pause_controller.resumed_signal.connect(self.on_resumed)
        self.pause_controller.stopped_signal.connect(self.on_stopped)  
        
        #self.automation_thread = None
        self.update_stats_signal.connect(self.update_stats)
        
        self.red_border_overlay = RedBorderOverlay()
        self.red_border_overlay.hide()

        #self.get_total_usage()
        sent, skipped,total_used, total_duration = self.get_total_usage()
        print(f"Total sent: {sent}, Total skipped: {skipped}")

        #self.settings = QSettings("MyCompany", "MyApp")
        self.settings = Settings()
        
        #keyboard.add_hotkey('ctrl+alt+s', self.start,suppress=True)
        # keyboard.add_hotkey('ctrl+alt+m', self.pause,suppress=True)
        # keyboard.add_hotkey('ctrl+alt+s', self.resume,suppress=True)
        keyboard.add_hotkey('ctrl+alt+k', self.on_skip_clicked, suppress=True)
        # In your __init__ method, add this line:
        keyboard.add_hotkey('ctrl+alt+x', self.on_stop_clicked, suppress=True)
        # shortcut = QShortcut(QKeySequence(""), self)
        # shortcut.activated.connect(self.on_pause_clicked)

        self.setWindowTitle("WhatsApp Automation Tool")
        self.setWindowIcon(QIcon(resource_path("icons/desk-icon.png")))
        self.resize(800, 600)

        self.layout = QVBoxLayout()
        self.toolbar = QHBoxLayout()
        
        self.setLayout(self.layout)

        # Top row layout
        self.top_row = QHBoxLayout()

        # Time tracking
        # self.elapsed_time = QTime(0, 0, 0)
        # self.timer = QTimer(self)
        # self.timer.timeout.connect(self.update_elapsed_time)
        #self.elapsed_seconds = 0
        # self.timer = QTimer(self)
        # self.timer.timeout.connect(self.update_timer)
        # self.timer.setInterval(1000)  # 1 second
        # self.seconds = 0
        # self.timer_running = False
        
        # Upload CSV Button (reduced width)
        self.upload_btn = QPushButton("Upload CSV")
        self.upload_btn.setFixedWidth(150)  # adjust as needed
        #self.upload_btn.clicked.connect(self.load_csv)
        
        self.upload_btn.clicked.connect(self.load_csv_async)

        self.top_row.addWidget(self.upload_btn)

        # Spacer between buttons (optional)
        self.top_row.addStretch()

        # Calibrate Icon Button
        self.calibrate_btn = QPushButton()
        self.calibrate_btn.setIcon(QIcon(resource_path("icons/calibrate.png")))
        self.calibrate_btn.setIconSize(QSize(28, 28))
        self.calibrate_btn.setFixedSize(42, 42)
        self.calibrate_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
            QPushButton:hover {
                border: 1px solid #aaa;
                border-radius: 6px;
            }
        """)

        self.calibrate_btn.setToolTip("Calibrate")
        self.top_row.addWidget(self.calibrate_btn)
        self.calibrate_btn.clicked.connect(self.show_calibration_menu)
        self.toolbar.addWidget(self.calibrate_btn)

        self.calibration_menu = QMenu(self)
        self.calibration_menu.addAction("Message", self.show_overlay)
        self.calibration_menu.addAction("Photo/Media",self.show_limited_overlay)
        

        # Profile Icon Button
        self.profile_btn = QPushButton()
        self.profile_btn.setIcon(QIcon(resource_path("icons/profile.png")))
        self.profile_btn.setIconSize(QSize(40, 40))
        self.profile_btn.setFixedSize(42, 42)
        self.profile_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
            QPushButton:hover {
                border: 1px solid #aaa;
                border-radius: 6px;
            }
        """)

        self.profile_btn.setToolTip("Profile")
        self.top_row.addWidget(self.profile_btn)
        self.profile_btn.clicked.connect(self.open_profile_dialog)


        self.blackprofile_btn = QPushButton()
        self.blackprofile_btn.setIcon(QIcon(resource_path("icons/block.png")))
        self.blackprofile_btn.setIconSize(QSize(30,30))
        self.blackprofile_btn.setFixedSize(42, 42)
        self.blackprofile_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
            QPushButton:hover {
                border: 1px solid #aaa;
                border-radius: 6px;
            }
        """)

        self.blackprofile_btn.setToolTip("Blocked")
        self.top_row.addWidget(self.blackprofile_btn)
        self.blackprofile_btn.clicked.connect(self.show_blacklist_dialog)
        #self.blackprofile_btn.clicked.connect(self.open_profile_dialog)


        # Settings Icon Button
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(QIcon(resource_path("icons/settings.png")))
        self.settings_btn.setIconSize(QSize(32, 32))
        self.settings_btn.setFixedSize(42, 42)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
            }
            QPushButton:hover {
                border: 1px solid #aaa;
                border-radius: 6px;
            }
        """)

        self.settings_btn.setToolTip("Settings")
        self.top_row.addWidget(self.settings_btn)
        self.settings_btn.clicked.connect(self.open_settings)
    

        # Add the row to the main layout
        self.layout.addLayout(self.top_row)

        # Split layout for table + message tab
        split_layout = QHBoxLayout()

        # Left side (Table + Search)
        left_layout = QVBoxLayout()

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search client...")
        self.search_bar.textChanged.connect(self.filter_table)
        
        self.search_bar.setVisible(False)
        left_layout.addWidget(self.search_bar)

        self.table = QTableWidget()
        self.table.setItemDelegateForColumn(0, RoundCheckboxDelegate())
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Index", "Client Name", "Mob"])
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1,150)
        self.table.setColumnWidth(2, 100)# Column 0 is usually the index column
        self.table.verticalHeader().setVisible(False)

        #self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setVisible(True)
        left_layout.addWidget(self.table)

         # table loading
        self.loading_overlay = LoadingOverlay(self)
        self.loading_overlay.hide()
        # Make sure it's on top of your table
        self.loading_overlay.setGeometry(self.table.geometry())

        self.add_blacklist= blacklistdb()
        self.add_blacklist.create_blacklist_table()



        # Right side (Message Tab)
        right_layout = QVBoxLayout()
        self.tabs = QTabWidget()
        self.message_tab = QWidget()
        self.tabs.addTab(self.message_tab, "Message")
        right_layout.addWidget(self.tabs)

        # Message Tab Content
        message_layout = QVBoxLayout()
        self.message_tab.setLayout(message_layout)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Enter your message here...")
        message_layout.addWidget(QLabel("Message:"))
        message_layout.addWidget(self.message_input)


        # media_layout = QHBoxLayout()
        # # Media label with fixed width and elided text
        # self.media_label = QLabel("No file selected")
        # self.media_label.setFixedWidth(300)  # Adjust width as needed
        # self.media_label.setToolTip("No file selected")  # Tooltip for full path
        # self.media_label.setStyleSheet("QLabel { color: gray; }")  # Optional style
        # self.media_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # # Button to select media
        # self.media_button = QPushButton("Choose Media File")
        # self.media_button.clicked.connect(self.choose_media_file)
        # # Add widgets to layout
        # media_layout.addWidget(self.media_button, stretch=0)
        # media_layout.addWidget(self.media_label, stretch=0)
        # media_layout.addStretch(1)  # Pushes everything to the left
        # message_layout.addLayout(media_layout)
        
        # Media file selection section
        media_layout = QHBoxLayout()
        self.media_label = QLabel("No file selected")
        self.media_label.setFixedWidth(300)
        self.media_label.setToolTip("No file selected")
        self.media_label.setStyleSheet("QLabel { color: gray; }")
        self.media_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.media_button = QPushButton("Choose Media File")
        self.media_button.clicked.connect(self.choose_media_file)

        media_layout.addWidget(self.media_button, stretch=0)
        media_layout.addWidget(self.media_label, stretch=0)
        media_layout.addStretch(1)

        # Create container for media section with preview
        self.media_container = QVBoxLayout()  # Make it an instance variable
        self.media_container.addLayout(media_layout)

        # Add to your main layout
        message_layout.addLayout(self.media_container)

        # Add both left and right to split layout
        split_layout.addLayout(left_layout, 1)  # 50%
        split_layout.addLayout(right_layout, 1)  # 50%
        self.layout.addLayout(split_layout)

        # Control Buttons
        control_layout = QHBoxLayout()
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.clicked.connect(self.on_skip_clicked)
        control_layout.addWidget(self.skip_btn)
        
        
        self.total_seconds = 0
        self.timer_running = False
        self.paused = False


        self.start_btn = QPushButton("Start")
        #self.start_btn.clicked.connect(self.test_send_message)
        self.start_btn.clicked.connect(self.handle_start_pause_resume)
        #self.start_btn.clicked.connect(lambda: self.trigger_button('Start'))

        control_layout.addWidget(self.start_btn)
        self.start_btn.setText("Start")
        self.start_btn.setStyleSheet("background-color: #0078d7; color: white; border-radius: 4px; padding: 6px 12px;")
        #QShortcut(QKeySequence("Ctrl+Alt+M"), self).activated.connect(self.toggle_timer)

        
        self.s_btn = QPushButton("Stop")
        self.s_btn.clicked.connect(self.on_stop_clicked)
        control_layout.addWidget(self.s_btn)
        
        
        self.exit_btn = QPushButton("Exit")
        control_layout.addWidget(self.exit_btn)
        self.exit_btn.clicked.connect(self.on_exit_clicked)

        

        self.layout.addLayout(control_layout)


        status_and_usage_layout = QHBoxLayout()

        # Status Box (unchanged)
        self.status_group = QGroupBox("Status")
        status_layout = QGridLayout()

        # Labels for static text
        self.label_current_clientid_text = QLabel("Current Client Id:")
        self.label_current_client_text = QLabel("Current Client Name:")
        self.label_total_client_text = QLabel("Total Clients:")
        self.label_sent_text = QLabel("Messages Sent:")
        self.label_skipped_text = QLabel("Skipped Count:")
        self.label_time_lapsed_text = QLabel("Time Lapsed:")
        
        #self.start_btn.clicked.connect(self.toggle_timer)
        # self.timer = QTimer()
        # self.timer.setInterval(1000)
        # self.timer.timeout.connect(self.update_timer)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timer)

        self.elapsed_seconds = 0

        # Labels for dynamic values
        self.label_current_clientid = QLabel("0")
        self.label_current_client = QLabel("-")
        self.label_total_client = QLabel("0")
        self.label_sent = QLabel("0")
        self.label_skipped = QLabel("0")
        self.label_time_lapsed = QLabel("00:00:00")

        # Add labels to layout
        status_layout.addWidget(self.label_current_clientid_text, 0, 0)
        status_layout.addWidget(self.label_current_clientid, 0, 1)

        status_layout.addWidget(self.label_current_client_text, 1, 0)
        status_layout.addWidget(self.label_current_client, 1, 1)

        status_layout.addWidget(self.label_total_client_text, 2, 0)
        status_layout.addWidget(self.label_total_client, 2, 1)

        status_layout.addWidget(self.label_sent_text, 3, 0)
        status_layout.addWidget(self.label_sent, 3, 1)

        status_layout.addWidget(self.label_skipped_text, 4, 0)
        status_layout.addWidget(self.label_skipped, 4, 1)

        status_layout.addWidget(self.label_time_lapsed_text, 5, 0)
        status_layout.addWidget(self.label_time_lapsed, 5, 1)


        self.current_duration = self.load_previous_duration()
        #self.label_time_lapsed.setText(self.current_duration)
        # self.status_group.setLayout(status_layout)
        # self.layout.addWidget(self.status_group)

        self.status_group.setLayout(status_layout)
        #self.layout.addWidget(self.status_group)

        self.usage_group = QGroupBox("Total Usage")
        usage_layout = QGridLayout()

        self.label_total_sent_text = QLabel("Total Messages Sent:")
        self.label_total_sent = QLabel("0")
        self.label_total_skipped_text = QLabel("Total Messages Skipped:")
        self.label_total_skipped = QLabel("0")
        self.label_total_used_days = QLabel("Total Days Used:")
        self.label_total_used = QLabel("0")
        
        self.label_total_used_hours = QLabel("Total HH:MM:SS Used:")
        self.label_total_hours = QLabel("00:00:00")

        usage_layout.addWidget(self.label_total_sent_text, 0, 0)
        usage_layout.addWidget(self.label_total_sent, 0, 1)
        usage_layout.addWidget(self.label_total_skipped_text, 1, 0)
        usage_layout.addWidget(self.label_total_skipped, 1, 1)
        usage_layout.addWidget(self.label_total_used_days, 2, 0)
        usage_layout.addWidget(self.label_total_used, 2, 1)

        usage_layout.addWidget(self.label_total_used_hours, 3, 0)
        usage_layout.addWidget(self.label_total_hours, 3, 1)

        self.usage_group.setLayout(usage_layout)

        # Add both groups to horizontal layout
        status_and_usage_layout.addWidget(self.status_group, 1)
        status_and_usage_layout.addWidget(self.usage_group, 1)

        # Add the combined layout to your main layout
        self.layout.addLayout(status_and_usage_layout)

        self.update_total_labels()

        # Internal data
        self.all_rows = []
        self.message_count = 0
        self.skipped_count = 0
        
        # Update your hotkeys to use the controller
        keyboard.add_hotkey('ctrl+alt+m', self.toggle_pause)
        keyboard.add_hotkey('ctrl+alt+k', self.pause_controller.skip)


    def _should_stop(self) -> bool:
        return self.stop_requested or self.pause_controller.stop_requested

    def _stop_aware_sleep(self, seconds):
        for _ in range(int(seconds*10)):
            if self.stop_requested:
                raise InterruptedError("Stopped during sleep")
            time.sleep(0.1)



    def check_free_space(required_mb=200):
        """Check if there's at least required_mb free space in temp dir drive."""
        temp_dir = os.getenv("TEMP", "/tmp")
        total, used, free = shutil.disk_usage(temp_dir)
        free_mb = free // (1024 * 1024)
        if free_mb < required_mb:
            return False, free_mb
        return True, free_mb
    
    def open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec_():  # OK pressed
            print("✅ Settings updated")
            self.settings.save()
    
    def toggle_pause(self):
        if self.pause_controller.paused:
           self.pause_controller.resume()
        else:
           self.pause_controller.pause()
    
    # def pause(self):
    #     self.pause_controller.pause()
    #     self.start_btn.setText("Resume")
    #     self.start_btn.setStyleSheet("background-color: orange;")
    #     self.red_border_overlay.hide()
    
    # def resume(self):
    #     self.pause_controller.resume() 
    #     self.start_btn.setText("Pause")
    #     self.start_btn.setStyleSheet("background-color: red;")
    #     self.red_border_overlay.show()

    # def show_blacklist_dialog(self):
    #     dialog = QDialog(self)
    #     dialog.setWindowTitle("Blacklisted Contacts")
    #     dialog.resize(400,400)    
    #     dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    #     layout = QVBoxLayout(dialog)

    #     table = QTableWidget()
    #     table.setColumnCount(3)
    #     table.setHorizontalHeaderLabels(["Index", "Client Name", "Mobile"])
    #     table.setColumnWidth(0, 60)
    #     table.setColumnWidth(1, 150)
    #     table.setColumnWidth(2, 150)
    #     layout.addWidget(table)

    #     if not hasattr(self, 'blacklist_db'):
    #         self.blacklist_db = blacklistdb()

    #     blacklist_data = self.blacklist_db.load_blacklist()  # returns list of tuples

    #     # Populate the QTableWidget directly from list of tuples
    #     table.setRowCount(len(blacklist_data))
    #     for row_idx, record in enumerate(blacklist_data):
    #         id_, name, mobile, _, _ = record  # unpack fields (ignoring timestamp, reason)
    #         table.setItem(row_idx, 0, QTableWidgetItem(str(id_)))
    #         table.setItem(row_idx, 1, QTableWidgetItem(name))
    #         table.setItem(row_idx, 2, QTableWidgetItem(mobile))

    #     dialog.setLayout(layout)
    #     dialog.exec_()
    
    

    def show_blacklist_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Blacklisted Contacts")
        dialog.resize(400, 400)
        dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        main_layout = QVBoxLayout(dialog)

        # -------- Search Box --------
        search_box = QLineEdit()
        search_box.setPlaceholderText("Search by name or mobile...")
        main_layout.addWidget(search_box)

        # -------- Blacklist Table --------
        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Index", "Client Name", "Mobile"])
        table.setColumnWidth(0, 60)
        table.setColumnWidth(1, 150)
        table.setColumnWidth(2, 120)
        main_layout.addWidget(table)

        # -------- Initialize DB --------
        if not hasattr(self, 'blacklist_db'):
            self.blacklist_db = blacklistdb()

        def load_table(data=None):
            if data is None:
                data = self.blacklist_db.load_blacklist()
            table.setRowCount(len(data))
            for row_idx, record in enumerate(data):
                id_, name, mobile, _, _ = record
                table.setItem(row_idx, 0, QTableWidgetItem(str(id_)))
                table.setItem(row_idx, 1, QTableWidgetItem(name))
                table.setItem(row_idx, 2, QTableWidgetItem(mobile))

        load_table()

        # -------- Search Functionality --------
        def filter_table(text):
            text = text.lower()
            filtered = []
            for record in self.blacklist_db.load_blacklist():
                _, name, mobile, _, _ = record
                if text in name.lower() or text in mobile.lower():
                    filtered.append(record)
            load_table(filtered)

        search_box.textChanged.connect(filter_table)

        # -------- Import/Export Buttons (Bottom) --------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # push buttons to the right

        import_btn = QPushButton("Import")
        import_btn.setFixedSize(90, 30)

        export_btn = QPushButton("Export")
        export_btn.setFixedSize(90, 30)

        clear_btn = QPushButton("Clear All")
        clear_btn.setFixedSize(90, 30)
          # make it red for warning
        #clear_btn.clicked.connect(clear_all)


        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(clear_btn)
        main_layout.addLayout(btn_layout)

        # -------- Button Logic --------
        def export_csv():
            path, _ = QFileDialog.getSaveFileName(dialog, "Export Blacklist CSV", "", "CSV Files (*.csv)")
            if path:
                try:
                    self.blacklist_db.export_blacklist_csv(path)
                    QMessageBox.information(dialog, "Success", "Blacklist exported successfully!")
                except Exception as e:
                    QMessageBox.critical(dialog, "Error", str(e))

        def import_csv():
            path, _ = QFileDialog.getOpenFileName(dialog, "Import Blacklist CSV", "", "CSV Files (*.csv)")
            if path:
                try:
                    self.blacklist_db.import_blacklist_csv(path)
                    QMessageBox.information(dialog, "Success", "Blacklist imported successfully!")
                    load_table()  # refresh table after import
                except Exception as e:
                    QMessageBox.critical(dialog, "Error", str(e))
        
        def clear_all():
            reply = QMessageBox.question(
                dialog,
                "Confirm Clear",
                "Are you sure you want to clear all blacklist data?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                try:
                    self.blacklist_db.clear_blacklist()
                    load_table([])
                    QMessageBox.information(dialog, "Success", "All blacklist data cleared!")
                except Exception as e:
                    QMessageBox.critical(dialog, "Error", str(e))            

        export_btn.clicked.connect(export_csv)
        import_btn.clicked.connect(import_csv)
        clear_btn.clicked.connect(clear_all)

        dialog.setLayout(main_layout)
        dialog.exec_()

    
    
    
    def type_contact_name_and_wait_for_result(self, client_name):
        """More reliable contact typing with better timing control"""
        try:
            # Stage 1: Clear search field thoroughly
            x_percent, y_percent = self.coords["search_bar"]   # ✅ FIXED
            search_coords = self.percent_to_coords(x_percent, y_percent)

            pyautogui.moveTo(*search_coords, duration=1)
            pyautogui.click()
            time.sleep(0.3)
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.press('backspace')
            time.sleep(0.5)

            # Stage 2: Type with direct pause control
            self.pause_controller.start_typing()
            try:
                pyperclip.copy(client_name)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(1)
                if self.pause_controller.skip_requested:
                    raise InterruptedError("Skip requested during typing")
            finally:
                self.pause_controller.finish_typing()

            # Stage 3: Verify contact exists (with retry logic)
            max_attempts = 1
            for attempt in range(max_attempts):
                time.sleep(0.8)
                
                if not self.is_contact_not_found():
                    print(f"✅ Contact '{client_name}' found (attempt {attempt+1})")
                    return True
                    
                print(f"⚠️ Contact not found, retrying... (attempt {attempt+1})")
                pyautogui.hotkey('ctrl', 'a')
                pyautogui.press('backspace')
                time.sleep(0.5)
                pyperclip.copy(client_name)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.1)

            print(f"❌ {client_name} not found after {max_attempts} attempts")
            return False

        except InterruptedError:
            print("⏭️ Typing interrupted by skip request")
            return False
        except Exception as e:
            print(f"Error in contact search: {e}")
            return False

        # cx, cy = self.percent_to_coords(*self.coords["contact_result"])
    
        # Bigger region to catch small text
        # region_w, region_h = 300, 100  
        # region_x = cx - region_w // 2
        # region_y = cy - region_h // 2

        # result_found = False
        # max_wait_result = 2
        # start_time = time.time()

        # while time.time() - start_time < max_wait_result:
        #     screenshot = pyautogui.screenshot(region=(region_x, region_y, region_w, region_h))
        #     found_text = pytesseract.image_to_string(screenshot).strip().lower()

        #     # Fuzzy match score (0 to 1)
        #     match_score = SequenceMatcher(None, client_name.lower(), found_text).ratio()
        #     print(f"OCR saw: '{found_text}' (match score: {match_score:.2f})")

        #     if client_name.lower() in found_text or match_score > 0.6:
        #         result_found = True
        #         break

        #     time.sleep(0.2)

       
    
    def on_paused(self):
        """Handle UI updates when paused"""
        self.start_btn.setText("Resume")
        self.timer.stop()
        self.start_btn.setStyleSheet(
            "background-color: orange; color: black; border-radius: 4px; padding: 6px 12px;")
        self.red_border_overlay.hide()
        
    def on_resumed(self):
        """Handle UI updates when resumed"""
        self.start_btn.setText("Pause")
        self.timer.start(1000)
        self.start_btn.setStyleSheet(
            "background-color: red; color: white; border-radius: 4px; padding: 6px 12px;")
        self.red_border_overlay.show()
        
        
    def on_skip_clicked(self):
        self.pause_controller.skip()
        print("⏭️ Skip requested")    

    # def send_whatsapp_message(self, client_name):
    #     try:
    #         self.red_border_overlay.show()
    #         message = self.message_input.toPlainText().strip()
    #         media_path = getattr(self, "selected_media_path", "")
    #         time.sleep(1)
            
    #          # Stage 1: Search & confirm contact via OCR
    #         if not self.type_contact_name_and_wait_for_result(client_name):
    #             return False    
        
    #         # STAGE 3: Select contact
    #         self.pause_controller.wait_if_paused()
    #         pyautogui.moveTo(*self.percent_to_coords(*self.coords["contact_result"]), duration=2.5)
    #         time.sleep(3)
    #         self.pause_controller.wait_if_paused()
    #         pyautogui.click()
        
    #         self.pause_controller.wait_if_paused
    #         if self.pause_controller.skip_requested:
    #             print(f"⏭️ Skip requested during send. Skipping: {client_name}")
    #             self.pause_controller.skip_requested = False
    #             return False  # ✅ Skip before proceeding

    #         if media_path:
    #             print("📎 Sending media:", media_path)
    #             self.pause_controller.wait_if_paused()
    #             if not os.path.isfile(media_path):
    #                 print("❌ Media path does not exist:", media_path)
    #                 return False

    #             self.pause_controller.wait_if_paused()
    #             time.sleep(2)
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["attachment_button"]), duration=1)
    #             pyautogui.click()
                
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["photo_video_option"]), duration=1)
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.click()                
    #             time.sleep(3)

    #             self.pause_controller.wait_if_paused()
    #             pyperclip.copy(media_path)
    #             time.sleep(2)
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.hotkey('ctrl', 'v')
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.press('enter')
    #             self.pause_controller.wait_if_paused()
    #             time.sleep(1)

    #             # 👉 Type message into caption box if media is being sent
    #             if message:
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.moveTo(*self.percent_to_coords(*self.coords["caption_box"]), duration=0.5)
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.click()
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.typewrite(message, interval=0.05)
                    
    #             self.pause_controller.wait_if_paused()
    #             time.sleep(4)
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["send_button"]), duration=2)
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.click()
    #             self.pause_controller.wait_if_paused()
    #             print("✅ Media + Caption sent")
    #             self.pause_controller.wait_if_paused()
    #             time.sleep(2)
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.press('esc')
    #             return True

    #         else:
    #             # 📝 No media — just send a text message
                
    #             if message:
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.moveTo(*self.percent_to_coords(*self.coords["message_box"]), duration=1)
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.click()
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.typewrite(message, interval=0.1)
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.press('enter')
    #                 self.pause_controller.wait_if_paused()
                
    #                 print("✅ Text message sent")
    #                 self.pause_controller.wait_if_paused()
    #                 return True
    #             else:
    #                 print("⚠️ No media or message to send.")
    #                 return False

    #     except InterruptedError:
    #         print("⏭️ Message skipped")
    #         self.pause_controller.reset_skip()
    #         return False
    #     except Exception as e:
    #         print(f"Error: {e}")
    #         return False
    # def send_whatsapp_message(self, client_name):
    #     try:
    #         self.red_border_overlay.show()
    #         message = self.message_input.toPlainText().strip()
    #         media_path = getattr(self, "selected_media_path", "")
    #         time.sleep(1)

    #         # Stage 1: Search & confirm contact via OCR
    #         if not self.type_contact_name_and_wait_for_result(client_name):
    #             return False    

    #         # Stage 2: Select contact
    #         self.pause_controller.wait_if_paused()
    #         pyautogui.moveTo(*self.percent_to_coords(*self.coords["contact_result"]), duration=2.5)
    #         time.sleep(3)
    #         self.pause_controller.wait_if_paused()
    #         pyautogui.click()

    #         # If skip requested at this point
    #         if self.pause_controller.skip_requested:
    #             print(f"⏭️ Skip requested during send. Skipping: {client_name}")
    #             self.pause_controller.reset_skip()
    #             return False  

    #         # ----------------------------
    #         # CASE 1: MEDIA (with/without message as caption)
    #         # ----------------------------
    #         if media_path:
    #             print("📎 Sending media:", media_path)
    #             if not os.path.isfile(media_path):
    #                 print("❌ Media path does not exist:", media_path)
    #                 return False
    #             time.sleep(1)    
    #             # Click attachment
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["attachment_button"]), duration=2)
    #             pyautogui.click()
    #             self.pause_controller.wait_if_paused()
    #             time.sleep(2)
    #             # Choose Photo/Video
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["photo_video_option"]), duration=1)
    #             pyautogui.click()
    #             time.sleep(3)

    #             # Paste file path
    #             pyperclip.copy(media_path)
    #             time.sleep(1)
    #             pyautogui.hotkey('ctrl', 'v')
    #             pyautogui.press('enter')
    #             time.sleep(2)

    #             # If caption text exists, type into caption box
    #             if message:
    #                 self.pause_controller.wait_if_paused()
    #                 pyautogui.moveTo(*self.percent_to_coords(*self.coords["caption_box"]), duration=2)
    #                 pyautogui.click()
    #                 pyautogui.typewrite(message, interval=0.05)

    #             # Send
    #             self.pause_controller.wait_if_paused()
    #             time.sleep(2)
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["send_button"]), duration=2)
    #             pyautogui.click()
    #             print("✅ Media sent" + (" with caption" if message else " without caption"))

    #             pyautogui.press('esc')
    #             return True

    #         # ----------------------------
    #         # CASE 2: ONLY MESSAGE
    #         # ----------------------------
    #         elif message:
    #             self.pause_controller.wait_if_paused()
    #             pyautogui.moveTo(*self.percent_to_coords(*self.coords["message_box"]), duration=1)
    #             pyautogui.click()
    #             pyautogui.typewrite(message, interval=0.1)
    #             pyautogui.press('enter')
    #             print("✅ Text message sent")
    #             return True

    #         # ----------------------------
    #         # CASE 3: NOTHING
    #         # ----------------------------
    #         else:
    #             print("⚠️ No media or message to send.")
    #             return False

    #     except InterruptedError:
    #         print("⏭️ Message skipped")
    #         self.pause_controller.reset_skip()
    #         return False
    #     except Exception as e:
    #         print(f"Error: {e}")
    #         return False
    def _stop_aware_sleep(self, seconds: float, chunk: float = 0.05):
        steps = int(max(1, seconds / chunk))
        for _ in range(steps):
            if self._should_stop():
                raise InterruptedError("Stopped during sleep")
            time.sleep(chunk)

    def send_whatsapp_message(self, client_name):
        try:
            # Check for stop before starting
            if self.pause_controller.stop_requested:
                raise InterruptedError("Stop requested")

            self.red_border_overlay.show()
            message = self.message_input.toPlainText().strip()
            media_paths = getattr(self, "selected_media_paths", [])

            self._stop_aware_sleep(1)

            # Stage 1: Search & confirm contact via OCR
            if not self.type_contact_name_and_wait_for_result(client_name):
                return False

            # Check stop
            if self.pause_controller.stop_requested:
                raise InterruptedError("Stop requested")

            # Stage 2: Select contact
            self.pause_controller.wait_if_paused()
            
            #pyautogui.moveTo(*self.percent_to_coords(*self.coords["contact_result"]), duration=self.settings.move_contact_result)
            x_percent, y_percent = self.coords["contact_result"]
            x, y = self.percent_to_coords(x_percent, y_percent)
            pyautogui.moveTo(x, y, duration=self.settings.move_contact_result)

            self._stop_aware_sleep(3)

            self.pause_controller.wait_if_paused()
            pyautogui.click()

            if self.pause_controller.stop_requested:
                raise InterruptedError("Stop requested")

            # Media/message handling...
            # For every sleep or wait, use self._stop_aware_sleep() or wait_if_paused() to be stop-aware

            # CASE 1: Media
            if media_paths:
                if self.pause_controller.stop_requested:
                    raise InterruptedError("Stop requested")

                # Verify all paths exist
                valid_media = [p for p in media_paths if os.path.isfile(p)]
                if not valid_media:
                    print("❌ No valid media files found")
                    return False
                time.sleep(1)
                # Build single string for multi-select (space separated paths)
                media_string = " ".join(f'"{p}"' for p in valid_media)  # quotes handle spaces in filenames
                print(f"📎 Sending multiple media: {media_string}")

                # Click attachment
                self.pause_controller.wait_if_paused()
                #pyautogui.moveTo(*self.percent_to_coords(*self.coords["attachment_button"]), duration=self.settings.move_attachment_button)
                x_percent, y_percent = self.coords["attachment_button"]
                x, y = self.percent_to_coords(x_percent, y_percent)
                pyautogui.moveTo(x, y, duration=self.settings.move_attachment_button)

                pyautogui.click()
                self.pause_controller.wait_if_paused()
                self._stop_aware_sleep(2)

                if self.pause_controller.stop_requested:
                    raise InterruptedError("Stop requested")

                # Choose Photo/Video
                #pyautogui.moveTo(*self.percent_to_coords(*self.coords["photo_video_option"]), duration=self.settings.move_photo_video_option)
                
                x_percent, y_percent = self.coords["photo_video_option"]
                x, y = self.percent_to_coords(x_percent,y_percent)
                pyautogui.moveTo(x, y, duration=self.settings.move_photo_video_option)
                
                pyautogui.click()
                self._stop_aware_sleep(2)

                # Paste all file paths at once
                pyperclip.copy(media_string)
                self._stop_aware_sleep(1)
                pyautogui.hotkey('ctrl', 'v')
                pyautogui.press('enter')
                self._stop_aware_sleep(3)

                # If caption exists → add
                if message:
                    if self.pause_controller.stop_requested:
                        raise InterruptedError("Stop requested")
                    self.pause_controller.wait_if_paused()
                    #pyautogui.moveTo(*self.percent_to_coords(*self.coords["caption_box"]), duration=self.settings.move_caption_box)
                    
                    x_percent, y_percent = self.coords["caption_box"]
                    x, y = self.percent_to_coords(x_percent, y_percent)
                    pyautogui.moveTo(x, y, duration=self.settings.move_caption_box)
                    
                    pyautogui.click()
                    pyautogui.typewrite(message, interval=0.05)

                if self.pause_controller.stop_requested:
                    raise InterruptedError("Stop requested")    
                # Send
                self.pause_controller.wait_if_paused()
                time.sleep(2)
                #pyautogui.moveTo(*self.percent_to_coords(*self.coords["send_button"]), duration=self.settings.move_send_button)
                
                x_percent, y_percent = self.coords["send_button"]
                x, y = self.percent_to_coords(x_percent, y_percent)
                pyautogui.moveTo(x, y, duration=self.settings.move_send_button)

                pyautogui.click()
                print("✅ Multiple media sent" + (" with caption" if message else ""))
                time.sleep(1)   # wait for WhatsApp to finish sending

                pyautogui.press('esc')    
                return True

            # ----------------------------
            # CASE 2: ONLY MESSAGE
            # ----------------------------
            elif message:
                if self.pause_controller.stop_requested:
                    raise InterruptedError("Stop requested")
                self.pause_controller.wait_if_paused()
                #pyautogui.moveTo(*self.percent_to_coords(*self.coords["message_box"]), duration=self.settings.move_message_box)
                
                x_percent, y_percent = self.coords["message_box"]
                x, y = self.percent_to_coords(x_percent, y_percent)
                pyautogui.moveTo(x, y, duration=self.settings.move_message_box)
                
                pyautogui.click()
                pyautogui.typewrite(message, interval=0.1)
                pyautogui.press('enter')
                print("✅ Text message sent")
                return True

            # ----------------------------
            # CASE 3: NOTHING
            # ----------------------------
            else:
                
                print("⚠️ No media or message to send.")
                return False

        except InterruptedError:
            print("⏭️ Message skipped")
            self.pause_controller.reset_skip()
            return False
        except Exception as e:
            print(f"Error: {e}")
            return False


    def stop(self):
        """Request to stop the automation immediately"""
        with self._lock:
            self._stop_requested = True
            self._paused = False  # ✅ force unpause so wait_if_paused can exit
        self.stopped_signal.emit()
        print("🛑 Stop requested")

    def stop_automation(self):
        """Stop the automation process"""
        self.stop_requested = True
        self.pause_controller.stop()

        if self.automation_thread and self.automation_thread.is_alive():
            print("🛑 Waiting for thread to finish...")
            self.automation_thread.join(timeout=1.0)

            if self.automation_thread.is_alive():
                print("⚠️ Thread still alive, forcing cleanup (cannot hard-kill threads)")
            else:
                print("✅ Automation thread exited cleanly")

        # Cleanup
        self.automation_thread = None
        self.on_stop_complete()


    def on_stop_complete(self):
        self.start_btn.setText("Start")  # Reset button label
        self.start_btn.setStyleSheet("background-color: #0078d7; color: white; border-radius: 4px; padding: 6px 12px;")
        self.timer.stop()
        self.red_border_overlay.hide()
        
        self.stop_requested = False
        self.is_automation_running = False    
        self.start_btn.setText("Start")# <-- Ensure automation flag is reset
            # 🔄 Reset all pause controller flags
        self.pause_controller.reset_all()
    
        print("✅ Automation completely stopped and cleaned up")


    def on_stopped(self):
        """Handle UI updates when stopped"""
        self.stop_automation()

    def str_to_timedelta(self,s):
        #h, m, s = map(int, s.split(':'))
        h, m, s = map(int, self.label_time_lapsed.text().split(':'))
        return timedelta(hours=h, minutes=m, seconds=s)

    def timedelta_to_str(self,td):
        total_seconds = int(td.total_seconds())
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02}:{m:02}:{s:02}"

    def initialize_database(self):
        conn = sqlite3.connect(user_resource_path("messages.db"))
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_stats (
                date TEXT PRIMARY KEY,
                sent INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                duration TEXT DEFAULT '00:00:00'
            )
        ''')

        conn.commit()
        conn.close()


    def load_previous_duration(self):
        """Load today's saved duration (if any) and resume timer from there"""
        conn = sqlite3.connect(user_resource_path("messages.db"))
        cursor = conn.cursor()
        today = date.today().isoformat()

        cursor.execute("SELECT duration FROM message_stats WHERE date = ?", (today,))
        row = cursor.fetchone()
        conn.close()

        if row and row[0]:
            h, m, s = map(int, row[0].split(":"))
            self.elapsed_seconds = h * 3600 + m * 60 + s
        else:
            self.elapsed_seconds = 0

        # Update the label immediately
        time_val = QTime(0, 0).addSecs(self.elapsed_seconds)
        
        self.label_time_lapsed.setText(time_val.toString("HH:mm:ss"))


    def get_total_usage(self):
        conn = sqlite3.connect(user_resource_path("messages.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(sent), SUM(skipped), COUNT(DISTINCT date) FROM message_stats")
        result = cursor.fetchone()
        
        # Get only non-zero durations
        cursor.execute("SELECT duration FROM message_stats WHERE duration IS NOT NULL AND duration != '00:00:00'")
        duration_records = cursor.fetchall()
        
        conn.close()

        # Calculate total duration in seconds
        total_seconds = 0
        for record in duration_records:
            if record[0] and record[0] != "00:00:00":
                try:
                    time_parts = record[0].split(':')
                    if len(time_parts) == 3:  # HH:MM:SS format
                        hours, minutes, seconds = map(int, time_parts)
                        total_seconds += hours * 3600 + minutes * 60 + seconds
                except ValueError:
                    pass  # Skip invalid formats
        
        # Convert total seconds back to HH:MM:SS format
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        total_duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        # If result is None, set all totals to 0
        if result is None:
            sent_total = skipped_total = total_usage = 0
        else:
            sent_total = result[0] if result[0] is not None else 0
            skipped_total = result[1] if result[1] is not None else 0
            total_usage = result[2] if result[2] is not None else 0

        return sent_total, skipped_total, total_usage, total_duration    

    def update_total_labels(self):
        sent_total, skipped_total, total_usage, total_duration = self.get_total_usage()
        self.label_total_sent.setText(str(sent_total))
        self.label_total_skipped.setText(str(skipped_total))
        self.label_total_used.setText(str(total_usage))
        self.label_total_hours.setText(str(total_duration))        

    # def increment_sent(self):
    #     update_stat("sent")
    #     self.update_label()
    #     self.update_total_labels()

    # def increment_skipped(self):
    #     update_stat("skipped")
    #     self.update_label()
    #     self.update_total_labels()

    def increment_sent(self):
        run_duration = self.parse_run_duration()  # Implement this to convert label text to timedelta
        self.update_stat("sent", run_duration)
        self.update_label()
        self.update_total_labels()

    def increment_skipped(self):
        run_duration = self.parse_run_duration()
        self.update_stat("skipped", run_duration)
        self.update_label()
        self.update_total_labels()

    def parse_run_duration(self):
        # Assumes label text is like "HH:mm:ss"
        time_str = self.label_time_lapsed.text()
        h, m, s = map(int, time_str.split(':'))
        return timedelta(hours=h, minutes=m, seconds=s)

    # def update_stat(self,type):
    #     conn = sqlite3.connect(resource_path("resources/messages.db"))
    #     cursor = conn.cursor()
    #     today = date.today().isoformat()
    #     cursor.execute("SELECT * FROM message_stats WHERE date = ?", (today,))
    #     row = cursor.fetchone()

    #     if row:
    #         if type == "sent":
    #             cursor.execute("UPDATE message_stats SET sent = sent + 1 WHERE date = ?", (today,))
    #         elif type == "skipped":
    #             cursor.execute("UPDATE message_stats SET skipped = skipped + 1 WHERE date = ?", (today,))
    #     else:
    #         cursor.execute("INSERT INTO message_stats (date, sent, skipped) VALUES (?, ?, ?)",
    #                        (today, 1 if type == "sent" else 0, 1 if type == "skipped" else 0))

    #     conn.commit()
    #     conn.close()
    
    def update_stat(self, type,run_duration=None):
        conn = sqlite3.connect(user_resource_path("messages.db"))
        cursor = conn.cursor()
        today = date.today().isoformat()

        duration_str = self.label_time_lapsed.text()  # <-- UI always reflects cumulative time now

        row = cursor.execute("SELECT sent, skipped FROM message_stats WHERE date = ?", (today,)).fetchone()

        if row:
            if type == "sent":
                cursor.execute("""
                    UPDATE message_stats
                    SET sent = sent + 1, duration = ?
                    WHERE date = ?""", (duration_str, today))
            elif type == "skipped":
                cursor.execute("""
                    UPDATE message_stats
                    SET skipped = skipped + 1, duration = ?
                    WHERE date = ?""", (duration_str, today))
        else:
            cursor.execute("""
                INSERT INTO message_stats (date, sent, skipped, duration)
                VALUES (?, ?, ?, ?)""", (
                    today,
                    1 if type == "sent" else 0,
                    1 if type == "skipped" else 0,
                    duration_str
                ))

        conn.commit()
        conn.close()

        
    def on_drive_upload_done(self, success, message):
        if success:
            print(message)
        else:
            QMessageBox.critical(self, "Upload Failed", message)
    
    def check_profile_filled(self):
        """Return True only if profile is filled correctly."""
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    return False

                mac_id = data.get("mac_id", "").strip()
                company_name = data.get("company_name", "").strip()

                if mac_id and company_name:
                    return True
        return False

    def get_profile_data(self):
        """Return mac_id, company_name if profile filled, else ('','')."""
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                try:
                    data = json.load(f)
                    mac_id = data.get("mac_id", "").strip()
                    company_name = data.get("company_name", "").strip()
                    return mac_id, company_name
                except json.JSONDecodeError:
                    return "", ""
        return "", ""
        
    def test_send_message(self):
    

        print("test_send_msg called")
        
        # Check if automation is already running
        if self.is_automation_running:
            print("⚠️ Automation is already running!")
            return
        if self.stop_requested:
            print("🛑 test_send_message aborted due to stop")
            return
    
        self.is_automation_running = True
    
        if not self.check_profile_filled():
            dlg = ProfileDialog(self)
            dlg.exec_()
            if not self.check_profile_filled():
                QMessageBox.critical(self, "Error", "You must complete Profile Settings before using the app.")
                sys.exit(0)

        if not self.search_bar.isVisible():
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Error")
            msg_box.setText("Kindly Select CSV File...!!")
            msg_box.setWindowIcon(QIcon("icons/error.png"))
            msg_box.exec_()
            return

        message = self.message_input.toPlainText().strip()
        media_paths = getattr(self, "selected_media_paths", [])

        if not media_paths and not message:
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Critical)
            msg_box.setWindowTitle("Error")
            msg_box.setText("Please provide either a message or select a media file.")
            msg_box.setWindowIcon(QIcon("icons/error.png"))
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.exec_()
            self.red_border_overlay.hide()
            return

        if self.start_btn.text() == "Start":
            # Clean up any previous thread
            if self.automation_thread and self.automation_thread.is_alive():
                print("🛑 Cleaning up previous thread...")
                self.stop_automation()
                time.sleep(1)  # Wait a bit for cleanup

            # Ask for start index
            dialog = QInputDialog(self)
            dialog.setInputMode(QInputDialog.IntInput)
            dialog.setWindowTitle("Enter Index")
            dialog.setLabelText("Please enter the index number:")
            dialog.setWindowIcon(QIcon(resource_path("icons/touch.png")))
            dialog.setFixedSize(300, 150)
            dialog.setIntValue(1) 
            dialog.setIntMaximum(2147483647)
            dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

            if dialog.exec_() == QInputDialog.Accepted:
                start_index = dialog.intValue()
                print("Index entered:", start_index)
            else:
                self.red_border_overlay.hide()
                return

            # Reset all states for fresh start
            self.stop_requested = False
            self.pause_controller.reset_stop()
            self.pause_controller.reset_skip()
            
            self.start_index = start_index
            print("start index", self.start_index)
            self.label_current_clientid.setText(str(self.start_index + 1))

            self.message_count = 0
            self.skipped_count = 0

            if self.check_profile_filled():
                mac_id, company_name = self.get_profile_data()
                self.upload_thread = DriveUploadThread(self.PATH, BASE_FOLDER, mac_id, company_name)
                print(self.PATH, BASE_FOLDER, mac_id, company_name)
            

            
                print("Uploading CSV to Drive silently...")
                #self.upload_thread = DriveUploadThread(self.PATH, BASE_FOLDER, MAC_ID, COMPANY_NAME)
                #print(self.PATH, BASE_FOLDER, MAC_ID, COMPANY_NAME)
                self.upload_thread.upload_done.connect(self.on_drive_upload_done)
                self.upload_thread.start()

                # Update UI
                self.start_btn.setText("Pause")
                self.start_btn.setStyleSheet("background-color: red; color: white; border-radius: 4px; padding: 6px 12px;")
                self.red_border_overlay.show()
                self.red_border_overlay.repaint()

                total_rows = self.table.rowCount()
                print("total_rows", total_rows)

                # Countdown before starting
                dialog = CountdownDialog(seconds=5, parent=self)
                if dialog.exec_() == QDialog.Accepted:
                    print("🚀 Sending now!")

                # Start timer
                self.timer.start(1000)
                
                # Mark automation as running
                self.is_automation_running = True
                try:
                    start_index = self.start_index or 0
                    
                    if not self.pause_controller.stop_requested:
                        # Create and start automation thread
                        self.automation_thread = threading.Thread(
                            target=self.run_automation,
                            args=(start_index,),
                            daemon=True
                        )
                        self.automation_thread.start()

                    else:
                        print("🛑 Automation not started because stop was requested")

                except Exception as e:
                    print(f"Error in test_send_message: {e}")
                    self.is_automation_running = False

            else:
                QMessageBox.warning(self, "Profile Missing", "⚠ Please fill your profile (MAC ID & Company Name) before uploading.")
                
    # def on_skip_clicked(self):
    #     self.skip_requested = True
    #     print("⏭️ Skip requested.")
    def run_automation(self, start_index):
        """The actual automation logic running in a separate thread"""
        total_rows = self.table.rowCount()
        self.message_count = 0
        self.skipped_count = 0
        skipped_contacts = []   # to keep track of skipped contacts

        try:
            for row in range(start_index, total_rows):
                # 🔴 Stop check at loop head
                if self.pause_controller.stop_requested:
                    print("🛑 Stop requested at loop head")
                    break

                # ⏸️ Pause handling
                try:
                    self.pause_controller.wait_if_paused()
                except InterruptedError:
                    print("🛑 Stopped during pause")
                    break

                # ✅ Get client details
                client_item = self.table.item(row, 1)
                mob_item    = self.table.item(row, 2)
                if not client_item or not mob_item:
                    continue

                client_name = client_item.text().strip()
                mob = mob_item.text().strip()

                # 🚫 Blacklist check
                if self.add_blacklist.is_blacklisted(mob):
                    print(f"⏭️ Skipping blacklisted mob: {mob} ({client_name}) at Row {row}")
                    self.skipped_count += 1
                    skipped_contacts.append(mob)
                    self.time_str = self.label_time_lapsed.text()
                    self.update_stats_signal.emit(row, client_name, self.message_count, self.skipped_count, self.time_str)
                    self.highlight_skipped_row(row)
                    continue

                # ⏭️ Skip requested
                if self.pause_controller.skip_requested:
                    print(f"⏭️ Skipped: {client_name} at Row {row}")
                    self.skipped_count += 1
                    skipped_contacts.append(mob)
                    self.pause_controller.reset_skip()
                    self.time_str = self.label_time_lapsed.text()
                    self.update_stats_signal.emit(row, client_name, self.message_count, self.skipped_count, self.time_str)
                    self.highlight_skipped_row(row)
                    continue

                try:
                    # 📤 Run the sending process
                    success = self.send_whatsapp_message(mob)
                    run_duration = self.parse_run_duration()

                    if success:
                        self.message_count += 1
                        self.update_stat("sent", run_duration)
                    else:
                        self.skipped_count += 1
                        skipped_contacts.append(mob)
                        self.update_stat("skipped", run_duration)

                    # 📊 Update live stats in UI
                    self.time_str = self.label_time_lapsed.text()
                    self.update_stats_signal.emit(row, client_name, self.message_count, self.skipped_count, self.time_str)

                    # ⏱ Controlled sleep with stop awareness
                    self._stop_aware_sleep(0.5)

                except InterruptedError:
                    print("🛑 Stop requested inside send_whatsapp_message")
                    break
                except Exception as e:
                    print(f"⚠️ Error while sending to {client_name}: {e}")
                    continue

        finally:
            self.is_automation_running = False
            print("✅ Automation completely stopped")
            print("📊 Final campaign summary:")
            print(f"✅ Total clients: {total_rows}")
            print(f"📨 Messages sent: {self.message_count}")
            print(f"⏭️ Skipped: {self.skipped_count}")
            print(f"📝 Skipped Contacts: {skipped_contacts}")

            self.pause_controller.pause()
            #self.on_stop_clicked()    
            self.red_border_overlay.hide()
            #self.campaign_finished_signal.emit()
            self.campaign_finished_signal.emit(
                total_rows,
                self.message_count,
                self.skipped_count,
                skipped_contacts
            )

            self.stop_complete_signal.emit()

            
    # def show_campaign_success_dialog(self):
    #     msg = QMessageBox()
    #     #msg.setIcon(QMessageBox.Information)
    #     msg.setWindowTitle("Campaign Status")
    #     msg.setText("Campaign finished successfully!")
    #     msg.setWindowIcon(QIcon(resource_path("icons/success.png")))
    #     msg.setIconPixmap(QPixmap(resource_path("icons/success.png")).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    #     msg.setStandardButtons(QMessageBox.Ok)
    #     msg.exec()
    # def show_campaign_success_dialog(self, total_clients, sent_count, skipped_count, skipped_contacts):
    #     msg = QMessageBox()
    #     msg.setWindowTitle("Campaign Status")
    #     msg.setWindowIcon(QIcon(resource_path("icons/success.png")))

    #     # ✅ Combine both old + new message text
    #     summary_text = (
    #         f"<b>🎉 Campaign finished successfully!</b><br><br>"
    #         f"<b>📊 Final Campaign Summary</b><br>"
    #         f"✅ Total clients: {total_clients}<br>"
    #         f"📨 Messages sent: {sent_count}<br>"
    #         f"⏭️ Skipped: {skipped_count}<br>"
    #         #f"📝 Skipped Contacts: {', '.join(skipped_contacts) if skipped_contacts else 'None'}"
    #     )

    #     msg.setText(summary_text)
    #     msg.setIconPixmap(
    #         QPixmap(resource_path("icons/success.png")).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    #     )
    #     msg.setStandardButtons(QMessageBox.Ok)
    #         # 💡 Increase message box width
    #     msg.setStyleSheet("""
    #         QMessageBox {
    #             min-width: 700px;        /* Wider overall box */
    #         }
    #         QLabel {
    #             min-width: 0px;          /* Prevent label from expanding unnecessarily */
    #             padding: 0px;            /* Remove inner padding */
    #             margin: 0px;             /* Remove outer margin */
    #         }
    #     """)


    #     msg.exec()

    def show_campaign_success_dialog(self, total_clients, sent_count, skipped_count, skipped_contacts):
        dialog = QDialog()
        dialog.setWindowTitle("Campaign Status")
        dialog.setWindowIcon(QIcon(resource_path("icons/success.png")))
        dialog.setStyleSheet("""
            QDialog {
                background-color: #fff;
                min-width: 400px;
                border-radius: 10px;
            }
            QLabel {
                font-size: 13px;
            }
            QPushButton {
                background-color: #0078d7;
                color: white;
                padding: 6px 18px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #005fa3;
            }
        """)

        # ✅ Icon
        icon_label = QLabel()
        icon_pixmap = QPixmap(resource_path("icons/success.png")).scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(icon_pixmap)

        # ✅ Summary text
        summary_text = (
            f"<b>🎉 Campaign finished successfully!</b><br>"
            f"<b>📊 Final Campaign Summary</b><br>"
            f"✅ Total clients: {total_clients}<br>"
            f"📨 Messages sent: {sent_count}<br>"
            f"⏭️ Skipped: {skipped_count}"
        )
        text_label = QLabel(summary_text)
        text_label.setTextFormat(Qt.RichText)
        text_label.setWordWrap(True)

        # ✅ Layouts
        h_layout = QHBoxLayout()
        h_layout.addWidget(icon_label, 0, Qt.AlignTop)
        h_layout.addWidget(text_label)
        h_layout.setSpacing(1)  # 👈 reduce this to control space between icon and text

        v_layout = QVBoxLayout(dialog)
        v_layout.addLayout(h_layout)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(dialog.accept)
        v_layout.addWidget(ok_button, alignment=Qt.AlignRight)

        dialog.exec_()


                    
    def highlight_skipped_row(self, row):
        """Highlight skipped row in the table"""
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(QBrush(QColor('red')))
                item.setForeground(QBrush(QColor('white')))
    
    update_stats_signal = pyqtSignal(int, str, int, int,str)
    
        
    # def load_csv(self):
    #     path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
    #     if not path:
    #         return

    #     self.loaded_csv_path = path  
    #     self.PATH = path
    #     self.table.setRowCount(0)
    #     self.all_rows.clear()

    #     with open(path, newline='', encoding='utf-8-sig') as file:
    #         reader = csv.DictReader(file)
    #         seen_names = set()  # To track duplicates

    #         temp_list = []
    #         for row in reader:
    #             name = row.get("client_name", "").strip()
    #             if name and name not in seen_names:
    #                 seen_names.add(name)
    #                 temp_list.append(name)

    #         # Add static index starting from 1
    #         self.all_rows = [(i + 1, name) for i, name in enumerate(temp_list)]

    #     self.update_table(self.all_rows)
    #     self.search_bar.setVisible(True)
    #     self.table.setVisible(True)
    #     self.label_total_client.setText(str(len(self.all_rows)))
        
        #self.upload_to_drive(path)
    

    def load_csv_async(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "sOpen CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return
        
        # # Show the loading overlay
        # self.loading_overlay.setGeometry(self.table.geometry())
        # self.loading_overlay.show()   
        
        self.PATH = file_path   
        
        # # Create thread pool if it doesn't exist
        if not hasattr(self, 'thread_pool'):
            self.thread_pool = QThreadPool()

        # Create and configure worker
        self.loader = CSVLoader(file_path)
        #self.loader.set_path(file_path)
        self.loader.signals.finished.connect(self.update_table)
        self.loader.signals.error.connect(self.show_error)

        self.loading_overlay.setGeometry(self.table.geometry())
        self.loading_overlay.show()
        self.loading_overlay.raise_()
        QApplication.processEvents()
    
        # Start the worker
        self.thread_pool.start(self.loader)

        
    # def update_table(self, final_df):
    #     # Fetch blacklisted mobiles from DBs
    #     self.loading_overlay.hide()
    #     if not hasattr(self, 'blacklist_db'):
    #         self.blacklist_db = blacklistdb()  # Your DB helper class
    #     blacklisted_mobiles = self.blacklist_db.get_all_blacklisted_mobiles()  # returns a set of mobiles

    #     self.table.setRowCount(len(final_df))
    #     self.table.setColumnCount(3)
    #     headers = ["Index", "Client Name", "Mob"]
    #     self.table.setHorizontalHeaderLabels(headers)

    #     for i, row in final_df.iterrows():
    #         widget = QWidget()
    #         layout = QHBoxLayout(widget)
    #         layout.setContentsMargins(5, 0, 5, 0)
    #         layout.setSpacing(2)

    #         checkbox = QCheckBox()
    #         checkbox.setStyleSheet("""
    #                  QCheckBox::indicator {
    #                     width: 10px;
    #                     height: 10px;
    #                     border-radius: 5px;
    #                     border: 1px solid gray;
    #                     }
    #                     QCheckBox::indicator:checked {
    #                      border: 1px solid #6DB800;
    #                      background: qradialgradient(
    #                       cx:0.5, cy:0.5, radius:0.7,
    #                      fx:0.5, fy:0.3,
    #                      stop:0 #A0FF40,
    #                      stop:1 #6DB800
    #                     ); 
    #                     } 
    #                     """)
    #         # Set checkbox style here if needed...
            
    #         # Check if this mobile is blacklisted, set checkbox checked
    #         mob = "" if pd.isna(row['mob']) else str(row['mob'])
            
    #         if mob in blacklisted_mobiles:
    #             checkbox.setChecked(True)
    #         else:
    #             checkbox.setChecked(False)

    #         # Add index label
    #         index_label = QLabel(str(row['Index']))

    #         layout.addWidget(checkbox)
    #         layout.addWidget(index_label)
    #         layout.addStretch()

    #         self.table.setCellWidget(i, 0, widget)
    #         client_name = "" if pd.isna(row['client_name']) else str(row['client_name'])
    #         self.table.setItem(i, 1, QTableWidgetItem(client_name))
    #         self.table.setItem(i, 2, QTableWidgetItem(mob))
    def on_checkbox_toggled(self, row, checked):
        if 0 <= row < len(self.checkbox_states):
            self.checkbox_states[row] = checked
            if checked:
                name = self.current_df.iloc[row]['client_name']
                print(f"Adding to blacklist - Row: {row}, Name: {name}")
            else:
                print(f"Removing from blacklist - Row: {row}")
        else:
            print(f"⚠ Row {row} out of range (len={len(self.checkbox_states)})")
            

    def update_table(self, final_df):
        #final_df, checkbox_states = data_tuple  # checkbox_states currently all False
        
        # Get blacklisted numbers from DB
        if not hasattr(self, 'blacklist_db'):
            self.blacklist_db = blacklistdb()
        blacklisted_mobiles = self.blacklist_db.get_all_blacklisted_mobiles()

        # Create updated checkbox states based on mobile match
        checkbox_states = []
        # self.current_df = final_df
        # self.table.setRowCount(len(final_df))

        # # Initialize state tracking lists
        # self.checkbox_states = [False] * len(final_df)
       

        for _, row in final_df.iterrows():
            mob = row['mob']
            checkbox_states.append(mob in blacklisted_mobiles)

        # Continue as before to fill the table with these checkbox states
        self.loading_overlay.hide()
        self.table.blockSignals(True)
        try:
            self.current_df = final_df
            self.table.setRowCount(len(final_df))
            self.checkbox_states = [False] * len(final_df)
            self.blacklist = {}   
            #self.blacklist = [False] * len(final_df)
            #self.checked_rows = [False] * len(final_df)

            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Index", "Client Name", "Mobile"])
            
            for row_idx, (i, row) in enumerate(final_df.iterrows()):
                item = QTableWidgetItem(str(row['Index']))
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)

                # ✅ Use row_idx instead of i
                item.setCheckState(Qt.Checked if checkbox_states[row_idx] else Qt.Unchecked)

                self.table.setItem(row_idx, 0, item)
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(row['client_name'])))
                self.table.setItem(row_idx, 2, QTableWidgetItem(str(row['mob'])))
                
                self.search_bar.setVisible(True)
                self.table.setVisible(True)
                self.label_total_client.setText(str(len(final_df)))
        finally:
            self.table.blockSignals(False)

        if not self.table.receivers(self.table.itemChanged):
            self.table.itemChanged.connect(self.handle_checkbox_change)

        # Adjust columns
        #self.table.setColumnWidth(0, 40)
        #self.table.setColumnWidth(1, 200)
        #self.table.horizontalHeader().setStretchLastSection(True)

        #self.highlight_blacklisted_rows()

    def show_error(self, message):
        self.loading_overlay.hide()
        # Show error message to user
        QMessageBox.critical(self, "Error", message)

    def verify_blacklist_contents(self):
        """Verify and print blacklist contents for debugging"""
        if not hasattr(self, 'blacklist'):
            print("Blacklist attribute doesn't exist!")
            return
            
        print("\nCurrent Blacklist Contents:")
        print(f"Total entries: {len(self.blacklist)}")
        
        for index, data in self.blacklist.items():
            print(f"\nIndex: {index}")
            print(f"Name: {data.get('name', 'N/A')}")
            print(f"Mobile: {data.get('mobile', 'N/A')}")
            print(f"Timestamp: {data.get('timestamp', 'N/A')}")
        
        print("\nTable Check States:")
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                print(f"Row {row}: Index {item.text()} - {'Checked' if item.checkState() == Qt.Checked else 'Unchecked'}")
    
    # def handle_checkbox_change(self, item):
    #     if item.column() == 0:
    #         try:
    #             row = item.row()  # zero-based
    #             # Update checkbox state list safely
    #             if 0 <= row < len(self.checkbox_states):
    #                 self.checkbox_states[row] = (item.checkState() == Qt.Checked)
    #             else:
    #                 print(f"Warning: row index {row} out of checkbox_states range")

    #             index = int(self.table.item(row, 0).text())
    #             name = self.table.item(row, 1).text()
    #             mobile = self.table.item(row, 2).text()

    #             if item.checkState() == Qt.Checked:
    #                 print(f"Adding to blacklist - Index: {index}, Name: {name}")
    #                 self.blacklist[index] = {
    #                     "name": name,
    #                     "mobile": mobile,
    #                     "timestamp": datetime.datetime.now().isoformat(),
    #                     "reason": ""
    #                 }
    #                 self.add_blacklist = blacklistdb()
    #                 self.add_blacklist.add_to_blacklist(index, name, mobile, reason="")
    #             else:
    #                 print(f"Removing from blacklist - Index: {index}")
    #                 self.add_blacklist.remove_from_blacklist(index)

    #             print(f"Current blacklist: {self.blacklist}")
    #         except Exception as e:
    #             print(f"Error in checkbox handler: {e}")

    def handle_checkbox_change(self, item):
        if item.column() == 0:
            try:
                row = item.row()
                if 0 <= row < len(self.checkbox_states):
                    self.checkbox_states[row] = (item.checkState() == Qt.Checked)

                index_val = int(self.table.item(row, 0).text())
                name = self.table.item(row, 1).text()
                mobile = self.table.item(row, 2).text()

                if item.checkState() == Qt.Checked:
                    print(f"Adding to blacklist - Row: {row}, Index: {index_val}, Name: {name}")
                    self.blacklist[row] = {
                        "index": index_val,
                        "name": name,
                        "mobile": mobile,
                        "timestamp": datetime.now().isoformat(),
                        "reason": ""
                    }
                    self.add_blacklist.add_to_blacklist(index_val, name, mobile, reason="")
                else:
                    print(f"Removing from blacklist - Row: {row}, Index: {index_val}")
                    self.add_blacklist.remove_from_blacklist(index_val)
                    if row in self.blacklist:
                        del self.blacklist[row]

                print(f"Current blacklist: {self.blacklist}")
            except Exception as e:
                print(f"Error in checkbox handler: {e}")

          
          
    # def filter_table(self, text):
    #     filtered = [
    #         (index, name) for index, name in self.all_rows if text.lower() in name.lower()
    #     ]
    #     self.update_table(filtered)
    def filter_table(self, text):
        text = text.lower().strip()
        for row in range(self.table.rowCount()):
            match = False
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(row, not match)

    def update_stats(self, row=0, current="", sent=0, skipped=0):
        self.label_current_clientid.setText(str(row + 1))
        self.label_current_client.setText(current)
        self.label_sent.setText(str(sent))
        self.label_skipped.setText(str(skipped))
        #self.label_time_lapsed.setText(("00:00:00"))
        
    def show_calibration_menu(self):
        # Show menu right below the Calibrate button
        button_pos = self.calibrate_btn.mapToGlobal(self.calibrate_btn.rect().bottomLeft())
        self.calibration_menu.exec_(button_pos)    
    def show_overlay(self):
        self.showMinimized()  # Minimize the main window
        self.overlay = Overlay(parent=self, limited=False)
        self.overlay.show()

    def show_limited_overlay(self):
        self.showMinimized()  # Optional
        self.overlay = Overlay(parent=self, limited=True)
        self.overlay.show()    

    def open_profile_dialog(self):
        dialog = ProfileDialog(self)
        dialog.exec_()    
    
    # def choose_media_file(self):
    #     file_filter = "Media Files (*.png *.jpg *.jpeg *.mp4 *.mp3 *.avi *.mov *.wav)"
    #     path, _ = QFileDialog.getOpenFileName(self, "Select Media File", "", file_filter)
    #     if path:
    #         normalized = os.path.normpath(path)  # ✅ Normalize path to use backslashes
    #         self.media_label.setText(os.path.basename(normalized))  # Show filename only
    #         self.selected_media_path = normalized  # ✅ Store cleaned path
    #         display_name = self.truncate_text(normalized, max_length=40)  
    
    def choose_media_file(self):
        # Filters
        image_filter = "Images (*.png *.jpg *.jpeg *.gif)"
        video_filter = "Videos (*.mp4 *.avi *.mov)"
        all_filter = "Media Files (*.png *.jpg *.jpeg *.gif *.mp4 *.avi *.mov)"

        # Allow multiple selection
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media Files",
            "",
            f"{all_filter};;{image_filter};;{video_filter}"
        )

        if not paths:
            return

        # Ensure storage
        if not hasattr(self, "selected_media_paths"):
            self.selected_media_paths = []

        # Temporary storage for new valid files
        new_media = []

        for path in paths:
            normalized = os.path.normpath(path)
            ext = os.path.splitext(normalized)[1].lower()

            # --- Video Rule: only 1 allowed ---
            if ext in ['.mp4', '.avi', '.mov']:
                # remove any existing video
                self.selected_media_paths = [
                    p for p in self.selected_media_paths
                    if os.path.splitext(p)[1].lower() not in ['.mp4', '.avi', '.mov']
                ]
                new_media.append(normalized)

            # --- Image Rule: max 5 images ---
            elif ext in ['.png', '.jpg', '.jpeg', '.gif']:
                current_image_count = sum(
                    1 for p in self.selected_media_paths
                    if os.path.splitext(p)[1].lower() in ['.png', '.jpg', '.jpeg', '.gif']
                )
                new_image_count = sum(
                    1 for p in new_media
                    if os.path.splitext(p)[1].lower() in ['.png', '.jpg', '.jpeg', '.gif']
                )
                if (current_image_count + new_image_count) <= 5:
                    new_media.append(normalized)

        # Extend with validated files only
        self.selected_media_paths.extend(new_media)

        # Refresh preview
        self.update_media_preview()
    
    def generate_video_thumbnail(self, video_path):
        """Generate a thumbnail for video files"""
        try:
            # Method 1: Use a video icon (simplest approach)
            video_icon = QPixmap(50, 50)
            video_icon.fill(Qt.transparent)
            
            painter = QPainter(video_icon)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Draw play icon
            painter.setBrush(QColor(0, 0, 0, 150))  # Semi-transparent black
            painter.drawEllipse(5, 5, 40, 40)
            
            painter.setBrush(Qt.white)
            painter.drawPolygon(
                QPoint(20, 15), 
                QPoint(20, 35), 
                QPoint(35, 25)
            )
            
            painter.end()
            return video_icon
            
        except Exception as e:
            print(f"Error generating video thumbnail: {e}")
            return None
    
    def update_media_preview(self):
        """Refresh all media previews (images + video)"""
        # Remove previous previews
        if hasattr(self, 'preview_container'):
            for i in reversed(range(self.preview_layout.count())):
                widget = self.preview_layout.itemAt(i).widget()
                if widget:
                    widget.deleteLater()
        else:
            self.preview_container = QWidget()
            self.preview_layout = QHBoxLayout(self.preview_container)
            self.preview_layout.setSpacing(2)  # Reduced spacing between previews
            self.preview_layout.setContentsMargins(0, 0, 0, 0)
            self.media_container.addWidget(self.preview_container)

        for file_path in self.selected_media_paths:
            ext = os.path.splitext(file_path)[1].lower()

            # --- Wrapper widget for each preview ---
            preview_widget = QWidget()
            preview_widget.setFixedSize(60, 60)  # Container size
            preview_widget.setStyleSheet("background: transparent;")

            # Absolute layout to overlay close button
            overlay_layout = QVBoxLayout(preview_widget)
            overlay_layout.setContentsMargins(0, 0, 0, 0)
            overlay_layout.setSpacing(0)

            # Preview label
            preview_label = QLabel(preview_widget)
            preview_label.setFixedSize(60, 60)
            preview_label.setAlignment(Qt.AlignCenter)
            preview_label.setStyleSheet("""
                QLabel {
                    border: 2px dashed #cccccc;
                    background-color: #f8f8f8;
                }
            """)

            if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull():
                    preview_label.setPixmap(pixmap.scaled(
                        preview_label.width(),
                        preview_label.height(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    ))
            elif ext in ['.mp4', '.avi', '.mov']:
                thumb = self.generate_video_thumbnail(file_path)
                preview_label.setPixmap(thumb)

            # Close button (overlay in top-right corner)
            close_btn = QPushButton("×", preview_widget)
            close_btn.setFixedSize(18, 18)
            close_btn.move(preview_label.width() - 20, 2)  # Position top-right
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: rgba(255, 0, 0, 180);
                    color: white;
                    border: none;
                    font-weight: bold;
                    font-size: 10px;
                    border-radius: 9px;
                }
                QPushButton:hover {
                    background-color: rgba(200, 0, 0, 200);
                }
            """)
            close_btn.clicked.connect(lambda _, fp=file_path: self.remove_media(fp))

            overlay_layout.addWidget(preview_label, alignment=Qt.AlignCenter)

            self.preview_layout.addWidget(preview_widget)


    def remove_media(self, file_path):
        """Remove specific media from selection"""
        if file_path in self.selected_media_paths:
            self.selected_media_paths.remove(file_path)
        self.update_media_preview()

        

    # def update_timer(self):
    #     self.elapsed_seconds += 1
    #     time_val = QTime(0, 0).addSecs(self.elapsed_seconds)
    #     self.label_time_lapsed.setText(f"{time_val.toString('HH:mm:ss')}")
    
    def update_timer(self):
        # Check if day changed
        current_day = date.today().isoformat()
        if not hasattr(self, "last_day"):
            self.last_day = current_day
        elif self.last_day != current_day:
            # New day → reset timer + labels
            self.elapsed_seconds = 0
            self.label_sent.setText("0")
            self.label_skipped.setText("0")
            self.label_current_clientid.setText("0")
            self.label_current_client.setText("")
            self.last_day = current_day
            print("🔄 New day detected → stats reset")

        # Increment elapsed time
        self.elapsed_seconds += 1
        time_val = QTime(0, 0).addSecs(self.elapsed_seconds)
        self.label_time_lapsed.setText(time_val.toString("HH:mm:ss"))


    def on_message_type_change(self, msg_type):
        # Show file picker only if Image or Video is selected
         self.attachment_button.setVisible(msg_type in ["Image", "Video"])

    def truncate_text(self, text, max_length=40):
        if len(text) <= max_length:
            return text
        return text[:20] + "..." + text[-15:]          
    
    def handle_start_pause_resume(self):
        current_text = self.start_btn.text()
        print(f"Button clicked. Current text: {current_text}")

        if current_text == "Start":
            # 🛑 Clean up any old automation
            if self.automation_thread and self.automation_thread.is_alive():
                print("🛑 Old automation still alive, stopping it first...")
                self.stop_automation()
                return

            # Reset state before fresh start
            self.pause_controller.reset_all()
            self.stop_requested = False
            self.is_automation_running = False  # allow test_send_message to run

            # 🚀 Call test_send_message() (this will start run_automation thread inside it)
            print("🚀 Calling test_send_message...")
            self.test_send_message()

            # test_send_message itself will switch button to Pause when it succeeds

        elif current_text == "Pause":
            print("⏸️ Pausing automation...")
            self.pause_controller.pause()
            self.start_btn.setText("Resume")
            self.start_btn.setStyleSheet(
                "background-color: orange; color: white; border-radius: 4px; padding: 6px 12px;"
            )

        elif current_text == "Resume":
            print("▶️ Resuming automation...")
            self.pause_controller.resume()
            self.start_btn.setText("Pause")
            self.start_btn.setStyleSheet(
                "background-color: red; color: white; border-radius: 4px; padding: 6px 12px;"
            )


    # def stop_automation(self):
    #     print("🛑 Force stopping automation...")
    #     self.pause_controller.stop()  # sets stop_requested = True & unpauses
    #     self.stop_requested = True

    #     if self.automation_thread and self.automation_thread.is_alive():
    #         self.automation_thread.join(timeout=2)
    #         if self.automation_thread.is_alive():
    #             print("⚠️ Thread still alive after join()")

    #     # Reset UI
    #     self.start_btn.setText("Start")
    #     self.start_btn.setStyleSheet("background-color: #0078d7; color: white;")
    #     self.red_border_overlay.hide()
    #     self.timer.stop()

    #     # Do NOT reset stop_requested here; it stays True until user clicks Start
    #     print("✅ Automation stopped and cleaned up")




    def setup_shortcuts(self):
        pass
        # keyboard.add_hotkey('ctrl+alt+s', lambda: self.trigger_button('Start'))
        # keyboard.add_hotkey('ctrl+alt+m', lambda: self.trigger_button('Pause'))

    def trigger_button(self, mode):
        print(f"trigger_button called with mode={mode}, button text={self.start_btn.text()}")
        
        if mode == 'Start' and self.start_btn.text() == 'Start':
            QTimer.singleShot(0, self.test_send_message)  # Execute in main thread

        elif mode == 'Pause' and self.start_btn.text() == 'Pause':
            QTimer.singleShot(0, self.pause)

        elif mode == 'Pause' and self.start_btn.text() == 'Resume':
            QTimer.singleShot(0, self.resume)
    
    # def on_stop_clicked(self):
    #     """Stop the automation process"""
    #     if self.automation_thread and self.automation_thread.is_alive():
    #         # Show confirmation dialog
    #         msg_box = QMessageBox(self)
    #         msg_box.setIcon(QMessageBox.Question)
    #         msg_box.setWindowTitle("Confirm Stop")
    #         msg_box.setText("Are you sure you want to stop the automation?")
    #         msg_box.setWindowIcon(QIcon(resource_path("icons/stop.png")))
    #         msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    #         msg_box.setDefaultButton(QMessageBox.No)
            
    #         if msg_box.exec_() == QMessageBox.Yes:
    #             self.stop_automation()
    #     else:
    #         QMessageBox.information(self, "Info", "No automation process is running.")
    def on_stop_clicked(self):
        """Stop button pressed"""
        if self.automation_thread and self.automation_thread.is_alive():
            print("🛑 Stop clicked")
            self.stop_automation()
        else:
            print("ℹ️ No automation running")

    def stop_automation(self):
        """Stop the automation immediately"""
        if getattr(self, "_stop_in_progress", False):
            return  # prevent recursion
        self._stop_in_progress = True

        print("🛑 Force stopping automation...")
        self.stop_requested = True
        self.pause_controller.stop()

        if self.automation_thread and self.automation_thread.is_alive():
            self.automation_thread.join(timeout=2)

        # Reset UI
        self.start_btn.setText("Start")
        self.start_btn.setStyleSheet("background-color: #0078d7; color: white; border-radius: 4px; padding: 6px 12px;")
        self.timer.stop()
        self.red_border_overlay.hide()

        # Only emit once, and ensure stop flag prevents recursion
        try:
            self.stop_complete_signal.emit()
        except Exception:
            pass

        self._stop_in_progress = False

    
    def closeEvent(self, event):
        self.on_exit_clicked()
        event.ignore()  # Prevent auto-close until confirmed inside on_exit_clicked()

    def on_exit_clicked(self):
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("Confirm Exit")
        msg_box.setText("Are you sure you want to exit?")
        msg_box.setWindowIcon(QIcon(resource_path("icons/close.png")))  # custom window titlebar icon

        # Optional: Replace default question icon with a custom image
        # pixmap = QPixmap("icons/question.png").scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # msg_box.setIconPixmap(pixmap)

        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        reply = msg_box.exec_()

        if reply == QMessageBox.Yes:
            print("✅ User confirmed exit.")
            self.skip_requested = True
            QApplication.quit()
        else:
            print("❌ Exit cancelled.")
    

    def keyPressEvent(self, event):
        if event.modifiers() == (Qt.ControlModifier | Qt.AltModifier):
            if event.key() == Qt.Key_K:
                print("⏭️ Skip triggered by Ctrl + Alt + K")
                self.skip_requested = True

    def on_skip_clicked(self):
        self.skip_requested = True
        print("⏭️ Skip requested.")

    # def is_contact_not_found(self):
    #     screenshot = pyautogui.screenshot()
    #     img_np = np.array(screenshot)
    #     img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
    #     gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    #     # 🔹 Load coordinates from layout JSON
    #     with open(DATA_FILE, "r") as f:
    #         data = json.load(f)

    #     # 🔹 Search across all sections
    #     all_regions = data.get("message", []) + data.get("photo_media", [])
    #     region = next((item for item in all_regions if item['type'] == 'contact_not_found'), None)

    #     if not region:
    #         print("❌ contact_not_found region not defined in layout.")
    #         return False

    #     x, y, w, h = region["x"], region["y"], region["width"], region["height"]

    #     # Crop dynamically
    #     cropped = gray[y:y+h, x:x+w]

    #     if cropped.size == 0:
    #         print("❌ Cropped region is empty — check your coordinates!")
    #         return False

    #     _, thresh = cv2.threshold(cropped, 150, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    #     pil_img = Image.fromarray(thresh)

    #     cv2.imwrite("debug_cropped.png", cropped)  # Debug

    #     text = pytesseract.image_to_string(pil_img).strip()
    #     print("OCR Text:", repr(text))

    #     return "no chats, contacts or messages found" in text.lower()
    def is_contact_not_found(self):
        screenshot = pyautogui.screenshot()
        img_np = np.array(screenshot)
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # Load coordinates from layout JSON
        with open(DATA_FILE, "r") as f:
            data = json.load(f)

        all_regions = data.get("message", []) + data.get("photo_media", [])
        region = next((item for item in all_regions if item['type'] == 'contact_not_found'), None)

        if not region:
            print("❌ contact_not_found region not defined in layout.")
            return False

        x, y, w, h = region["x"], region["y"], region["width"], region["height"]

        cropped = gray[y:y+h, x:x+w]
        if cropped.size == 0:
            print("❌ Cropped region is empty — check your coordinates!")
            return False

        _, thresh = cv2.threshold(cropped, 150, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        pil_img = Image.fromarray(thresh)

        cv2.imwrite("debug_cropped1.png", cropped)  # keep for debugging

        text = pytesseract.image_to_string(pil_img).lower().replace("\n", " ").strip()
        print("OCR Text:", repr(text))

        # ✅ Substring check for robustness
        keywords = ["no chats", "no contacts", "no messages"]
        return any(word in text for word in keywords)


    
    def percent_to_coords(self,x_percent, y_percent):
        screenWidth, screenHeight = pyautogui.size()
        return int(screenWidth * x_percent), int(screenHeight * y_percent)
    
    @property
    def coords(self):
        # dynamically load every time you access coords
        return self.get_coords()


    def get_coords():
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
        except FileNotFoundError:
            print("layout_data.json not found.")
            return {}
        except json.JSONDecodeError:
            print("layout_data.json contains invalid JSON.")
            return {}

        coordz = {}
        for section in ['message', 'photo_media']:
            for item in data.get(section, []):
                if all(k in item for k in ('type', 'center_x_percent', 'center_y_percent')):
                    coordz[item['type']] = (
                        item['center_x_percent'],
                        item['center_y_percent']
                    )

        # Debug print
        print("coords = {")
        for k, v in coordz.items():
            print(f'    "{k}": ({v[0]}, {v[1]}),')
        print("}")
        
        return coordz

    coords = get_coords()

            
class CountdownDialog(QDialog):
    def __init__(self, seconds=5, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.seconds = seconds

        self.setWindowTitle("Please Wait")
        self.setFixedSize(350, 200)
        self.setStyleSheet("background-color: white;")
        
    
        self.label = QLabel(f"⏳ Whatsapp Sending Starts in {self.seconds}...", self)
        self.label.setStyleSheet("font-size: 16px; font-family: 'Segoe UI';")
        self.label.setAlignment(Qt.AlignCenter)
        
        self.info_label = QLabel("⚠️ Keep WhatsApp Web active", self)
        self.info_label.setStyleSheet("font-size: 14px; font-family: 'Segoe UI'; color: #FF5722;")
        self.info_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout()
        
        layout.addWidget(self.label)
        layout.addWidget(self.info_label)
        self.setLayout(layout)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)

    def update_countdown(self):
        self.seconds -= 1
        if self.seconds > 0:
            self.label.setText(f"⏳ Whatsapp Sending Starts in {self.seconds}...")
        else:
            self.timer.stop()
            self.accept()  # Closes the dialog

                
class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowIcon(QIcon(resource_path("icons/desk-icon.ico")))  # ← Add this line
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(600, 320)  # Total splash window size
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        pixmap = QPixmap(resource_path("icons/logo.png")).scaled(600, 320, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        target_size = QSize(600, 320)
        
        self.logo_label = QLabel()
        self.logo_label.setPixmap(pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.logo_label,alignment=Qt.AlignCenter)
        
        cropped_pixmap = pixmap.copy(
            (pixmap.width() - target_size.width()) // 2,
            (pixmap.height() - target_size.height()) // 2,
            target_size.width(),
            target_size.height()
        )
        cropped_pixmap.save("cropped_logo.png", "PNG")
        
        self.logo_label = QLabel()
        self.logo_label.setPixmap(cropped_pixmap)
        self.logo_label.setAlignment(Qt.AlignCenter)
        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setFixedHeight(8)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 0px;
                background-color: #ccc;
            }
            QProgressBar::chunk {
                background-color: #2d89ef;
            }
        """)
        layout.addWidget(self.progress)

        self.setLayout(layout)

        self.layout_file = self.get_layout_file()  # store path in the instance

        # Ensure layout file exists
        if not os.path.exists(self.layout_file):
            with open(self.layout_file, "w") as f:
                json.dump([], f, indent=4)
        
        self.counter = 0
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(30)  # Adjust speed here

    def update_progress(self):
        self.counter += 1
        self.progress.setValue(self.counter)
        if self.counter >= 100:
            self.timer.stop()
            self.launch_main()

    def launch_main(self):  
        self.close()
        self.main = WhatsAppAutomationUI()
        self.main.setWindowIcon(QIcon(resource_path("icons/desk-icon.ico")))  # ← Add this line
        self.main.show()

    @staticmethod 
    def get_user_data_path():
        """Return writable app data folder (cross-platform)."""
        data_path = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        os.makedirs(data_path, exist_ok=True)
        return data_path

    @classmethod    
    def get_layout_file(cls):
        """Return full path to layout_data.json inside AppData."""
        return os.path.join(cls.get_user_data_path(), "layout_data.json")

                    
if __name__ == "__main__":
    
    ok, free_mb = WhatsAppAutomationUI.check_free_space(200)  # require 200 MB free
    if not ok:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Not enough disk space.\nOnly {free_mb} MB free. Please empty space and try again.",
            "Setup Error",
            0x10
        )
        sys.exit(1)

    try:    
        if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
            QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
        if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
            QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
        app = QApplication(sys.argv)
        #window = WhatsAppAutomationUI()
        #window.show()
        app.setWindowIcon(QIcon(resource_path("icons/desk-icon.ico")))  # or .png if not packed
    
        splash = SplashScreen()
        splash.show()
        

        sys.exit(app.exec_())
    except Exception as e:
        import traceback, ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"Unexpected error during setup:\n{e}",
            "Setup Error",
            0x10
        )
        sys.exit(1)

    #pyinstaller --add-data "resources/Tesseract-OCR;resources/Tesseract-OCR" --icon=icons/app.ico main.py

    
    #pyinstaller --onefile --windowed --add-data "resources/*;resources"  --exclude-module PySide6  --add-data "icons/*;icons" def10.py

#working pyinstaller --windowed  --add-data "resources/*;resources" --exclude-module PySide6  --add-data "icons/*;icons" def10.py


#test single pyinstaller --onefile --windowed --add-data "resources/*;resources"  --exclude-module PySide6  --add-data "icons/*;icons" --add-data "resources/Tesseract-OCR;resources/Tesseract-OCR" --icon=icons/desk-icon.ico  --version-file=resources/file_version.txt def19.py
#test pyinstaller --windowed  --add-data "resources/*;resources" --exclude-module PySide6  --add-data "icons/*;icons"  --add-data "resources/Tesseract-OCR;resources/Tesseract-OCR" --icon=icons/desk-icon.ico  def16.py



#final pyinstaller --onefile --windowed --add-data "resources/license.txt;resources" --add-data "icons/*;icons" --exclude-module PySide6 --add-data "resources/Tesseract-OCR;resources/Tesseract-OCR" --icon=icons/desk-icon.ico --version-file=resources/file_version.txt def20.py




# pyinstaller --onefile --windowed --add-data "resources/license.txt;resources" --add-data "icons/*;icons" --add-data "resources/Tesseract-OCR;resources/Tesseract-OCR" --add-data "support/*;support" --exclude-module PySide6 --icon=icons/desk-icon.ico --version-file=resources/file_version.txt def21.py

