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
    QProgressBar, QSizePolicy
)

from config import config
from core.planner import TitanAgent
from voice.wake_word import TitanWakeListener
from voice.tts import TitanTTS
from voice.stt import TitanSTT


class AgentWorker(QObject):
    """Background worker to run async TitanAgent tasks without blocking the Qt GUI."""
    thought_signal = Signal(str)
    tool_start_signal = Signal(str, str)
    tool_end_signal = Signal(str, str)
    response_signal = Signal(str, str)  # text, provider
    status_signal = Signal(str)  # status state: 'idle', 'thinking', 'executing', 'listening'

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


class TacticalOrbWidget(QWidget):
    """Animated tactical reactor core reflecting AI state."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 50)
        self.state = "idle"  # 'idle', 'listening', 'thinking', 'executing'
        self.angle = 0
        self.pulse = 0
        self.pulse_dir = 1
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._animate)
        self.timer.start(35)

    def set_state(self, state: str):
        self.state = state
        self.update()

    def _animate(self):
        self.angle = (self.angle + 4) % 360
        self.pulse += self.pulse_dir * 0.04
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

        # State colors
        if self.state == "listening":
            base_color = QColor(255, 170, 0)       # Amber / Gold
        elif self.state == "thinking":
            base_color = QColor(190, 80, 255)      # Cyber Magenta
        elif self.state == "executing":
            base_color = QColor(0, 255, 128)       # Neon Emerald
        else:
            base_color = QColor(0, 230, 255)       # Tactical Cyan

        # Outer pulsing glow ring
        glow_radius = 18 + int(self.pulse * 5)
        glow_color = QColor(base_color.red(), base_color.green(), base_color.blue(), int(60 + self.pulse * 80))
        painter.setPen(QPen(glow_color, 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPoint(int(cx), int(cy)), glow_radius, glow_radius)

        # Rotating outer segment ticks
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)
        pen_tick = QPen(base_color, 2)
        painter.setPen(pen_tick)
        for i in range(4):
            painter.rotate(90)
            painter.drawLine(14, 0, 19, 0)
        painter.restore()

        # Inner solid glowing core
        core_gradient = QLinearGradient(cx - 10, cy - 10, cx + 10, cy + 10)
        core_gradient.setColorAt(0.0, QColor(255, 255, 255, 220))
        core_gradient.setColorAt(0.7, base_color)
        core_gradient.setColorAt(1.0, QColor(base_color.red(), base_color.green(), base_color.blue(), 120))
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(core_gradient))
        painter.drawEllipse(QPoint(int(cx), int(cy)), 10, 10)


class TitanHUDWindow(QWidget):
    """
    T.I.T.A.N. Cyberpunk Floating Desktop HUD Overlay.
    - Draggable, always-on-top translucent desktop widget
    - Live hardware telemetry gauges (CPU, RAM, Battery)
    - Interactive chat log & tactical prompt box
    - Integrated voice listener & hotkey support
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
        self.resize(440, 560)
        
        # Position near top right of primary screen
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 460, 60)

    def _setup_async_worker(self):
        # Dedicated thread for asyncio loop
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
        # Outer Card Layout with Rounded Glow Effect
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Central Tactical Container
        self.container = QFrame(self)
        self.container.setObjectName("hud_container")
        self.container.setStyleSheet("""
            #hud_container {
                background-color: rgba(10, 15, 26, 0.92);
                border: 1px solid rgba(0, 230, 255, 0.45);
                border-radius: 14px;
            }
        """)

        # Drop shadow glow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 220, 255, 90))
        shadow.setOffset(0, 0)
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(14, 12, 14, 12)
        container_layout.setSpacing(10)

        # 1. Header Bar (Draggable)
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        self.orb = TacticalOrbWidget(self)
        header_layout.addWidget(self.orb)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        self.title_label = QLabel("T.I.T.A.N. HUD")
        self.title_label.setStyleSheet("color: #00e5ff; font-weight: bold; font-size: 14px; letter-spacing: 1px;")
        
        self.sub_label = QLabel("AMD Ryzen AI [NPU READY]")
        self.sub_label.setStyleSheet("color: #7090b0; font-size: 10px; text-transform: uppercase;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.sub_label)
        header_layout.addLayout(title_box)

        header_layout.addStretch()

        # Engine Badge
        self.engine_badge = QLabel("NPU")
        self.engine_badge.setStyleSheet("""
            background-color: rgba(0, 230, 255, 0.15);
            color: #00e5ff;
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid rgba(0, 230, 255, 0.4);
        """)
        header_layout.addWidget(self.engine_badge)

        # Voice Toggle Button
        self.voice_btn = QPushButton("🎤")
        self.voice_btn.setFixedSize(26, 26)
        self.voice_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.voice_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #ffffff;
                border-radius: 13px;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }
            QPushButton:hover { background: rgba(0, 230, 255, 0.25); border-color: #00e5ff; }
        """)
        self.voice_btn.clicked.connect(self._toggle_voice)
        header_layout.addWidget(self.voice_btn)

        # Close Button
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(26, 26)
        self.close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.08);
                color: #aaaaaa;
                border-radius: 13px;
                border: 1px solid rgba(255, 255, 255, 0.15);
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(255, 60, 60, 0.4); color: #ffffff; border-color: #ff3333; }
        """)
        self.close_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.close_btn)

        container_layout.addLayout(header_layout)

        # 2. Telemetry Gauge Bar
        telemetry_frame = QFrame()
        telemetry_frame.setStyleSheet("""
            background: rgba(0, 0, 0, 0.35);
            border-radius: 8px;
            padding: 4px;
            border: 1px solid rgba(255, 255, 255, 0.05);
        """)
        tele_layout = QHBoxLayout(telemetry_frame)
        tele_layout.setContentsMargins(8, 4, 8, 4)

        self.cpu_label = QLabel("CPU: --%")
        self.cpu_label.setStyleSheet("color: #a0c0e0; font-size: 11px;")
        
        self.ram_label = QLabel("RAM: --%")
        self.ram_label.setStyleSheet("color: #a0c0e0; font-size: 11px;")

        self.bat_label = QLabel("BAT: --%")
        self.bat_label.setStyleSheet("color: #a0c0e0; font-size: 11px;")

        tele_layout.addWidget(self.cpu_label)
        tele_layout.addStretch()
        tele_layout.addWidget(self.ram_label)
        tele_layout.addStretch()
        tele_layout.addWidget(self.bat_label)

        container_layout.addWidget(telemetry_frame)

        # 3. Chat / Log Stream
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: rgba(5, 8, 16, 0.85);
                color: #e0f0ff;
                border: 1px solid rgba(0, 230, 255, 0.2);
                border-radius: 8px;
                padding: 8px;
                font-family: 'Segoe UI', 'Consolas', sans-serif;
                font-size: 12px;
                line-height: 1.4;
            }
            QScrollBar:vertical {
                border: none;
                background: rgba(0,0,0,0.2);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(0, 230, 255, 0.3);
                border-radius: 3px;
            }
        """)
        self._append_message("system", "T.I.T.A.N. Tactical HUD Initialized. Standing by.")
        container_layout.addWidget(self.chat_display)

        # 4. Input Bar
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Commander > Enter command...")
        self.input_field.setStyleSheet("""
            QLineEdit {
                background-color: rgba(15, 25, 45, 0.9);
                color: #ffffff;
                border: 1px solid rgba(0, 230, 255, 0.35);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00e5ff;
                background-color: rgba(20, 35, 60, 0.95);
            }
        """)
        self.input_field.returnPressed.connect(self._on_send_command)
        input_layout.addWidget(self.input_field)

        self.send_btn = QPushButton("▶")
        self.send_btn.setFixedSize(36, 34)
        self.send_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.send_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00b4d8, stop:1 #0077b6);
                color: white;
                font-weight: bold;
                border-radius: 8px;
                border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #00e5ff, stop:1 #0096c7);
            }
        """)
        self.send_btn.clicked.connect(self._on_send_command)
        input_layout.addWidget(self.send_btn)

        container_layout.addLayout(input_layout)
        main_layout.addWidget(self.container)

    def _start_telemetry_timer(self):
        self.tele_timer = QTimer(self)
        self.tele_timer.timeout.connect(self._update_telemetry)
        self.tele_timer.start(2500)
        self._update_telemetry()

    def _update_telemetry(self):
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            self.cpu_label.setText(f"CPU: {cpu:.0f}%")
            self.ram_label.setText(f"RAM: {ram:.0f}%")

            battery = psutil.sensors_battery()
            if battery:
                plugged = "⚡" if battery.power_plugged else ""
                self.bat_label.setText(f"BAT: {battery.percent:.0f}%{plugged}")
            else:
                self.bat_label.setText("BAT: AC")
        except Exception:
            pass

    def _setup_global_hotkeys(self):
        """Register global hotkey (Ctrl + Space) to summon/toggle HUD."""
        try:
            from pynput import keyboard

            def on_activate():
                # Emit to Qt main thread
                QTimer.singleShot(0, self.toggle_visibility)

            self.hotkey_listener = keyboard.GlobalHotKeys({
                '<ctrl>+<space>': on_activate,
                '<ctrl>+<shift>+t': on_activate,
            })
            self.hotkey_listener.daemon = True
            self.hotkey_listener.start()
        except Exception as e:
            print(f"[HUD] Global hotkey registration warning: {e}")

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
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(0, 230, 255, 0.3);
                    color: #00e5ff;
                    border-radius: 13px;
                    border: 1px solid #00e5ff;
                }
            """)
            self._start_voice_detection()
            self._append_message("system", "Voice listening activated. Say 'TITAN' to command.")
        else:
            self.voice_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.08);
                    color: #ffffff;
                    border-radius: 13px;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                }
            """)
            self._stop_voice_detection()
            self._append_message("system", "Voice listening disabled.")

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
        """Called when wake-word 'TITAN' is detected."""
        QTimer.singleShot(0, lambda: self._handle_voice_prompt())

    def _handle_voice_prompt(self):
        self.orb.set_state("listening")
        self.show()
        self.raise_()
        self._append_message("system", "Listening for voice command...")

        def _record_and_transcribe():
            if self.stt:
                audio = self.stt.record_speech_until_silence(max_seconds=7.0)
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

        # Handle local GUI slash shortcuts
        if text.lower() in ("/clear", "/cls"):
            self.chat_display.clear()
            self._append_message("system", "Chat buffer cleared.")
            return

        self._append_message("user", text)
        self.worker.execute_command(text)

    @Slot(str)
    def _on_agent_thought(self, thought: str):
        self._append_message("thought", thought)

    @Slot(str, str)
    def _on_tool_start(self, name: str, args: str):
        self.orb.set_state("executing")
        self._append_message("tool_start", f"Executing: {name} {args}")

    @Slot(str, str)
    def _on_tool_end(self, name: str, result: str):
        if len(result) > 120:
            result = result[:120] + "..."
        self._append_message("tool_end", f"Done: {result}")

    @Slot(str, str)
    def _on_agent_response(self, text: str, provider: str):
        # Update badge
        badge_text = "NPU" if provider == "local_flm" else "CLOUD"
        badge_color = "#00e5ff" if provider == "local_flm" else "#ff00ff"
        self.engine_badge.setText(badge_text)
        self.engine_badge.setStyleSheet(f"""
            background-color: rgba(255, 255, 255, 0.08);
            color: {badge_color};
            font-size: 10px;
            font-weight: bold;
            padding: 3px 8px;
            border-radius: 6px;
            border: 1px solid {badge_color};
        """)

        self._append_message("agent", text)
        if self.voice_enabled and self.tts:
            self.tts.speak(text, block=False)

    @Slot(str)
    def _on_status_change(self, state: str):
        self.orb.set_state(state)

    def _append_message(self, msg_type: str, content: str):
        clean_content = content.replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        if msg_type == "user":
            html = f'<div style="margin: 4px 0;"><b style="color: #00ffaa;">Commander:</b> <span style="color: #ffffff;">{clean_content}</span></div>'
        elif msg_type == "agent":
            html = f'<div style="margin: 6px 0; background: rgba(0, 230, 255, 0.07); padding: 6px; border-radius: 6px; border-left: 2px solid #00e5ff;"><b style="color: #00e5ff;">TITAN:</b> <span style="color: #e6f7ff;">{clean_content}</span></div>'
        elif msg_type == "thought":
            html = f'<div style="margin: 2px 0; color: #8899aa; font-style: italic; font-size: 11px;">&gt; {clean_content}</div>'
        elif msg_type == "tool_start":
            html = f'<div style="margin: 2px 0; color: #ffd166; font-size: 11px;">⚙ <i>{clean_content}</i></div>'
        elif msg_type == "tool_end":
            html = f'<div style="margin: 2px 0; color: #06d6a0; font-size: 11px;">✔ <i>{clean_content}</i></div>'
        else:
            html = f'<div style="margin: 2px 0; color: #708090; font-size: 11px;">[SYSTEM] {clean_content}</div>'

        self.chat_display.append(html)
        # Scroll to bottom
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # --- Draggable Window Logic ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.drag_position.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


def launch_hud(enable_voice: bool = False):
    """Entry point to start the T.I.T.A.N. GUI HUD Application."""
    app = QApplication.instance() or QApplication(sys.argv)
    agent = TitanAgent()
    hud = TitanHUDWindow(agent=agent, enable_voice=enable_voice)
    hud.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_hud(enable_voice="--voice" in sys.argv)
