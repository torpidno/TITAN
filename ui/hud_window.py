import sys
import os
import asyncio
import threading
import psutil
from typing import Optional, Dict, Any

from PySide6.QtCore import (
    Qt, QTimer, QPoint, Signal, Slot, QObject, QThread, QPropertyAnimation,
    QEasingCurve, QRect, QSize
)
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QIcon, QLinearGradient,
    QPainterPath, QCursor
)
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QScrollArea, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy
)

from config import config
from core.planner import TitanAgent
from voice.wake_word import TitanWakeListener
from voice.tts import TitanTTS
from voice.stt import TitanSTT


class AgentWorker(QObject):
    """Background worker to run async TitanAgent tasks without blocking GUI."""
    thought_signal = Signal(str)
    tool_start_signal = Signal(str, str)
    tool_end_signal = Signal(str, str)
    response_signal = Signal(str, str)  # text, provider
    status_signal = Signal(str)  # 'idle', 'thinking', 'executing', 'listening'

    def __init__(self, agent: TitanAgent):
        super().__init__()
        self.agent = agent
        self.loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def execute_command(self, user_text: str):
        if not self.loop:
            return

        async def _run():
            self.status_signal.emit("thinking")
            try:
                res = await self.agent.process_user_input(
                    user_text,
                    on_thought=lambda t: self.thought_signal.emit(t),
                    on_tool_start=lambda name, args: self.tool_start_signal.emit(name, str(args)),
                    on_tool_end=lambda name, result: self.tool_end_signal.emit(name, str(result))
                )
                text = res.get("text", "") if isinstance(res, dict) else str(res)
                provider = res.get("provider", "local_flm") if isinstance(res, dict) else "local_flm"
                self.response_signal.emit(text, provider)
            except Exception as e:
                self.response_signal.emit(f"Error executing command: {e}", "local_flm")
            finally:
                self.status_signal.emit("idle")

        asyncio.run_coroutine_threadsafe(_run(), self.loop)


