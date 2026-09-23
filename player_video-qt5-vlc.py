#!/usr/bin/env python3
import sys
import os
import vlc
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, 
                             QPushButton, QHBoxLayout, QVBoxLayout, 
                             QFileDialog, QFrame)

class ClickableVideoWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setStyleSheet("background-color: #000000; border: none;")

    def mouseDoubleClickEvent(self, event):
        """Переключение полноэкранного режима по двойному клику."""
        if self.parent_window:
            self.parent_window.toggle_fullscreen()
        event.accept()

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Видеоплеер")
        self.resize(850, 520)

        self.current_file = None

        # Светлая минималистичная тема QSS
        self.light_qss = """
            QMainWindow { background-color: #f5f5f5; }
            QWidget { background-color: #f5f5f5; color: #2c3e50; font-family: "Ubuntu", sans-serif; font-size: 13px; }
            QPushButton { background-color: #ffffff; border: 1px solid #dcdde1; border-radius: 4px; padding: 6px 15px; min-width: 80px; }
            QPushButton:hover { background-color: #f1f2f6; border: 1px solid #b2bec3; }
            QPushButton:pressed { background-color: #dcdde1; }
            QPushButton:checked { background-color: #007acc; color: #ffffff; border-color: #005999; }
        """
        self.setStyleSheet(self.light_qss)

        # Инициализация ядра VLC и событий
        self.vlc_instance = vlc.Instance()
        self.player = self.vlc_instance.media_player_new()
        
        # Настраиваем обработку окончания видео через менеджер событий VLC
        self.event_manager = self.player.event_manager()
        self.event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_video_ended)

        self.video_area = ClickableVideoWidget(self)

        self.open_button = QPushButton("Открыть")
        self.play_button = QPushButton("Воспроизвести")
        self.stop_button = QPushButton("Стоп")
        
        self.loop_button = QPushButton("Повтор")
        self.loop_button.setCheckable(True)

        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.play_pause)
        self.stop_button.clicked.connect(self.stop)

        self.open_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.stop_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.loop_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Контейнер для кнопок управления
        self.controls_container = QWidget()
        control_layout = QHBoxLayout(self.controls_container)
        control_layout.setSpacing(8)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.addWidget(self.open_button)
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch(1)
        control_layout.addWidget(self.loop_button)

        # Главный Layout приложения
        self.main_layout = QVBoxLayout()
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)
        self.main_layout.addWidget(self.video_area, stretch=1)
        self.main_layout.addWidget(self.controls_container)

        container = QWidget()
        container.setLayout(self.main_layout)
        self.setCentralWidget(container)

        if sys.platform.startswith('linux'):
            self.player.set_xwindow(int(self.video_area.winId()))

    def toggle_fullscreen(self):
        """Переключение полноэкранного режима."""
        if self.isFullScreen():
            self.main_layout.setContentsMargins(10, 10, 10, 10)
            self.setStyleSheet(self.light_qss)
            self.showNormal()
            self.controls_container.show()
        else:
            self.controls_container.hide()
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.setStyleSheet("QMainWindow { background-color: #000000; }")
            self.showFullScreen()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space:
            self.play_pause()
        elif event.key() == Qt.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
        else:
            super().keyPressEvent(event)

    def on_video_ended(self, event):
        """Вызывается потоком VLC, когда видео доходит до конца."""
        if self.loop_button.isChecked():
            # Зацикливание: перезапуск нужно делать в потоке Qt, используем QTimer.singleShot
            QTimer.singleShot(0, self.restart_video)
        else:
            QTimer.singleShot(0, self.stop)

    def restart_video(self):
        self.player.stop()
        self.player.play()

    def open_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Выберите видеофайл", "", 
            "Видео (*.mpg *.mpeg *.m1v *.m2v *.vob *.mp4 *.avi *.mkv);;Все файлы (*)"
        )
        if filename:
            self.current_file = filename
            media = self.vlc_instance.media_new(filename)
            self.player.set_media(media)
            self.player.play()
            self.play_button.setText("Пауза")

    def play_pause(self):
        if not self.current_file:
            return
        if self.player.is_playing():
            self.player.pause()
            self.play_button.setText("Продолжить")
        else:
            self.player.play()
            self.play_button.setText("Пауза")

    def stop(self):
        self.player.stop()
        self.play_button.setText("Воспроизвести")
        if self.isFullScreen():
            self.toggle_fullscreen()

    def closeEvent(self, event):
        self.player.stop()
        event.accept()

if __name__ == "__main__":
    from PyQt5.QtCore import QTimer  # Импортируем локально для вызова внутри колбэка VLC
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec_())

