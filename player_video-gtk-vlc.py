#!/usr/bin/env python3
import sys
import vlc
import gi
import ctypes  # Добавлено для инициализации X11 потоков

# ВАЖНО: Инициализируем многопоточность X11 ДО импорта и инициализации GTK
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
        self.set_default_size(850, 520)
        self.set_border_width(0)

        self.current_file = None
        self.is_fullscreen = False

        # Светлая минималистичная тема через CSS
        css = b"""
            window { background-color: #f5f5f5; }
            button {
                background-color: #ffffff;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 6px 15px;
                min-width: 80px;
                color: #2c3e50;
                font-family: "Ubuntu", sans-serif;
                font-size: 16px;
            }
            button:hover { background-color: #f1f2f6; border-color: #b2bec3; }
            button:active { background-color: #dcdde1; }
            button:checked { background-color: #007acc; color: #ffffff; border-color: #005999; }
            .video-area { background-color: #000000; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # VLC: Настраиваем принудительный вывод через VA-API без некорректных флагов
        vlc_args = [
            "--avcodec-hw=vaapi",       # Форсируем использование VA-API
            "--vout=xcb_window",        # Оптимальный вывод видео для GTK на X11
            "--quiet"                   # Отключаем лишний спам логов в консоль
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
        self.controls.set_margin_top(0)
        self.controls.set_margin_bottom(10)
        self.controls.pack_start(self.open_button, False, False, 0)
        self.controls.pack_start(self.play_button, False, False, 0)
        self.controls.pack_start(self.stop_button, False, False, 0)
        self.controls.pack_start(Gtk.Box(), True, True, 0)  # stretch
        self.controls.pack_start(self.loop_button, False, False, 0)

        # Главный layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.main_box.set_margin_top(10)
        self.main_box.set_margin_start(10)
        self.main_box.set_margin_end(10)
        self.main_box.pack_start(self.video_area, True, True, 0)
        self.main_box.pack_start(self.controls, False, False, 0)

        self.add(self.main_box)

        # Клавиши
        self.connect("key-press-event", self.on_key_press)
        self.connect("destroy", self.on_destroy)
        self.connect("window-state-event", self.on_window_state)

    def on_video_realize(self, widget):
        """Привязка VLC к DrawingArea (X11)."""
        xid = widget.get_window().get_xid()
        self.player.set_xwindow(xid)

    def on_video_button_press(self, widget, event):
        """Двойной клик → полноэкранный режим."""
        if event.type == Gdk.EventType._2BUTTON_PRESS:
            self.toggle_fullscreen()
            return True
        return False

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.unfullscreen()
            self.controls.show()
            self.main_box.set_margin_top(10)
            self.main_box.set_margin_start(10)
            self.main_box.set_margin_end(10)
            self.main_box.set_margin_bottom(0)
        else:
            self.controls.hide()
            self.main_box.set_margin_top(0)
            self.main_box.set_margin_start(0)
            self.main_box.set_margin_end(0)
            self.main_box.set_margin_bottom(0)
            self.fullscreen()

    def on_window_state(self, widget, event):
        """Отслеживаем реальное состояние полноэкранного режима."""
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
        """Вызывается из потока VLC — перекидываем в главный цикл GTK."""
        if self.loop_button.get_active():
            GLib.idle_add(self.restart_video)
        else:
            GLib.idle_add(self.stop, None)

    def restart_video(self):
        self.player.stop()
        self.player.play()
        return False  # убрать из idle

    def open_file(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Выберите видеофайл",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )

        filter_video = Gtk.FileFilter()
        filter_video.set_name("Видео")
        for ext in ("*.mpg", "*.mpeg", "*.m1v", "*.m2v", "*.vob",
                    "*.mp4", "*.avi", "*.mkv", "*.webm", "*.mov"):
            filter_video.add_pattern(ext)
        dialog.add_filter(filter_video)

        filter_all = Gtk.FileFilter()
        filter_all.set_name("Все файлы")
        filter_all.add_pattern("*")
        dialog.add_filter(filter_all)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self.current_file = filename
            media = self.vlc_instance.media_new(filename)
            self.player.set_media(media)
            self.player.play()
            self.play_button.set_label("Пауза")
        dialog.destroy()

    def play_pause(self, button):
        if not self.current_file:
            return
        if self.player.is_playing():
            self.player.pause()
            self.play_button.set_label("Продолжить")
        else:
            self.player.play()
            self.play_button.set_label("Пауза")

    def stop(self, button):
        self.player.stop()
        self.play_button.set_label("Воспроизвести")
        if self.is_fullscreen:
            self.toggle_fullscreen()

    def on_destroy(self, widget):
        self.player.stop()
        Gtk.main_quit()

if __name__ == "__main__":
    win = VideoPlayer()
    win.show_all()
    Gtk.main()

