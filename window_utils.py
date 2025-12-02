"""Утилиты для работы с окнами Tkinter."""

import os
import tkinter as tk
from typing import Optional

# Попытка импортировать PIL для работы с иконками
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Константы для прокрутки мыши
MOUSEWHEEL_DELTA_DIVISOR = 120
LINUX_SCROLL_UP = 4
LINUX_SCROLL_DOWN = 5


def set_window_icon(window: tk.Tk, icon_photos_list: Optional[list] = None) -> None:
    """Установка иконки приложения для окна.
    
    Args:
        window: Окно Tkinter для установки иконки
        icon_photos_list: Список для хранения ссылок на изображения (опционально)
    """
    try:
        # Сначала пробуем использовать .ico файл для Windows
        ico_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "icon.ico")
        if os.path.exists(ico_path):
            try:
                window.iconbitmap(ico_path)
                return
            except Exception:
                pass
        
        # Путь к PNG иконке
        icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "1000x1000.png")
        
        if os.path.exists(icon_path):
            if HAS_PIL:
                img = Image.open(icon_path)
                photo = ImageTk.PhotoImage(img)
                window.iconphoto(False, photo)
                if icon_photos_list is not None:
                    icon_photos_list.append(photo)
            else:
                try:
                    photo = tk.PhotoImage(file=icon_path)
                    window.iconphoto(False, photo)
                    if icon_photos_list is not None:
                        icon_photos_list.append(photo)
                except Exception:
                    pass
    except Exception as e:
        print(f"Не удалось установить иконку: {e}")


def bind_mousewheel(widget: tk.Widget, canvas: Optional[tk.Canvas] = None) -> None:
    """Привязка прокрутки колесом мыши к виджету.
    
    Args:
        widget: Виджет для привязки прокрутки
        canvas: Опциональный Canvas для прокрутки
    """
    def on_mousewheel(event):
        """Обработчик прокрутки для Windows и macOS."""
        scroll_amount = int(-1 * (event.delta / MOUSEWHEEL_DELTA_DIVISOR))
        target = canvas if canvas else widget
        if hasattr(target, 'yview_scroll'):
            target.yview_scroll(scroll_amount, "units")
    
    def on_mousewheel_linux(event):
        """Обработчик прокрутки для Linux."""
        target = canvas if canvas else widget
        if hasattr(target, 'yview_scroll'):
            if event.num == LINUX_SCROLL_UP:
                target.yview_scroll(-1, "units")
            elif event.num == LINUX_SCROLL_DOWN:
                target.yview_scroll(1, "units")
    
    # Windows и macOS
    widget.bind("<MouseWheel>", on_mousewheel)
    # Linux
    widget.bind("<Button-4>", on_mousewheel_linux)
    widget.bind("<Button-5>", on_mousewheel_linux)
    
    # Привязка к дочерним виджетам
    def bind_to_children(parent):
        """Рекурсивная привязка прокрутки к дочерним виджетам."""
        for child in parent.winfo_children():
            try:
                child.bind("<MouseWheel>", on_mousewheel)
                child.bind("<Button-4>", on_mousewheel_linux)
                child.bind("<Button-5>", on_mousewheel_linux)
                bind_to_children(child)
            except (AttributeError, tk.TclError):
                pass
    
    bind_to_children(widget)


def setup_window_resize_handler(window: tk.Toplevel, canvas: Optional[tk.Canvas] = None, 
                                canvas_window: Optional[int] = None) -> None:
    """Настройка обработчика изменения размера для окна с canvas.
    
    Args:
        window: Окно для обработки изменения размера
        canvas: Canvas виджет (опционально)
        canvas_window: ID окна canvas (опционально)
    """
    def on_resize(event):
        if canvas and canvas_window is not None:
            try:
                canvas_width = window.winfo_width() - 20
                canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
            except (AttributeError, tk.TclError):
                pass
    
    window.bind('<Configure>', on_resize)