class MinimalOrbWidget(QWidget):
    """Minimalist breathing status indicator."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(26, 26)
        self.state = "idle"  # 'idle', 'listening', 'thinking', 'executing'
        self.pulse = 0.0
        self.pulse_dir = 1
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(40)

    def set_state(self, state: str):
        self.state = state
        self.update()

    def _animate(self):
        self.pulse += self.pulse_dir * 0.05
        if self.pulse > 1.0:
            self.pulse = 1.0
            self.pulse_dir = -1
        elif self.pulse < 0.0:
            self.pulse = 0.0
            self.pulse_dir = 1
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        if self.state == "listening":
            base = QColor(251, 191, 36)      # Amber
        elif self.state == "thinking":
            base = QColor(192, 132, 252)     # Purple
        elif self.state == "executing":
            base = QColor(52, 211, 153)      # Emerald
        else:
            base = QColor(0, 245, 212)       # Mint Cyan

        # Soft outer pulse halo
        halo_radius = 8 + int(self.pulse * 3)
        halo_color = QColor(base.red(), base.green(), base.blue(), int(35 + self.pulse * 45))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo_color))
        painter.drawEllipse(QPoint(int(cx), int(cy)), halo_radius, halo_radius)

        # Core dot
        painter.setBrush(QBrush(base))
        painter.drawEllipse(QPoint(int(cx), int(cy)), 5, 5)


class TitanHUDWindow(QWidget):
    """
    T.I.T.A.N. Minimalist & Clean Floating Desktop HUD.
    - Sleek obsidian frosted glass with ultra-fine accent borders
    - Unified telemetry capsule (CPU, RAM, Battery)
    - Distraction-free clean message stream & prompt pill
    """

    def __init__(self, agent: TitanAgent, enable_voice: bool = False):
        super().__init__()
        self.agent = agent
        self.voice_enabled = enable_voice
        self.drag_position = QPoint()
        
        # Audio systems
        self.tts = TitanTTS() if enable_voice else None
        self.stt = TitanSTT() if enable_voice else None
        self.wake_detector: Optional[TitanWakeListener] = None

        self._setup_async_worker()
        self._init_window_properties()
        self._build_ui()
        self._start_telemetry_timer()
        self._setup_global_hotkeys()

        if self.voice_enabled:
            self._start_voice_detection()

    def _init_window_properties(self):
        self.setWindowTitle("T.I.T.A.N. Tactical HUD")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.SubWindow
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(400, 500)
        
        # Position neatly near top-right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 430, 50)

    def _setup_async_worker(self):
        self.async_loop = asyncio.new_event_loop()
        self.async_thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self.async_thread.start()

        self.worker = AgentWorker(self.agent)
        self.worker.set_loop(self.async_loop)
        self.worker.thought_signal.connect(self._on_agent_thought)
        self.worker.tool_start_signal.connect(self._on_tool_start)
        self.worker.tool_end_signal.connect(self._on_tool_end)
        self.worker.response_signal.connect(self._on_agent_response)
        self.worker.status_signal.connect(self._on_status_change)

    def _run_async_loop(self):
        asyncio.set_event_loop(self.async_loop)
        self.async_loop.run_forever()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Main Glass Card
        self.container = QFrame(self)
        self.container.setObjectName("main_card")
        self.container.setStyleSheet("""
            #main_card {
                background-color: rgba(13, 17, 23, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 16px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 12, 14, 12)
        container_layout.setSpacing(8)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.orb = MinimalOrbWidget(self)
        header_layout.addWidget(self.orb)

        self.title_label = QLabel("TITAN")
        self.title_label.setStyleSheet("""
            color: #f8fafc;
            font-weight: 700;
            font-size: 13px;
            letter-spacing: 1.5px;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        """)
        header_layout.addWidget(self.title_label)

        # Telemetry Pill
        self.tele_pill = QLabel("0% · 0% · AC")
        self.tele_pill.setStyleSheet("""
            color: #94a3b8;
            font-size: 10px;
            background: rgba(255, 255, 255, 0.05);
            padding: 2px 8px;
            border-radius: 10px;
            font-family: 'Consolas', 'Courier New', monospace;
        """)
        header_layout.addWidget(self.tele_pill)

        header_layout.addStretch()

        # Engine Badge
        self.engine_badge = QLabel("NPU")
        self.engine_badge.setStyleSheet("""
            background: rgba(0, 245, 212, 0.12);
            color: #00f5d4;
            font-size: 9px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
            letter-spacing: 0.5px;
        """)
        header_layout.addWidget(self.engine_badge)

        # Voice Button
        self.voice_btn = QPushButton("🎙")
        self.voice_btn.setFixedSize(22, 22)
        self.voice_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #94a3b8;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover { color: #00f5d4; }
        """)
        self.voice_btn.clicked.connect(self._toggle_voice)
        header_layout.addWidget(self.voice_btn)

        # Close Button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #64748b;
                border: none;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { color: #ef4444; }
        """)
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)

        container_layout.addLayout(header_layout)

        # 2. Minimalist Message Feed
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background: transparent;
                color: #f1f5f9;
                border: none;
                padding: 4px;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: 12px;
                line-height: 1.45;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 2px;
            }
        """)
        self._append_message("system", "TITAN ready.")
        container_layout.addWidget(self.chat_display)

        # 3. Minimalist Capsule Input Bar
        input_frame = QFrame()
        input_frame.setObjectName("input_capsule")
        input_frame.setStyleSheet("""
            #input_capsule {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }
            #input_capsule:focus-within {
                border: 1px solid rgba(0, 245, 212, 0.45);
                background-color: rgba(255, 255, 255, 0.07);
            }
        """)
        capsule_layout = QHBoxLayout(input_frame)
        capsule_layout.setContentsMargins(10, 3, 6, 3)
        capsule_layout.setSpacing(4)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask TITAN or type command...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                color: #ffffff;
                border: none;
                font-size: 12px;
                padding: 5px 0;
            }
        """)
        self.input_field.returnPressed.connect(self._on_send_command)
        capsule_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("↑")
        self.send_btn.setFixedSize(26, 26)
        self.send_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 245, 212, 0.15);
                color: #00f5d4;
                font-weight: bold;
                font-size: 13px;
                border-radius: 13px;
                border: none;
            }
            QPushButton:hover {
                background: #00f5d4;
                color: #000000;
            }
        """)
        self.send_btn.clicked.connect(self._on_send_command)
        capsule_layout.addWidget(self.send_btn)

        container_layout.addWidget(input_frame)
        main_layout.addWidget(self.container)

    def _start_telemetry_timer(self):
        self.tele_timer = QTimer(self)
        self.tele_timer.timeout.connect(self._update_telemetry)
        self.tele_timer.start(3000)
        self._update_telemetry()

    def _update_telemetry(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            battery = psutil.sensors_battery()
            bat_str = f"{battery.percent:.0f}%" + ("⚡" if battery.power_plugged else "") if battery else "AC"
            self.tele_pill.setText(f"{cpu:.0f}% CPU · {ram:.0f}% RAM · {bat_str}")
        except Exception:
            pass

    def _setup_global_hotkeys(self):
        try:
            from pynput import keyboard

            def on_activate():
                QTimer.singleShot(0, self.toggle_visibility)

            self.hotkey_listener = keyboard.GlobalHotKeys({
                '<ctrl>+<space>': on_activate,
                '<ctrl>+<shift>+t': on_activate,
            })
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
        except Exception as e:
            print(f"[HUD] Global hotkey warning: {e}")

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()
            self.input_field.setFocus()

    def _toggle_voice(self):
        self.voice_enabled = not self.voice_enabled
        if self.voice_enabled:
            self.voice_btn.setStyleSheet("color: #00f5d4; font-size: 12px;")
            self._start_voice_detection()
            self._append_message("system", "Listening for 'TITAN'...")
        else:
            self.voice_btn.setStyleSheet("color: #94a3b8; font-size: 12px;")
            self._stop_voice_detection()
            self._append_message("system", "Voice disabled.")

    def _start_voice_detection(self):
        if not self.wake_detector:
            if not self.stt:
                self.stt = TitanSTT()
            if not self.tts:
                self.tts = TitanTTS()

            self.wake_detector = TitanWakeListener(
                on_wake_callback=lambda phrase: self._on_voice_wake()
            )
            self.wake_detector.start()

    def _stop_voice_detection(self):
        if self.wake_detector:
            self.wake_detector.stop()
            self.wake_detector = None

    def _on_voice_wake(self):
        QTimer.singleShot(0, lambda: self._handle_voice_prompt())

    def _handle_voice_prompt(self):
        self.orb.set_state("listening")
        self.show()
        self.raise_()
        self._append_message("system", "Listening...")

        def _record_and_transcribe():
            if self.stt:
                audio = self.stt.record_speech_until_silence(max_seconds=6.0)
                text = self.stt.transcribe(audio)
                if text:
                    QTimer.singleShot(0, lambda: self._process_voice_text(text))
                else:
                    QTimer.singleShot(0, lambda: self.orb.set_state("idle"))

        threading.Thread(target=_record_and_transcribe, daemon=True).start()

    def _process_voice_text(self, text: str):
        self._append_message("user", text)
        self.worker.execute_command(text)

    def _on_send_command(self):
        text = self.input_field.text().strip()
        if not text:
            return
        self.input_field.clear()

        if text.lower() in ("/clear", "/cls"):
            self.chat_display.clear()
            self._append_message("system", "Cleared.")
            return

        self._append_message("user", text)
        self.worker.execute_command(text)

    @Slot(str)
    def _on_agent_thought(self, thought: str):
        self._append_message("thought", thought)

    @Slot(str, str)
    def _on_tool_start(self, name: str, args: str):
        self.orb.set_state("executing")
        self._append_message("tool_start", f"{name}")

    @Slot(str, str)
    def _on_tool_end(self, name: str, result: str):
        if len(result) > 100:
            result = result[:100] + "..."
        self._append_message("tool_end", f"{name} done")

    @Slot(str, str)
    def _on_agent_response(self, text: str, provider: str):
        badge_text = "NPU" if provider == "local_flm" else "CLOUD"
        badge_color = "#00f5d4" if provider == "local_flm" else "#c084fc"
        self.engine_badge.setText(badge_text)
        self.engine_badge.setStyleSheet(f"""
            background: rgba(255, 255, 255, 0.08);
            color: {badge_color};
            font-size: 9px;
            font-weight: 700;
            padding: 2px 6px;
            border-radius: 4px;
        """)

        self._append_message("agent", text)
        if self.voice_enabled and self.tts:
            self.tts.speak(text, block=False)

    @Slot(str)
    def _on_status_change(self, state: str):
        self.orb.set_state(state)

    def _append_message(self, msg_type: str, content: str):
        clean = content.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        if msg_type == "user":
            html = f'<div style="margin: 4px 0; color: #f8fafc;"><b>You:</b> <span style="color: #cbd5e1;">{clean}</span></div>'
        elif msg_type == "agent":
            html = f'<div style="margin: 5px 0; background: rgba(0, 245, 212, 0.06); padding: 6px 8px; border-radius: 8px; border-left: 2px solid #00f5d4;"><b style="color: #00f5d4;">TITAN:</b> <span style="color: #f1f5f9;">{clean}</span></div>'
        elif msg_type == "thought":
            html = f'<div style="margin: 1px 0; color: #64748b; font-size: 10px;">&gt; {clean}</div>'
        elif msg_type == "tool_start":
            html = f'<div style="margin: 1px 0; color: #fbbf24; font-size: 10px;">⚙ <i>{clean}</i></div>'
        elif msg_type == "tool_end":
            html = f'<div style="margin: 1px 0; color: #34d399; font-size: 10px;">✔ <i>{clean}</i></div>'
        else:
            html = f'<div style="margin: 1px 0; color: #475569; font-size: 10px;">{clean}</div>'

        self.chat_display.append(html)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # --- Smooth Draggable Window ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


def launch_hud(enable_voice: bool = False):
    """Entry point to start the minimal T.I.T.A.N. GUI HUD."""
    app = QApplication.instance() or QApplication(sys.argv)
    agent = TitanAgent()
    hud = TitanHUDWindow(agent=agent, enable_voice=enable_voice)
    hud.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_hud(enable_voice="--voice" in sys.argv)
