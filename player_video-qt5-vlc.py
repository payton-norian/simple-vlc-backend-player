#!/usr/bin/env python3
import os
import sys
import platform

import vlc
from PyQt5 import QtCore, QtGui, QtWidgets


class VideoSlider(QtWidgets.QSlider):
    sliderPressedCustom = QtCore.pyqtSignal()
    sliderReleasedCustom = QtCore.pyqtSignal()

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.sliderPressedCustom.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            self.sliderReleasedCustom.emit()


class VideoPlayer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Видеоплеер")
        self.resize(850, 560)
        self.setAcceptDrops(True)

        self.current_file = None
        self.is_fullscreen = False
        self.is_slider_pressed = False
        self.was_playing_before_seek = False

        # VLC
        vlc_args = [
            "--avcodec-hw=vaapi",
            "--quiet",
        ]

        self.vlc_instance = vlc.Instance(vlc_args)
        self.player = self.vlc_instance.media_player_new()

        # Qt-видеоповерхность
        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setObjectName("videoFrame")
        self.video_frame.setMinimumSize(320, 180)
        self.video_frame.setAttribute(QtCore.Qt.WA_NativeWindow, True)
        self.video_frame.setAutoFillBackground(True)

        # Таймлайн
        self.timeline = VideoSlider(QtCore.Qt.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.setValue(0)
        self.timeline.setTracking(False)
        self.timeline.setToolTip("Перемотка")

        self.timeline.sliderPressedCustom.connect(self.on_slider_pressed)
        self.timeline.sliderReleasedCustom.connect(self.on_slider_released)

        # Кнопки
        self.open_button = QtWidgets.QPushButton("Открыть")
        self.play_button = QtWidgets.QPushButton("Воспроизвести")
        self.stop_button = QtWidgets.QPushButton("Стоп")
        self.loop_button = QtWidgets.QPushButton("Повтор")
        self.loop_button.setCheckable(True)

        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.play_pause)
        self.stop_button.clicked.connect(self.stop)

        # Панель управления
        controls = QtWidgets.QHBoxLayout()
        controls.setContentsMargins(10, 0, 10, 10)
        controls.setSpacing(8)

        controls.addWidget(self.open_button)
        controls.addWidget(self.play_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        controls.addWidget(self.loop_button)

        # Основной layout
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 0)
        layout.setSpacing(10)

        layout.addWidget(self.video_frame, 1)
        layout.addWidget(self.timeline)
        layout.addLayout(controls)

        # Таймер обновления таймлайна
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update_timeline)

        # События VLC
        event_manager = self.player.event_manager()
        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self.on_video_ended
        )

        self.apply_styles()

    # ------------------------------------------------------------------
    # Стили
    # ------------------------------------------------------------------

    def apply_styles(self):
        self.setStyleSheet("""
            QPushButton {
                color: #2c3e50;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 6px 15px;
                min-width: 80px;
                font-family: Ubuntu, sans-serif;
                font-size: 16px;
                background-color: #ffffff;
            }

            QPushButton:hover {
                background-color: #f1f2f6;
                border-color: #b2bec3;
            }

            QPushButton:pressed {
                background-color: #dcdde1;
            }

            QPushButton:checked {
                background-color: #007acc;
                color: white;
                border-color: #005999;
            }

            QFrame#videoFrame {
                background-color: black;
            }

            QSlider::groove:horizontal {
                height: 6px;
                background: white;
                border: 1px solid #dcdde1;
                border-radius: 3px;
            }

            QSlider::sub-page:horizontal {
                background: #007acc;
                border-radius: 3px;
            }

            QSlider::add-page:horizontal {
                background: white;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                width: 14px;
                margin: -5px 0;
                background: white;
                border: 1px solid #b2bec3;
                border-radius: 7px;
            }

            QSlider::handle:horizontal:hover {
                background: #f1f2f6;
                border-color: #007acc;
            }
        """)

    # ------------------------------------------------------------------
    # Привязка VLC к Qt-виджету
    # ------------------------------------------------------------------

    def bind_video_output(self):
        """
        VLC должен получить native window ID уже созданного Qt-виджета.
        """
        handle = int(self.video_frame.winId())

        system = platform.system()

        if system == "Windows":
            self.player.set_hwnd(handle)
        elif system == "Darwin":
            self.player.set_nsobject(handle)
        else:
            self.player.set_xwindow(handle)

    # ------------------------------------------------------------------
    # Таймлайн
    # ------------------------------------------------------------------

    def update_timeline(self):
        if self.is_slider_pressed:
            return

        if not self.player.get_media():
            return

        length = self.player.get_length()
        current_time = self.player.get_time()

        if length <= 0 or current_time < 0:
            return

        value = int(current_time * 1000 / length)

        blocked = self.timeline.blockSignals(True)
        self.timeline.setValue(max(0, min(1000, value)))
        self.timeline.blockSignals(blocked)

    def on_slider_pressed(self):
        self.is_slider_pressed = True
        self.was_playing_before_seek = bool(self.player.is_playing())

        # Пауза уменьшает вероятность скачков во время перемотки.
        if self.was_playing_before_seek:
            self.player.pause()

    def on_slider_released(self):
        if not self.player.get_media():
            self.is_slider_pressed = False
            return

        length = self.player.get_length()

        if length > 0:
            position = self.timeline.value() / 1000.0
            target_time = int(length * position)

            # Надёжнее, чем set_position(), особенно для локальных файлов.
            self.player.set_time(target_time)

        self.is_slider_pressed = False

        if self.was_playing_before_seek:
            self.player.play()

    # ------------------------------------------------------------------
    # Управление воспроизведением
    # ------------------------------------------------------------------

    def load_and_play(self, filename):
        if not filename:
            return

        self.current_file = filename

        self.player.stop()

        media = self.vlc_instance.media_new(filename)
        self.player.set_media(media)

        # Повторно привязываем видеовывод перед запуском.
        self.bind_video_output()

        result = self.player.play()

        if result == -1:
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось воспроизвести файл."
            )
            return

        self.play_button.setText("Пауза")
        self.timeline.setValue(0)
        self.timer.start()

    def play_pause(self):
        if not self.current_file:
            return

        if self.player.is_playing():
            self.player.pause()
            self.timer.stop()
            self.play_button.setText("Продолжить")
        else:
            self.player.play()
            self.timer.start()
            self.play_button.setText("Пауза")

    def stop(self):
        self.player.stop()
        self.timer.stop()

        blocked = self.timeline.blockSignals(True)
        self.timeline.setValue(0)
        self.timeline.blockSignals(blocked)

        self.play_button.setText("Воспроизвести")

        if self.is_fullscreen:
            self.toggle_fullscreen()

    # ------------------------------------------------------------------
    # Открытие файлов
    # ------------------------------------------------------------------

    def open_file(self):
        filters = (
            "Видео (*.mpg *.mpeg *.m1v *.m2v *.vob *.mp4 "
            "*.avi *.mkv *.webm *.mov);;Все файлы (*)"
        )

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл",
            "",
            filters
        )

        if filename:
            self.load_and_play(filename)

    # ------------------------------------------------------------------
    # Drag and Drop
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_and_play(url.toLocalFile())
                break

        event.acceptProposedAction()

    # ------------------------------------------------------------------
    # Полноэкранный режим
    # ------------------------------------------------------------------

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.timeline.show()
            self.open_button.show()
            self.play_button.show()
            self.stop_button.show()
            self.loop_button.show()
            self.is_fullscreen = False
        else:
            self.timeline.hide()
            self.open_button.hide()
            self.play_button.hide()
            self.stop_button.hide()
            self.loop_button.hide()
            self.showFullScreen()
            self.is_fullscreen = True

    # ------------------------------------------------------------------
    # События
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())

            if child is self.video_frame or self.video_frame.isAncestorOf(child):
                self.toggle_fullscreen()

        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Space:
            self.play_pause()
            event.accept()
            return

        if event.key() == QtCore.Qt.Key_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
            event.accept()
            return

        super().keyPressEvent(event)

    def on_video_ended(self, event):
        QtCore.QMetaObject.invokeMethod(
            self,
            "handle_video_ended",
            QtCore.Qt.QueuedConnection
        )

    @QtCore.pyqtSlot()
    def handle_video_ended(self):
        if self.loop_button.isChecked():
            self.timeline.setValue(0)
            self.player.stop()
            self.player.play()
            self.play_button.setText("Пауза")
            self.timer.start()
        else:
            self.stop()

    def closeEvent(self, event):
        self.timer.stop()
        self.player.stop()
        self.player.release()
        self.vlc_instance.release()
        event.accept()


def main():
    app = QtWidgets.QApplication(sys.argv)

    window = VideoPlayer()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
