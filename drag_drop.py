"""Модуль для обработки drag and drop функциональности."""

import os
import sys
import tkinter as tk
from typing import Callable, List, Optional

# Попытка импортировать tkinterdnd2
HAS_TKINTERDND2 = False
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKINTERDND2 = True
except ImportError:
    HAS_TKINTERDND2 = False


def setup_drag_drop(root: tk.Tk, on_drop_callback: Callable[[List[str]], None]) -> None:
    """Настройка drag and drop для главного окна.
    
    Args:
        root: Корневое окно Tkinter
        on_drop_callback: Функция обратного вызова при сбросе файлов
    """
    if HAS_TKINTERDND2:
        try:
            root.drop_target_register(DND_FILES)
            root.dnd_bind('<<Drop>>', lambda e: _on_drop_files(e, on_drop_callback))
        except Exception:
            pass


def setup_window_drag_drop(window: tk.Toplevel, on_drop_callback: Callable[[List[str]], None]) -> None:
    """Настройка drag and drop для дочернего окна.
    
    Args:
        window: Дочернее окно Tkinter
        on_drop_callback: Функция обратного вызова при сбросе файлов
    """
    if HAS_TKINTERDND2:
        try:
            window.drop_target_register(DND_FILES)
            window.dnd_bind('<<Drop>>', lambda e: _on_drop_files(e, on_drop_callback))
        except Exception:
            pass


def _on_drop_files(event: tk.Event, callback: Callable[[List[str]], None]) -> None:
    """Обработчик события сброса файлов.
    
    Args:
        event: Событие drag and drop
        callback: Функция обратного вызова
    """
    if not HAS_TKINTERDND2:
        return
    
    try:
        # Получаем список файлов из события
        files_str = event.data
        if not files_str:
            return
        
        # Обрабатываем строку с путями (формат зависит от платформы)
        files = []
        if sys.platform == 'win32':
            # Windows: пути разделены пробелами, но могут быть в фигурных скобках
            files_str = files_str.strip('{}')
            files = [f.strip() for f in files_str.split('} {')]
        else:
            # Linux/Mac: пути разделены пробелами
            files = files_str.split()
        
        # Фильтруем только существующие файлы
        valid_files = [f for f in files if os.path.exists(f) and os.path.isfile(f)]
        
        if valid_files:
            callback(valid_files)
    except Exception as e:
        print(f"Ошибка при обработке drag and drop: {e}")


def setup_treeview_drag_drop(tree: tk.ttk.Treeview, 
                             on_move_callback: Callable[[int, int], None]) -> None:
    """Настройка drag and drop для перестановки элементов в Treeview.
    
    Args:
        tree: Treeview виджет
        on_move_callback: Функция обратного вызова при перемещении (start_idx, target_idx)
    """
    drag_item = None
    drag_start_index = None
    drag_start_y = None
    is_dragging = False
    
    def on_button_press(event):
        nonlocal drag_item, drag_start_index, drag_start_y, is_dragging
        item = tree.identify_row(event.y)
        if item:
            drag_item = item
            drag_start_index = tree.index(item)
            drag_start_y = event.y
            is_dragging = False
    
    def on_drag_motion(event):
        nonlocal is_dragging
        if drag_item and drag_start_y is not None:
            if abs(event.y - drag_start_y) > 5:
                is_dragging = True
    
    def on_drag_release(event):
        nonlocal drag_item, drag_start_index, drag_start_y, is_dragging
        if drag_item and is_dragging:
            target_item = tree.identify_row(event.y)
            if target_item and target_item != drag_item:
                try:
                    start_idx = tree.index(drag_item)
                    target_idx = tree.index(target_item)
                    if 0 <= start_idx and 0 <= target_idx:
                        on_move_callback(start_idx, target_idx)
                except Exception:
                    pass
        
        # Сброс состояния
        drag_item = None
        drag_start_index = None
        drag_start_y = None
        is_dragging = False
    
    tree.bind('<Button-1>', on_button_press)
    tree.bind('<B1-Motion>', on_drag_motion)
    tree.bind('<ButtonRelease-1>', on_drag_release)

