import sys
import os
from typing import Dict, Any

from PySide6.QtCore import Qt, QThread, Slot, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QFormLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QRadioButton,
    QProgressBar, QTextEdit, QFileDialog, QStatusBar, QMessageBox, QCheckBox
)
from PySide6.QtGui import QFont, QIcon

# Import the worker and helper classes from our other file
from compressor_worker import CompressorWorker, ImageStats, ProcessResult

# ==============================================================================
# SCRIPT CONFIGURATION DEFAULTS
# ==============================================================================
# Will use these to populate the GUI initially
CONFIG_DEFAULTS: Dict[str, Any] = {
    "input_folder": "raw_images",
    "output_folder": "jpeg_images",
    "supported_extensions": (".png", ".webp", ".bmp", ".tiff", ".gif"),
    "worker_count": os.cpu_count() or 4,
    "target_size_mode": True,
    "min_quality": 70,
    "max_quality": 98,
    "base_quality": 92,
    "target_size_kb": 250,
    "save_on_target_failure": True,
}

class ImageCompressorApp(QMainWindow):
    """The ABSOLUTE HOLY Main Window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Image Compressor")
        self.setGeometry(100, 100, 900, 700)

        # Worker thread management
        self.thread: QThread | None = None
        self.worker: CompressorWorker | None = None

        # Main widget and layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # Create UI sections
        self._create_settings_panel()
        self._create_output_panel()
        
        self.main_layout.addLayout(self.settings_layout, stretch=1)
        self.main_layout.addLayout(self.output_layout, stretch=2)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Idle. Ready to start.")
        #Test log panel
        self.log_edit.append("Logger Running...")
        
    def _create_settings_panel(self):
        """Creates the left panel with all configuration options."""
        self.settings_layout = QVBoxLayout()
        self.settings_layout.setContentsMargins(10, 10, 10, 10)
        
        # --- Group Boxes for organization ---
        self._create_io_group()
        self._create_strategy_group()
        self._create_concurrency_group()
        
        # --- Start/Stop Button ---
        self.start_button = QPushButton("🚀 Start Compression")
        self.start_button.setFixedHeight(40)
        font = self.start_button.font()
        font.setPointSize(12)
        font.setBold(True)
        self.start_button.setFont(font)
        self.start_button.clicked.connect(self.toggle_compression)
        
        # --- Add all widgets to layout ---
        self.settings_layout.addWidget(self.io_group)
        self.settings_layout.addWidget(self.strategy_group)
        self.settings_layout.addWidget(self.concurrency_group)
        self.settings_layout.addStretch()
        self.settings_layout.addWidget(self.start_button)
        
        self.control_widgets = [
            self.io_group, self.strategy_group, self.concurrency_group
        ]

    def _create_io_group(self):
        self.io_group = QGroupBox("Input / Output")
        layout = QFormLayout()

        # Input folder
        self.input_folder_edit = QLineEdit(CONFIG_DEFAULTS['input_folder'])
        input_btn = QPushButton("Browse...")
        input_btn.clicked.connect(self._select_input_folder)
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_folder_edit)
        input_layout.addWidget(input_btn)
        layout.addRow("Input Folder:", input_layout)

        # Output folder
        self.output_folder_edit = QLineEdit(CONFIG_DEFAULTS['output_folder'])
        output_btn = QPushButton("Browse...")
        output_btn.clicked.connect(self._select_output_folder)
        output_layout = QHBoxLayout()
        output_layout.addWidget(self.output_folder_edit)
        output_layout.addWidget(output_btn)
        layout.addRow("Output Folder:", output_layout)

        self.io_group.setLayout(layout)

    def _create_strategy_group(self):
        self.strategy_group = QGroupBox("Compression Strategy & Quality")
        main_layout = QVBoxLayout()
        
        # Radio buttons for strategy selection
        self.target_size_radio = QRadioButton("Target Size (Iterative)")
        self.target_size_radio.setChecked(CONFIG_DEFAULTS['target_size_mode'])
        self.target_size_radio.toggled.connect(self._update_strategy_widgets)
        
        self.relative_quality_radio = QRadioButton("Relative Quality (Size-based)")
        self.relative_quality_radio.setChecked(not CONFIG_DEFAULTS['target_size_mode'])
        
        radio_layout = QHBoxLayout()
        radio_layout.addWidget(self.target_size_radio)
        radio_layout.addWidget(self.relative_quality_radio)
        main_layout.addLayout(radio_layout)

        # --- Target Size Settings ---
        self.target_size_group = QGroupBox("Target Size Settings")
        ts_layout = QFormLayout()
        self.target_size_spinbox = QSpinBox()
        self.target_size_spinbox.setRange(10, 5000)
        self.target_size_spinbox.setValue(CONFIG_DEFAULTS['target_size_kb'])
        self.target_size_spinbox.setSuffix(" KB")
        ts_layout.addRow("Target Size:", self.target_size_spinbox)
        self.save_on_failure_checkbox = QCheckBox("Save best attempt if target is missed")
        self.save_on_failure_checkbox.setChecked(CONFIG_DEFAULTS['save_on_target_failure'])
        ts_layout.addRow(self.save_on_failure_checkbox)
        self.target_size_group.setLayout(ts_layout)
        main_layout.addWidget(self.target_size_group)

        # --- Relative Quality Settings ---
        self.relative_quality_group = QGroupBox("Relative Quality Settings")
        rq_layout = QFormLayout()
        self.base_quality_spinbox = QSpinBox()
        self.base_quality_spinbox.setRange(1, 100)
        self.base_quality_spinbox.setValue(CONFIG_DEFAULTS['base_quality'])
        rq_layout.addRow("Base Quality (for avg size):", self.base_quality_spinbox)
        self.relative_quality_group.setLayout(rq_layout)
        main_layout.addWidget(self.relative_quality_group)

        # --- General Quality Settings ---
        general_quality_group = QGroupBox("General Quality Limits")
        gq_layout = QFormLayout()
        self.min_quality_spinbox = QSpinBox()
        self.min_quality_spinbox.setRange(1, 100)
        self.min_quality_spinbox.setValue(CONFIG_DEFAULTS['min_quality'])
        gq_layout.addRow("Minimum Quality:", self.min_quality_spinbox)
        self.max_quality_spinbox = QSpinBox()
        self.max_quality_spinbox.setRange(1, 100)
        self.max_quality_spinbox.setValue(CONFIG_DEFAULTS['max_quality'])
        gq_layout.addRow("Maximum Quality:", self.max_quality_spinbox)
        general_quality_group.setLayout(gq_layout)
        main_layout.addWidget(general_quality_group)
        
        self.strategy_group.setLayout(main_layout)
        self._update_strategy_widgets() # Initial setup

    def _create_concurrency_group(self):
        self.concurrency_group = QGroupBox("Concurrency")
        layout = QFormLayout()
        self.worker_spinbox = QSpinBox()
        self.worker_spinbox.setRange(1, os.cpu_count() * 2)
        self.worker_spinbox.setValue(CONFIG_DEFAULTS['worker_count'])
        layout.addRow("Worker Processes:", self.worker_spinbox)
        self.concurrency_group.setLayout(layout)

    def _create_output_panel(self):
        """Creates the right panel for progress bar and log output."""
        self.output_layout = QVBoxLayout()
        self.output_layout.setContentsMargins(10, 10, 10, 10)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Courier", 10))
        self.log_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        self.output_layout.addWidget(QLabel("Progress :"))
        self.output_layout.addWidget(self.progress_bar)
        self.output_layout.addWidget(QLabel("Holy Logger:"))
        self.output_layout.addWidget(self.log_edit, stretch=1)
    
    @Slot()
    def _select_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if folder:
            self.input_folder_edit.setText(folder)

    @Slot()
    def _select_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_folder_edit.setText(folder)

    @Slot()
    def _update_strategy_widgets(self):
        is_target_mode = self.target_size_radio.isChecked()
        self.target_size_group.setEnabled(is_target_mode)
        self.relative_quality_group.setEnabled(not is_target_mode)

    @Slot()
    def toggle_compression(self):
        if self.thread and self.thread.isRunning():
            self.stop_compression()
        else:
            self.start_compression()

    def start_compression(self):
        """Gathers config, creates worker/thread, and starts the process."""
        config = self.get_config_from_ui()
        
        if not os.path.isdir(config['input_folder']):
            QMessageBox.critical(self, "Error", f"Input folder not found:\n{config['input_folder']}")
            return
        
        os.makedirs(config['output_folder'], exist_ok=True)

        # UI changes for running state
        self.set_controls_enabled(False)
        self.start_button.setText("🛑 Stop Compression")
        self.log_edit.clear()
        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Starting...")

        # Create and start the thread
        self.thread = QThread()
        self.worker = CompressorWorker(config)
        self.worker.moveToThread(self.thread)

        # Connect signals from worker to slots in GUI
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_compression_finished)
        self.worker.error.connect(self.on_compression_error)
        self.worker.log_message.connect(self.log_edit.append)
        self.worker.progress_updated.connect(self.update_progress)
        
        self.thread.start()

    def stop_compression(self):
        self.status_bar.showMessage("Stopping...")
        if self.worker:
            self.worker.stop() # Tell worker to stop gracefully
        if self.thread:
            self.thread.quit()
            self.thread.wait(5000) # Wait up to 5s for thread to finish
        self.on_compression_finished() # Cleanup UI

    @Slot()
    def on_compression_finished(self):
        """Cleans up after the thread is done."""
        self.status_bar.showMessage("Finished. Ready for new task.", 5000)
        self.set_controls_enabled(True)
        self.start_button.setText("🚀 Start Compression")
        
        # Clean up thread and worker to prevent issues on restart
        if self.thread:
            if not self.thread.isFinished():
                self.thread.quit()
                self.thread.wait()
            self.thread = None
        self.worker = None

    @Slot(str)
    def on_compression_error(self, message: str):
        QMessageBox.critical(self, "Worker Error", message)
        self.on_compression_finished()

    @Slot(int, int)
    def update_progress(self, value, maximum):
        if self.progress_bar.maximum() != maximum:
            self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        self.status_bar.showMessage(f"Processing image {value} of {maximum}...")

    def get_config_from_ui(self) -> Dict[str, Any]:
        """Reads all values from the UI widgets and returns a config dict."""
        return {
            "input_folder": self.input_folder_edit.text(),
            "output_folder": self.output_folder_edit.text(),
            "supported_extensions": CONFIG_DEFAULTS['supported_extensions'],
            "worker_count": self.worker_spinbox.value(),
            "target_size_mode": self.target_size_radio.isChecked(),
            "min_quality": self.min_quality_spinbox.value(),
            "max_quality": self.max_quality_spinbox.value(),
            "base_quality": self.base_quality_spinbox.value(),
            "target_size_kb": self.target_size_spinbox.value(),
            "save_on_target_failure": self.save_on_failure_checkbox.isChecked()
        }

    def set_controls_enabled(self, enabled: bool):
        """Enables or disables all setting widgets."""
        for widget in self.control_widgets:
            widget.setEnabled(enabled)

    def closeEvent(self, event):
        """Ensure thread is stopped when closing the window."""
        if self.thread and self.thread.isRunning():
            self.stop_compression()
        event.accept()

if __name__ == "__main__":
    # Ensure raw_images folder exists for a good first-time user experience
    if not os.path.exists(CONFIG_DEFAULTS['input_folder']):
        os.makedirs(CONFIG_DEFAULTS['input_folder'])
        
    app = QApplication(sys.argv)
    window = ImageCompressorApp()
    window.show()
    sys.exit(app.exec())
