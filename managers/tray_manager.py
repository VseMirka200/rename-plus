"""Модуль для управления системным треем."""

import logging
import os
import threading
import tkinter as tk
from typing import Callable, Optional, TYPE_CHECKING

# Попытка импортировать pystray
HAS_PYSTRAY = False
if TYPE_CHECKING:
    import pystray
    from pystray import MenuItem

try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image as PILImage
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    # Создаем заглушки для type hints, если pystray не установлен
    class pystray:
        class Icon:
            pass
        class MenuItem:
            pass


class TrayManager:
    """Класс для управления системным треем."""
    
    def __init__(self, root: tk.Tk, 
                 show_callback: Callable[[], None],
                 quit_callback: Callable[[], None]):
        """Инициализация менеджера трея.
        
        Args:
            root: Корневое окно Tkinter
            show_callback: Функция для показа окна
            quit_callback: Функция для выхода из приложения
        """
        self.root = root
        self.show_callback = show_callback
        self.quit_callback = quit_callback
        self.tray_icon = None
        self.tray_thread = None
    
    def setup(self) -> None:
        """Настройка трей-иконки."""
        if not HAS_PYSTRAY:
            return
        
        try:
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "materials", "icon", "icon.ico")
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "materials", "icon", "1000x1000.png")
            
            if os.path.exists(icon_path):
                img = PILImage.open(icon_path)
                img = img.resize((64, 64), PILImage.Resampling.LANCZOS)
                
                menu = pystray.Menu(
                    item('Показать', self.show_window),
                    item('Выход', self.quit_app)
                )
                
                self.tray_icon = pystray.Icon("Ренейм+", img, "Ренейм+", menu)
                
                # Запускаем трей в отдельном потоке
                self.tray_thread = threading.Thread(target=self._run_tray, daemon=True)
                self.tray_thread.start()
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Не удалось настроить трей-иконку: {e}", exc_info=True)
    
    def _run_tray(self) -> None:
        """Запуск трей-иконки."""
        if self.tray_icon:
            self.tray_icon.run()
    
    def show_window(self, icon: Optional[pystray.Icon] = None, item: Optional[pystray.MenuItem] = None) -> None:
        """Показать главное окно."""
        self.show_callback()
    
    def quit_app(self, icon: Optional[pystray.Icon] = None, item: Optional[pystray.MenuItem] = None) -> None:
        """Выход из приложения."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.quit_callback()
    
    def stop(self) -> None:
        """Остановка трей-иконки."""
        if self.tray_icon:
            self.tray_icon.stop()


