import os
import sys
from pathlib import Path

from typing import Optional

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QPixmap, QIcon, QFont, QColor, QPainter
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox,
    QFrame, QSplitter, QSizePolicy, QLineEdit
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import requests
import tempfile

FREE_DICT_API_BASE = os.environ.get(
    "FREEDICT_API_BASE",
    "https://api.dictionaryapi.dev/api/v2/entries/en",
)


DARK_THEME = """
QMainWindow { background: #1c2333; }
QLabel#preview {
    background: #262f45;
    border: 1px solid #3a4760;
    border-radius: 18px;
    color: #cad2ea;
    font-size: 18px;
}
QLabel#nameLabel {
    color: #f0f4ff;
    font-size: 16px;
    margin-top: 4px;
}
QLabel#panelLabel {
    color: #d4dbf2;
    font-size: 15px;
    margin: 6px 2px;
}

QListWidget#leftList, QListWidget#rightList {
    background: #252c40;
    border: 1px solid #3b4764;
    border-radius: 14px;
    padding: 6px;
    color: #f2f5ff;
    font-size: 14px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    margin: 4px;
    border-radius: 10px;
}
QListWidget::item:selected {
    background: #4a5b82;
    color: white;
}
QListWidget::item:hover {
    background: #313a53;
}

QPushButton {
    background: #384564;
    border: 1px solid #4d5d80;
    padding: 8px 16px;
    border-radius: 12px;
    color: #f7f9ff;
    font-size: 14px;
}
QPushButton:hover { background: #435074; }
QPushButton:pressed { background: #323d59; }
QPushButton:disabled {
    background: #2a3146;
    border-color: #3b4764;
    color: #9ba5c3;
}
"""

LIGHT_THEME = """
QMainWindow { background: #e6e9f1; }
QLabel#preview {
    background: #f8f9fd;
    border: 1px solid #cfd6e6;
    border-radius: 18px;
    color: #3d4459;
    font-size: 18px;
}
QLabel#nameLabel {
    color: #2f3547;
    font-size: 16px;
    margin-top: 4px;
}
QLabel#panelLabel {
    color: #4c556c;
    font-size: 15px;
    margin: 6px 2px;
}

QListWidget#leftList, QListWidget#rightList {
    background: #f9fafe;
    border: 1px solid #cfd6e6;
    border-radius: 14px;
    padding: 6px;
    color: #2e3548;
    font-size: 14px;
    outline: none;
}
QListWidget::item {
    padding: 8px 10px;
    margin: 4px;
    border-radius: 10px;
}
QListWidget::item:selected {
    background: #dfe7ff;
    color: #1d2550;
}
QListWidget::item:hover {
    background: #eef1fb;
}

QPushButton {
    background: #f2f4fb;
    border: 1px solid #c1c9dc;
    padding: 8px 16px;
    border-radius: 12px;
    color: #2e3548;
    font-size: 14px;
}
QPushButton:hover { background: #e8ecf7; }
QPushButton:pressed { background: #dce1f0; }
QPushButton:disabled {
    background: #eef0f6;
    border-color: #d4d7e3;
    color: #a6acbe;
}
"""

THEMES = {
    "dark": DARK_THEME,
    "light": LIGHT_THEME,
}


