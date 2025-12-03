#!/usr/bin/env python3
import sys
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, List, Tuple
import time
from dotenv import load_dotenv

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QComboBox, 
                             QFileDialog, QDialog, QGridLayout, QListWidget, QListWidgetItem)
from PyQt5.QtCore import Qt, QTimer, QPoint, QSize
from PyQt5.QtGui import QFont, QPainter, QColor, QBrush, QPen, QPolygon

# Charger les variables d'environnement
APP_DIR = Path(__file__).parent.resolve()
ENV_FILE = APP_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    print(f"Attention : fichier .env introuvable : {ENV_FILE}")
    sys.exit(1)

DISPLAY = os.getenv('DISPLAY', ':0')
PROFILES_DIR = Path(os.getenv('PROFILES_DIR', str(Path.home() / ".config/dofus_linux_toolbox")))
os.environ['DISPLAY'] = DISPLAY

SCRIPTS_DIR = None
PROFILES_FILE = None
ALWAYS_ON_TOP = False

# ==================== Fonctions utilitaires ==================== #

def load_data() -> Dict:
    try:
        with open(PROFILES_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data: Dict) -> None:
    with open(PROFILES_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_profiles() -> Tuple[Dict[str, List[str]], str]:
    data = load_data()
    return data.get("profiles", {}), data.get("active", "")

def save_initiative(profile_name: str) -> None:
    data = load_data()
    data["active"] = profile_name
    save_data(data)

def run_cmd(cmd: List[str], timeout=5) -> Tuple[str, int]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip(), result.returncode
    except:
        return "", 1

def get_dofus_windows() -> List[Tuple[str, str]]:
    out, code = run_cmd(['wmctrl', '-l', '-p'])
    if code != 0:
        return []
    windows = []
    for line in out.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        win_id, win_name = parts[0], parts[4]
        if win_name == "Dofus" or win_name.startswith("Dofus-"):
            windows.append((win_id, win_name))
    return windows

def update_cycle_scripts(profile_name: str) -> None:
    profiles, _ = load_profiles()
    profile_data = profiles.get(profile_name, {})
    
    if isinstance(profile_data, dict):
        initiative = profile_data.get("windows", [])
    else:
        initiative = profile_data
    
    if not initiative:
        return
    
    classes_str = "'" + "' '" .join(initiative) + "'"
    
    script_content = f"""#!/bin/bash
STATE_FILE="/tmp/dofus_window_index"
CLASS_INI=({classes_str})
AVAILABLE=($(wmctrl -l | grep "Dofus-" | awk '{{print $4}}' | cut -d'-' -f2))
if [[ ${{#AVAILABLE[@]}} -eq 0 ]]; then exit 1; fi
if [ -f "$STATE_FILE" ]; then INDEX=$(cat "$STATE_FILE"); else INDEX=0; fi
TOTAL=${{#CLASS_INI[@]}}
for ((i=1; i<=TOTAL; i++)); do
    NEXT=$(( (INDEX + i) % TOTAL ))
    CLASS_NAME=${{CLASS_INI[$NEXT]}}
    if printf '%s\\n' "${{AVAILABLE[@]}}" | grep -q "^$CLASS_NAME$"; then
        wmctrl -a "Dofus-$CLASS_NAME"
        echo "$NEXT" > "$STATE_FILE"
        exit 0
    fi
done
"""
    
    script_content_back = script_content.replace(
        "NEXT=$(( (INDEX + i) % TOTAL ))",
        "NEXT=$(( (INDEX - i + TOTAL) % TOTAL ))"
    )
    
    forward_path = SCRIPTS_DIR / "cycle_windows_dofus.sh"
    backward_path = SCRIPTS_DIR / "cycle_backward_windows_dofus.sh"
    
    for path, content in [(forward_path, script_content), (backward_path, script_content_back)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            f.write(content)
        path.chmod(0o755)

def rename_windows(profile_name: str) -> None:
    profiles, _ = load_profiles()
    profile_data = profiles.get(profile_name, {})
    
    if isinstance(profile_data, dict):
        initiative = profile_data.get("windows", [])
    else:
        initiative = profile_data
    
    if not initiative:
        print("Erreur : pas de fenêtres dans le profil")
        return
    
    windows = get_dofus_windows()
    print(f"DEBUG: Fenêtres trouvées: {windows}")
    print(f"DEBUG: Initiative: {initiative}")
    
    if not windows:
        print("Erreur : aucune fenêtre Dofus trouvée")
        return

    for idx, (win_id, win_name) in enumerate(windows):
        if idx < len(initiative):
            new_name = f"Dofus-{initiative[idx]}"
            print(f"DEBUG: Renommage {win_id} de '{win_name}' à '{new_name}'")
            run_cmd(['wmctrl', '-ir', win_id, '-b', 'remove,maximized_vert,maximized_horz'])
            run_cmd(['wmctrl', '-ir', win_id, '-N', new_name])

    if len(windows) > 1:
        print(f"DEBUG: Muting {len(windows) - 1} fenêtres")
        cmds = []
        for win_id, _ in windows[1:]:
            pid_out, _ = run_cmd(['xprop', '-id', win_id, '_NET_WM_PID'])
            if pid_out and '=' in pid_out:
                pid = pid_out.split('=')[1].strip()
                print(f"DEBUG: Muting PID {pid}")
                cmds.append(f"pactl list sink-inputs 2>/dev/null | grep -B5 'process.id = \"{pid}\"' | grep 'Sink Input' | awk '{{print $3}}' | xargs -r -I {{}} pactl set-sink-input-mute {{}} 1 2>/dev/null")
        if cmds:
            subprocess.Popen(['bash', '-c', ' && '.join(cmds)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def reorganize_windows(profile_name: str) -> None:
    profiles, _ = load_profiles()
    profile_data = profiles.get(profile_name, {})
    
    if isinstance(profile_data, dict):
        initiative = profile_data.get("windows", [])
    else:
        initiative = profile_data
    
    if not initiative:
        return
    
    windows = get_dofus_windows()
    if not windows:
        return

    out, _ = run_cmd(['wmctrl', '-d'])
    current_ws = next((line.split()[0] for line in out.splitlines() if ' * ' in line), '0')
    other_ws = '1' if current_ws == '0' else '0'

    window_map = {}
    for win_id, win_name in windows:
        for class_name in initiative:
            if class_name.lower() in win_name.lower() or f"Dofus-{class_name}" in win_name:
                window_map[class_name] = win_id
                break
    
    if len(window_map) < len(windows):
        mapped_classes = set(window_map.keys())
        unmapped_windows = [w for w in windows if not any(w[1].find(c) >= 0 for c in mapped_classes)]
        unmapped_classes = [c for c in initiative if c not in mapped_classes]
        
        for win, cls in zip(unmapped_windows, unmapped_classes):
            window_map[cls] = win[0]

    for win_id, _ in windows:
        run_cmd(['wmctrl', '-ir', win_id, '-t', other_ws])

    time.sleep(0.3)

    for class_name in initiative:
        if class_name in window_map:
            win_id = window_map[class_name]
            run_cmd(['wmctrl', '-ir', win_id, '-t', current_ws])
            time.sleep(0.1)

def invite_group(profile_name: str) -> None:
    profiles, _ = load_profiles()
    profile_data = profiles.get(profile_name, {})
    
    if isinstance(profile_data, dict):
        characters = profile_data.get("characters", [])
    else:
        characters = []
    
    if not characters:
        return
    
    for character in characters:
        invite_cmd = f"/invite {character}"
        run_cmd(['xdotool', 'type', '--clearmodifiers', invite_cmd])
        time.sleep(0.1)
        run_cmd(['xdotool', 'key', 'Return'])
        time.sleep(0.1)

# ==================== Dialogue de compte à rebours ==================== #

class CountdownDialog(QDialog):
    def __init__(self, parent=None, callback=None):
        super().__init__(parent)
        self.setWindowTitle("Prêt à inviter")
        self.setFixedSize(280, 160)
        self.setStyleSheet("""
            QDialog {
                background-color: #1a0f08;
                border: 2px solid #8b7355;
                border-radius: 15px;
            }
            QLabel {
                color: #d4af37;
            }
        """)
        
        self.callback = callback
        self.counter = 15
        
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        label = QLabel("Clique sur le chat")
        label.setFont(QFont("Arial", 13, QFont.Bold))
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        
        self.timer_label = QLabel("1.5")
        self.timer_label.setFont(QFont("Arial", 60, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #d4af37;")
        layout.addWidget(self.timer_label)
        
        self.setLayout(layout)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(100)
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
    
    def update_countdown(self):
        self.counter -= 1
        time_left = self.counter / 10.0
        self.timer_label.setText(f"{time_left:.1f}")
        
        if self.counter <= 0:
            self.timer.stop()
            self.close()
            if self.callback:
                self.callback()

# ==================== Bouton action ==================== #

class ActionButton(QPushButton):
    def __init__(self, text, size=80):
        super().__init__(text)
        self.size = size
        self.setFixedSize(size, size)
        self.setFont(QFont("Arial", int(size * 0.28), QFont.Bold))
        self.is_hovered = False
        
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.is_active = False
    
    def set_active(self, active):
        self.is_active = active
        self.update()
    
    def enterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        half = self.size // 2
        
        diamond = QPolygon([
            QPoint(half, 2),
            QPoint(self.size - 2, half),
            QPoint(half, self.size - 2),
            QPoint(2, half)
        ])
        
        if self.is_active:
            border_color = QColor("#d4af37")
            bg_color = QColor("#3d3d2d")
            text_color = QColor("#ffda66")
        elif self.is_hovered:
            border_color = QColor("#c9a961")
            bg_color = QColor("#2a1810")
            text_color = QColor("#d4af37")
        else:
            border_color = QColor("#8b7355")
            bg_color = QColor("#1a0f08")
            text_color = QColor("#8b7355")
        
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 3))
        painter.drawPolygon(diamond)
        
        painter.setPen(text_color)
        painter.setFont(self.font())
        painter.drawText(event.rect(), Qt.AlignCenter, self.text())

# ==================== ComboBox  ==================== #

class StyledComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(50)
        self.setFont(QFont("Arial", 12, QFont.Bold))
        
        self.base_stylesheet = """
            QComboBox {
                background-color: #1a0f08;
                color: #d4af37;
                border: 2px solid #8b7355;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            QComboBox:hover {
                border: 2px solid #d4af37;
                background-color: #2a1810;
            }
            QComboBox::drop-down {
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: none;
            }
        """
        self.setStyleSheet(self.base_stylesheet)
        self.currentTextChanged.connect(self.on_selection_changed)
    
    def on_selection_changed(self, text):
        if text:
            self.setStyleSheet(self.base_stylesheet + """
                QComboBox {
                    background-color: #2a1810;
                    border: 2px solid #d4af37;
                }
            """)
        else:
            self.setStyleSheet(self.base_stylesheet)
    
    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        popup.setStyleSheet("""
            QWidget {
                background-color: #0d0805;
            }
            QListView {
                background-color: #1a0f08;
                color: #d4af37;
                border: 2px solid #8b7355;
                border-radius: 8px;
                outline: none;
            }
            QListView::item {
                padding: 8px 12px;
                height: 40px;
                font-weight: bold;
            }
            QListView::item:hover {
                background-color: #3d2817;
                border: 2px solid #d4af37;
            }
            QListView::item:selected {
                background-color: #8b7355;
                color: #ffda66;
                border: none;
            }
        """)

# ==================== Interface principale ==================== #

class DofusControl(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dofus Control")
        
        self.profiles = {}
        self.active_profile = ""
        self.drag_start = None
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("QMainWindow { background-color: #0d0805; }")
        self.resize(300, 400)
        
        self.setup_ui()
        self.load_initial_profiles()
    
    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet("""
            QWidget {
                background-color: #1a0f08;
                border: 2px solid #8b7355;
                border-radius: 15px;
            }
        """)
        self.setCentralWidget(central)
        
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(20)
        
        # Header
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        
        title = QLabel("Toolbox")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setStyleSheet("color: #d4af37; letter-spacing: 4px;border: none;")
        header.addWidget(title)
        header.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(45, 45)
        close_btn.setFont(QFont("Arial", 18, QFont.Bold))
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d2817;
                color: #d4af37;
                border: 2px solid #8b7355;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #5a3a22;
                border: 2px solid #d4af37;
            }
        """)
        close_btn.clicked.connect(self.close)
        header.addWidget(close_btn)
        
        main_layout.addLayout(header)
        
        # Dropdown profil
        self.profile_combo = StyledComboBox()
        self.profile_combo.currentTextChanged.connect(self.on_profile_selected)
        main_layout.addWidget(self.profile_combo)
        
        # Afficher les classes du profil actif
        self.classes_label = QLabel("")
        self.classes_label.setFont(QFont("Arial", 12))
        self.classes_label.setStyleSheet("color: #a68c5e; text-align: center;border:none;")
        self.classes_label.setAlignment(Qt.AlignCenter)
        self.classes_label.setWordWrap(True)
        main_layout.addWidget(self.classes_label)
        
        main_layout.addSpacing(15)
        
        # Grille 2x2 de boutons
        grid = QGridLayout()
        grid.setSpacing(20)
        grid.setContentsMargins(0, 0, 0, 0)
        
        # Top
        self.load_btn = ActionButton("📂", 80)
        self.load_btn.clicked.connect(self.load_profiles_file)
        self.load_btn.setToolTip("Charger un json pour les profiles")
        grid.addWidget(self.load_btn, 0, 1, Qt.AlignHCenter)
        
        # Middle row
        self.rename_btn = ActionButton("📝", 80)
        self.rename_btn.clicked.connect(self.action_rename)
        self.rename_btn.setToolTip("Renommer fenêtres")
        grid.addWidget(self.rename_btn, 1, 0, Qt.AlignHCenter)
        
        self.center_btn = ActionButton("🔒", 80)
        self.center_btn.clicked.connect(self.toggle_always_on_top)
        self.center_btn.setToolTip("Lock au premier plan")
        grid.addWidget(self.center_btn, 1, 1, Qt.AlignHCenter)
        
        self.reorg_btn = ActionButton("🔀", 80)
        self.reorg_btn.clicked.connect(self.action_reorganize)
        self.reorg_btn.setToolTip("Réorganiser fenêtres")
        grid.addWidget(self.reorg_btn, 1, 2, Qt.AlignHCenter)
        
        # Bottom
        self.invite_btn = ActionButton("👥", 80)
        self.invite_btn.clicked.connect(self.action_invite_group)
        self.invite_btn.setToolTip("Inviter groupe")
        grid.addWidget(self.invite_btn, 2, 1, Qt.AlignHCenter)
        
        main_layout.addLayout(grid)
        main_layout.addStretch()
        
        central.setLayout(main_layout)
    
    def toggle_always_on_top(self):
        global ALWAYS_ON_TOP
        ALWAYS_ON_TOP = not ALWAYS_ON_TOP
        
        flags = self.windowFlags()
        if ALWAYS_ON_TOP:
            flags |= Qt.WindowStaysOnTopHint
            self.center_btn.set_active(True)
        else:
            flags &= ~Qt.WindowStaysOnTopHint
            self.center_btn.set_active(False)
        
        self.setWindowFlags(flags)
        self.show()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
    
    def mouseMoveEvent(self, event):
        if self.drag_start is not None and event.buttons() == Qt.LeftButton:
            self.move(event.globalPos() - self.drag_start)
            event.accept()
    
    def mouseReleaseEvent(self, event):
        self.drag_start = None
    
    def load_profiles_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Charger profil", str(Path.home()), "JSON (*.json)"
        )
        
        if not file_path:
            return
        
        global PROFILES_FILE, SCRIPTS_DIR
        PROFILES_FILE = Path(file_path)
        SCRIPTS_DIR = PROFILES_FILE.parent / "scripts"
        
        config_file = APP_DIR / "last_profile.txt"
        with open(config_file, 'w') as f:
            f.write(str(PROFILES_FILE))
        
        try:
            data = load_data()
            self.profiles = data.get("profiles", {})
            self.active_profile = data.get("active", "")
            self.update_profile_list()
        except:
            pass
    
    def load_initial_profiles(self):
        default_path = PROFILES_DIR / "profiles.json"
        
        last_profile_file = APP_DIR / "last_profile.txt"
        if last_profile_file.exists():
            try:
                with open(last_profile_file, 'r') as f:
                    last_path = Path(f.read().strip())
                    if last_path.exists():
                        default_path = last_path
            except:
                pass
        
        global PROFILES_FILE, SCRIPTS_DIR
        PROFILES_FILE = default_path
        SCRIPTS_DIR = default_path.parent / "scripts"
        
        if default_path.exists():
            try:
                data = load_data()
                self.profiles = data.get("profiles", {})
                self.active_profile = data.get("active", "")
                self.update_profile_list()
            except:
                pass
    
    def update_profile_list(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(list(self.profiles.keys()))
        if self.active_profile in self.profiles:
            self.profile_combo.setCurrentText(self.active_profile)
        self.profile_combo.blockSignals(False)
        self.display_profile_classes()
    
    def display_profile_classes(self):
        profile_name = self.profile_combo.currentText()
        if profile_name in self.profiles:
            profile_data = self.profiles[profile_name]
            
            if isinstance(profile_data, dict):
                windows = profile_data.get("windows", [])
            else:
                windows = profile_data
            
            if windows:
                classes_text = " → ".join(windows)
                self.classes_label.setText(f"{classes_text}")
            else:
                self.classes_label.setText("")
        else:
            self.classes_label.setText("")
    
    def on_profile_selected(self, profile_name):
        if not profile_name or profile_name not in self.profiles:
            return
        save_initiative(profile_name)
        update_cycle_scripts(profile_name)
        self.display_profile_classes()
    
    def action_rename(self):
        if not PROFILES_FILE or not PROFILES_FILE.exists():
            return
        
        windows = get_dofus_windows()
        if not windows:
            return
        
        profile_name = self.profile_combo.currentText()
        if profile_name:
            rename_windows(profile_name)
    
    def action_reorganize(self):
        if not PROFILES_FILE or not PROFILES_FILE.exists():
            return
        
        windows = get_dofus_windows()
        if not windows:
            return
        
        profile_name = self.profile_combo.currentText()
        if profile_name:
            reorganize_windows(profile_name)
    
    def action_invite_group(self):
        if not PROFILES_FILE or not PROFILES_FILE.exists():
            return
        
        profile_name = self.profile_combo.currentText()
        if not profile_name:
            return
        
        countdown = CountdownDialog(self, lambda: self.launch_invites(profile_name))
        countdown.exec_()
    
    def launch_invites(self, profile_name: str):
        invite_group(profile_name)

def main():
    app = QApplication(sys.argv)
    window = DofusControl()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()