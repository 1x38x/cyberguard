import sys
import os
import json
import base64
import io
import pathlib
import threading
import time
from datetime import datetime
from typing import List

from PIL import ImageGrab
from window_select import WindowSelectDialog, grab_selected_window
from screenshot_worker import ScreenshotWorker
from tts import speak_text
import requests
from PySide6.QtCore import Qt, QPoint, QSize, QThread, Signal, QObject, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette, QFont, QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLineEdit,
    QPushButton,
    QLabel,
    QSplitter,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
    QSizePolicy,
    QFrame,
    QFileDialog,
)

###############################################################################
# ────────────────────────────── CONFIG ───────────────────────────────────── #
###############################################################################

APP_NAME = "Cybersecurity Advisor"
API_KEY_ENV = "GEMINI_API_KEY"
API_KEY_FILE = pathlib.Path("api_key.txt")
MODEL_NAME = "gemini-2.0-flash"
CHAT_WIDTH_MAX = 600
THEME_DARK = {
    "bg": "#000000",
    "panel": "#111111",
    "accent": "#ffffff",
    "accent_hover": "#cccccc",
    "text": "#ffffff",
    "subtext": "#cccccc",
    "user_bubble": "#222222",
    "assistant_bubble": "#111111",
}

###############################################################################
# ──────────────────────────── CORE HELPERS ───────────────────────────────── #
###############################################################################

def load_api_key() -> str:
    key = os.getenv(API_KEY_ENV, "").strip()
    if key:
        return key
    if API_KEY_FILE.exists():
        try:
            return API_KEY_FILE.read_text().strip()
        except Exception:
            pass
    return ""

def save_api_key(key: str):
    try:
        API_KEY_FILE.write_text(key.strip())
    except Exception as exc:
        QMessageBox.warning(None, "Save error", f"Could not save key: {exc}")

###############################################################################
# ────────────────────────── NETWORK WORKER ──────────────────────────────── #
###############################################################################

class GeminiWorker(QThread):
    responseReady = Signal(str)
    error = Signal(str)

    def __init__(self, prompt: str, api_key: str, is_image=False):
        super().__init__()
        self.prompt = prompt
        self.api_key = api_key
        self.is_image = is_image  # If True the prompt is base64 screenshot

    def run(self):
        try:
            if self.is_image:
                text = self._analyze_image()
            else:
                text = self._query_text()
            self.responseReady.emit(text)
        except Exception as exc:
            self.error.emit(str(exc))

    # --- Internal helpers -------------------------------------------------- #
    def _post(self, payload: dict) -> dict:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={self.api_key}"
        )
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def _query_text(self) -> str:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "You are a cybersecurity expert advisor. Explain in plain language: "
                                + self.prompt
                            )
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1024,
            },
        }
        data = self._post(payload)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def _analyze_image(self) -> str:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "As a cybersecurity expert, analyze this screenshot for threats and "
                                "explain findings in simple terms."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": self.prompt,  # base64
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1024,
            },
        }
        data = self._post(payload)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

###############################################################################
# ───────────────────────── GUI COMPONENTS ───────────────────────────────── #
###############################################################################

import re
class Bubble(QFrame):
    def __init__(self, text: str, is_user: bool):
        super().__init__()
        self.is_user = is_user
        # Remove *, **, _, and extra whitespace from text, and strip emojis
        clean_text = re.sub(r'[\*_`]', '', text)
        clean_text = re.sub(r'[\u2600-\u27BF\U0001f300-\U0001f64F\U0001f680-\U0001f6FF\U0001f700-\U0001f77F\U0001f780-\U0001f7FF\U0001f800-\U0001f8FF\U0001f900-\U0001f9FF\U0001fa00-\U0001fa6F\U0001fa70-\U0001faff\U00002702-\U000027B0]+', '', clean_text)
        self.text_label = QLabel(clean_text)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_label.setStyleSheet("color: " + THEME_DARK["text"])
        self.text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.text_label)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setMinimumWidth(200)
        self.setMaximumWidth(800)
        self.setStyleSheet(
            (
                f"background-color: {THEME_DARK['user_bubble' if is_user else 'assistant_bubble']};"
                "border-radius: 10px; padding: 12px;"
            )
        )