def resource_path(rel: str) -> str:
    """
    PyInstaller 打包后资源路径兼容
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        exe_candidate = exe_dir / rel
        if exe_candidate.exists():
            return str(exe_candidate)
        if hasattr(sys, "_MEIPASS"):
            bundle_candidate = Path(sys._MEIPASS) / rel
            if bundle_candidate.exists():
                return str(bundle_candidate)
        return str(exe_candidate)
    return str(Path(__file__).resolve().parent / rel)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("edu工具")
        self.setMinimumSize(1000, 650)

        # data 目录（相对 exe/app.py）
        self.data_dir = Path(resource_path("data"))
        self.images = {}   # basename -> image path
        self.audios = {}   # basename -> audio path

        self.left_all = []     # 所有可用 basename
        self.left_current = [] # 左侧当前 basename
        self.right_current = []# 右侧当前 basename
        self.current_name = None
        self.current_audio_path = None
        self.temp_audio_files = []  # 在线音频临时文件列表
        self.search_results = []

        # 音频播放器
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.9)

        self.current_theme = "dark"

        self._build_ui()
        self.apply_theme(self.current_theme)
        self._load_data()

    # ---------- UI ----------
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        # 左侧列表
        self.left_list = QListWidget()
        self.left_list.setObjectName("leftList")
        self.left_list.itemClicked.connect(self.on_left_click)
        self.left_label = QLabel("待选 (0)")
        self.left_label.setObjectName("panelLabel")

        # 右侧列表
        self.right_list = QListWidget()
        self.right_list.setObjectName("rightList")
        self.right_list.itemClicked.connect(self.on_right_click)
        self.right_label = QLabel("已选 (0)")
        self.right_label.setObjectName("panelLabel")

        # 中间预览
        self.preview = QLabel("点击左侧文件开始")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setObjectName("preview")
        self.preview.setMinimumHeight(360)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.setWordWrap(True)

        # 文件名显示
        self.name_label = QLabel("")
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setObjectName("nameLabel")

        # 控制按钮
        self.btn_move = QPushButton("换图")
        self.btn_move.clicked.connect(self.move_to_right)
        self.btn_move.setEnabled(False)

        self.btn_reset = QPushButton("重置")
        self.btn_reset.clicked.connect(self.reset_all)

        self.btn_play = QPushButton("播放音频")
        self.btn_play.clicked.connect(self.play_current_audio)
        self.btn_play.setEnabled(False)

        # 主题切换按钮
        theme_row = QHBoxLayout()
        theme_row.addStretch(1)
        self.btn_theme_light = QPushButton("浅色主题")
        self.btn_theme_light.clicked.connect(lambda: self.apply_theme("light"))
        self.btn_theme_dark = QPushButton("深色主题")
        self.btn_theme_dark.clicked.connect(lambda: self.apply_theme("dark"))
        theme_row.addWidget(self.btn_theme_light)
        theme_row.addWidget(self.btn_theme_dark)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("在线搜词...")
        self.search_input.setMinimumWidth(180)
        self.search_input.returnPressed.connect(self.handle_search)
        self.btn_search = QPushButton("搜索")
        self.btn_search.clicked.connect(self.handle_search)
        theme_row.addWidget(self.search_input)
        theme_row.addWidget(self.btn_search)
        theme_row.addStretch(1)

        # 布局：左右 + 中间预览区
        center_box = QVBoxLayout()
        center_box.addLayout(theme_row)
        center_box.addSpacing(6)
        center_box.addWidget(self.preview, 1)
        center_box.addWidget(self.name_label)
        center_box.addSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_move)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch(1)

        center_box.addLayout(btn_row)

        center_widget = QWidget()
        center_widget.setLayout(center_box)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_panel(self.left_label, self.left_list))
        splitter.addWidget(center_widget)
        splitter.addWidget(self._build_panel(self.right_label, self.right_list))
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 2)
        layout = QHBoxLayout()
        layout.addWidget(splitter)
        root.setLayout(layout)

    def _build_panel(self, label_widget: QLabel, widget: QWidget) -> QWidget:
        box = QVBoxLayout()
        label_widget.setAlignment(Qt.AlignLeft)
        box.addWidget(label_widget)
        box.addWidget(widget, 1)
        container = QWidget()
        container.setLayout(box)
        return container

    def apply_theme(self, theme_name: str):
        theme = THEMES.get(theme_name, THEMES["dark"])
        self.setStyleSheet(theme)
        if theme_name not in THEMES:
            theme_name = "dark"
        self.current_theme = theme_name
        if hasattr(self, "btn_theme_light"):
            self.btn_theme_light.setEnabled(self.current_theme != "light")
        if hasattr(self, "btn_theme_dark"):
            self.btn_theme_dark.setEnabled(self.current_theme != "dark")

    def cleanup_temp_audios(self):
        for path in self.temp_audio_files:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        self.temp_audio_files = []

    def handle_search(self):
        if not hasattr(self, "search_input"):
            return
        word = self.search_input.text().strip()
        if not word:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            display_text, audio_path = self.fetch_word_data(word)
        except ValueError:
            self._show_not_found(word)
            return
        except Exception as exc:
            QMessageBox.warning(self, "提示", f"搜索失败：{exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.stop_audio()
        self.preview.setPixmap(QPixmap())
        self.preview.setText(display_text)
        self.current_name = word
        self.name_label.setText(word)
        self.current_audio_path = audio_path
        self.btn_move.setEnabled(False)
        self.btn_play.setEnabled(bool(audio_path))
        self._record_search_result(word, display_text, audio_path)
        self.refresh_lists()

    def fetch_word_data(self, word: str):
        definition, dict_audio = self._query_dictionary(word)

        if not definition:
            raise ValueError("未找到对应的单词")

        display_parts = [word, definition]
        display_text = "\n".join([part for part in display_parts if part])

        audio_path = None
        if dict_audio:
            audio_path = self._download_audio(dict_audio)
        if not audio_path:
            audio_path = self._download_audio(
                f"https://dict.youdao.com/dictvoice?type=2&audio={word}"
            )

        return display_text, audio_path

    def _query_dictionary(self, word: str):
        base = FREE_DICT_API_BASE.rstrip('/')
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

        variants = {base}
        lowered_base = base.lower()
        if lowered_base.endswith('/en'):
            root = base[:-3]
            variants.add(f"{root}/en_US")
            variants.add(f"{root}/en_GB")

        words = []
        for variant in [word, word.strip(), word.lower(), word.upper()]:
            if variant and variant not in words:
                words.append(variant)

        session = requests.Session()
        for lang_base in variants:
            for w in words:
                encoded_word = requests.utils.quote(w)
                url = f"{lang_base}/{encoded_word}"
                resp = None
                for _ in range(3):
                    try:
                        resp = session.get(url, timeout=(5, 10), headers=headers)
                        break
                    except requests.RequestException:
                        resp = None
                        continue
                if not resp or resp.status_code != 200:
                    continue
                try:
                    data = resp.json()
                except ValueError:
                    continue
                if not isinstance(data, list) or not data:
                    continue
                entry = data[0]
                definitions = []
                for meaning in entry.get("meanings", []):
                    part = meaning.get("partOfSpeech", "")
                    defs = meaning.get("definitions") or []
                    for item in defs:
                        candidate = item.get("definition")
                        if not candidate:
                            continue
                        if part:
                            definitions.append(f"{part}: {candidate}")
                        else:
                            definitions.append(candidate)
                        if len(definitions) >= 3:
                            break
                    if len(definitions) >= 3:
                        break
                audio_url = None
                for phonetic in entry.get("phonetics") or []:
                    candidate = phonetic.get("audio")
                    if candidate:
                        audio_url = candidate
                        break
                if definitions or audio_url:
                    definition_text = "\n".join(definitions)
                    return definition_text, audio_url
        return None, None

    def _download_audio(self, url: Optional[str]):
        if not url:
            return None
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, timeout=5, headers=headers)
            if not (resp.ok and resp.content):
                return None
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tmp.write(resp.content)
            tmp.close()
            self.temp_audio_files.append(tmp.name)
            return tmp.name
        except Exception:
            return None

    def _record_search_result(self, word: str, text: str, audio: Optional[str]):
        lowered = word.lower()
        self.search_results = [entry for entry in self.search_results if entry["name"].lower() != lowered]
        self.search_results.insert(0, {
            "type": "search",
            "name": word,
            "text": text,
            "audio": audio,
        })

    def _create_search_icon(self, text: str) -> QIcon:
        pix = QPixmap(48, 48)
        if self.current_theme == "light":
            pix.fill(QColor("#dfe7ff"))
            pen_color = QColor("#1d2550")
        else:
            pix.fill(QColor("#4a5b82"))
            pen_color = QColor("#ffffff")
        painter = QPainter(pix)
        painter.setPen(pen_color)
        painter.setFont(QFont("Arial", 16, QFont.Bold))
        painter.drawText(pix.rect(), Qt.AlignCenter, text[:2].upper())
        painter.end()
        return QIcon(pix)

    def show_search_result(self, entry: dict):
        self.stop_audio()
        self.preview.setPixmap(QPixmap())
        self.preview.setText(entry.get("text", entry.get("name", "")))
        self.current_name = entry.get("name", "")
        self.name_label.setText(self.current_name)
        self.current_audio_path = entry.get("audio")
        self.btn_move.setEnabled(False)
        self.btn_play.setEnabled(bool(self.current_audio_path))

    def _show_not_found(self, word: str):
        self.preview.setPixmap(QPixmap())
        self.preview.setText(f"未找到单词：{word}")
        self.current_name = word
        self.name_label.setText(word)
        self.current_audio_path = None
        self.btn_move.setEnabled(False)
        self.btn_play.setEnabled(False)


    # ---------- Data ----------
    def _load_data(self):
        if not self.data_dir.exists():
            QMessageBox.warning(self, "提示", f"未找到 data 文件夹：\n{self.data_dir}\n请放在程序同级目录。")
            return

        # 收集图片 / 音频
        img_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        aud_ext = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

        for p in self.data_dir.iterdir():
            if not p.is_file():
                continue
            suffix = p.suffix.lower()
            name = p.stem
            if suffix in img_ext:
                self.images[name] = p
            elif suffix in aud_ext:
                self.audios[name] = p

        # 只显示有图片的项目
        self.left_all = sorted(self.images.keys())
        self.reset_all()

    # ---------- Events ----------
    def on_left_click(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        self.show_item(name, from_left=True)

    def on_right_click(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if isinstance(data, dict) and data.get("type") == "search":
            self.show_search_result(data)
        else:
            name = data if isinstance(data, str) else str(data)
            self.show_item(name, from_left=False)

    def show_item(self, name: str, from_left: bool):
        self.current_name = name
        self.name_label.setText(name)

        # 显示图片
        img_path = self.images.get(name)
        if img_path and img_path.exists():
            pix = QPixmap(str(img_path))
            if not pix.isNull():
                self.preview.setPixmap(
                    pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                self.preview.setText("")
            else:
                self.preview.setPixmap(QPixmap())
                self.preview.setText("图片无法加载")
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("未找到对应图片")

        # 播放同名音频
        aud_path = self.audios.get(name)
        if aud_path and aud_path.exists():
            self.current_audio_path = str(aud_path)
            self.play_audio(aud_path)
            self.btn_play.setEnabled(True)
        else:
            self.current_audio_path = None
            self.stop_audio()
            self.btn_play.setEnabled(False)

        # 左侧选中时允许移动
        self.btn_move.setEnabled(from_left)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_name:
            img_path = self.images.get(self.current_name)
            if img_path and img_path.exists():
                pix = QPixmap(str(img_path))
                self.preview.setPixmap(
                    pix.scaled(self.preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

    # ---------- Audio ----------
    def play_audio(self, path: Path):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()

    def play_current_audio(self):
        if not self.current_audio_path:
            return
        audio_path = Path(self.current_audio_path)
        if audio_path.exists():
            self.play_audio(audio_path)
            self.btn_play.setEnabled(True)
        else:
            self.current_audio_path = None
            self.stop_audio()
            self.btn_play.setEnabled(False)

    def stop_audio(self):
        self.player.stop()

    # ---------- Actions ----------
    def move_to_right(self):
        name = self.current_name
        if not name or name not in self.left_current:
            return

        current_index = self.left_current.index(name)
        # 从左移除
        self.left_current.pop(current_index)
        # 加到右边
        if name not in self.right_current:
            self.right_current.append(name)

        self.refresh_lists()

        # 自动切换到下一个待选内容
        next_name = None
        if self.left_current:
            next_index = min(current_index, len(self.left_current) - 1)
            next_name = self.left_current[next_index]

        if next_name:
            self.select_left_item(next_name)
            self.show_item(next_name, from_left=True)
        else:
            self.current_name = None
            self.current_audio_path = None
            self.preview.setText("所有图片已完成")
            self.preview.setPixmap(QPixmap())
            self.name_label.setText("")
            self.btn_move.setEnabled(False)
            self.btn_play.setEnabled(False)

    def reset_all(self):
        self.current_name = None
        self.left_current = self.left_all.copy()
        self.right_current = []
        self.preview.setText("点击左侧文件开始")
        self.preview.setPixmap(QPixmap())
        self.name_label.setText("")
        self.btn_move.setEnabled(False)
        self.btn_play.setEnabled(False)
        self.stop_audio()
        self.current_audio_path = None
        self.search_results = []
        self.cleanup_temp_audios()
        self.refresh_lists()

    def refresh_lists(self):
        self.left_list.clear()
        self.right_list.clear()

        # 左侧
        for name in self.left_current:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            # 缩略图 icon
            img_path = self.images.get(name)
            if img_path and img_path.exists():
                ico = QIcon(str(img_path))
                item.setIcon(ico)
            self.left_list.addItem(item)

        # 右侧
        for name in self.right_current:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            img_path = self.images.get(name)
            if img_path and img_path.exists():
                ico = QIcon(str(img_path))
                item.setIcon(ico)
            self.right_list.addItem(item)

        for entry in self.search_results:
            item = QListWidgetItem(entry["name"])
            item.setData(Qt.UserRole, entry)
            item.setIcon(self._create_search_icon(entry["name"]))
            if entry.get("text"):
                item.setToolTip(entry["text"])
            self.right_list.addItem(item)

        self.update_counts()

    def update_counts(self):
        self.left_label.setText(f"待选 ({len(self.left_current)})")
        total_right = len(self.right_current) + len(self.search_results)
        self.right_label.setText(f"已选 ({total_right})")

    def select_left_item(self, name: str):
        for row in range(self.left_list.count()):
            item = self.left_list.item(row)
            if item and item.data(Qt.UserRole) == name:
                self.left_list.setCurrentRow(row)
                break


def main():
    app = QApplication(sys.argv)
    # 适度抗锯齿 / 字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
