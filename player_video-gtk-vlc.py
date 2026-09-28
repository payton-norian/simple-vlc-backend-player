#!/usr/bin/env python3
import sys
import vlc
import gi
import ctypes
import urllib.parse

# Инициализируем многопоточность X11 ДО импорта и инициализации GTK
try:
    x11 = ctypes.cdll.LoadLibrary('libX11.so.6')
    x11.XInitThreads()
except OSError:
    print("Предупреждение: Не удалось загрузить libX11.so.6 для XInitThreads")

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib

class VideoPlayer(Gtk.Window):
    def __init__(self):
        super().__init__(title="Видеоплеер")
        self.set_default_size(850, 560)  # Увеличили высоту для таймлайна
        self.set_border_width(0)

        self.current_file = None
        self.is_fullscreen = False
        self.is_slider_pressed = False  # Флаг: держит ли пользователь ползунок
        self.timer_id = None            # ID таймера обновления таймлайна

        # Светлая минималистичная тема через CSS
        css = (
            "button {"
            "color: #2c3e50;"
            "border: 1px solid #dcdde1;"
            "border-radius: 4px;"
            "padding: 6px 15px;"
            "min-width: 80px;"
            "font-family: Ubuntu, sans-serif;"
            "font-size: 16px;"
            "}"
            "button:hover {"
            "background-color: #f1f2f6;"
            "border-color: #b2bec3;"
            "}"
            "button:active {"
            "background-color: #dcdde1;"
            "}"
            "button:checked {"
            "background-color: #007acc;"
            "color: #ffffff;"
            "border-color: #005999;"
            "}"
            ".video-area {"
            "background-color: #000000;"
            "}"
            "scale trough {"
            "background-color: #ffffff;"
            "border: 1px solid #dcdde1;"
            "border-radius: 3px;"
            "min-height: 6px;"
            "}"
            "scale highlight {"
            "background-color: #007acc;"
            "border-radius: 3px;"
            "}"
            "scale slider {"
            "background-color: #ffffff;"
            "border: 1px solid #b2bec3;"
            "min-width: 14px;"
            "min-height: 14px;"
            "border-radius: 50%;"
            "}"
            "scale slider:hover {"
            "background-color: #f1f2f6;"
            "border-color: #007acc;"
            "}"
        ).encode("utf-8")

        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # VLC: Настраиваем принудительный вывод
        vlc_args = [
            "--avcodec-hw=vaapi",
            "--vout=xcb_window",
            "--quiet"
        ]
        self.vlc_instance = vlc.Instance(vlc_args)
        self.player = self.vlc_instance.media_player_new()

        # Событие окончания видео
        event_manager = self.player.event_manager()
        event_manager.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_video_ended)

        # Видео-область
        self.video_area = Gtk.DrawingArea()
        self.video_area.get_style_context().add_class("video-area")
        self.video_area.set_hexpand(True)
        self.video_area.set_vexpand(True)
        self.video_area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.video_area.connect("button-press-event", self.on_video_button_press)
        self.video_area.connect("realize", self.on_video_realize)

        # ---- СОЗДАНИЕ ТАЙМЛАЙНА ----
        # Инициализируем ползунок от 0 до 1000 с шагом 1
        self.timeline = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.timeline.set_draw_value(False)  # Скрываем стандартные цифры процентов над ползунком
        self.timeline.set_can_focus(False)
        
        # Сигналы для отслеживания перемотки мышкой
        self.timeline.connect("button-press-event", self.on_slider_pressed)
        self.timeline.connect("button-release-event", self.on_slider_released)
        self.timeline.connect("value-changed", self.on_slider_moved)
        # ----------------------------

        # Кнопки
        self.open_button = Gtk.Button(label="Открыть")
        self.play_button = Gtk.Button(label="Воспроизвести")
        self.stop_button = Gtk.Button(label="Стоп")
        self.loop_button = Gtk.ToggleButton(label="Повтор")

        for btn in (self.open_button, self.play_button, self.stop_button, self.loop_button):
            btn.set_can_focus(False)

        self.open_button.connect("clicked", self.open_file)
        self.play_button.connect("clicked", self.play_pause)
        self.stop_button.connect("clicked", self.stop)

        # Панель управления
        self.controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.controls.set_margin_start(10)
        self.controls.set_margin_end(10)
        self.controls.set_margin_bottom(10)
        self.controls.pack_start(self.open_button, False, False, 0)
        self.controls.pack_start(self.play_button, False, False, 0)
        self.controls.pack_start(self.stop_button, False, False, 0)
        self.controls.pack_start(Gtk.Box(), True, True, 0)
        self.controls.pack_start(self.loop_button, False, False, 0)

        # Главный layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        
        # Укладываем элементы по порядку сверху вниз
        self.main_box.pack_start(self.video_area, True, True, 0)
        self.main_box.pack_start(self.timeline, False, False, 0)  # Таймлайн между видео и кнопками
        self.main_box.pack_start(self.controls, False, False, 0)

        self.add(self.main_box)

        # ---- НАСТРОЙКА DRAG AND DROP ----
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self.on_drag_data_received)
        # ----------------------------------

        # Клавиши
        self.connect("key-press-event", self.on_key_press)
        self.connect("destroy", self.on_destroy)
        self.connect("window-state-event", self.on_window_state)

    # ---- ЛОГИКА ТАЙМЛАЙНА ----
    def start_timer(self):

        if self.timer_id is None:
            self.timer_id = GLib.timeout_add(200, self.update_timeline)

    def stop_timer(self):

        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def update_timeline(self):

        if self.player.is_playing() and not self.is_slider_pressed:
            vlc_pos = self.player.get_position()
            if vlc_pos >= 0:
                # Временно блокируем сигнал value-changed, чтобы избежать зацикливания при автообновлении
                self.timeline.handler_block_by_func(self.on_slider_moved)
                self.timeline.set_value(int(vlc_pos * 1000))
                self.timeline.handler_unblock_by_func(self.on_slider_moved)
        return True  # Возврат True указывает GLib продолжать работу таймера

    def on_slider_pressed(self, widget, event):
        self.is_slider_pressed = True
        return False

    def on_slider_released(self, widget, event):
        self.is_slider_pressed = False
        # Делаем финальную точную перемотку при отпускании
        vlc_pos = self.timeline.get_value() / 1000.0
        self.player.set_position(vlc_pos)
        return False

    def on_slider_moved(self, widget):

        if self.current_file and self.is_slider_pressed:
            vlc_pos = self.timeline.get_value() / 1000.0
            self.player.set_position(vlc_pos)

    # ---- ОБРАБОТКА DRAG AND DROP ----
    def on_drag_data_received(self, widget, context, x, y, selection_data, info, time):
        uris = selection_data.get_uris()
        if uris:
            first_uri = uris[0]
            if first_uri.startswith("file://"):
                filename = urllib.parse.unquote(first_uri[7:])
                self.load_and_play(filename)
        context.finish(True, False, time)

    # ---- УПРАВЛЕНИЕ ПЛЕЕРОМ ----
    def load_and_play(self, filename):

        self.current_file = filename
        media = self.vlc_instance.media_new(filename)
        self.player.set_media(media)
        self.player.play()
        self.play_button.set_label("Пауза")
        self.start_timer()

    def open_file(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Выберите видеофайл", parent=self, action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        filter_video = Gtk.FileFilter()
        filter_video.set_name("Видео")
        for ext in ("*.mpg", "*.mpeg", "*.m1v", "*.m2v", "*.vob", "*.mp4", "*.avi", "*.mkv", "*.webm", "*.mov"):
            filter_video.add_pattern(ext)
        dialog.add_filter(filter_video)
        
        if dialog.run() == Gtk.ResponseType.OK:
            self.load_and_play(dialog.get_filename())
        dialog.destroy()

    def play_pause(self, button):
        if not self.current_file:
            return
        if self.player.is_playing():
            self.player.pause()
            self.stop_timer()
            self.play_button.set_label("Продолжить")
        else:
            self.player.play()
            self.start_timer()
            self.play_button.set_label("Пауза")

    def stop(self, button):
        self.player.stop()
        self.stop_timer()
        self.timeline.set_value(0)
        self.play_button.set_label("Воспроизвести")
        if self.is_fullscreen:
            self.toggle_fullscreen()

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.unfullscreen()
            self.timeline.show()  # Возвращаем таймлайн
            self.controls.show()
            self.main_box.set_margin_top(10)
            self.main_box.set_margin_start(10)
            self.main_box.set_margin_end(10)
        else:
            self.controls.hide()
            self.timeline.hide()  # Скрываем таймлайн в полноэкранном режиме
            self.main_box.set_margin_top(0)
            self.main_box.set_margin_start(0)
            self.main_box.set_margin_end(0)
            self.fullscreen()

    def on_video_realize(self, widget):
        xid = widget.get_window().get_xid()
        self.player.set_xwindow(xid)

    def on_video_button_press(self, widget, event):
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_fullscreen()
            return True
        return False

    def on_window_state(self, widget, event):
        self.is_fullscreen = bool(event.new_window_state & Gdk.WindowState.FULLSCREEN)
        return False

    def on_key_press(self, widget, event):
        keyval = event.keyval
        if keyval == Gdk.KEY_space:
            self.play_pause(None)
            return True
        elif keyval == Gdk.KEY_Escape and self.is_fullscreen:
            self.toggle_fullscreen()
            return True
        return False

    def on_video_ended(self, event):
        if self.loop_button.get_active():
            GLib.idle_add(self.restart_video)
        else:
            GLib.idle_add(self.stop, None)

    def restart_video(self):
        self.player.stop()
        self.player.play()
        self.start_timer()
        return False

    def on_destroy(self, widget):
        self.stop_timer()
        self.player.stop()
        Gtk.main_quit()


if __name__ == "__main__":
    win = VideoPlayer()
    win.show_all()
    Gtk.main()