class ChatArea(QWidget):
    def __init__(self):
        super().__init__()
        self.vbox = QVBoxLayout()
        self.vbox.addStretch(1)
        container = QWidget()
        container.setLayout(self.vbox)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(container)
        self.scroll.setStyleSheet("border: none;")
        self.scroll.setMinimumWidth(400)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.scroll)

    def add_message(self, text: str, is_user: bool):
        bubble = Bubble(text, is_user)
        wrapper = QHBoxLayout()
        if is_user:
            wrapper.addStretch(1)
            wrapper.addWidget(bubble, stretch=2)
        else:
            wrapper.addWidget(bubble, stretch=2)
            wrapper.addStretch(1)
        wrapper.setAlignment(Qt.AlignTop)
        self.vbox.insertLayout(self.vbox.count() - 1, wrapper)
        QTimer.singleShot(100, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def clear_chat(self):
        # Remove all layouts except the last stretch
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            if item is not None:
                if item.layout():
                    # Remove all widgets from the layout
                    layout = item.layout()
                    while layout.count():
                        witem = layout.takeAt(0)
                        widget = witem.widget()
                        if widget is not None:
                            widget.deleteLater()
                    layout.deleteLater()
                elif item.widget():
                    item.widget().deleteLater()

###############################################################################
# ───────────────────────────── SETTINGS DIALOG ───────────────────────────── #
###############################################################################

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API Key Settings")
        form = QFormLayout(self)
        self.api_edit = QLineEdit(load_api_key())
        self.api_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Gemini API key:", self.api_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        form.addWidget(buttons)

    def save(self):
        key = self.api_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Invalid", "API key cannot be empty")
            return
        save_api_key(key)
        self.accept()

###############################################################################
# ───────────────────────────── MAIN WINDOW ──────────────────────────────── #
###############################################################################

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._workers = []  # Keep references to running GeminiWorker threads
        self.setWindowTitle(APP_NAME)
        self.resize(960, 720)
        self.setMinimumSize(720, 480)
        self.api_key = load_api_key()
        self.tts_enabled = False
        self.complex_mode = False
        self._tts_proc = None

        self.chat = ChatArea()

        # Right sidebar ------------------------------------------------------ #
        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        logo = QLabel("Cybersec Advisor")
        logo.setStyleSheet("color: #FFFFFF; font-weight: bold; font-size: 16px;")
        side_layout.addWidget(logo)
        side_layout.addSpacing(10)

        # TTS toggle
        self.tts_enabled = False
        self.tts_btn = QPushButton("Enable Voice (TTS)")
        self.tts_btn.setCheckable(True)
        self.tts_btn.clicked.connect(self.toggle_tts)
        side_layout.addWidget(self.tts_btn)

        # Complex Mode toggle
        self.complex_mode = False
        self.complex_btn = QPushButton("Enable Complex Mode")
        self.complex_btn.setCheckable(True)
        self.complex_btn.clicked.connect(self.toggle_complex_mode)
        side_layout.addWidget(self.complex_btn)

        # Stop Speaking button
        self.stop_speaking_btn = QPushButton("Stop Speaking")
        self.stop_speaking_btn.clicked.connect(self.stop_speaking)
        self.stop_speaking_btn.setEnabled(False)
        side_layout.addWidget(self.stop_speaking_btn)

        # Spinner animation (QLabel with GIF)
        from PySide6.QtGui import QMovie
        self.spinner = QLabel()
        self.spinner.setAlignment(Qt.AlignCenter)
        self.spinner_movie = QMovie(":/qt-project.org/styles/commonstyle/images/working-32.gif")
        self.spinner.setMovie(self.spinner_movie)
        self.spinner.hide()
        side_layout.addWidget(self.spinner)
        btn_scan = QPushButton("Scan screen for threats")
        btn_scan.clicked.connect(self.scan_screen)
        side_layout.addWidget(btn_scan)
        btn_clear = QPushButton("Clear chat")
        btn_clear.clicked.connect(self.chat.clear_chat)
        side_layout.addWidget(btn_clear)
        side_layout.addStretch(1)

        # Suggested topics
        side_layout.addWidget(QLabel("💡 Suggested:"))
        for tip in [
            "What is phishing?",
            "How to create secure passwords",
            "Explain two‑factor authentication",
            "What is ransomware?",
        ]:
            b = QPushButton(tip)
            b.clicked.connect(lambda _, t=tip: self.send_prompt(t))
            side_layout.addWidget(b)

        splitter = QSplitter()
        splitter.addWidget(self.chat)
        splitter.addWidget(side_panel)
        splitter.setSizes([700, 260])
        self.setCentralWidget(splitter)

        # Bottom input ------------------------------------------------------- #
        input_bar = QWidget()
        input_layout = QHBoxLayout(input_bar)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Type your message…")
        self.input_edit.returnPressed.connect(self.send_current_input)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self.send_current_input)
        input_layout.addWidget(self.input_edit)
        input_layout.addWidget(send_btn)
        input_bar.setStyleSheet(
            f"background:{THEME_DARK['panel']}; padding:6px; border-top:1px solid #1f2937;"
        )
        self.addToolBarBreak()
        self.addToolBar(Qt.BottomToolBarArea, self._wrap_widget_in_toolbar(input_bar))

        # Menu ----------------------------------------------------------------#
        menu = self.menuBar().addMenu("Settings")
        act_api = QAction("API key…", self)
        act_api.triggered.connect(self.open_settings)
        menu.addAction(act_api)

        self.apply_styles()
        # Welcome message
        self.chat.add_message(
            "Welcome! I am your Cybersecurity Advisor. Ask me anything about keeping your digital life secure.",
            is_user=False,
        )

    # --------------------------------------------------------------------- #
    def _wrap_widget_in_toolbar(self, w):
        from PySide6.QtWidgets import QToolBar

        tb = QToolBar()
        tb.addWidget(w)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(0, 0))
        tb.setStyleSheet("border:none;")
        return tb

    def apply_styles(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(THEME_DARK["bg"]))
        palette.setColor(QPalette.WindowText, QColor(THEME_DARK["text"]))
        palette.setColor(QPalette.Base, QColor(THEME_DARK["panel"]))
        palette.setColor(QPalette.Text, QColor(THEME_DARK["text"]))
        self.setPalette(palette)

    # --------------------------------------------------------------------- #
    def open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            self.api_key = load_api_key()

    def send_current_input(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self.send_prompt(text)

    def send_prompt(self, prompt: str):
        self.chat.add_message(prompt, is_user=True)
        self.spinner.show()
        self.spinner_movie.start()
        if not self.api_key:
            self.spinner.hide()
            self.chat.add_message(
                "Please set your Gemini API key first (Settings → API key).", False
            )
            return
        worker = GeminiWorker(prompt, self.api_key)
        # Use concise, friendly response handler
        worker.responseReady.connect(self._handle_ai_response)
        worker.error.connect(lambda e: self.chat.add_message(f"⚠️ {e}", False))
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()

    def _handle_ai_response(self, text):
        self.stop_speaking_btn.setEnabled(False)
        self.spinner.hide()
        if self.complex_mode:
            response = text.strip()
        else:
            response = self._summarize_response_short(text)
        self.chat.add_message(response, False)
        if self.tts_enabled:
            try:
                clean = self._clean_for_tts(response)
                speak_text(clean)
                import platform, subprocess
                self._tts_proc = None
                if platform.system() == "Linux":
                    self._tts_proc = subprocess.Popen(["mpg123", "tts_output.mp3"])
                elif platform.system() == "Darwin":
                    self._tts_proc = subprocess.Popen(["afplay", "tts_output.mp3"])
                elif platform.system() == "Windows":
                    # os.startfile is not killable; skip stop for now
                    os.startfile("tts_output.mp3")
                self.stop_speaking_btn.setEnabled(True)
            except Exception as e:
                self.chat.add_message(f"[Voice Error] {e}", False)

    def scan_screen(self):
        self.spinner.show()
        self.spinner_movie.start()
        if not self.api_key:
            self.spinner.hide()
            self.chat.add_message(
                "Please set your Gemini API key first (Settings → API key).", False
            )
            return
        # Show window selection dialog
        dlg = WindowSelectDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.get_selected_id() is not None:
            win_id = dlg.get_selected_id()
            self.chat.add_message("Capturing selected window…", False)
            self.screenshot_worker = ScreenshotWorker(win_id)
            self.screenshot_worker.finished.connect(self._scan_screen_bg)
            self.screenshot_worker.error.connect(lambda e: self.chat.add_message(f"Screenshot failed: {e}", False))
            self.screenshot_worker.finished.connect(lambda: self._cleanup_worker(self.screenshot_worker))
            self._workers.append(self.screenshot_worker)
            self.screenshot_worker.start()
        else:
            self.spinner.hide()
            self.chat.add_message("Screenshot canceled or no window selected.", False)

    def _scan_screen_bg(self, b64):
        try:
            worker = GeminiWorker(b64, self.api_key, is_image=True)
            worker.responseReady.connect(self._handle_scan_result)
            worker.error.connect(lambda e: self.chat.add_message(f"Screenshot failed: {e}", False))
            worker.finished.connect(lambda: self._cleanup_worker(worker))
            self._workers.append(worker)
            worker.start()
        except Exception as exc:
            self.chat.add_message(f"Screenshot failed: {exc}", False)

    def _cleanup_worker(self, worker):
        try:
            self._workers.remove(worker)
        except ValueError:
            pass

    def closeEvent(self, event):
        # Stop any TTS playback
        self.stop_speaking()
        # Wait for all threads to finish before closing
        for worker in self._workers:
            if worker.isRunning():
                worker.quit()
                worker.wait()
        event.accept()

    def stop_speaking(self):
        import platform
        if self._tts_proc is not None:
            try:
                self._tts_proc.terminate()
            except Exception:
                pass
            self._tts_proc = None
        self.stop_speaking_btn.setEnabled(False)
        # On Windows, can't stop os.startfile playback

    def toggle_tts(self):
        self.tts_enabled = self.tts_btn.isChecked()
        if self.tts_enabled:
            self.tts_btn.setText("Disable Voice (TTS)")
        else:
            self.tts_btn.setText("Enable Voice (TTS)")

    def toggle_complex_mode(self):
        self.complex_mode = self.complex_btn.isChecked()
        if self.complex_mode:
            self.complex_btn.setText("Disable Complex Mode")
        else:
            self.complex_btn.setText("Enable Complex Mode")

    def _summarize_response_short(self, text):
        # Short, clear, easy-to-understand summary (1-2 sentences, no ...)
        import re
        explanations = {
            'phishing': 'Phishing: a cyber attack where attackers trick you into giving up personal information. Always check the sender and links before clicking.',
            'malware': 'Malware: malicious software designed to harm or exploit your device or data.',
            'ransomware': 'Ransomware: malware that locks your files and demands payment to unlock them.',
            'two-factor authentication': 'Two-factor authentication: adds an extra layer of security by requiring a second verification step.',
            'password': 'A strong password uses a mix of letters, numbers, and symbols, and is unique for each account.',
            'encryption': 'Encryption: protects your data by converting it into a code that only authorized parties can read.',
            'threat': 'A threat is any potential danger to your digital security, like hackers or malware.',
        }
        # Remove playful endings
        text = re.sub(r"(Stay safe!|Let me know if you have more questions!|Hope that helps!|Think of it like this:)", "", text, flags=re.I)
        # Get first 1-2 sentences, no ...
        sentences = re.split(r"(?<=[.!?]) +", text.strip())
        summary = " ".join(sentences[:2]).strip()
        # Append relevant explanation if key term present and not already explained
        for term, explanation in explanations.items():
            if re.search(rf'\b{re.escape(term)}\b', summary, re.I) and explanation.split(':')[0].lower() not in summary.lower():
                summary = summary.rstrip('.') + ". " + explanation
                break
        return summary.strip()

    def _clean_for_tts(self, text):
        # Remove markdown formatting and extra whitespace
        import re
        text = re.sub(r'[\*_`~\[\]#>-]', '', text)  # Remove markdown chars
        text = re.sub(r'\s+', ' ', text)  # Collapse whitespace
        text = text.replace('•', 'bullet point').replace('-', ' ')  # Make lists clearer
        return text.strip()

    def _handle_scan_result(self, result: str):
        # Summarize and simplify for non-technical users
        friendly = self._summarize_response_short(result)
        self.chat.add_message(friendly, False)
        if self.tts_enabled:
            try:
                speak_text(friendly)
                # Play the mp3 (cross-platform)
                import platform, subprocess
                if platform.system() == "Linux":
                    subprocess.Popen(["mpg123", "tts_output.mp3"])
                elif platform.system() == "Darwin":
                    subprocess.Popen(["afplay", "tts_output.mp3"])
                elif platform.system() == "Windows":
                    os.startfile("tts_output.mp3")
            except Exception as e:
                self.chat.add_message(f"[Voice Error] {e}", False)

###############################################################################
# ──────────────────────────────── MAIN ──────────────────────────────────── #
###############################################################################

def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
