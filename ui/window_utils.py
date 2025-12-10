"""Утилиты для работы с окнами Tkinter.

Этот модуль содержит вспомогательные функции для работы с окнами,
включая установку иконок, привязку прокрутки мыши и обработку изменения размеров.
"""

import os
import sys
import tkinter as tk
from typing import Optional, Tuple

# Попытка импортировать PIL для работы с иконками
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Попытка импортировать ctypes для Windows API (для установки иконки в панели задач)
if sys.platform == 'win32':
    try:
        import ctypes
        from ctypes import wintypes
        HAS_CTYPES = True
    except ImportError:
        HAS_CTYPES = False
else:
    HAS_CTYPES = False

# Константы для прокрутки мыши
MOUSEWHEEL_DELTA_DIVISOR = 120  # Делитель для нормализации прокрутки в Windows
LINUX_SCROLL_UP = 4  # Код прокрутки вверх для Linux
LINUX_SCROLL_DOWN = 5  # Код прокрутки вниз для Linux


def load_image_icon(
    icon_name: str,
    size: Optional[Tuple[int, int]] = None,
    icons_list: Optional[list] = None
) -> Optional[tk.PhotoImage]:
    """Загрузка иконки из папки materials/icon.
    
    Универсальная функция для загрузки изображений иконок с автоматическим
    определением формата (PNG, ICO) и опциональным изменением размера.
    
    Args:
        icon_name: Имя файла иконки (например, "Логотип.png" или "ВКонтакте.png")
        size: Кортеж (width, height) для изменения размера. Если None, размер не изменяется.
        icons_list: Список для сохранения ссылки на изображение (предотвращает удаление GC).
    
    Returns:
        PhotoImage объект или None если загрузка не удалась.
    """
    if not HAS_PIL:
        return None
    
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Пробуем разные варианты путей
        possible_paths = [
            os.path.join(base_dir, "materials", "icon", icon_name),
            os.path.join(base_dir, "materials", "icon", icon_name.replace('.png', '.ico')),
            os.path.join(base_dir, "materials", "icon", icon_name.replace('.ico', '.png')),
        ]
        
        image_path = None
        for path in possible_paths:
            if os.path.exists(path):
                image_path = path
                break
        
        if not image_path:
            return None
        
        img = Image.open(image_path)
        
        # Изменяем размер если указан
        if size:
            img = img.resize(size, Image.Resampling.LANCZOS)
        
        photo = ImageTk.PhotoImage(img)
        
        # Сохраняем ссылку если передан список
        if icons_list is not None:
            icons_list.append(photo)
        
        return photo
    except Exception:
        return None


def set_window_icon(window: tk.Tk, icon_photos_list: Optional[list] = None) -> None:
    """Установка иконки приложения для окна и панели задач.
    
    Пытается загрузить иконку из файлов Логотип.ico или Логотип.png.
    Использует iconbitmap для Windows (лучше всего для панели задач) и
    iconphoto для кроссплатформенной поддержки.
    Также использует Windows API для более надежной установки иконки в панели задач.
    
    Args:
        window: Окно Tkinter для установки иконки
        icon_photos_list: Список для хранения ссылок на изображения (опционально).
                         Необходим для предотвращения удаления изображений сборщиком мусора.
    """
    try:
        base_dir = os.path.dirname(os.path.dirname(__file__))
        
        # Сначала пробуем использовать .ico файл для Windows (лучше всего для панели задач)
        ico_path = os.path.join(base_dir, "materials", "icon", "Логотип.ico")
        ico_path = os.path.normpath(ico_path)
        
        if os.path.exists(ico_path):
            try:
                # Преобразуем в абсолютный путь для надежности
                ico_path = os.path.abspath(ico_path)
                
                # Используем Windows API для установки иконки в панели задач (более надежно)
                if sys.platform == 'win32' and HAS_CTYPES:
                    try:
                        # Получаем HWND окна
                        window.update_idletasks()
                        # Получаем дескриптор окна через winfo_id
                        try:
                            hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
                            if hwnd == 0:
                                # Если GetParent вернул 0, пробуем другой способ
                                hwnd = ctypes.windll.user32.FindWindowW(None, window.title())
                        except Exception:
                            # Если не удалось получить HWND, пропускаем Windows API
                            hwnd = None
                        
                        if hwnd:
                            # Загружаем иконку через LoadImage
                            # IMAGE_ICON = 1, LR_LOADFROMFILE = 0x0010, LR_DEFAULTSIZE = 0x0040
                            hicon_small = ctypes.windll.user32.LoadImageW(
                                0, ico_path, 1, 0, 0, 0x0010 | 0x0040
                            )
                            hicon_big = ctypes.windll.user32.LoadImageW(
                                0, ico_path, 1, 0, 0, 0x0010 | 0x0040
                            )
                            
                            if hicon_small:
                                # WM_SETICON = 0x0080, ICON_SMALL = 0, ICON_BIG = 1
                                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon_small)
                            if hicon_big:
                                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon_big)
                    except Exception as api_error:
                        # Если Windows API не сработал, используем стандартный метод
                        pass
                
                # iconbitmap устанавливает иконку для окна и панели задач в Windows
                window.iconbitmap(ico_path)
                
                # Также устанавливаем как иконку по умолчанию для всех окон
                if HAS_PIL:
                    try:
                        img = Image.open(ico_path)
                        photo = ImageTk.PhotoImage(img)
                        window.iconphoto(True, photo)  # True = установить как иконку по умолчанию
                        if icon_photos_list is not None:
                            icon_photos_list.append(photo)
                    except Exception:
                        pass
                
                # Принудительно обновляем окно для применения иконки
                window.update_idletasks()
                return
            except Exception as e:
                print(f"Не удалось установить иконку через iconbitmap: {e}")
        
        # Если .ico не найден, используем PNG иконку
        icon_path = os.path.join(base_dir, "materials", "icon", "Логотип.png")
        icon_path = os.path.normpath(icon_path)
        
        if os.path.exists(icon_path):
            if HAS_PIL:
                try:
                    img = Image.open(icon_path)
                    # Для панели задач лучше использовать иконку по умолчанию (True)
                    photo = ImageTk.PhotoImage(img)
                    window.iconphoto(True, photo)  # True = установить как иконку по умолчанию для всех окон
                    if icon_photos_list is not None:
                        icon_photos_list.append(photo)
                    # Принудительно обновляем окно для применения иконки
                    window.update_idletasks()
                except Exception as e:
                    print(f"Не удалось установить PNG иконку через PIL: {e}")
            else:
                try:
                    photo = tk.PhotoImage(file=icon_path)
                    window.iconphoto(True, photo)  # True = установить как иконку по умолчанию
                    if icon_photos_list is not None:
                        icon_photos_list.append(photo)
                    # Принудительно обновляем окно для применения иконки
                    window.update_idletasks()
                except Exception as e:
                    print(f"Не удалось установить PNG иконку: {e}")
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


