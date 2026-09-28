#!/usr/bin/env python3

import os
import platform
import sys

import vlc
from PyQt5 import QtCore, QtWidgets


class VideoSlider(QtWidgets.QSlider):
    """
    QSlider, который сообщает о начале и окончании перетаскивания.
    """

    seekStarted = QtCore.pyqtSignal()
    seekFinished = QtCore.pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.seekStarted.emit()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        if event.button() == QtCore.Qt.LeftButton:
            self.seekFinished.emit()


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

        # Центральный виджет Qt
        self.central = QtWidgets.QWidget()
        self.central.setObjectName("central")
        self.setCentralWidget(self.central)

        # Видеоповерхность
        self.video_frame = QtWidgets.QFrame()
        self.video_frame.setObjectName("videoFrame")
        self.video_frame.setAttribute(QtCore.Qt.WA_NativeWindow, True)
        self.video_frame.setAutoFillBackground(True)
        self.video_frame.setMinimumSize(320, 180)

        # Таймлайн
        self.timeline = VideoSlider(QtCore.Qt.Horizontal)
        self.timeline.setRange(0, 1000)
        self.timeline.setValue(0)
        self.timeline.setTracking(False)
        self.timeline.setFocusPolicy(QtCore.Qt.NoFocus)
        self.timeline.setToolTip("Перемотка")

        self.timeline.seekStarted.connect(self.on_slider_pressed)
        self.timeline.seekFinished.connect(self.on_slider_released)

        # Кнопки
        self.open_button = QtWidgets.QPushButton("Открыть")
        self.play_button = QtWidgets.QPushButton("Воспроизвести")
        self.stop_button = QtWidgets.QPushButton("Стоп")
        self.loop_button = QtWidgets.QPushButton("Повтор")
        self.loop_button.setCheckable(True)

        self.open_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.play_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.stop_button.setFocusPolicy(QtCore.Qt.NoFocus)
        self.loop_button.setFocusPolicy(QtCore.Qt.NoFocus)

        self.open_button.clicked.connect(self.open_file)
        self.play_button.clicked.connect(self.play_pause)
        self.stop_button.clicked.connect(self.stop)

        # Панель кнопок
        self.controls = QtWidgets.QHBoxLayout()
        self.controls.setContentsMargins(10, 0, 10, 10)
        self.controls.setSpacing(8)

        self.controls.addWidget(self.open_button)
        self.controls.addWidget(self.play_button)
        self.controls.addWidget(self.stop_button)
        self.controls.addStretch()
        self.controls.addWidget(self.loop_button)

        # Главный layout.
        # ВАЖНО: сохраняем его в self.main_layout,
        # чтобы менять отступы при полноэкранном режиме.
        self.main_layout = QtWidgets.QVBoxLayout(self.central)
        self.main_layout.setContentsMargins(10, 10, 10, 0)
        self.main_layout.setSpacing(10)

        self.main_layout.addWidget(self.video_frame, 1)
        self.main_layout.addWidget(self.timeline)
        self.main_layout.addLayout(self.controls)

        # Таймер обновления таймлайна
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update_timeline)

        # Событие окончания видео
        event_manager = self.player.event_manager()
        event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached,
            self.on_video_ended
        )

        self.apply_styles()

    # ================================================================
    # Внешний вид
    # ================================================================

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow,
            QWidget#central {
                background-color: black;
            }

            QFrame#videoFrame {
                background-color: black;
                border: none;
            }

            QPushButton {
                color: #2c3e50;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 6px 15px;
                min-width: 80px;
                font-family: Ubuntu, sans-serif;
                font-size: 16px;
                background-color: white;
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

            QSlider::groove:horizontal {
                height: 6px;
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 3px;
            }

            QSlider::sub-page:horizontal {
                background-color: #007acc;
                border-radius: 3px;
            }

            QSlider::add-page:horizontal {
                background-color: white;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                width: 14px;
                margin: -5px 0;
                background-color: white;
                border: 1px solid #b2bec3;
                border-radius: 7px;
            }

            QSlider::handle:horizontal:hover {
                background-color: #f1f2f6;
                border-color: #007acc;
            }
        """)

    # ================================================================
    # Вывод VLC в Qt
    # ================================================================

    def bind_video_output(self):
        """
        Передаём VLC native ID видеоповерхности Qt.
        """

        window_id = int(self.video_frame.winId())
        system = platform.system()

        if system == "Windows":
            self.player.set_hwnd(window_id)

        elif system == "Darwin":
            self.player.set_nsobject(window_id)

        else:
            # Linux/X11
            self.player.set_xwindow(window_id)

    # ================================================================
    # Таймлайн и перемотка
    # ================================================================

    def update_timeline(self):
        if self.is_slider_pressed:
            return

        if not self.player.get_media():
            return

        current_time = self.player.get_time()
        total_time = self.player.get_length()

        if current_time < 0 or total_time <= 0:
            return

        value = int(current_time * 1000 / total_time)
        value = max(0, min(1000, value))

        # Не вызываем лишние сигналы во время автоматического обновления
        old_state = self.timeline.blockSignals(True)
        self.timeline.setValue(value)
        self.timeline.blockSignals(old_state)

    def on_slider_pressed(self):
        self.is_slider_pressed = True
        self.was_playing_before_seek = bool(self.player.is_playing())

        # На время перемотки ставим видео на паузу
        if self.was_playing_before_seek:
            self.player.pause()

    def on_slider_released(self):
        if not self.player.get_media():
            self.is_slider_pressed = False
            return

        total_time = self.player.get_length()

        if total_time > 0:
            position = self.timeline.value() / 1000.0
            target_time = int(total_time * position)

            # Перемотка в миллисекундах
            self.player.set_time(target_time)

        self.is_slider_pressed = False

        if self.was_playing_before_seek:
            self.player.play()

    # ================================================================
    # Управление воспроизведением
    # ================================================================

    def load_and_play(self, filename):
        if not filename:
            return

        filename = os.path.abspath(filename)
        self.current_file = filename

        self.player.stop()

        media = self.vlc_instance.media_new(filename)
        self.player.set_media(media)

        # Нужно вызвать после создания native Qt-виджета
        self.bind_video_output()

        result = self.player.play()

        if result == -1:
            QtWidgets.QMessageBox.warning(
                self,
                "Ошибка",
                "Не удалось воспроизвести файл."
            )
            return

        self.timeline.setValue(0)
        self.play_button.setText("Пауза")
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

        old_state = self.timeline.blockSignals(True)
        self.timeline.setValue(0)
        self.timeline.blockSignals(old_state)

        self.play_button.setText("Воспроизвести")

        if self.is_fullscreen:
            self.toggle_fullscreen()

    # ================================================================
    # Открытие файла
    # ================================================================

    def open_file(self):
        video_filter = (
            "Видео (*.mpg *.mpeg *.m1v *.m2v *.vob *.mp4 "
            "*.avi *.mkv *.webm *.mov);;Все файлы (*)"
        )

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Выберите видеофайл",
            "",
            video_filter
        )

        if filename:
            self.load_and_play(filename)

    # ================================================================
    # Drag and Drop
    # ================================================================

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.load_and_play(url.toLocalFile())
                break

        event.acceptProposedAction()

    # ================================================================
    # Полноэкранный режим
    # ================================================================

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            # Сначала выходим из полноэкранного режима
            self.showNormal()

            # Возвращаем обычные отступы
            self.main_layout.setContentsMargins(10, 10, 10, 0)
            self.main_layout.setSpacing(10)

            self.timeline.show()
            self.controls_widget_show()

            self.is_fullscreen = False

        else:
            # Убираем все отступы и промежутки.
            # Благодаря этому белой рамки быть не должно.
            self.main_layout.setContentsMargins(0, 0, 0, 0)
            self.main_layout.setSpacing(0)

            self.timeline.hide()
            self.controls_widget_hide()

            self.showFullScreen()
            self.is_fullscreen = True

    def controls_widget_hide(self):
        self.open_button.hide()
        self.play_button.hide()
        self.stop_button.hide()
        self.loop_button.hide()

    def controls_widget_show(self):
        self.open_button.show()
        self.play_button.show()
        self.stop_button.show()
        self.loop_button.show()

    # ================================================================
    # Клавиши и двойной щелчок
    # ================================================================

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())

            if child is self.video_frame or (
                child is not None and self.video_frame.isAncestorOf(child)
            ):
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

    # ================================================================
    # Окончание видео
    # ================================================================

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

    # ================================================================
    # Завершение программы
    # ================================================================

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
