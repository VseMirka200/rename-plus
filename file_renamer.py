"""Модуль для переименования файлов с графическим интерфейсом."""

import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog

# Настройка логирования
logger = logging.getLogger(__name__)

# Попытка импортировать PIL для закругленных углов
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Попытка импортировать tkinterdnd2 для лучшей поддержки drag and drop
HAS_TKINTERDND2 = False
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKINTERDND2 = True
except ImportError:
    HAS_TKINTERDND2 = False

# Попытка импортировать pystray для системного трея
HAS_PYSTRAY = False
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image as PILImage
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

from core.metadata import MetadataExtractor
from core.rename_methods import (
    AddRemoveMethod,
    CaseMethod,
    MetadataMethod,
    NewNameMethod,
    NumberingMethod,
    RegexMethod,
    RenameMethod,
    ReplaceMethod,
)
from ui.ui_components import UIComponents, StyleManager
from managers.library_manager import LibraryManager
from managers.settings_manager import SettingsManager, TemplatesManager
from ui.window_utils import set_window_icon, bind_mousewheel, setup_window_resize_handler
from core.file_operations import (
    add_file_to_list,
    validate_filename,
    check_conflicts,
    rename_files_thread
)
from ui.drag_drop import setup_drag_drop as setup_drag_drop_util, setup_treeview_drag_drop
from managers.tray_manager import TrayManager
from utils.logger import Logger
from core.methods_manager import MethodsManager


class FileRenamerApp:
    """Главный класс приложения для переименования файлов."""
    
    def __init__(self, root):
        """Инициализация приложения.
        
        Args:
            root: Корневое окно Tkinter
        """
        self.root = root
        self.root.title("Ренейм+")
        self.root.geometry("1000x600")
        self.root.minsize(1000, 600)  # Минимальный размер соответствует начальному размеру
        
        # Установка иконки приложения
        self._icon_photos = []
        set_window_icon(self.root, self._icon_photos)
        
        # Настройка адаптивности
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Настройка цветовой схемы и стилей
        self.style_manager = StyleManager()
        self.colors = self.style_manager.colors
        self.style = self.style_manager.style
        self.ui_components = UIComponents()
        
        # Настройка фона окна
        self.root.configure(bg=self.colors['bg_main'])
        
        # Привязка изменения размера окна для адаптивного масштабирования
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Данные приложения
        # Список файлов: {path, old_name, new_name, extension, status}
        self.files: List[Dict] = []
        self.undo_stack: List[List[Dict]] = []  # Стек для отмены
        # Методы переименования (используем methods_manager)
        
        # Окна для вкладок
        self.windows = {
            'actions': None,
            'tabs': None,  # Окно с вкладками для логов, настроек и т.д.
            'methods': None  # Окно методов переименования
        }
        self.tabs_window_notebook = None  # Notebook для вкладок
        
        # Инициализация логгера
        self.logger = Logger()
        
        # Инициализация модуля метаданных
        self.metadata_extractor = MetadataExtractor()
        
        # Инициализация менеджера методов
        self.methods_manager = MethodsManager(self.metadata_extractor)
        
        # Трей-иконка
        self.tray_manager = None
        self.minimize_to_tray = False  # По умолчанию закрывать приложение при закрытии окна
        
        # Менеджеры настроек и шаблонов
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings
        self.templates_manager = TemplatesManager()
        self.saved_templates = self.templates_manager.templates
        
        # Менеджер библиотек
        self.library_manager = LibraryManager(
            self.root, 
            log_callback=lambda msg: self.logger.log(msg)
        )
        
        # Создание интерфейса
        self.create_widgets()
        
        # Привязка горячих клавиш
        self.setup_hotkeys()
        
        # Настройка drag and drop для файлов из проводника
        self.setup_drag_drop()
        
        # Настройка перестановки файлов в таблице
        self.setup_treeview_drag_drop()
        
        # Инициализация трей-иконки
        self.setup_tray_icon()
        
        # Обработчик закрытия окна - сворачивание в трей
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        
        # Проверка и установка необходимых библиотек (после создания интерфейса)
        # Выполняем с задержкой, чтобы окно успело отобразиться
        self.root.after(100, self.library_manager.check_and_install)
    
    def bind_mousewheel(self, widget, canvas=None):
        """Привязка прокрутки колесом мыши к виджету."""
        bind_mousewheel(widget, canvas)
    
    def create_rounded_button(self, parent, text, command, bg_color, fg_color='white', 
                             font=('Robot', 10, 'bold'), padx=16, pady=10, 
                             active_bg=None, active_fg='white', width=None, expand=True):
        """Создание кнопки с закругленными углами через Canvas"""
        return self.ui_components.create_rounded_button(
            parent, text, command, bg_color, fg_color, font, padx, pady,
            active_bg, active_fg, width, expand
        )
    
    def on_window_resize(self, event=None):
        """Обработчик изменения размера окна для адаптивного масштабирования"""
        if event and event.widget == self.root:
            # Обновляем размеры колонок таблицы при изменении размера окна
            if hasattr(self, 'list_frame') and self.list_frame:
                try:
                    # Используем небольшую задержку для получения актуального размера
                    self.root.after(50, self.update_tree_columns)
                    # Также обновляем при следующем событии для более плавной работы
                    self.root.after(200, self.update_tree_columns)
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
    def load_settings(self):
        """Загрузка настроек из файла"""
        return self.settings_manager.load_settings()
    
    def save_settings(self, settings_dict):
        """Сохранение настроек в файл"""
        return self.settings_manager.save_settings(settings_dict)
    
    def load_templates(self):
        """Загрузка сохраненных шаблонов из файла"""
        return self.templates_manager.load_templates()
    
    def save_templates(self):
        """Сохранение шаблонов в файл"""
        return self.templates_manager.save_templates(self.saved_templates)
    
    def setup_window_resize_handler(self, window, canvas=None, canvas_window=None):
        """Настройка обработчика изменения размера для окна с canvas"""
        setup_window_resize_handler(window, canvas, canvas_window)
    
    def update_tree_columns(self):
        """Обновление размеров колонок таблицы в соответствии с размером окна"""
        if hasattr(self, 'list_frame') and hasattr(self, 'tree') and self.list_frame and self.tree:
            try:
                list_frame_width = self.list_frame.winfo_width()
                if list_frame_width > 100:  # Минимальная ширина для расчетов
                    # Вычитаем ширину скроллбара (примерно 20px) и отступы
                    available_width = max(list_frame_width - 30, 200)  # Минимальная ширина уменьшена
                    
                    # Убеждаемся, что минимальные ширины не слишком большие для маленьких окон
                    min_width_old = max(50, int(available_width * 0.15))
                    min_width_new = max(50, int(available_width * 0.15))
                    min_width_ext = max(35, int(available_width * 0.08))
                    min_width_path = max(60, int(available_width * 0.25))
                    min_width_status = max(40, int(available_width * 0.10))
                    
                    self.tree.column("old_name", width=int(available_width * 0.22), minwidth=min_width_old)
                    self.tree.column("new_name", width=int(available_width * 0.22), minwidth=min_width_new)
                    self.tree.column("extension", width=int(available_width * 0.10), minwidth=min_width_ext)
                    self.tree.column("path", width=int(available_width * 0.35), minwidth=min_width_path)
                    self.tree.column("status", width=int(available_width * 0.11), minwidth=min_width_status)
            except Exception as e:
                pass
    
    def update_scrollbar_visibility(self, widget, scrollbar, orientation='vertical'):
        """Автоматическое управление видимостью скроллбара.
        
        Args:
            widget: Виджет (Treeview, Listbox, Text, Canvas)
            scrollbar: Скроллбар для управления
            orientation: Ориентация ('vertical' или 'horizontal')
        """
        try:
            if isinstance(widget, ttk.Treeview):
                # Для Treeview проверяем количество элементов
                items = widget.get_children()
                if not items:
                    if orientation == 'vertical':
                        scrollbar.grid_remove()
                    else:
                        scrollbar.grid_remove()
                    return
                
                # Проверяем, нужен ли скроллбар
                widget.update_idletasks()
                if orientation == 'vertical':
                    widget_height = widget.winfo_height()
                    # Приблизительная высота одного элемента
                    item_height = 20
                    visible_items = max(1, widget_height // item_height) if widget_height > 0 else 1
                    needs_scroll = len(items) > visible_items
                else:
                    widget_width = widget.winfo_width()
                    # Для горизонтального скроллбара проверяем ширину контента
                    needs_scroll = False
                    for item in items:
                        for col in widget['columns']:
                            cell_width = widget.column(col, 'width')
                            if cell_width and widget_width > 0:
                                if cell_width > widget_width:
                                    needs_scroll = True
                                    break
                        if needs_scroll:
                            break
                
            elif isinstance(widget, tk.Listbox):
                # Для Listbox проверяем количество элементов
                count = widget.size()
                widget.update_idletasks()
                widget_height = widget.winfo_height()
                if widget_height > 0:
                    # Приблизительная высота одного элемента
                    item_height = widget.bbox(0)[3] - widget.bbox(0)[1] if count > 0 and widget.bbox(0) else 20
                    visible_items = max(1, widget_height // item_height) if item_height > 0 else 1
                    needs_scroll = count > visible_items
                else:
                    needs_scroll = count > 0
            
            elif isinstance(widget, tk.Text):
                # Для Text проверяем количество строк
                widget.update_idletasks()
                widget_height = widget.winfo_height()
                if widget_height > 0:
                    line_height = widget.dlineinfo('1.0')
                    if line_height:
                        line_height = line_height[3]
                        visible_lines = max(1, widget_height // line_height) if line_height > 0 else 1
                        total_lines = int(widget.index('end-1c').split('.')[0])
                        needs_scroll = total_lines > visible_lines
                    else:
                        needs_scroll = False
                else:
                    needs_scroll = False
            
            elif isinstance(widget, tk.Canvas):
                # Для Canvas проверяем размер контента
                widget.update_idletasks()
                bbox = widget.bbox("all")
                if bbox:
                    if orientation == 'vertical':
                        canvas_height = widget.winfo_height()
                        content_height = bbox[3] - bbox[1]
                        needs_scroll = content_height > canvas_height and canvas_height > 1
                    else:
                        canvas_width = widget.winfo_width()
                        content_width = bbox[2] - bbox[0]
                        needs_scroll = content_width > canvas_width and canvas_width > 1
                else:
                    needs_scroll = False
            else:
                return
            
            # Показываем или скрываем скроллбар
            if needs_scroll:
                if scrollbar.winfo_manager() == '':
                    # Скроллбар не размещен, размещаем его
                    if hasattr(scrollbar, '_grid_info'):
                        scrollbar.grid(**scrollbar._grid_info)
                    elif hasattr(scrollbar, '_pack_info'):
                        scrollbar.pack(**scrollbar._pack_info)
                else:
                    # Скроллбар уже размещен, просто показываем
                    try:
                        scrollbar.grid()
                    except tk.TclError:
                        try:
                            scrollbar.pack()
                        except tk.TclError as e:
                            logger.debug(f"Не удалось показать скроллбар: {e}")
            else:
                # Сохраняем информацию о размещении перед скрытием
                try:
                    grid_info = scrollbar.grid_info()
                    if grid_info:
                        scrollbar._grid_info = grid_info
                        scrollbar.grid_remove()
                except tk.TclError:
                    try:
                        pack_info = scrollbar.pack_info()
                        if pack_info:
                            scrollbar._pack_info = pack_info
                            scrollbar.pack_forget()
                    except tk.TclError as e:
                        logger.debug(f"Не удалось скрыть скроллбар: {e}")
        except (AttributeError, tk.TclError, ValueError):
            # Игнорируем ошибки при обновлении
            pass
    
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        
        # === ОСНОВНОЙ КОНТЕЙНЕР С ВКЛАДКАМИ ===
        # Создаем Notebook для вкладок
        main_notebook = ttk.Notebook(self.root)
        main_notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Обработчик изменения размера главного окна (только для активной вкладки)
        def on_root_resize(event=None):
            # Проверяем, какая вкладка активна
            if hasattr(self, 'main_notebook') and self.main_notebook:
                try:
                    selected_tab = self.main_notebook.index(self.main_notebook.select())
                    # Обновляем только если активна вкладка "Файлы" (индекс 0)
                    if selected_tab == 0:
                        if hasattr(self, 'update_tree_columns'):
                            self.root.after(100, self.update_tree_columns)
                        # Обновляем размер canvas в правой панели методов
                        if hasattr(self, 'settings_canvas') and self.settings_canvas:
                            try:
                                canvas_width = self.settings_canvas.winfo_width()
                                if canvas_width > 1 and hasattr(self, 'settings_canvas_window'):
                                    self.settings_canvas.itemconfig(self.settings_canvas_window, width=canvas_width)
                                # Обновляем видимость скроллбара при изменении размера окна
                                if hasattr(self, 'update_scroll_region'):
                                    self.root.after(150, self.update_scroll_region)
                            except (AttributeError, tk.TclError):
                                pass
                except (tk.TclError, AttributeError):
                    pass
        
        self.root.bind('<Configure>', on_root_resize)
        
        # Сохраняем ссылку на notebook
        self.main_notebook = main_notebook
        
        # === ВКЛАДКА 1: ОСНОВНОЕ СОДЕРЖИМОЕ (файлы и методы) ===
        main_tab = tk.Frame(main_notebook, bg=self.colors['bg_main'])
        main_notebook.add(main_tab, text="Файлы")
        main_tab.columnconfigure(0, weight=1)
        main_tab.rowconfigure(0, weight=1)
        
        # Используем обычный Frame для распределения пространства (50/50)
        main_container = tk.Frame(main_tab, bg=self.colors['bg_main'])
        main_container.grid(row=0, column=0, sticky="nsew")
        main_container.columnconfigure(0, weight=6, uniform="panels")  # Левая панель занимает 60%
        main_container.columnconfigure(1, weight=4, uniform="panels")  # Правая панель занимает 40%
        main_container.rowconfigure(0, weight=1)
        
        # Сохраняем ссылку на main_container для обновления размеров
        self.main_container = main_container
        
        # Принудительно обновляем конфигурацию колонок после создания
        def update_column_config():
            main_container.columnconfigure(0, weight=6, uniform="panels")
            main_container.columnconfigure(1, weight=4, uniform="panels")
            main_container.update_idletasks()
            # Дополнительное обновление после создания всех виджетов
            self.root.after(500, lambda: main_container.columnconfigure(0, weight=6, uniform="panels"))
            self.root.after(500, lambda: main_container.columnconfigure(1, weight=4, uniform="panels"))
        
        self.root.after(100, update_column_config)
        self.root.after(300, update_column_config)
        self.root.after(500, update_column_config)
        
        # Обработчик изменения размера для обновления колонок таблицы (только для этой вкладки)
        def on_resize(event=None):
            # Проверяем, что событие относится к этой вкладке и она активна
            if event and event.widget == main_container:
                # Проверяем, активна ли вкладка "Файлы"
                if hasattr(self, 'main_notebook') and self.main_notebook:
                    try:
                        selected_tab = self.main_notebook.index(self.main_notebook.select())
                        if selected_tab != 0:  # Если не активна вкладка "Файлы", не обновляем
                            return
                    except (tk.TclError, AttributeError):
                        pass
                
                # Принудительно обновляем веса колонок при изменении размера
                main_container.columnconfigure(0, weight=6, uniform="panels")
                main_container.columnconfigure(1, weight=4, uniform="panels")
                if hasattr(self, 'update_tree_columns'):
                    self.root.after(50, self.update_tree_columns)
                # Обновляем размер canvas в правой панели
                if hasattr(self, 'settings_canvas') and self.settings_canvas:
                    try:
                        canvas_width = self.settings_canvas.winfo_width()
                        if canvas_width > 1:
                            self.settings_canvas.itemconfig(self.settings_canvas_window, width=canvas_width)
                        # Обновляем видимость скроллбара при изменении размера
                        if hasattr(self, 'update_scroll_region'):
                            self.root.after(100, self.update_scroll_region)
                    except (AttributeError, tk.TclError):
                        pass
        
        main_container.bind('<Configure>', on_resize)  # При изменении размера
        main_tab.bind('<Configure>', lambda e: on_resize(e) if e.widget == main_tab else None)
        
        # Левая часть - список файлов
        left_panel = ttk.LabelFrame(main_container, text=f"Список файлов (Файлов: {len(self.files)})", 
                                    style='Card.TLabelframe', padding=6)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)  # Строка с таблицей файлов
        
        # Сохраняем ссылку на left_panel для обновления заголовка
        self.left_panel = left_panel
        
        
        # Панель управления файлами
        control_panel = tk.Frame(left_panel, bg=self.colors['bg_card'])
        control_panel.pack(fill=tk.X, pady=(0, 6))
        control_panel.columnconfigure(0, weight=1)
        control_panel.columnconfigure(1, weight=1)
        control_panel.columnconfigure(2, weight=1)
        
        # Кнопки управления - компактное расположение
        btn_add_files = self.create_rounded_button(
            control_panel, "Добавить файлы", self.add_files,
            self.colors['primary'], 'white', 
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_files.grid(row=0, column=0, padx=(0, 4), sticky="ew")
        
        btn_add_folder = self.create_rounded_button(
            control_panel, "Добавить папку", self.add_folder,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_folder.grid(row=0, column=1, padx=(0, 4), sticky="ew")
        
        btn_clear = self.create_rounded_button(
            control_panel, "Очистить", self.clear_files,
            self.colors['danger'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear.grid(row=0, column=2, padx=(0, 4), sticky="ew")
        
        # Таблица файлов
        list_frame = ttk.Frame(left_panel)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Создание таблицы с прокруткой
        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        
        columns = ("old_name", "new_name", "extension", "path", "status")
        self.tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            style='Custom.Treeview'
        )
        
        scrollbar_y.config(command=self.tree.yview)
        scrollbar_x.config(command=self.tree.xview)
        
        # Настройка колонок
        self.tree.heading("old_name", text="Исходное имя")
        self.tree.heading("new_name", text="Новое имя")
        self.tree.heading("extension", text="Расширение")
        self.tree.heading("path", text="Путь")
        self.tree.heading("status", text="Статус")
        
        # Настройка тегов для цветового выделения
        # Светло-зеленый для готовых
        self.tree.tag_configure('ready', background='#D1FAE5', foreground='#065F46')
        # Светло-красный для ошибок
        self.tree.tag_configure('error', background='#FEE2E2', foreground='#991B1B')
        # Светло-желтый для конфликтов
        self.tree.tag_configure('conflict', background='#FEF3C7', foreground='#92400E')
        
        # Настройка колонок с адаптивными размерами (процент от ширины)
        # Используем минимальные ширины, которые будут обновлены при изменении размера
        self.tree.column("old_name", width=120, anchor='w', minwidth=60)
        self.tree.column("new_name", width=120, anchor='w', minwidth=60)
        self.tree.column("extension", width=50, anchor='center', minwidth=40)
        self.tree.column("path", width=200, anchor='w', minwidth=80)
        self.tree.column("status", width=60, anchor='center', minwidth=50)
        
        # Обновляем колонки после инициализации
        self.root.after(200, self.update_tree_columns)
        
        # Сохраняем ссылку на list_frame для обновления размеров
        self.list_frame = list_frame
        
        # Настройка тегов для цветового выделения
        self.tree.tag_configure('ready', background='#D1FAE5')  # Светло-зеленый для готовых
        self.tree.tag_configure('error', background='#FEE2E2')  # Светло-красный для ошибок
        self.tree.tag_configure('conflict', background='#FEF3C7')  # Светло-желтый для конфликтов
        
        # Размещение виджетов
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        # Сохраняем ссылки на скроллбары для автоматического управления
        self.tree_scrollbar_y = scrollbar_y
        self.tree_scrollbar_x = scrollbar_x
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Привязка прокрутки колесом мыши для таблицы
        self.bind_mousewheel(self.tree, self.tree)
        
        # Автоматическое управление видимостью скроллбаров для Treeview
        def update_tree_scrollbars(*args):
            self.update_scrollbar_visibility(self.tree, scrollbar_y, 'vertical')
            self.update_scrollbar_visibility(self.tree, scrollbar_x, 'horizontal')
        
        # Обработчики событий только для этой вкладки
        def on_tree_event(event=None):
            # Проверяем, активна ли вкладка "Файлы"
            if hasattr(self, 'main_notebook') and self.main_notebook:
                try:
                    selected_tab = self.main_notebook.index(self.main_notebook.select())
                    if selected_tab == 0:  # Только если активна вкладка "Файлы"
                        self.root.after_idle(update_tree_scrollbars)
                except (tk.TclError, AttributeError):
                    pass
        
        self.tree.bind('<<TreeviewSelect>>', on_tree_event)
        self.tree.bind('<Configure>', on_tree_event)
        
        # Привязка сортировки
        for col in ("old_name", "new_name", "extension", "path", "status"):
            self.tree.heading(col, command=lambda c=col: self.sort_column(c))
        
        # === ПРОГРЕСС БАР (под списком файлов слева) ===
        progress_container = tk.Frame(left_panel, bg=self.colors['bg_card'])
        progress_container.pack(fill=tk.X, pady=(0, 0))
        progress_container.columnconfigure(1, weight=1)
        
        progress_label = tk.Label(progress_container, text="Прогресс:", 
                                 font=('Robot', 8, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        progress_label.grid(row=0, column=0, padx=(0, 8), sticky="w")
        
        self.progress = ttk.Progressbar(progress_container, mode='determinate')
        self.progress.grid(row=0, column=1, sticky="ew")
        
        # === ПРАВАЯ ПАНЕЛЬ (только методы) ===
        # Правая панель занимает 70% пространства
        right_panel = ttk.LabelFrame(main_container, text="Методы переименования", 
                                     style='Card.TLabelframe', padding=6)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)
        
        # Внутренний Frame для содержимого с минимальными отступами
        methods_frame = tk.Frame(right_panel, bg=self.colors['bg_card'])
        methods_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        methods_frame.columnconfigure(0, weight=1)
        methods_frame.rowconfigure(1, weight=1)  # Строка с настройками метода
        
        # Сохраняем ссылку на панель
        self.right_panel = right_panel
        
        # Выбор метода
        method_label = tk.Label(methods_frame, text="Выберите метод:", 
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        method_label.pack(anchor=tk.W, pady=(0, 6))
        
        self.method_var = tk.StringVar()
        method_values = [
            "Новое имя", "Добавить/Удалить", "Замена", "Регистр",
            "Нумерация", "Метаданные", "Регулярные выражения"
        ]
        self.method_combo = ttk.Combobox(
            methods_frame,
            textvariable=self.method_var,
            values=method_values,
            state="readonly",
            font=('Robot', 9)
        )
        self.method_combo.pack(fill=tk.X, pady=(0, 8))
        self.method_combo.bind("<<ComboboxSelected>>", self.on_method_selected)
        self.method_combo.current(0)  # "Новое имя" по умолчанию
        
        # Область настроек метода с прокруткой
        settings_container = tk.Frame(methods_frame, bg=self.colors['bg_card'])
        settings_container.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        settings_container.columnconfigure(0, weight=1)
        settings_container.rowconfigure(0, weight=1)
        
        # Canvas для прокрутки настроек
        settings_canvas = tk.Canvas(settings_container, bg=self.colors['bg_card'], 
                                    highlightthickness=0)
        settings_scrollbar = ttk.Scrollbar(settings_container, orient="vertical", 
                                           command=settings_canvas.yview)
        scrollable_frame = tk.Frame(settings_canvas, bg=self.colors['bg_card'])
        
        # Флаг для предотвращения бесконечных циклов
        _updating_scroll = False
        
        def update_scroll_region():
            """Обновление области прокрутки и видимости скроллбара"""
            nonlocal _updating_scroll
            if _updating_scroll:
                return
            _updating_scroll = True
            try:
                bbox = settings_canvas.bbox("all")
                if bbox:
                    # Устанавливаем scrollregion точно по содержимому
                    settings_canvas.configure(scrollregion=bbox)
                    
                    # Используем универсальную функцию для управления скроллбаром
                    self.update_scrollbar_visibility(settings_canvas, settings_scrollbar, 'vertical')
                else:
                    settings_scrollbar.grid_remove()
            except (AttributeError, tk.TclError):
                pass
            finally:
                _updating_scroll = False
        
        def on_frame_configure(event):
            # Обновляем scrollregion и видимость скроллбара с задержкой
            self.root.after_idle(update_scroll_region)
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        
        settings_canvas_window = settings_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(event):
            if event.widget == settings_canvas:
                try:
                    canvas_width = event.width
                    if canvas_width > 1:
                        settings_canvas.itemconfig(settings_canvas_window, width=canvas_width)
                    # Обновляем видимость скроллбара при изменении размера canvas с задержкой
                    self.root.after_idle(update_scroll_region)
                except (AttributeError, tk.TclError):
                    pass
        
        settings_canvas.bind('<Configure>', on_canvas_configure)
        
        def on_scroll(*args):
            """Обработчик прокрутки"""
            settings_scrollbar.set(*args)
            # Не вызываем update_scroll_region здесь, чтобы избежать циклов
        
        settings_canvas.configure(yscrollcommand=on_scroll)
        
        # Сохраняем функцию обновления для использования извне
        self.update_scroll_region = update_scroll_region
        
        # Сохраняем ссылки для обновления размеров
        self.settings_canvas = settings_canvas
        self.settings_canvas_window = settings_canvas_window
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(settings_canvas, settings_canvas)
        self.bind_mousewheel(scrollable_frame, settings_canvas)
        
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.settings_frame = scrollable_frame
        
        # Объединенная группа кнопок
        method_buttons_frame = tk.Frame(methods_frame, bg=self.colors['bg_card'])
        method_buttons_frame.pack(fill=tk.X, pady=(0, 0))
        
        font = ('Robot', 9, 'bold')
        padx = 6  # Компактные отступы
        
        # Кнопки шаблонов (показываются только для метода "Новое имя")
        self.template_buttons_frame = tk.Frame(method_buttons_frame, bg=self.colors['bg_card'])
        self.template_buttons_frame.pack(fill=tk.X, pady=(0, 6))
        
        self.btn_quick = self.create_rounded_button(
            self.template_buttons_frame, "Быстрые шаблоны", self.show_quick_templates,
            self.colors['primary'], 'white',
            font=font, padx=padx, pady=6,
            active_bg=self.colors['primary_hover'], expand=True)
        self.btn_quick.pack(fill=tk.X, pady=(0, 4))
        
        self.btn_save_template = self.create_rounded_button(
            self.template_buttons_frame, "Сохранить шаблон", self.save_current_template,
            '#10B981', 'white',
            font=font, padx=padx, pady=6,
            active_bg='#059669', expand=True)
        self.btn_save_template.pack(fill=tk.X, pady=(0, 4))
        
        self.btn_saved = self.create_rounded_button(
            self.template_buttons_frame, "Сохраненные шаблоны", self.show_saved_templates,
            self.colors['primary'], 'white',
            font=font, padx=padx, pady=6,
            active_bg=self.colors['primary_hover'], expand=True)
        self.btn_saved.pack(fill=tk.X)
        
        # Кнопка "Начать переименование" внизу на всю ширину
        btn_start_rename = self.create_rounded_button(
            method_buttons_frame, "Начать переименование", self.start_rename,
            self.colors['success'], 'white',
            font=font, padx=6, pady=8,
            active_bg=self.colors['success_hover'], expand=True)
        btn_start_rename.pack(fill=tk.X, pady=(6, 0))
        
        # Скрытый listbox для внутреннего использования методов (для функции удаления)
        self.methods_listbox = tk.Listbox(methods_frame, height=0)
        self.methods_listbox.pack_forget()  # Скрываем его
        
        # Создаем log_text для логирования (будет использоваться в окне лога)
        self.logger.set_log_widget(None)
        
        # Инициализация первого метода (Новое имя)
        self.on_method_selected()
        
        
        
        # === СОЗДАНИЕ ВКЛАДОК НА ГЛАВНОМ ЭКРАНЕ ===
        # Создаем вкладки для логов, о программе и поддержки
        self._create_main_log_tab()
        self._create_main_about_tab()
        self._create_main_support_tab()
        
    
    def open_actions_window(self):
        """Открытие окна действий"""
        if self.windows['actions'] is not None and self.windows['actions'].winfo_exists():
            # Если окно свернуто, разворачиваем его
            try:
                if self.windows['actions'].state() == 'iconic':
                    self.windows['actions'].deiconify()
            except (AttributeError, tk.TclError):
                pass
            self.windows['actions'].lift()
            self.windows['actions'].focus_force()
            return
        
        window = tk.Toplevel(self.root)
        window.title("🚀 Действия")
        window.geometry("600x180")
        window.minsize(500, 150)
        window.configure(bg=self.colors['bg_card'])
        
        # Установка иконки
        try:
            set_window_icon(window, self._icon_photos)
        except Exception:
            pass
        
        # Настройка адаптивности окна
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        
        # Обработчик изменения размера окна
        def on_actions_window_resize(event):
            if event.widget == window:
                try:
                    # Обновляем размеры кнопок и прогресс-бара
                    window.update_idletasks()
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        window.bind('<Configure>', on_actions_window_resize)
        
        self.windows['actions'] = window
        
        # Основной контейнер для масштабирования
        main_frame = tk.Frame(window, bg=self.colors['bg_card'])
        main_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Кнопки действий
        buttons_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        buttons_frame.grid(row=0, column=0, sticky="ew")
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
        
        btn_start = self.create_rounded_button(
            buttons_frame, "Начать переименование", self.start_rename,
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['success_hover'])
        btn_start.grid(row=0, column=1, sticky="ew", padx=4)
        
        # Прогресс бар
        progress_container = tk.Frame(main_frame, bg=self.colors['bg_card'])
        progress_container.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        progress_container.columnconfigure(0, weight=1)
        
        progress_label = tk.Label(progress_container, text="Прогресс:", 
                                 font=('Robot', 9, 'bold'),
                            bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        progress_label.pack(anchor=tk.W, pady=(0, 6))
        
        self.progress_window = ttk.Progressbar(progress_container, mode='determinate')
        self.progress_window.pack(fill=tk.X)
        
        # Обработчик закрытия окна - делаем окно статичным (сворачиваем вместо закрытия)
        def on_close_actions_window():
            # Вместо закрытия сворачиваем окно
            try:
                if window.winfo_exists():
                    window.iconify()
            except (AttributeError, tk.TclError):
                pass
        
        window.protocol("WM_DELETE_WINDOW", on_close_actions_window)
    
    def open_methods_window(self):
        """Открытие окна методов переименования"""
        if self.windows['methods'] is not None and self.windows['methods'].winfo_exists():
            try:
                if self.windows['methods'].state() == 'iconic':
                    self.windows['methods'].deiconify()
            except (AttributeError, tk.TclError):
                pass
            self.windows['methods'].lift()
            self.windows['methods'].focus_force()
            if hasattr(self, 'methods_window_listbox'):
                self._update_methods_window_list()
            return
        
        window = tk.Toplevel(self.root)
        window.title("Методы переименования")
        window.geometry("500x650")
        window.minsize(450, 550)
        window.configure(bg=self.colors['bg_card'])
        try:
            set_window_icon(window, self._icon_photos)
        except Exception:
            pass
        
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        self.windows['methods'] = window
        
        # Основной контейнер
        main_frame = tk.Frame(window, bg=self.colors['bg_card'])
        main_frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Заголовок
        header_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        title_label = tk.Label(header_frame, text="Методы переименования", 
                              font=('Robot', 12, 'bold'),
                              bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        title_label.pack(anchor=tk.W)
        
        # Кнопки управления (вертикально, с названиями)
        header_buttons = tk.Frame(header_frame, bg=self.colors['bg_card'])
        header_buttons.pack(fill=tk.X, pady=(10, 0))
        header_buttons.columnconfigure(0, weight=1)
        
        btn_add = self.create_rounded_button(
            header_buttons, "Добавить", lambda: self._add_method_from_window(),
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=10,
            active_bg=self.colors['primary_hover'])
        btn_add.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        btn_remove = self.create_rounded_button(
            header_buttons, "Удалить", lambda: self._remove_method_from_window(),
            self.colors['primary_light'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=10,
            active_bg=self.colors['primary'])
        btn_remove.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        
        btn_clear = self.create_rounded_button(
            header_buttons, "Очистить", lambda: self._clear_methods_from_window(),
            self.colors['danger'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=10,
            active_bg=self.colors['danger_hover'])
        btn_clear.grid(row=2, column=0, sticky="ew")
        
        # Контент с двумя панелями
        content_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.columnconfigure(1, weight=2)
        content_frame.rowconfigure(0, weight=1)
        
        # Левая панель: список методов
        list_panel = ttk.LabelFrame(content_frame, text="Список", 
                                   style='Card.TLabelframe', padding=8)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_panel.columnconfigure(0, weight=1)
        list_panel.rowconfigure(0, weight=1)
        
        list_scroll = tk.Frame(list_panel, bg=self.colors['bg_card'])
        list_scroll.grid(row=0, column=0, sticky="nsew")
        list_scroll.columnconfigure(0, weight=1)
        list_scroll.rowconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(list_scroll)
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.methods_window_listbox = tk.Listbox(list_scroll, font=('Robot', 9),
                                                bg='white', fg=self.colors['text_primary'],
                                                selectbackground=self.colors['primary'],
                                                selectforeground='white',
                                                yscrollcommand=scrollbar.set)
        self.methods_window_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.config(command=self.methods_window_listbox.yview)
        self.methods_window_listbox.bind('<<ListboxSelect>>', 
                                       lambda e: self._on_method_selected_in_window())
        
        # Сохраняем ссылку на скроллбар
        self.methods_window_scrollbar = scrollbar
        
        # Автоматическое управление видимостью скроллбара для Listbox
        def update_methods_scrollbar(*args):
            self.update_scrollbar_visibility(self.methods_window_listbox, scrollbar, 'vertical')
        
        # Мгновенное обновление без задержки
        self.methods_window_listbox.bind('<Configure>', lambda e: update_methods_scrollbar())
        
        self._update_methods_window_list()
        
        # Обновляем скроллбар сразу после обновления списка
        update_methods_scrollbar()
        
        # Правая панель: настройки
        settings_panel = ttk.LabelFrame(content_frame, text="Настройки", 
                                       style='Card.TLabelframe', padding=8)
        settings_panel.grid(row=0, column=1, sticky="nsew")
        settings_panel.columnconfigure(0, weight=1)
        settings_panel.rowconfigure(1, weight=1)
        
        # Выбор типа метода
        self.methods_window_method_var = tk.StringVar()
        method_combo = ttk.Combobox(settings_panel,
                                   textvariable=self.methods_window_method_var,
                                   values=["Новое имя", "Добавить/Удалить", "Замена", 
                                          "Регистр", "Нумерация", "Метаданные", 
                                          "Регулярные выражения"],
                                   state="readonly", width=18, font=('Robot', 9))
        method_combo.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        method_combo.current(0)
        method_combo.bind("<<ComboboxSelected>>", 
                         lambda e: self._on_method_type_selected_in_window())
        
        # Область настроек
        settings_canvas = tk.Canvas(settings_panel, bg=self.colors['bg_card'], 
                                   highlightthickness=0)
        settings_scrollbar = ttk.Scrollbar(settings_panel, orient="vertical", 
                                          command=settings_canvas.yview)
        self.methods_window_settings_frame = tk.Frame(settings_canvas, 
                                                      bg=self.colors['bg_card'])
        
        self.methods_window_settings_frame.bind(
            "<Configure>",
            lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        
        canvas_win = settings_canvas.create_window((0, 0), 
                                                   window=self.methods_window_settings_frame, 
                                                   anchor="nw")
        
        def on_canvas_configure(event):
            if event.widget == settings_canvas:
                try:
                    settings_canvas.itemconfig(canvas_win, width=event.width)
                except (AttributeError, tk.TclError):
                    pass
        
        settings_canvas.bind('<Configure>', on_canvas_configure)
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)
        
        self.bind_mousewheel(settings_canvas, settings_canvas)
        self.bind_mousewheel(self.methods_window_settings_frame, settings_canvas)
        
        settings_canvas.grid(row=1, column=0, sticky="nsew")
        settings_scrollbar.grid(row=1, column=1, sticky="ns")
        
        # Автоматическое управление видимостью скроллбара для Canvas
        def update_methods_settings_scrollbar(*args):
            self.update_scrollbar_visibility(settings_canvas, settings_scrollbar, 'vertical')
        
        self.methods_window_settings_frame.bind('<Configure>', lambda e: window.after_idle(update_methods_settings_scrollbar))
        settings_canvas.bind('<Configure>', lambda e: window.after_idle(update_methods_settings_scrollbar))
        window.bind('<Configure>', lambda e: window.after_idle(update_methods_settings_scrollbar))
        
        self._on_method_type_selected_in_window()
        
        # Кнопка применения
        btn_apply = self.create_rounded_button(
            main_frame, "✅ Применить", lambda: self._apply_methods_from_window(),
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=12, pady=6,
            active_bg=self.colors['success_hover'])
        btn_apply.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        
        def on_close():
            try:
                if window.winfo_exists():
                    window.iconify()
            except (AttributeError, tk.TclError):
                pass
        
        window.protocol("WM_DELETE_WINDOW", on_close)
    
    def _update_methods_window_list(self):
        """Обновление списка методов"""
        if not hasattr(self, 'methods_window_listbox'):
            return
        self.methods_window_listbox.delete(0, tk.END)
        for i, method in enumerate(self.methods_manager.get_methods()):
            name = self._get_method_display_name(method)
            self.methods_window_listbox.insert(tk.END, f"{i+1}. {name}")
    
    def _get_method_display_name(self, method):
        """Получение имени метода для отображения"""
        return self.methods_manager.get_method_display_name(method)
    
    def _on_method_selected_in_window(self):
        """Обработка выбора метода из списка"""
        selection = self.methods_window_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        methods = self.methods_manager.get_methods()
        if 0 <= index < len(methods):
            method = methods[index]
            self._load_method_settings(method)
    
    def _load_method_settings(self, method):
        """Загрузка настроек метода"""
        method_map = {
            NewNameMethod: (0, "Новое имя"),
            AddRemoveMethod: (1, "Добавить/Удалить"),
            ReplaceMethod: (2, "Замена"),
            CaseMethod: (3, "Регистр"),
            NumberingMethod: (4, "Нумерация"),
            MetadataMethod: (5, "Метаданные"),
            RegexMethod: (6, "Регулярные выражения")
        }
        
        for cls, (idx, name) in method_map.items():
            if isinstance(method, cls):
                self.methods_window_method_var.set(name)
                break
        
        self._on_method_type_selected_in_window()
    
    def _on_method_type_selected_in_window(self, event=None):
        """Обработка выбора типа метода"""
        for widget in self.methods_window_settings_frame.winfo_children():
            widget.destroy()
        
        method_name = self.methods_window_method_var.get()
        method_creators = {
            "Новое имя": self._create_new_name_settings,
            "Добавить/Удалить": self._create_add_remove_settings,
            "Замена": self._create_replace_settings,
            "Регистр": self._create_case_settings,
            "Нумерация": self._create_numbering_settings,
            "Метаданные": self._create_metadata_settings,
            "Регулярные выражения": self._create_regex_settings
        }
        
        creator = method_creators.get(method_name)
        if creator:
            creator()
    
    def _create_new_name_settings(self):
        """Настройки для метода Новое имя"""
        btn = self.create_rounded_button(
            self.methods_window_settings_frame, "Быстрые шаблоны", 
            self.show_quick_templates, self.colors['primary'], 'white',
            font=('Robot', 8), padx=8, pady=4, active_bg=self.colors['primary_hover'])
        btn.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(self.methods_window_settings_frame, text="Шаблон:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_new_name_template = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_new_name_template,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        num_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        num_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(num_frame, text="Начальный номер:", font=('Robot', 8),
                bg=self.colors['bg_card'], fg=self.colors['text_primary']).pack(side=tk.LEFT)
        
        self.methods_window_new_name_start_number = tk.StringVar(value="1")
        tk.Entry(num_frame, textvariable=self.methods_window_new_name_start_number,
                font=('Robot', 8), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1, width=8).pack(side=tk.LEFT, padx=(5, 0))
    
    def _create_add_remove_settings(self):
        """Настройки для метода Добавить/Удалить"""
        self.methods_window_add_remove_op = tk.StringVar(value="add")
        op_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        op_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Radiobutton(op_frame, text="Добавить", variable=self.methods_window_add_remove_op,
                      value="add", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(op_frame, text="Удалить", variable=self.methods_window_add_remove_op,
                      value="remove", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT)
        
        tk.Label(self.methods_window_settings_frame, text="Текст:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_add_remove_text = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_add_remove_text,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        self.methods_window_add_remove_pos = tk.StringVar(value="before")
        pos_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        pos_frame.pack(fill=tk.X)
        
        tk.Radiobutton(pos_frame, text="Перед", variable=self.methods_window_add_remove_pos,
                      value="before", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(pos_frame, text="После", variable=self.methods_window_add_remove_pos,
                      value="after", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT)
    
    def _create_replace_settings(self):
        """Настройки для метода Замена"""
        tk.Label(self.methods_window_settings_frame, text="Найти:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_replace_find = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_replace_find,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(self.methods_window_settings_frame, text="Заменить на:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_replace_with = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_replace_with,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        self.methods_window_replace_case = tk.BooleanVar(value=False)
        tk.Checkbutton(self.methods_window_settings_frame, text="Учитывать регистр",
                      variable=self.methods_window_replace_case,
                      bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(anchor=tk.W)
    
    def _create_case_settings(self):
        """Настройки для метода Регистр"""
        self.methods_window_case_type = tk.StringVar(value="lower")
        case_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        case_frame.pack(fill=tk.X)
        
        types = [("lower", "Строчные"), ("upper", "Заглавные"),
                ("capitalize", "Первая заглавная"), ("title", "Заглавные слова")]
        
        for value, text in types:
            tk.Radiobutton(case_frame, text=text, variable=self.methods_window_case_type,
                          value=value, bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                          font=('Robot', 8)).pack(anchor=tk.W)
    
    def _create_numbering_settings(self):
        """Настройки для метода Нумерация"""
        params_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        params_frame.pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(params_frame, text="С:", font=('Robot', 8),
                bg=self.colors['bg_card'], fg=self.colors['text_primary']).pack(side=tk.LEFT)
        self.methods_window_numbering_start = tk.StringVar(value="1")
        tk.Entry(params_frame, textvariable=self.methods_window_numbering_start,
                font=('Robot', 8), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1, width=6).pack(side=tk.LEFT, padx=5)
        
        tk.Label(params_frame, text="Шаг:", font=('Robot', 8),
                bg=self.colors['bg_card'], fg=self.colors['text_primary']).pack(side=tk.LEFT)
        self.methods_window_numbering_step = tk.StringVar(value="1")
        tk.Entry(params_frame, textvariable=self.methods_window_numbering_step,
                font=('Robot', 8), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1, width=6).pack(side=tk.LEFT, padx=5)
        
        tk.Label(params_frame, text="Цифр:", font=('Robot', 8),
                bg=self.colors['bg_card'], fg=self.colors['text_primary']).pack(side=tk.LEFT)
        self.methods_window_numbering_digits = tk.StringVar(value="3")
        tk.Entry(params_frame, textvariable=self.methods_window_numbering_digits,
                font=('Robot', 8), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1, width=6).pack(side=tk.LEFT, padx=5)
        
        tk.Label(self.methods_window_settings_frame, text="Формат ({n} для номера):", 
                font=('Robot', 8), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_numbering_format = tk.StringVar(value="({n})")
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_numbering_format,
                font=('Robot', 8), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        self.methods_window_numbering_pos = tk.StringVar(value="end")
        pos_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        pos_frame.pack(fill=tk.X)
        
        tk.Radiobutton(pos_frame, text="В начале", variable=self.methods_window_numbering_pos,
                      value="start", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(pos_frame, text="В конце", variable=self.methods_window_numbering_pos,
                      value="end", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT)
    
    def _create_metadata_settings(self):
        """Настройки для метода Метаданные"""
        tk.Label(self.methods_window_settings_frame, text="Тег:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_metadata_tag = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_metadata_tag,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(self.methods_window_settings_frame, 
                text="Примеры: {width}x{height}, {date_created}",
                font=('Robot', 7), bg=self.colors['bg_card'], 
                fg=self.colors['text_muted']).pack(anchor=tk.W, pady=(0, 8))
        
        self.methods_window_metadata_pos = tk.StringVar(value="end")
        pos_frame = tk.Frame(self.methods_window_settings_frame, bg=self.colors['bg_card'])
        pos_frame.pack(fill=tk.X)
        
        tk.Radiobutton(pos_frame, text="В начале", variable=self.methods_window_metadata_pos,
                      value="start", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT, padx=(0, 10))
        tk.Radiobutton(pos_frame, text="В конце", variable=self.methods_window_metadata_pos,
                      value="end", bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                      font=('Robot', 8)).pack(side=tk.LEFT)
    
    def _create_regex_settings(self):
        """Настройки для метода Регулярные выражения"""
        tk.Label(self.methods_window_settings_frame, text="Паттерн:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_regex_pattern = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_regex_pattern,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(self.methods_window_settings_frame, text="Заменить на:", 
                font=('Robot', 9), bg=self.colors['bg_card'], 
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 4))
        
        self.methods_window_regex_replace = tk.StringVar()
        tk.Entry(self.methods_window_settings_frame,
                textvariable=self.methods_window_regex_replace,
                font=('Robot', 9), bg='white', fg=self.colors['text_primary'],
                relief=tk.SOLID, borderwidth=1).pack(fill=tk.X, pady=(0, 8))
        
        tk.Label(self.methods_window_settings_frame, 
                text="Группы: \\1, \\2 и т.д.",
                font=('Robot', 7), bg=self.colors['bg_card'], 
                fg=self.colors['text_muted']).pack(anchor=tk.W)
    
    def _add_method_from_window(self):
        """Добавление метода"""
        method_name = self.methods_window_method_var.get()
        
        try:
            method = None
            if method_name == "Новое имя":
                template = self.methods_window_new_name_template.get()
                if not template:
                    raise ValueError("Введите шаблон")
                start = int(self.methods_window_new_name_start_number.get() or "1")
                method = NewNameMethod(template, self.metadata_extractor, start)
            elif method_name == "Добавить/Удалить":
                method = AddRemoveMethod(
                    self.methods_window_add_remove_op.get(),
                    self.methods_window_add_remove_text.get(),
                    self.methods_window_add_remove_pos.get()
                )
            elif method_name == "Замена":
                method = ReplaceMethod(
                    self.methods_window_replace_find.get(),
                    self.methods_window_replace_with.get(),
                    self.methods_window_replace_case.get()
                )
            elif method_name == "Регистр":
                method = CaseMethod(self.methods_window_case_type.get(), "name")
            elif method_name == "Нумерация":
                method = NumberingMethod(
                    int(self.methods_window_numbering_start.get() or "1"),
                    int(self.methods_window_numbering_step.get() or "1"),
                    int(self.methods_window_numbering_digits.get() or "3"),
                    self.methods_window_numbering_format.get(),
                    self.methods_window_numbering_pos.get()
                )
            elif method_name == "Метаданные":
                if not self.metadata_extractor:
                    messagebox.showerror("Ошибка", "Модуль метаданных недоступен")
                    return
                method = MetadataMethod(
                    self.methods_window_metadata_tag.get(),
                    self.methods_window_metadata_pos.get(),
                    self.metadata_extractor
                )
            elif method_name == "Регулярные выражения":
                method = RegexMethod(
                    self.methods_window_regex_pattern.get(),
                    self.methods_window_regex_replace.get()
                )
            
            if method:
                self.methods_manager.add_method(method)
                self.methods_listbox.insert(tk.END, method_name)
                self._update_methods_window_list()
                self.log(f"Добавлен метод: {method_name}")
                self.apply_methods()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить метод: {e}")
    
    def _remove_method_from_window(self):
        """Удаление метода"""
        selection = self.methods_window_listbox.curselection()
        if not selection:
            messagebox.showwarning("Предупреждение", "Выберите метод")
            return
        
        index = selection[0]
        methods = self.methods_manager.get_methods()
        if 0 <= index < len(methods):
            self.methods_manager.remove_method(index)
            self.methods_listbox.delete(index)
            self._update_methods_window_list()
            self.log(f"Удален метод: {index + 1}")
            self.apply_methods()
    
    def _clear_methods_from_window(self):
        """Очистка всех методов"""
        if self.methods_manager.get_methods():
            if messagebox.askyesno("Подтверждение", "Очистить все методы?"):
                self.methods_manager.clear_methods()
                self.methods_listbox.delete(0, tk.END)
                self._update_methods_window_list()
                self.log("Все методы очищены")
    
    def _apply_methods_from_window(self):
        """Применение методов"""
        self.apply_methods()
        messagebox.showinfo("Готово", "Методы применены!")
    
    def open_tabs_window(self, tab_name='log'):
        """Открытие окна с вкладками (логи, настройки, о программе, поддержка)"""
        # Если окно уже открыто, переключаемся на нужную вкладку
        if self.windows['tabs'] is not None and self.windows['tabs'].winfo_exists():
            self.windows['tabs'].lift()
            self.windows['tabs'].focus_force()
            if self.tabs_window_notebook:
                # Переключаемся на нужную вкладку
                tab_index_map = {'log': 0, 'settings': 1, 'about': 2, 'support': 3}
                if tab_name in tab_index_map:
                    self.tabs_window_notebook.select(tab_index_map[tab_name])
            return
        
        # Создаем новое окно с вкладками
        window = tk.Toplevel(self.root)
        window.title("Информация и настройки")
        window.geometry("800x600")
        window.minsize(600, 500)
        window.configure(bg=self.colors['bg_card'])
        
        # Установка иконки
        try:
            set_window_icon(window, self._icon_photos)
        except Exception:
            pass
        
        # Настройка адаптивности окна
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        
        self.windows['tabs'] = window
        
        # Создаем Notebook для вкладок
        notebook = ttk.Notebook(window)
        notebook.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.tabs_window_notebook = notebook
        
        # Создаем вкладки
        self._create_log_tab(notebook)
        self._create_settings_tab(notebook)
        self._create_about_tab(notebook)
        self._create_support_tab(notebook)
        
        # Переключаемся на нужную вкладку
        tab_index_map = {'log': 0, 'settings': 1, 'about': 2, 'support': 3}
        if tab_name in tab_index_map:
            notebook.select(tab_index_map[tab_name])
        
        # Обработчик закрытия окна
        def on_close():
            self.logger.set_log_widget(None)
            self.close_window('tabs')
        
        window.protocol("WM_DELETE_WINDOW", on_close)
    
    def open_log_window(self):
        """Переключение на вкладку лога операций в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(1)  # Индекс 1 - вкладка лога
    
    def open_settings_window(self):
        """Переключение на вкладку настроек в главном окне (удалено)"""
        pass
    
    def open_about_window(self):
        """Переключение на вкладку о программе в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(2)  # Индекс 2 - вкладка о программе (после удаления настроек)
    
    def open_support_window(self):
        """Переключение на вкладку поддержки в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(3)  # Индекс 3 - вкладка поддержки (после удаления настроек)
    
    def _create_main_log_tab(self):
        """Создание вкладки лога операций на главном экране"""
        log_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        self.main_notebook.add(log_tab, text="Лог операций")
        
        # Панель управления логом
        log_controls = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_controls.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        log_controls.columnconfigure(1, weight=1)
        log_controls.columnconfigure(2, weight=1)
        
        # Заголовок
        log_title = tk.Label(log_controls, text="Лог операций",
                            font=('Robot', 11, 'bold'),
                            bg=self.colors['bg_card'],
                            fg=self.colors['text_primary'])
        log_title.grid(row=0, column=0, padx=(0, 12), sticky="w")
        
        btn_clear_log = self.create_rounded_button(
            log_controls, "Очистить лог", self.clear_log,
            self.colors['danger'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear_log.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Кнопка выгрузки лога
        btn_save_log = self.create_rounded_button(
            log_controls, "Выгрузить лог", self.save_log,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_save_log.grid(row=0, column=2, padx=3, sticky="ew")
        
        # Лог операций
        log_frame = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        log_container = tk.Frame(log_frame, bg=self.colors['bg_card'], 
                                relief='flat', borderwidth=1,
                                highlightbackground=self.colors['border'],
                                highlightthickness=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        log_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL)
        log_text_widget = tk.Text(log_container, yscrollcommand=log_scroll.set,
                               font=('Consolas', 10),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'],
                               relief='flat', borderwidth=0,
                               padx=12, pady=10,
                               wrap=tk.WORD)
        log_scroll.config(command=log_text_widget.yview)
        
        log_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Сохраняем ссылку на скроллбар
        self.log_scrollbar = log_scroll
        
        # Привязка прокрутки колесом мыши для лога
        self.bind_mousewheel(log_text_widget, log_text_widget)
        
        # Автоматическое управление видимостью скроллбара для Text
        def update_log_scrollbar(*args):
            self.update_scrollbar_visibility(log_text_widget, log_scroll, 'vertical')
        
        log_text_widget.bind('<Key>', lambda e: self.root.after_idle(update_log_scrollbar))
        log_text_widget.bind('<Button-1>', lambda e: self.root.after_idle(update_log_scrollbar))
        log_text_widget.bind('<Configure>', lambda e: self.root.after_idle(update_log_scrollbar))
        
        # Сохраняем ссылку на log_text
        self.logger.set_log_widget(log_text_widget)
    
    def _create_main_about_tab(self):
        """Создание вкладки о программе на главном экране"""
        about_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(about_tab, text="О программе")
        
        # Содержимое о программе с прокруткой
        canvas = tk.Canvas(about_tab, bg=self.colors['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(about_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_card'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(event):
            if event.widget == canvas:
                try:
                    canvas_width = event.width
                    canvas.itemconfig(canvas_window, width=canvas_width)
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == about_tab:
                try:
                    canvas_width = about_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        about_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(canvas, canvas)
        self.bind_mousewheel(scrollable_frame, canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        about_tab.rowconfigure(0, weight=1)
        about_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=40, pady=40)
        
        # Описание программы - карточка
        about_card = ttk.LabelFrame(content_frame, text="О программе", 
                                    style='Card.TLabelframe', padding=20)
        about_card.pack(fill=tk.X, pady=(10, 20))
        
        # Контейнер для изображения и описания
        about_content_frame = tk.Frame(about_card, bg=self.colors['bg_card'])
        about_content_frame.pack(fill=tk.X)
        
        # Изображение программы слева от текста
        image_frame = tk.Frame(about_content_frame, bg=self.colors['bg_card'])
        image_frame.pack(side=tk.LEFT, padx=(0, 20))
        try:
            image_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "Иконка.png")
            if not os.path.exists(image_path):
                image_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "1000x1000.png")
            if os.path.exists(image_path) and HAS_PIL:
                img = Image.open(image_path)
                img = img.resize((200, 200), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                image_label = tk.Label(image_frame, image=photo, bg=self.colors['bg_card'])
                image_label.image = photo
                image_label.pack()
        except Exception as e:
            print(f"Ошибка загрузки изображения: {e}")
        
        # Описание программы справа от изображения
        desc_frame = tk.Frame(about_content_frame, bg=self.colors['bg_card'])
        desc_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        desc_text = """Ренейм+ - это мощная и удобная программа для массового переименования файлов. 

Программа предоставляет широкий набор инструментов для работы с именами файлов: 
переименование по различным шаблонам, поддержка метаданных (EXIF, ID3 и др.), 
предпросмотр изменений перед применением, удобный интерфейс с поддержкой Drag & Drop, 
возможность перестановки файлов в списке и многое другое.

Программа поможет вам быстро и эффективно организовать ваши файлы."""
        
        desc_label = tk.Label(desc_frame, 
                              text=desc_text,
                              font=('Robot', 10),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['text_primary'],
                              justify=tk.LEFT,
                              anchor=tk.NW,
                              wraplength=500)
        desc_label.pack(anchor=tk.NW, fill=tk.X)
        
        # Разработчики - карточка
        dev_card = ttk.LabelFrame(content_frame, text="👥 Разработчики", 
                                  style='Card.TLabelframe', padding=20)
        dev_card.pack(fill=tk.X, pady=(0, 20))
        
        # Разработчики
        dev_text = "Разработчики: Urban SOLUTION"
        
        dev_label = tk.Label(dev_card, 
                            text=dev_text,
                            font=('Robot', 10),
                            bg=self.colors['bg_card'], 
                            fg=self.colors['text_primary'],
                            justify=tk.LEFT,
                            anchor=tk.W)
        dev_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        # Разработал
        def open_vk_profile(event):
            import webbrowser
            webbrowser.open("https://vk.com/vsemirka200")
        
        dev_by_frame = tk.Frame(dev_card, bg=self.colors['bg_card'])
        dev_by_frame.pack(anchor=tk.W, fill=tk.X)
        
        dev_by_prefix = tk.Label(dev_by_frame, 
                                text="Автора идеи: ",
                                font=('Robot', 10),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['text_primary'],
                                justify=tk.LEFT)
        dev_by_prefix.pack(side=tk.LEFT)
        
        # Иконка VK рядом с именем
        try:
            vk_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "ВКонтакте.png")
            if os.path.exists(vk_icon_path) and HAS_PIL:
                vk_img = Image.open(vk_icon_path)
                vk_img = vk_img.resize((16, 16), Image.Resampling.LANCZOS)
                vk_photo = ImageTk.PhotoImage(vk_img)
                vk_icon_label = tk.Label(dev_by_frame, image=vk_photo, bg=self.colors['bg_card'])
                vk_icon_label.image = vk_photo
                vk_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        except Exception as e:
            print(f"Ошибка загрузки иконки VK: {e}")
        
        dev_name_label = tk.Label(dev_by_frame, 
                                 text="Олюшин Владислав Викторович",
                                 font=('Robot', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['primary'],
                                 cursor='hand2',
                                 justify=tk.LEFT)
        dev_name_label.pack(side=tk.LEFT)
        dev_name_label.bind("<Button-1>", open_vk_profile)
        
        # Наши соц сети - карточка
        social_card = ttk.LabelFrame(content_frame, text="🌐 Наши соц сети", 
                                     style='Card.TLabelframe', padding=20)
        social_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_vk_social(event):
            import webbrowser
            webbrowser.open("https://vk.com/urban_solution")
        
        vk_frame = tk.Frame(social_card, bg=self.colors['bg_card'])
        vk_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Иконка VK
        try:
            vk_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "ВКонтакте.png")
            if os.path.exists(vk_icon_path) and HAS_PIL:
                vk_img = Image.open(vk_icon_path)
                vk_img = vk_img.resize((16, 16), Image.Resampling.LANCZOS)
                vk_photo = ImageTk.PhotoImage(vk_img)
                vk_icon_label = tk.Label(vk_frame, image=vk_photo, bg=self.colors['bg_card'])
                vk_icon_label.image = vk_photo
                vk_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        except Exception as e:
            print(f"Ошибка загрузки иконки VK: {e}")
        
        vk_label = tk.Label(vk_frame, 
                           text="ВКонтакте",
                           font=('Robot', 10),
                           bg=self.colors['bg_card'], 
                           fg=self.colors['primary'],
                           cursor='hand2',
                           justify=tk.LEFT)
        vk_label.pack(side=tk.LEFT)
        vk_label.bind("<Button-1>", open_vk_social)
        
        def open_tg_channel(event):
            import webbrowser
            webbrowser.open("https://t.me/+n1JeH5DS-HQ2NjYy")
        
        tg_frame = tk.Frame(social_card, bg=self.colors['bg_card'])
        tg_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Иконка Telegram
        try:
            tg_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "Telegram.png")
            if os.path.exists(tg_icon_path) and HAS_PIL:
                tg_img = Image.open(tg_icon_path)
                tg_img = tg_img.resize((16, 16), Image.Resampling.LANCZOS)
                tg_photo = ImageTk.PhotoImage(tg_img)
                tg_icon_label = tk.Label(tg_frame, image=tg_photo, bg=self.colors['bg_card'])
                tg_icon_label.image = tg_photo
                tg_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        except Exception as e:
            print(f"Ошибка загрузки иконки Telegram: {e}")
        
        tg_label = tk.Label(tg_frame, 
                           text="Telegram",
                           font=('Robot', 10),
                           bg=self.colors['bg_card'], 
                           fg=self.colors['primary'],
                           cursor='hand2',
                           justify=tk.LEFT)
        tg_label.pack(side=tk.LEFT)
        tg_label.bind("<Button-1>", open_tg_channel)
        
        # GitHub - отдельная карточка
        github_card = ttk.LabelFrame(content_frame, text="💻 Посмотреть код", 
                                     style='Card.TLabelframe', padding=20)
        github_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/VseMirka200/nazovi")
        
        github_frame = tk.Frame(github_card, bg=self.colors['bg_card'])
        github_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Иконка GitHub
        try:
            github_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "GitHUB.png")
            if os.path.exists(github_icon_path) and HAS_PIL:
                github_img = Image.open(github_icon_path)
                github_img = github_img.resize((16, 16), Image.Resampling.LANCZOS)
                github_photo = ImageTk.PhotoImage(github_img)
                github_icon_label = tk.Label(github_frame, image=github_photo, bg=self.colors['bg_card'])
                github_icon_label.image = github_photo
                github_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        except Exception as e:
            print(f"Ошибка загрузки иконки GitHub: {e}")
        
        github_label = tk.Label(github_frame, 
                               text="GitHub",
                               font=('Robot', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['primary'],
                               cursor='hand2',
                               justify=tk.LEFT)
        github_label.pack(side=tk.LEFT)
        github_label.bind("<Button-1>", open_github)
        
        # Контакты разработчиков - карточка
        contact_card = ttk.LabelFrame(content_frame, text="📧 Связаться с разработчиками", 
                                      style='Card.TLabelframe', padding=20)
        contact_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_email(event):
            import webbrowser
            webbrowser.open("mailto:urban-solution@ya.ru")
        
        contact_frame = tk.Frame(contact_card, bg=self.colors['bg_card'])
        contact_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Иконка email (используем простую иконку или эмодзи, так как специальной иконки нет)
        email_icon_label = tk.Label(contact_frame, 
                                    text="📧",
                                    font=('Robot', 10),
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['primary'])
        email_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        
        contact_label = tk.Label(contact_frame, 
                                text="urban-solution@ya.ru",
                                font=('Robot', 10),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['primary'],
                                cursor='hand2',
                                justify=tk.LEFT)
        contact_label.pack(side=tk.LEFT)
        contact_label.bind("<Button-1>", open_email)
        
    
    def _create_main_support_tab(self):
        """Создание вкладки поддержки на главном экране"""
        support_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(support_tab, text="Поддержка")
        
        # Содержимое поддержки без скроллбара
        content_frame = tk.Frame(support_tab, bg=self.colors['bg_card'])
        content_frame.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        content_frame.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        support_tab.columnconfigure(0, weight=1)
        
        # Описание - карточка
        desc_card = ttk.LabelFrame(content_frame, text="Поддержать проект", 
                                   style='Card.TLabelframe', padding=20)
        desc_card.pack(fill=tk.X, pady=(10, 20))
        
        # Первый параграф
        desc_text1 = "Если вам нравится эта программа и она помогает вам в работе,\nвы можете поддержать её развитие!"
        
        desc_label1 = tk.Label(desc_card, 
                               text=desc_text1,
                               font=('Robot', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_primary'],
                               justify=tk.LEFT,
                               anchor=tk.W)
        desc_label1.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        # Заголовок списка
        support_heading = tk.Label(desc_card, 
                                  text="Ваша поддержка поможет:",
                                  font=('Robot', 10),
                                  bg=self.colors['bg_card'], 
                                  fg=self.colors['text_primary'],
                                  justify=tk.LEFT,
                                  anchor=tk.W)
        support_heading.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Маркированный список
        support_list = """- Добавлять новые функции
- Улучшать существующие возможности
- Исправлять ошибки
- Поддерживать проект активным"""
        
        support_list_label = tk.Label(desc_card, 
                                     text=support_list,
                                     font=('Robot', 10),
                                     bg=self.colors['bg_card'], 
                                     fg=self.colors['text_primary'],
                                     justify=tk.LEFT,
                                     anchor=tk.W)
        support_list_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 12))
        
        # Ссылка на донат
        def open_donation(event):
            import webbrowser
            webbrowser.open("https://pay.cloudtips.ru/p/1fa22ea5")
        
        donation_label = tk.Label(desc_card, 
                                 text="Поддержать проект",
                                 font=('Robot', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['primary'],
                                 cursor='hand2',
                                 justify=tk.LEFT)
        donation_label.pack(anchor=tk.W, pady=(8, 0))
        donation_label.bind("<Button-1>", open_donation)
    
    def _create_log_tab(self, notebook):
        """Создание вкладки лога операций"""
        # Фрейм для вкладки лога
        log_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        notebook.add(log_tab, text="Лог операций")
        
        # Панель управления логом
        log_controls = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_controls.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        log_controls.columnconfigure(1, weight=1)
        log_controls.columnconfigure(2, weight=1)
        
        # Заголовок
        log_title = tk.Label(log_controls, text="Лог операций",
                                  font=('Robot', 11, 'bold'),
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['text_primary'])
        log_title.grid(row=0, column=0, padx=(0, 12), sticky="w")
        
        btn_clear_log = self.create_rounded_button(
            log_controls, "Очистить лог", self.clear_log,
            self.colors['danger'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear_log.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Кнопка выгрузки лога
        btn_save_log = self.create_rounded_button(
            log_controls, "Выгрузить лог", self.save_log,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_save_log.grid(row=0, column=2, padx=3, sticky="ew")
        
        # Лог операций
        log_frame = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        log_container = tk.Frame(log_frame, bg=self.colors['bg_card'], 
                                relief='flat', borderwidth=1,
                                highlightbackground=self.colors['border'],
                                highlightthickness=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        log_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL)
        log_text_widget = tk.Text(log_container, yscrollcommand=log_scroll.set,
                                  wrap=tk.WORD, font=('Consolas', 9),
                                  bg=self.colors['bg_secondary'],
                                  fg=self.colors['text_primary'],
                                  insertbackground=self.colors['text_primary'],
                                  relief='flat', borderwidth=0,
                                  padx=10, pady=10)
        log_scroll.config(command=log_text_widget.yview)
        
        log_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Сохраняем ссылку на виджет лога
        self.log_text_widget = log_text_widget
        
        # Привязка прокрутки колесиком мыши
        self.bind_mousewheel(log_text_widget, log_text_widget)
        
        # Сохраняем ссылку на log_text
        self.logger.set_log_widget(log_text_widget)
    
    def _create_settings_tab(self, notebook):
        """Создание вкладки настроек"""
        # Фрейм для вкладки настроек
        settings_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        notebook.add(settings_tab, text="Настройки")
        
        # Содержимое настроек с прокруткой
        canvas = tk.Canvas(settings_tab, bg=self.colors['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_card'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    
        def on_canvas_configure(event):
            if event.widget == canvas:
                try:
                    canvas_width = event.width
                    canvas.itemconfig(canvas_window, width=canvas_width)
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == settings_tab:
                try:
                    canvas_width = settings_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        settings_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(canvas, canvas)
        self.bind_mousewheel(scrollable_frame, canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        settings_tab.rowconfigure(0, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=40, pady=40)
        
        # Заголовок
        title_label = tk.Label(content_frame, text="Настройки", 
                              font=('Robot', 20, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['text_primary'])
        title_label.pack(anchor=tk.W, pady=(0, 25))
        
        # Секция: Общие настройки
        general_frame = ttk.LabelFrame(content_frame, text="Общие настройки", 
                                      style='Card.TLabelframe', padding=20)
        general_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Автоматическое применение методов
        auto_apply_var = tk.BooleanVar(value=self.settings.get('auto_apply', False))
        auto_apply_check = tk.Checkbutton(general_frame, 
                                         text="Автоматически применять методы при добавлении",
                                         variable=auto_apply_var,
                                         font=('Robot', 10),
                                         bg=self.colors['bg_card'],
                                         fg=self.colors['text_primary'],
                                         selectcolor='white',
                                         activebackground=self.colors['bg_card'],
                                         activeforeground=self.colors['text_primary'])
        auto_apply_check.pack(anchor=tk.W, pady=5)
        
        # Показывать предупреждения
        show_warnings_var = tk.BooleanVar(value=self.settings.get('show_warnings', True))
        show_warnings_check = tk.Checkbutton(general_frame, 
                                            text="Показывать предупреждения перед переименованием",
                                            variable=show_warnings_var,
                                            font=('Robot', 10),
                                            bg=self.colors['bg_card'],
                                            fg=self.colors['text_primary'],
                                            selectcolor='white',
                                            activebackground=self.colors['bg_card'],
                                            activeforeground=self.colors['text_primary'])
        show_warnings_check.pack(anchor=tk.W, pady=5)
        
        # Секция: Интерфейс
        ui_frame = ttk.LabelFrame(content_frame, text="Интерфейс", 
                                 style='Card.TLabelframe', padding=20)
        ui_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Размер шрифта
        font_size_label = tk.Label(ui_frame, text="Размер шрифта:",
                                   font=('Robot', 11, 'bold'),
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['text_primary'])
        font_size_label.pack(anchor=tk.W, pady=(0, 8))
        
        font_size_var = tk.StringVar(value=self.settings.get('font_size', '10'))
        font_size_combo = ttk.Combobox(ui_frame, textvariable=font_size_var,
                                      values=["8", "9", "10", "11", "12"],
                                      state="readonly", width=10)
        font_size_combo.pack(anchor=tk.W, pady=(0, 10))
        
        # Секция: Файлы
        files_frame = ttk.LabelFrame(content_frame, text="Работа с файлами", 
                                    style='Card.TLabelframe', padding=20)
        files_frame.pack(fill=tk.X, pady=(0, 20))
        
        # Резервное копирование
        backup_var = tk.BooleanVar(value=self.settings.get('backup', False))
        backup_check = tk.Checkbutton(files_frame, 
                                      text="Создавать резервные копии перед переименованием",
                                      variable=backup_var,
                                      font=('Robot', 10),
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['text_primary'],
                                      selectcolor='white',
                                      activebackground=self.colors['bg_card'],
                                      activeforeground=self.colors['text_primary'])
        backup_check.pack(anchor=tk.W, pady=5)
        
        # Кнопка сохранения
        def save_settings_handler():
            settings_to_save = {
                'auto_apply': auto_apply_var.get(),
                'show_warnings': show_warnings_var.get(),
                'font_size': font_size_var.get(),
                'backup': backup_var.get()
            }
            if self.save_settings(settings_to_save):
                self.settings.update(settings_to_save)
                messagebox.showinfo("Настройки", "Настройки успешно сохранены!")
            else:
                messagebox.showerror("Ошибка", "Не удалось сохранить настройки!")
        
        save_btn = self.create_rounded_button(
            content_frame, "Сохранить настройки",
            save_settings_handler,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        save_btn.pack(pady=(10, 0))
    
    def _create_about_tab(self, notebook):
        """Создание вкладки о программе"""
        # Фрейм для вкладки о программе
        about_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        notebook.add(about_tab, text="О программе")
        
        # Содержимое о программе с прокруткой
        canvas = tk.Canvas(about_tab, bg=self.colors['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(about_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_card'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        
        def on_canvas_configure(event):
            if event.widget == canvas:
                try:
                    canvas_width = event.width
                    canvas.itemconfig(canvas_window, width=canvas_width)
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == about_tab:
                try:
                    canvas_width = about_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        about_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(canvas, canvas)
        self.bind_mousewheel(scrollable_frame, canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        about_tab.rowconfigure(0, weight=1)
        about_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=40, pady=40)
        
        # Иконка программы
        try:
            icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "1000x1000.png")
            if os.path.exists(icon_path) and HAS_PIL:
                img = Image.open(icon_path)
                # Уменьшаем размер для отображения
                img = img.resize((128, 128), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                icon_label = tk.Label(content_frame, image=photo, bg=self.colors['bg_card'])
                icon_label.image = photo  # Сохраняем ссылку
                icon_label.pack(pady=(10, 20))
        except Exception as e:
            print(f"Ошибка загрузки иконки: {e}")  # Отладочная информация
        
        # Описание программы - карточка
        about_card = ttk.LabelFrame(content_frame, text="О программе", 
                                    style='Card.TLabelframe', padding=20)
        about_card.pack(fill=tk.X, pady=(0, 20))
        
        # Основное описание
        desc_text1 = "Программа для удобного переименования файлов"
        
        desc_label1 = tk.Label(about_card, 
                              text=desc_text1,
                              font=('Robot', 10),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['text_primary'],
                              justify=tk.LEFT,
                              anchor=tk.W)
        desc_label1.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        # Заголовок возможностей
        features_heading = tk.Label(about_card, 
                                   text="Возможности:",
                                   font=('Robot', 10),
                                   bg=self.colors['bg_card'], 
                                   fg=self.colors['text_primary'],
                                   justify=tk.LEFT,
                                   anchor=tk.W)
        features_heading.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Список возможностей
        features_list = """- Переименование по различным методам
- Поддержка метаданных (EXIF, ID3 и др.)
- Предпросмотр изменений перед применением
- Drag & Drop для добавления файлов
- Перестановка файлов в списке
- Отмена операций"""
        
        features_label = tk.Label(about_card, 
                                 text=features_list,
                                 font=('Robot', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['text_primary'],
                                 justify=tk.LEFT,
                                 anchor=tk.W)
        features_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        # Заголовок технологий
        tech_heading = tk.Label(about_card, 
                               text="Используемые технологии:",
                               font=('Robot', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_primary'],
                               justify=tk.LEFT,
                               anchor=tk.W)
        tech_heading.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Список технологий
        tech_list = """- Python 3
- Tkinter
- tkinterdnd2"""
        
        tech_label = tk.Label(about_card, 
                             text=tech_list,
                             font=('Robot', 10),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_primary'],
                             justify=tk.LEFT,
                             anchor=tk.W)
        tech_label.pack(anchor=tk.W, fill=tk.X)
        
        # Контакты разработчиков - карточка
        contact_card = ttk.LabelFrame(content_frame, text="📧 Связаться с разработчиками", 
                                      style='Card.TLabelframe', padding=20)
        contact_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_email(event):
            import webbrowser
            webbrowser.open("mailto:urban-solution@ya.ru")
        
        contact_frame = tk.Frame(contact_card, bg=self.colors['bg_card'])
        contact_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Иконка email (используем простую иконку или эмодзи, так как специальной иконки нет)
        email_icon_label = tk.Label(contact_frame, 
                                    text="📧",
                                    font=('Robot', 10),
                                    bg=self.colors['bg_card'],
                                    fg=self.colors['primary'])
        email_icon_label.pack(side=tk.LEFT, padx=(0, 4))
        
        contact_label = tk.Label(contact_frame, 
                                text="urban-solution@ya.ru",
                                font=('Robot', 10),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['primary'],
                                cursor='hand2',
                                justify=tk.LEFT)
        contact_label.pack(side=tk.LEFT)
        contact_label.bind("<Button-1>", open_email)
        
    
    def _create_support_tab(self, notebook):
        """Создание вкладки поддержки"""
        # Фрейм для вкладки поддержки
        support_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        notebook.add(support_tab, text="Поддержка")
        
        # Содержимое поддержки без скроллбара
        content_frame = tk.Frame(support_tab, bg=self.colors['bg_card'])
        content_frame.grid(row=0, column=0, sticky="nsew", padx=40, pady=40)
        content_frame.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        support_tab.columnconfigure(0, weight=1)
        
        # Описание - карточка
        desc_card = ttk.LabelFrame(content_frame, text="Поддержать проект", 
                                   style='Card.TLabelframe', padding=20)
        desc_card.pack(fill=tk.X, pady=(10, 20))
        
        # Первый параграф
        desc_text1 = "Если вам нравится эта программа и она помогает вам в работе,\nвы можете поддержать её развитие!"
        
        desc_label1 = tk.Label(desc_card, 
                               text=desc_text1,
                               font=('Robot', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_primary'],
                               justify=tk.LEFT,
                               anchor=tk.W)
        desc_label1.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        # Заголовок списка
        support_heading = tk.Label(desc_card, 
                                  text="Ваша поддержка поможет:",
                                  font=('Robot', 10),
                                  bg=self.colors['bg_card'], 
                                  fg=self.colors['text_primary'],
                                  justify=tk.LEFT,
                                  anchor=tk.W)
        support_heading.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Маркированный список
        support_list = """- Добавлять новые функции
- Улучшать существующие возможности
- Исправлять ошибки
- Поддерживать проект активным"""
        
        support_list_label = tk.Label(desc_card, 
                                     text=support_list,
                                     font=('Robot', 10),
                                     bg=self.colors['bg_card'], 
                                     fg=self.colors['text_primary'],
                                     justify=tk.LEFT,
                                     anchor=tk.W)
        support_list_label.pack(anchor=tk.W, fill=tk.X, pady=(0, 12))
        
        # Ссылка на донат
        def open_donation(event):
            import webbrowser
            webbrowser.open("https://pay.cloudtips.ru/p/1fa22ea5")
        
        donation_label = tk.Label(desc_card, 
                                 text="Поддержать проект",
                                 font=('Robot', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['primary'],
                                 cursor='hand2',
                                 justify=tk.LEFT)
        donation_label.pack(anchor=tk.W, pady=(8, 0))
        donation_label.bind("<Button-1>", open_donation)
    
    def close_window(self, window_name: str):
        """Закрытие окна"""
        if window_name in self.windows and self.windows[window_name] is not None:
            if window_name == 'tabs':
                # Сохраняем log_text для логирования
                self.logger.set_log_widget(None)
            try:
                self.windows[window_name].destroy()
            except (AttributeError, tk.TclError):
                # Прогресс-бар может быть уничтожен
                pass
            self.windows[window_name] = None
    
    
    def setup_hotkeys(self):
        """Настройка горячих клавиш"""
        self.root.bind('<Control-a>', lambda e: self.add_files())
        self.root.bind('<Control-z>', lambda e: self.undo_rename())
        self.root.bind('<Delete>', lambda e: self.delete_selected())
        self.root.bind('<Control-o>', lambda e: self.add_folder())
    
    def setup_tray_icon(self):
        """Настройка трей-иконки"""
        self.tray_manager = TrayManager(
            self.root,
            self.show_window,
            self.quit_app
        )
        self.tray_manager.setup()
    
    def show_window(self):
        """Показать главное окно"""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            try:
                self.root.state('normal')
            except tk.TclError as e:
                logger.debug(f"Не удалось изменить состояние окна: {e}")
        except Exception:
            pass
    
    def quit_app(self):
        """Полный выход из приложения"""
        if self.tray_manager:
            self.tray_manager.stop()
        self.root.quit()
        self.root.destroy()
    
    def on_close_window(self):
        """Обработчик закрытия главного окна"""
        # Всегда закрываем приложение при закрытии окна
        self.quit_app()
    
    def _on_drop_files_callback(self, files: List[str]) -> None:
        """Обработчик сброса файлов."""
        self._process_dropped_files(files)
    
    def setup_drag_drop(self):
        """Настройка drag and drop для файлов из проводника"""
        setup_drag_drop_util(self.root, self._on_drop_files_callback)
        
        # Дополнительная настройка для совместимости
        if HAS_TKINTERDND2:
            try:
                # Проверяем, что root поддерживает drag and drop
                if not hasattr(self.root, 'drop_target_register'):
                    # Если root не поддерживает DnD, возможно он создан как обычный tk.Tk()
                    if not hasattr(self, '_drag_drop_logged'):
                        self.log("Перетаскивание файлов из проводника недоступно")
                        self.log("💡 Перезапустите программу для активации drag and drop")
                        self.log("💡 Убедитесь, что tkinterdnd2 установлена: pip install tkinterdnd2")
                        self._drag_drop_logged = True
                    return
                
                # Регистрируем окно как цель для перетаскивания файлов
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind('<<Drop>>', self._on_drop_files)
                
                # Регистрируем левую панель (где находится таблица)
                # Получаем родительский фрейм таблицы
                try:
                    if hasattr(self.tree.master, 'master'):
                        left_panel = self.tree.master.master
                    else:
                        left_panel = self.tree.master
                    if hasattr(left_panel, 'drop_target_register'):
                        left_panel.drop_target_register(DND_FILES)
                        left_panel.dnd_bind('<<Drop>>', self._on_drop_files)
                    
                    # Также регистрируем фрейм списка файлов
                    list_frame = self.tree.master
                    if hasattr(list_frame, 'drop_target_register'):
                        list_frame.drop_target_register(DND_FILES)
                        list_frame.dnd_bind('<<Drop>>', self._on_drop_files)
                except Exception as e:
                    logger.debug(f"Не удалось зарегистрировать drag and drop для панелей: {e}")
                
                # Регистрируем таблицу для перетаскивания файлов
                # ttk.Treeview может не поддерживать напрямую, но попробуем
                try:
                    if hasattr(self.tree, 'drop_target_register'):
                        self.tree.drop_target_register(DND_FILES)
                        self.tree.dnd_bind('<<Drop>>', self._on_drop_files)
                except Exception as e:
                    logger.debug(f"Не удалось зарегистрировать drag and drop для treeview: {e}")
                
                # Логируем успешную настройку (только при первом запуске)
                if not hasattr(self, '_drag_drop_logged'):
                    msg = "✅ Drag and drop файлов включен - можно перетаскивать файлы из проводника"
                    self.log(msg)
                    self._drag_drop_logged = True
                return
            except Exception as e:
                logger.error(f"Ошибка настройки drag and drop (tkinterdnd2): {e}", exc_info=True)
                error_msg = f"Ошибка настройки drag and drop (tkinterdnd2): {e}"
                if not hasattr(self, '_drag_drop_logged'):
                    self.log(error_msg)
                    self.log("💡 Установите библиотеку: pip install tkinterdnd2")
                    self._drag_drop_logged = True
        
        # Если ничего не сработало
        if not hasattr(self, '_drag_drop_logged'):
            self.log("Перетаскивание файлов из проводника недоступно")
            self.log("💡 Для включения установите: pip install tkinterdnd2")
            self.log("💡 Или используйте кнопки 'Добавить файлы' / 'Добавить папку'")
            self.log("💡 Перестановка файлов в таблице доступна - перетащите строку мышью")
            self._drag_drop_logged = True
    
    def _on_drop_files(self, event):
        """Обработка события перетаскивания файлов"""
        # Сразу выводим в консоль для отладки
        # print("=== DRAG AND DROP EVENT TRIGGERED ===")
        
        try:
            # Получаем данные из события
            data = event.data
            # print(f"Event data received: {type(data)}, length: {len(data) if data else 0}")
            
            # tkinterdnd2 на Windows возвращает файлы в формате: {file1} {file2} {file3}
            # Где каждый файл заключен в фигурные скобки
            processed_files = []
            
            # Логируем исходные данные для отладки
            if not data:
                error_msg = "Данные не получены из события перетаскивания"
                self.log(error_msg)
                return
            
            # Разбираем по фигурным скобкам (стандартный формат tkinterdnd2)
            # Формат: {C:\path\file1.ext} {C:\path\file2.ext} ...
            file_paths = []
            
            # Используем более надёжный метод разбора путей
            import re
            
            # Метод 1: Ищем все паттерны {путь} - основной формат tkinterdnd2
            # Используем нежадное совпадение, чтобы правильно обрабатывать множественные пути
            pattern = r'\{([^}]+)\}'
            matches = re.findall(pattern, data)
            
            if matches:
                # Найдены пути в фигурных скобках - это основной формат tkinterdnd2
                file_paths = [match.strip() for match in matches if match.strip()]
                self.log(f"Найдено путей в фигурных скобках: {len(file_paths)}")
            else:
                # Метод 2: Если нет фигурных скобок, пробуем другие форматы
                if data.strip():
                    # Убираем внешние кавычки, если есть
                    data_clean = data.strip().strip('"').strip("'")
                    
                    # Проверяем, является ли это одним существующим путем
                    if os.path.exists(data_clean):
                        file_paths = [data_clean]
                        self.log("Найден один путь без скобок")
                    else:
                        # Метод 3: Пробуем разделить по пробелам (может не сработать для путей с пробелами)
                        parts = data.split()
                        for part in parts:
                            part_clean = part.strip('"').strip("'").strip('{}')
                            if part_clean and (os.path.exists(part_clean) or os.path.isfile(part_clean)):
                                file_paths.append(part_clean)
            
            # Метод 4: Если всё ещё пусто, пробуем как один файл (может быть путь с пробелами без скобок)
            if not file_paths and data.strip():
                data_clean = data.strip().strip('"').strip("'").strip('{}')
                if data_clean:
                    file_paths = [data_clean]
                    self.log("Пробую как один путь")
            
            self.log(f"Всего найдено путей для обработки: {len(file_paths)}")
            
            # Обрабатываем каждый путь
            skipped_count = 0
            files_found = 0
            folders_found = 0
            
            for i, file_path in enumerate(file_paths):
                # Очищаем путь от лишних символов
                original_path = file_path
                file_path = file_path.strip('{}').strip('"').strip("'").strip()
                
                if not file_path:
                    skipped_count += 1
                    continue
                
                # Нормализуем путь (преобразуем в абсолютный и стандартизируем)
                try:
                    if not os.path.isabs(file_path):
                        # Если относительный путь, пробуем преобразовать
                        file_path = os.path.abspath(file_path)
                    else:
                        file_path = os.path.normpath(file_path)
                except Exception as e:
                    self.log(f"Ошибка нормализации пути '{original_path}': {e}")
                    skipped_count += 1
                    continue
                
                # Проверяем существование
                if os.path.exists(file_path):
                    if os.path.isfile(file_path):
                        processed_files.append(file_path)
                        files_found += 1
                    elif os.path.isdir(file_path):
                        # Если папка, добавляем все файлы рекурсивно
                        folder_file_count = 0
                        try:
                            for root, dirs, filenames in os.walk(file_path):
                                for filename in filenames:
                                    full_path = os.path.join(root, filename)
                                    processed_files.append(full_path)
                                    folder_file_count += 1
                            folders_found += 1
                            self.log(f"Из папки '{os.path.basename(file_path)}' найдено: {folder_file_count} файлов")
                        except Exception as e:
                            self.log(f"Ошибка при обработке папки '{file_path}': {e}")
                else:
                    # Логируем несуществующие пути
                    skipped_count += 1
                    self.log(f"Путь не найден: {file_path}")
            
            # Выводим итоговую статистику
            if skipped_count > 0:
                self.log(f"Пропущено несуществующих/ошибочных путей: {skipped_count}")
            
            if files_found > 0:
                self.log(f"Найдено файлов: {files_found}")
            if folders_found > 0:
                self.log(f"Обработано папок: {folders_found}")
            
            self.log(f"Всего файлов готово к добавлению: {len(processed_files)}")
            
            if processed_files:
                self._process_dropped_files(processed_files)
            else:
                self.log("Не найдено файлов для добавления. Проверьте пути в логе выше.")
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            self.log(f"❌ Ошибка при обработке перетащенных файлов: {error_msg}")
            print(f"Ошибка drag and drop:\n{traceback.format_exc()}")
    
    def _process_dropped_files(self, files):
        """Обработка перетащенных файлов"""
        if not files:
            self.log("Список файлов пуст")
            return
        
        files_before = len(self.files)
        skipped = 0
        
        for file_path in files:
            if os.path.isfile(file_path):
                self.add_file(file_path)
            else:
                skipped += 1
                self.log(f"Пропущен (не файл): {file_path}")
        
        # Обновляем интерфейс после добавления всех файлов
        self.refresh_treeview()
        self.update_status()
        
        # Подсчитываем реальное количество добавленных файлов
        files_after = len(self.files)
        actual_count = files_after - files_before
        
        if actual_count > 0:
            msg = f"✅ Добавлено файлов перетаскиванием: {actual_count}"
            if skipped > 0:
                msg += f" (пропущено: {skipped})"
            self.log(msg)
        else:
            msg = "Не удалось добавить файлы (возможно, все файлы уже в списке)"
            self.log(msg)
    
    def setup_treeview_drag_drop(self):
        """Настройка drag and drop для перестановки файлов в таблице"""
        # Переменные для отслеживания перетаскивания
        self.drag_item = None
        self.drag_start_index = None
        self.drag_start_y = None
        self.is_dragging = False
        
        # Привязка событий для drag and drop внутри таблицы
        # Используем отдельные привязки, чтобы не конфликтовать с обычным кликом
        self.tree.bind('<Button-1>', self.on_treeview_button_press, add='+')
        self.tree.bind('<B1-Motion>', self.on_treeview_drag_motion, add='+')
        self.tree.bind('<ButtonRelease-1>', self.on_treeview_drag_release, add='+')
    
    def on_treeview_button_press(self, event):
        """Начало нажатия кнопки мыши (определяем начало перетаскивания)"""
        # Проверяем, что клик по строке, а не по заголовку
        item = self.tree.identify_row(event.y)
        region = self.tree.identify_region(event.x, event.y)
        
        # Игнорируем клики по заголовкам и другим областям
        if region == "heading" or region == "separator":
            return
        
        if item:
            self.drag_item = item
            self.drag_start_index = self.tree.index(item)
            self.drag_start_y = event.y
            self.is_dragging = False
    
    def on_treeview_drag_motion(self, event):
        """Перемещение при перетаскивании строки"""
        if self.drag_item is None:
            return
        
        # Проверяем, что мышь переместилась достаточно далеко для начала перетаскивания
        if not self.is_dragging:
            if self.drag_start_y is not None and abs(event.y - self.drag_start_y) > 5:
                self.is_dragging = True
                # Выделяем исходный элемент
                self.tree.selection_set(self.drag_item)
        
        if self.is_dragging:
            item = self.tree.identify_row(event.y)
            if item and item != self.drag_item:
                # Визуальная индикация текущей позиции
                self.tree.selection_set(item)
                # Прокручиваем к элементу, если он вне видимой области
                self.tree.see(item)
    
    def on_treeview_drag_release(self, event):
        """Завершение перетаскивания строки"""
        if self.drag_item and self.is_dragging:
            target_item = self.tree.identify_row(event.y)
            
            if target_item and target_item != self.drag_item:
                try:
                    # Получаем индексы
                    start_idx = self.tree.index(self.drag_item)
                    target_idx = self.tree.index(target_item)
                    
                    # Перемещаем элемент в списке и в дереве
                    if 0 <= start_idx < len(self.files) and 0 <= target_idx < len(self.files):
                        # Перемещаем в списке файлов
                        file_data = self.files.pop(start_idx)
                        self.files.insert(target_idx, file_data)
                        
                        # Обновляем дерево
                        self.refresh_treeview()
                        
                        # Выделяем перемещенный элемент
                        children = self.tree.get_children()
                        if target_idx < len(children):
                            self.tree.selection_set(children[target_idx])
                            self.tree.see(children[target_idx])  # Прокручиваем к элементу
                        
                        self.log(f"Файл '{file_data['old_name']}' перемещен с позиции {start_idx + 1} на {target_idx + 1}")
                except Exception as e:
                    self.log(f"Ошибка при перемещении файла: {e}")
        
        # Сброс состояния
        self.drag_item = None
        self.drag_start_index = None
        self.drag_start_y = None
        self.is_dragging = False
    
    def refresh_treeview(self):
        """Обновление таблицы для синхронизации с списком файлов"""
        # Удаляем все элементы
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Добавляем элементы в правильном порядке
        for file_data in self.files:
            status = file_data.get('status', 'Готов')
            tags = ()
            if status == "Готов":
                tags = ('ready',)
            elif "Ошибка" in status:
                tags = ('error',)
            elif "Конфликт" in status:
                tags = ('conflict',)
            
            self.tree.insert("", tk.END, values=(
                file_data['old_name'],
                file_data['new_name'],
                file_data['extension'],
                file_data['path'],
                status
            ), tags=tags)
        
        # Обновляем видимость скроллбаров после обновления содержимого
        if hasattr(self, 'tree_scrollbar_y') and hasattr(self, 'tree_scrollbar_x'):
            self.root.after_idle(lambda: self.update_scrollbar_visibility(self.tree, self.tree_scrollbar_y, 'vertical'))
            self.root.after_idle(lambda: self.update_scrollbar_visibility(self.tree, self.tree_scrollbar_x, 'horizontal'))
    
    def log(self, message: str):
        """Добавление сообщения в лог"""
        self.logger.log(message)
    
    def clear_log(self):
        """Очистка лога операций"""
        self.logger.clear()
    
    def save_log(self):
        """Сохранение/выгрузка лога в файл"""
        self.logger.save()
    
    def add_files(self):
        """Добавление файлов через диалог выбора"""
        files = filedialog.askopenfilenames(title="Выберите файлы")
        if files:
            files_before = len(self.files)
            for file_path in files:
                self.add_file(file_path)
            # Обновляем интерфейс
            self.refresh_treeview()
            self.update_status()
            actual_count = len(self.files) - files_before
            self.log(f"Добавлено файлов: {actual_count}")
    
    def add_folder(self):
        """Добавление папки с рекурсивным поиском"""
        folder = filedialog.askdirectory(title="Выберите папку")
        if folder:
            count = 0
            for root, dirs, files in os.walk(folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    self.add_file(file_path)
                    count += 1
            self.update_status()
            self.log(f"Добавлено файлов из папки: {count}")
    
    def add_file(self, file_path: str):
        """Добавление одного файла в список"""
        if not os.path.isfile(file_path):
            return
        
        # Нормализуем путь для проверки дубликатов
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # Проверяем, нет ли уже такого файла в списке
        for existing_file in self.files:
            existing_path = os.path.normpath(os.path.abspath(existing_file.get('full_path', '')))
            if existing_path == file_path:
                # Файл уже есть в списке, пропускаем
                return
        
        path_obj = Path(file_path)
        old_name = path_obj.stem
        extension = path_obj.suffix
        path = str(path_obj.parent)
        
        file_data = {
            'path': path,
            'old_name': old_name,
            'new_name': old_name,
            'extension': extension,
            'full_path': file_path,
            'status': 'Готов'
        }
        
        self.files.append(file_data)
    
    def clear_files(self):
        """Очистка списка файлов"""
        if self.files:
            if messagebox.askyesno("Подтверждение", "Очистить список файлов?"):
                self.files.clear()
                for item in self.tree.get_children():
                    self.tree.delete(item)
                self.update_status()
                self.log("Список файлов очищен")
    
    def delete_selected(self):
        """Удаление выбранных файлов из списка"""
        selected = self.tree.selection()
        if selected:
            for item in selected:
                index = self.tree.index(item)
                self.tree.delete(item)
                if index < len(self.files):
                    self.files.pop(index)
            self.update_status()
            self.log(f"Удалено файлов из списка: {len(selected)}")
    
    def update_status(self):
        """Обновление статусной строки"""
        count = len(self.files)
        if hasattr(self, 'left_panel'):
            self.left_panel.config(text=f"Список файлов (Файлов: {count})")
    
    def sort_column(self, col: str):
        """Сортировка по колонке"""
        items = [(self.tree.set(item, col), item) for item in self.tree.get_children("")]
        items.sort()
        
        for index, (val, item) in enumerate(items):
            self.tree.move(item, "", index)
    
    def on_method_selected(self, event=None):
        """Обработка выбора метода переименования"""
        # Очистка области настроек
        for widget in self.settings_frame.winfo_children():
            widget.destroy()
        
        method_name = self.method_var.get()
        
        # Показываем/скрываем кнопки шаблонов в зависимости от метода
        if hasattr(self, 'template_buttons_frame'):
            if method_name == "Новое имя":
                self.template_buttons_frame.pack(fill=tk.X, pady=(0, 6))
            else:
                self.template_buttons_frame.pack_forget()
        
        if method_name == "Новое имя":
            self.create_new_name_settings()
        elif method_name == "Добавить/Удалить":
            self.create_add_remove_settings()
        elif method_name == "Замена":
            self.create_replace_settings()
        elif method_name == "Регистр":
            self.create_case_settings()
        elif method_name == "Нумерация":
            self.create_numbering_settings()
        elif method_name == "Метаданные":
            self.create_metadata_settings()
        elif method_name == "Регулярные выражения":
            self.create_regex_settings()
        
        # Обновляем scrollregion и видимость скроллбара после создания содержимого
        if hasattr(self, 'update_scroll_region'):
            self.root.after(10, self.update_scroll_region)
    
    def create_add_remove_settings(self):
        """Создание настроек для метода Добавить/Удалить"""
        ttk.Label(self.settings_frame, text="Операция:", font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        self.add_remove_op = tk.StringVar(value="add")
        ttk.Radiobutton(
            self.settings_frame, text="Добавить текст",
            variable=self.add_remove_op, value="add", font=('Robot', 9)
        ).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(
            self.settings_frame, text="Удалить текст",
            variable=self.add_remove_op, value="remove", font=('Robot', 9)
        ).pack(anchor=tk.W, pady=1)
        
        ttk.Label(self.settings_frame, text="Текст:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.add_remove_text = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.add_remove_text.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Позиция:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.add_remove_pos = tk.StringVar(value="before")
        ttk.Radiobutton(
            self.settings_frame, text="Перед именем",
            variable=self.add_remove_pos, value="before", font=('Robot', 9)
        ).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(
            self.settings_frame, text="После имени",
            variable=self.add_remove_pos, value="after", font=('Robot', 9)
        ).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.add_remove_pos, value="start", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.add_remove_pos, value="end", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        
        # Для удаления
        ttk.Label(self.settings_frame, text="Удалить (если выбрано удаление):", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.remove_type = tk.StringVar(value="chars")
        ttk.Radiobutton(self.settings_frame, text="N символов", variable=self.remove_type, value="chars", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Диапазон", variable=self.remove_type, value="range", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        
        ttk.Label(self.settings_frame, text="Количество/Начало:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.remove_start = ttk.Entry(self.settings_frame, width=10, font=('Robot', 9))
        self.remove_start.pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Конец (для диапазона):", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.remove_end = ttk.Entry(self.settings_frame, width=10, font=('Robot', 9))
        self.remove_end.pack(anchor=tk.W, pady=(0, 4))
    
    def get_file_types(self):
        """Определение типов файлов в списке"""
        if not self.files:
            return {}
        
        extensions = {}
        for file_data in self.files:
            ext = file_data['extension'].lower()
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
        
        return extensions
    
    def get_suggested_templates(self):
        """Получение рекомендуемых шаблонов на основе типов файлов"""
        extensions = self.get_file_types()
        if not extensions:
            return []
        
        # Определяем доминирующий тип
        main_ext = max(extensions.items(), key=lambda x: x[1])[0]
        
        templates = []
        
        # Шаблоны для изображений
        image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic']
        if main_ext in image_exts:
            templates.extend([
                ("Фото_{n:03d}", "Фото_001, Фото_002, ..."),
                ("IMG_{n:03d}", "IMG_001, IMG_002, ..."),
                ("{date_created}_Фото_{n:02d}", "2024-01-01_Фото_01, ..."),
                ("{width}x{height}_{n}", "1920x1080_1, ..."),
                ("Photo_{n:04d}", "Photo_0001, Photo_0002, ..."),
                ("Изображение_{n}", "Изображение_1, Изображение_2, ..."),
            ])
        
        # Шаблоны для документов
        doc_exts = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt']
        if main_ext in doc_exts:
            templates.extend([
                ("Документ_{n:03d}", "Документ_001, Документ_002, ..."),
                ("Doc_{n:03d}", "Doc_001, Doc_002, ..."),
                ("{date_created}_Документ_{n}", "2024-01-01_Документ_1, ..."),
                ("Файл_{n:02d}", "Файл_01, Файл_02, ..."),
                ("Document_{n:04d}", "Document_0001, ..."),
            ])
        
        # Шаблоны для видео
        video_exts = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']
        if main_ext in video_exts:
            templates.extend([
                ("Видео_{n:03d}", "Видео_001, Видео_002, ..."),
                ("Video_{n:03d}", "Video_001, Video_002, ..."),
                ("{date_created}_Видео_{n}", "2024-01-01_Видео_1, ..."),
                ("Clip_{n:02d}", "Clip_01, Clip_02, ..."),
                ("Movie_{n:04d}", "Movie_0001, Movie_0002, ..."),
            ])
        
        # Шаблоны для аудио
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']
        if main_ext in audio_exts:
            templates.extend([
                ("Аудио_{n:03d}", "Аудио_001, Аудио_002, ..."),
                ("Audio_{n:03d}", "Audio_001, Audio_002, ..."),
                ("Track_{n:02d}", "Track_01, Track_02, ..."),
                ("{date_created}_Трек_{n}", "2024-01-01_Трек_1, ..."),
                ("Song_{n:04d}", "Song_0001, Song_0002, ..."),
            ])
        
        # Шаблоны для архивов
        archive_exts = ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']
        if main_ext in archive_exts:
            templates.extend([
                ("Архив_{n:03d}", "Архив_001, Архив_002, ..."),
                ("Archive_{n:03d}", "Archive_001, Archive_002, ..."),
                ("{date_created}_Архив_{n}", "2024-01-01_Архив_1, ..."),
                ("Backup_{n:02d}", "Backup_01, Backup_02, ..."),
            ])
        
        # Шаблоны для таблиц и данных
        data_exts = ['.xlsx', '.xls', '.csv', '.json', '.xml']
        if main_ext in data_exts:
            templates.extend([
                ("Данные_{n:03d}", "Данные_001, Данные_002, ..."),
                ("Data_{n:03d}", "Data_001, Data_002, ..."),
                ("{date_created}_Данные_{n}", "2024-01-01_Данные_1, ..."),
                ("Table_{n:02d}", "Table_01, Table_02, ..."),
            ])
        
        # Универсальные шаблоны
        templates.extend([
            ("Файл_{n:03d}", "Файл_001, Файл_002, ..."),
            ("{n:04d}", "0001, 0002, 0003, ..."),
            ("Новый_{n:03d}", "Новый_001, Новый_002, ..."),
            ("{date_created}_{n:02d}", "2024-01-01_01, 2024-01-01_02, ..."),
            ("{date_modified}_{name}", "2024-01-01_старое_имя, ..."),
            ("{name}_{n:03d}", "старое_имя_001, старое_имя_002, ..."),
            ("{n:02d}_{name}", "01_старое_имя, 02_старое_имя, ..."),
        ])
        
        return templates
    
    def create_new_name_settings(self):
        """Создание настроек для метода Новое имя"""
        # Показываем кнопки шаблонов в общей группе кнопок
        if hasattr(self, 'template_buttons_frame'):
            self.template_buttons_frame.pack(fill=tk.X, pady=(0, 6))
        
        # Поле ввода шаблона
        template_label_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        template_label_frame.pack(fill=tk.X, pady=(0, 2))
        
        template_label = tk.Label(template_label_frame, text="Новое имя (шаблон):", 
                                 font=('Robot', 9, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        template_label.pack(side=tk.LEFT)
        
        self.new_name_template = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.new_name_template.pack(fill=tk.X, pady=(0, 4))
        
        # Настройка начального номера
        number_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        number_frame.pack(fill=tk.X, pady=(0, 4))
        
        number_label = tk.Label(number_frame, text="Начальный номер для {n}:", 
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        number_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.new_name_start_number = ttk.Entry(number_frame, width=10, font=('Robot', 9))
        self.new_name_start_number.insert(0, "1")
        self.new_name_start_number.pack(side=tk.LEFT, padx=(0, 5))
        
        # Подсказка
        hint_label = tk.Label(number_frame, 
                             text="(для {n}, {n:02d}, {n:03d} и т.д.)",
                             font=('Robot', 8),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_secondary'])
        hint_label.pack(side=tk.LEFT)
        
        # Автоматическое применение при изменении шаблона или начального номера
        # Используем переменную для отслеживания таймера, чтобы избежать множественных вызовов
        if not hasattr(self, '_template_change_timer'):
            self._template_change_timer = None
        
        def on_template_change(event=None):
            # Отменяем предыдущий таймер, если он есть
            if hasattr(self, '_template_change_timer') and self._template_change_timer:
                try:
                    self.root.after_cancel(self._template_change_timer)
                except (tk.TclError, ValueError) as e:
                    logger.debug(f"Не удалось отменить таймер в on_template_change: {e}")
            # Устанавливаем новый таймер для применения через 150 мс (быстрее для мгновенного отображения)
            if hasattr(self, 'root'):
                self._template_change_timer = self.root.after(150, self._apply_template_delayed)
        
        def on_number_change(event=None):
            # Отменяем предыдущий таймер, если он есть
            if hasattr(self, '_template_change_timer') and self._template_change_timer:
                try:
                    self.root.after_cancel(self._template_change_timer)
                except (tk.TclError, ValueError) as e:
                    logger.debug(f"Не удалось отменить таймер в on_number_change: {e}")
            # Устанавливаем новый таймер для применения через 150 мс (быстрее для мгновенного отображения)
            if hasattr(self, 'root'):
                self._template_change_timer = self.root.after(150, self._apply_template_delayed)
        
        # Привязка событий
        self.new_name_template.bind('<KeyRelease>', on_template_change)
        self.new_name_template.bind('<FocusOut>', lambda e: self._apply_template_immediate())
        self.new_name_start_number.bind('<KeyRelease>', on_number_change)
        self.new_name_start_number.bind('<FocusOut>', lambda e: self._apply_template_immediate())
        
        # Если шаблон уже есть в поле, применяем его сразу
        if hasattr(self, 'new_name_template'):
            template = self.new_name_template.get().strip()
            if template and self.files:
                # Применяем шаблон с небольшой задержкой после создания виджетов
                self.root.after(100, lambda: self._apply_template_immediate())
        
        # Предупреждение
        warning_frame = tk.Frame(self.settings_frame, bg='#FEF3C7', 
                                relief='flat', borderwidth=1,
                                highlightbackground='#FCD34D',
                                highlightthickness=1)
        warning_frame.pack(fill=tk.X, pady=(4, 4))
        
        warning_label = tk.Label(warning_frame, text="БЕЗ {name} - имя полностью заменяется!", 
                               font=('Robot', 9, 'bold'),
                               bg='#FEF3C7', fg='#92400E',
                               padx=10, pady=6)
        warning_label.pack(anchor=tk.W)
        
        # Кликабельные переменные
        vars_label = tk.Label(self.settings_frame, 
                             text="Доступные переменные (кликните для вставки):", 
                             font=('Robot', 9, 'bold'),
                             bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        vars_label.pack(anchor=tk.W, pady=(4, 4))
        
        variables_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        variables_frame.pack(fill=tk.X, pady=(0, 0))
        
        # Контейнер для переменных с фоном
        vars_container = tk.Frame(variables_frame, bg=self.colors['bg_secondary'], 
                                 relief='flat', borderwidth=1,
                                 highlightbackground=self.colors['border'],
                                 highlightthickness=1)
        vars_container.pack(fill=tk.X, padx=0, pady=(0, 0))
        
        # Список переменных с описаниями
        variables = [
            ("{name}", "старое имя"),
            ("{ext}", "расширение"),
            ("{n}", "номер файла"),
            ("{n:03d}", "номер с нулями (001, 002)"),
            ("{n:02d}", "номер с нулями (01, 02)"),
            ("{width}x{height}", "размеры изображения"),
            ("{width}", "ширина изображения"),
            ("{height}", "высота изображения"),
            ("{date_created}", "дата создания"),
            ("{date_modified}", "дата изменения"),
            ("{file_size}", "размер файла")
        ]
        
        # Создание кликабельных меток для переменных
        for i, (var, desc) in enumerate(variables):
            var_frame = tk.Frame(vars_container, bg=self.colors['bg_secondary'])
            # Уменьшаем отступ для последнего элемента
            if i == len(variables) - 1:
                var_frame.pack(anchor=tk.W, pady=(2, 0), padx=8, fill=tk.X)
            else:
                var_frame.pack(anchor=tk.W, pady=2, padx=8, fill=tk.X)
            
            # Кликабельная метка с переменной
            var_label = tk.Label(var_frame, text=f"  {var}", 
                               font=('Courier New', 11, 'bold'), 
                               foreground=self.colors['primary'], 
                               cursor="hand2",
                               bg=self.colors['bg_secondary'])
            var_label.pack(side=tk.LEFT)
            var_label.bind("<Button-1>", lambda e, v=var: self.insert_variable(v))
            def on_enter(event, label=var_label):
                label.config(underline=True,
                           fg=self.colors['primary_hover'])
            
            def on_leave(event, label=var_label):
                label.config(underline=False,
                           fg=self.colors['primary'])
            
            var_label.bind("<Enter>", on_enter)
            var_label.bind("<Leave>", on_leave)
            
            # Описание
            desc_label = tk.Label(var_frame, text=f"- {desc}", 
                                 font=('Robot', 10),
                                 foreground=self.colors['text_secondary'],
                                 bg=self.colors['bg_secondary'])
            desc_label.pack(side=tk.LEFT, padx=(10, 0))
    
    def insert_variable(self, variable: str):
        """Вставка переменной в поле шаблона"""
        if hasattr(self, 'new_name_template'):
            current_text = self.new_name_template.get()
            cursor_pos = self.new_name_template.index(tk.INSERT)
            new_text = current_text[:cursor_pos] + variable + current_text[cursor_pos:]
            self.new_name_template.delete(0, tk.END)
            self.new_name_template.insert(0, new_text)
            # Устанавливаем курсор после вставленной переменной
            self.new_name_template.icursor(cursor_pos + len(variable))
            self.new_name_template.focus()
            
            # Автоматически применяем шаблон сразу после вставки переменной
            if hasattr(self, 'root') and self.files:
                # Применяем с небольшой задержкой, чтобы пользователь увидел вставленную переменную
                self.root.after(100, self._apply_template_immediate)
    
    def show_quick_templates(self):
        """Показать окно с быстрыми шаблонами"""
        try:
            templates = self.get_suggested_templates()
            
            if not templates:
                messagebox.showinfo(
                    "Шаблоны",
                    "Добавьте файлы для предложения шаблонов"
                )
                return
            
            # Создание окна выбора шаблона
            template_window = tk.Toplevel(self.root)
            template_window.title("Быстрые шаблоны")
            template_window.geometry("500x400")
            template_window.transient(self.root)  # Делаем окно модальным относительно главного
            template_window.grab_set()  # Захватываем фокус
            
            # Установка иконки
            try:
                set_window_icon(template_window, self._icon_photos)
            except Exception:
                pass
            
            # Убеждаемся, что окно видимо
            template_window.update()
            template_window.deiconify()
            
            # Настройка фона окна
            template_window.configure(bg=self.colors['bg_main'])
            
            # Информация о типах файлов
            extensions = self.get_file_types()
            ext_info = ", ".join([f"{ext} ({count})" for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:5]])
            info_label = tk.Label(template_window, text=f"Типы файлов: {ext_info}", 
                                 font=('Robot', 9),
                                 bg=self.colors['bg_main'], 
                                 fg=self.colors['text_primary'])
            info_label.pack(pady=5)
            
            # Список шаблонов
            listbox_frame = tk.Frame(template_window, bg=self.colors['bg_main'])
            listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, 
                                font=('Robot', 10),
                                bg='white', fg='black',
                                selectbackground=self.colors['primary'],
                                selectforeground='white',
                                relief=tk.SOLID,
                                borderwidth=1)
            scrollbar.config(command=listbox.yview)
            
            for template, description in templates:
                listbox.insert(tk.END, f"{template:30s} → {description}")
            
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Автоматическое управление видимостью скроллбара
            def update_template_scrollbar(*args):
                self.update_scrollbar_visibility(listbox, scrollbar, 'vertical')
            
            listbox.bind('<Configure>', lambda e: template_window.after_idle(update_template_scrollbar))
            template_window.after(100, update_template_scrollbar)
            
            # Убеждаемся, что окно видимо
            template_window.update()
            template_window.deiconify()  # Показываем окно, если оно было скрыто
            
            # Кнопки
            btn_frame = tk.Frame(template_window, bg=self.colors['bg_main'])
            btn_frame.pack(fill=tk.X, padx=10, pady=5)
            
            def select_template():
                selection = listbox.curselection()
                if selection:
                    selected = listbox.get(selection[0])
                    template = selected.split("→")[0].strip()
                    self.new_name_template.delete(0, tk.END)
                    self.new_name_template.insert(0, template)
                    template_window.destroy()
                    self.log(f"Выбран шаблон: {template}")
                    # Немедленно применяем шаблон
                    self.apply_template_quick(auto=True)
            
            btn_select = self.create_rounded_button(
                btn_frame, "Выбрать", select_template,
                self.colors['primary'], 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg=self.colors['primary_hover'])
            btn_select.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            btn_cancel = self.create_rounded_button(
                btn_frame, "Отмена", template_window.destroy,
                '#818CF8', 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg='#6366F1')
            btn_cancel.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            
            # Двойной клик для выбора
            listbox.bind('<Double-Button-1>', lambda e: select_template())
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть окно быстрых шаблонов:\n{e}")
            if hasattr(self, 'log'):
                self.log(f"Ошибка открытия быстрых шаблонов: {e}")
    
    def save_current_template(self):
        """Сохранение текущего шаблона"""
        if not hasattr(self, 'new_name_template'):
            return
        
        template = self.new_name_template.get().strip()
        if not template:
            messagebox.showwarning("Предупреждение", "Введите шаблон для сохранения")
            return
        
        # Запрашиваем имя для шаблона
        template_name = simpledialog.askstring(
            "Сохранить шаблон",
            "Введите имя для шаблона:",
            initialvalue=template[:30]  # Предлагаем первые 30 символов
        )
        
        if template_name:
            template_name = template_name.strip()
            if template_name:
                # Получаем начальный номер, если есть
                start_number = "1"
                if hasattr(self, 'new_name_start_number'):
                    start_number = self.new_name_start_number.get().strip() or "1"
                
                # Сохраняем шаблон
                self.saved_templates[template_name] = {
                    'template': template,
                    'start_number': start_number
                }
                # Обновляем в менеджере шаблонов
                self.templates_manager.templates = self.saved_templates
                self.save_templates()
                # Автосохранение шаблонов
                self.templates_manager.save_templates(self.saved_templates)
                self.log(f"Шаблон '{template_name}' сохранен")
                messagebox.showinfo("Успех", f"Шаблон '{template_name}' успешно сохранен!")
    
    def show_saved_templates(self):
        """Показать окно с сохраненными шаблонами"""
        try:
            # Обновляем список шаблонов из менеджера
            self.saved_templates = self.templates_manager.templates
            
            if not self.saved_templates:
                messagebox.showinfo("Информация", "Нет сохраненных шаблонов")
                return
            
            # Создание окна выбора шаблона
            template_window = tk.Toplevel(self.root)
            template_window.title("Сохраненные шаблоны")
            template_window.geometry("600x500")
            template_window.transient(self.root)  # Делаем окно модальным относительно главного
            template_window.grab_set()  # Захватываем фокус
            
            # Установка иконки
            try:
                set_window_icon(template_window, self._icon_photos)
            except Exception:
                pass
            
            # Настройка фона окна
            template_window.configure(bg=self.colors['bg_main'])
            
            # Заголовок
            header_frame = tk.Frame(template_window, bg=self.colors['bg_main'])
            header_frame.pack(fill=tk.X, padx=10, pady=10)
            
            title_label = tk.Label(header_frame, text="Сохраненные шаблоны", 
                                  font=('Robot', 14, 'bold'),
                                  bg=self.colors['bg_main'], fg=self.colors['text_primary'])
            title_label.pack(anchor=tk.W)
            
            # Список шаблонов
            list_frame = tk.Frame(template_window, bg=self.colors['bg_main'])
            list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
            
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                font=('Robot', 10),
                                bg='white', fg='black',
                                selectbackground=self.colors['primary'],
                                selectforeground='white',
                                relief=tk.SOLID,
                                borderwidth=1)
            scrollbar.config(command=listbox.yview)
            
            # Заполняем список шаблонов
            template_keys = sorted(self.saved_templates.keys())
            for template_name in template_keys:
                template_data = self.saved_templates[template_name]
                if isinstance(template_data, dict):
                    template = template_data.get('template', '')
                else:
                    template = str(template_data)
                display_text = f"{template_name} → {template}"
                listbox.insert(tk.END, display_text)
            
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Автоматическое управление видимостью скроллбара
            def update_saved_template_scrollbar(*args):
                self.update_scrollbar_visibility(listbox, scrollbar, 'vertical')
            
            listbox.bind('<Configure>', lambda e: template_window.after_idle(update_saved_template_scrollbar))
            template_window.after(100, update_saved_template_scrollbar)
            
            # Убеждаемся, что окно видимо
            template_window.update()
            template_window.deiconify()  # Показываем окно, если оно было скрыто
            
            # Кнопки
            btn_frame = tk.Frame(template_window, bg=self.colors['bg_main'])
            btn_frame.pack(fill=tk.X, padx=10, pady=10)
            btn_frame.columnconfigure(0, weight=1)
            btn_frame.columnconfigure(1, weight=1)
            btn_frame.columnconfigure(2, weight=1)
            btn_frame.columnconfigure(3, weight=1)
            btn_frame.columnconfigure(4, weight=1)
            
            def apply_template():
                selection = listbox.curselection()
                if selection:
                    template_name = sorted(self.saved_templates.keys())[selection[0]]
                    template_data = self.saved_templates[template_name]
                    template = template_data['template']
                    start_number = template_data.get('start_number', '1')
                    
                    # Применяем шаблон
                    self.new_name_template.delete(0, tk.END)
                    self.new_name_template.insert(0, template)
                    
                    if hasattr(self, 'new_name_start_number'):
                        self.new_name_start_number.delete(0, tk.END)
                        self.new_name_start_number.insert(0, start_number)
                    
                    template_window.destroy()
                    self.log(f"Применен сохраненный шаблон: {template_name}")
                    # Применяем шаблон
                    self.apply_template_quick(auto=True)
            
            def delete_template():
                selection = listbox.curselection()
                if selection:
                    template_name = sorted(self.saved_templates.keys())[selection[0]]
                    if messagebox.askyesno("Подтверждение", f"Удалить шаблон '{template_name}'?"):
                        del self.saved_templates[template_name]
                        # Обновляем в менеджере шаблонов
                        self.templates_manager.templates = self.saved_templates
                        self.save_templates()
                        # Автосохранение шаблонов
                        self.templates_manager.save_templates(self.saved_templates)
                        listbox.delete(selection[0])
                        self.log(f"Шаблон '{template_name}' удален")
                        if not self.saved_templates:
                            template_window.destroy()
                            messagebox.showinfo("Информация", "Все шаблоны удалены")
            
            btn_apply = self.create_rounded_button(
                btn_frame, "Применить", apply_template,
                self.colors['success'], 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg=self.colors['success_hover'])
            btn_apply.grid(row=0, column=0, sticky="ew", padx=(0, 5))
            
            def export_templates():
                """Выгрузка сохраненных шаблонов в JSON файл"""
                from tkinter import filedialog
                import json
                
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".json",
                    filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                    title="Сохранить шаблоны"
                )
                
                if file_path:
                    try:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            json.dump(self.saved_templates, f, ensure_ascii=False, indent=2)
                        messagebox.showinfo("Успех", f"Шаблоны успешно сохранены в:\n{file_path}")
                        self.log(f"Шаблоны выгружены в: {file_path}")
                    except Exception as e:
                        messagebox.showerror("Ошибка", f"Не удалось сохранить шаблоны:\n{e}")
                        self.log(f"Ошибка выгрузки шаблонов: {e}")
            
            btn_delete = self.create_rounded_button(
                btn_frame, "Удалить", delete_template,
                self.colors['danger'], 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg=self.colors['danger_hover'])
            btn_delete.grid(row=0, column=1, sticky="ew", padx=(0, 5))
            
            btn_export = self.create_rounded_button(
                btn_frame, "Выгрузить", export_templates,
                self.colors['primary'], 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg=self.colors['primary_hover'])
            btn_export.grid(row=0, column=2, sticky="ew", padx=(0, 5))
            
            btn_close = self.create_rounded_button(
                btn_frame, "Закрыть", template_window.destroy,
                '#818CF8', 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg='#6366F1')
            btn_close.grid(row=0, column=3, sticky="ew")
            
            # Двойной клик для применения
            listbox.bind('<Double-Button-1>', lambda e: apply_template())
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть окно сохраненных шаблонов:\n{e}")
            self.log(f"Ошибка открытия сохраненных шаблонов: {e}")
    
    def _apply_template_immediate(self):
        """Немедленное применение шаблона (при потере фокуса)"""
        if hasattr(self, 'new_name_template'):
            template = self.new_name_template.get().strip()
            if template:
                try:
                    self.apply_template_quick(auto=True)
                except Exception as e:
                    # Логируем ошибки, но не показываем пользователю при автоматическом применении
                    try:
                        if hasattr(self, 'log'):
                            self.log(f"Ошибка при применении шаблона: {e}")
                    except Exception as log_error:
                        logger.debug(f"Не удалось залогировать ошибку применения шаблона: {log_error}")
    
    def _apply_template_delayed(self):
        """Отложенное применение шаблона (используется для автоматического применения при вводе)"""
        # Сбрасываем таймер
        self._template_change_timer = None
        if hasattr(self, 'new_name_template'):
            template = self.new_name_template.get().strip()
            if template:
                try:
                    # Применяем шаблон
                    self.apply_template_quick(auto=True)
                    # Убеждаемся, что таблица обновлена
                    if hasattr(self, 'refresh_treeview'):
                        self.refresh_treeview()
                except Exception as e:
                    # Логируем ошибки, но не показываем пользователю при автоматическом применении
                    try:
                        if hasattr(self, 'log'):
                            self.log(f"Ошибка при автоматическом применении шаблона: {e}")
                    except Exception as log_error:
                        logger.debug(f"Не удалось залогировать ошибку применения шаблона: {log_error}")
    
    def apply_template_quick(self, auto=False):
        """Быстрое применение шаблона: добавление метода и применение"""
        template = self.new_name_template.get().strip()
        
        if not template:
            if not auto:
                messagebox.showwarning(
                    "Предупреждение",
                    "Введите шаблон или выберите из быстрых шаблонов"
                )
            return
        
        try:
            # Удаляем старый метод "Новое имя", если он есть
            methods_to_remove = []
            for i, method in enumerate(self.methods_manager.get_methods()):
                if isinstance(method, NewNameMethod):
                    methods_to_remove.append(i)
            
            # Удаляем в обратном порядке, чтобы индексы не сбились
            for i in reversed(methods_to_remove):
                self.methods_manager.remove_method(i)
                if i < self.methods_listbox.size():
                    self.methods_listbox.delete(i)
            
            # Создаем новый метод используя общий метод
            method = self._create_new_name_method(template)
            
            # Добавляем метод
            self.methods_manager.add_method(method)
            self.methods_listbox.insert(tk.END, "Новое имя")
            
            if not auto:
                self.log(f"Добавлен метод: Новое имя (шаблон: {template})")
            
            # Автоматически применяем метод
            if self.files:
                # Применяем методы и принудительно обновляем таблицу
                self.apply_methods()
                # Полностью обновляем таблицу для отображения изменений
                self.refresh_treeview()
                # Принудительно обновляем отображение
                self.root.update_idletasks()
            
            if not auto:
                messagebox.showinfo(
                    "Готово",
                    f"Шаблон '{template}' применен!\n"
                    f"Проверьте предпросмотр в таблице."
                )
            
        except Exception as e:
            if not auto:
                messagebox.showerror("Ошибка", f"Не удалось применить шаблон: {e}")
            else:
                # Используем try-except для логирования, так как log может быть не инициализирован
                try:
                    self.log(f"Ошибка при применении шаблона: {e}")
                except Exception as log_error:
                    logger.debug(f"Не удалось залогировать ошибку применения шаблона: {log_error}")
    
    def create_replace_settings(self):
        """Создание настроек для метода Замена"""
        ttk.Label(self.settings_frame, text="Найти:", font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        self.replace_find = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.replace_find.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Заменить на:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.replace_with = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.replace_with.pack(fill=tk.X, pady=(0, 4))
        
        self.replace_case = tk.BooleanVar()
        ttk.Checkbutton(self.settings_frame, text="Учитывать регистр", variable=self.replace_case, font=('Robot', 9)).pack(anchor=tk.W, pady=2)
        
        self.replace_full = tk.BooleanVar()
        ttk.Checkbutton(self.settings_frame, text="Только полное совпадение", variable=self.replace_full, font=('Robot', 9)).pack(anchor=tk.W, pady=2)
        
        self.replace_whole_name = tk.BooleanVar()
        ttk.Checkbutton(
            self.settings_frame,
            text="Заменить все имя (если 'Найти' = полное имя)",
            variable=self.replace_whole_name,
            font=('Robot', 9)
        ).pack(anchor=tk.W, pady=2)
    
    def create_case_settings(self) -> None:
        """Создание настроек для метода Регистр."""
        self.case_type = tk.StringVar(value="lower")
        ttk.Radiobutton(self.settings_frame, text="Верхний регистр", variable=self.case_type, value="upper", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Нижний регистр", variable=self.case_type, value="lower", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Первая заглавная", variable=self.case_type, value="capitalize", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Заглавные каждого слова", variable=self.case_type, value="title", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        
        ttk.Label(self.settings_frame, text="Применить к:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.case_apply = tk.StringVar(value="name")
        ttk.Radiobutton(self.settings_frame, text="Имени", variable=self.case_apply, value="name", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Расширению", variable=self.case_apply, value="ext", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="Всему", variable=self.case_apply, value="all", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
    
    def create_numbering_settings(self) -> None:
        """Создание настроек для метода Нумерация."""
        ttk.Label(self.settings_frame, text="Начальный индекс:", font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        self.numbering_start = ttk.Entry(self.settings_frame, width=10, font=('Robot', 9))
        self.numbering_start.insert(0, "1")
        self.numbering_start.pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Шаг:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.numbering_step = ttk.Entry(self.settings_frame, width=10, font=('Robot', 9))
        self.numbering_step.insert(0, "1")
        self.numbering_step.pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Количество цифр:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.numbering_digits = ttk.Entry(self.settings_frame, width=10, font=('Robot', 9))
        self.numbering_digits.insert(0, "3")
        self.numbering_digits.pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Формат:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.numbering_format = tk.StringVar(value="({n})")
        ttk.Entry(self.settings_frame, textvariable=self.numbering_format, width=20, font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        ttk.Label(
            self.settings_frame,
            text="(используйте {n} для номера)",
            font=('Robot', 8)
        ).pack(anchor=tk.W, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Позиция:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.numbering_pos = tk.StringVar(value="end")
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.numbering_pos, value="start", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.numbering_pos, value="end", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
    
    def create_metadata_settings(self) -> None:
        """Создание настроек для метода Метаданные."""
        if not self.metadata_extractor:
            ttk.Label(self.settings_frame, text="Модуль метаданных недоступен.\nУстановите Pillow: pip install Pillow", 
                     foreground="#000000", font=('Robot', 9)).pack(pady=10)
            return
        
        ttk.Label(self.settings_frame, text="Тег метаданных:", font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        self.metadata_tag = tk.StringVar(value="{width}x{height}")
        metadata_options = [
            "{width}x{height}",
            "{date_created}",
            "{date_modified}",
            "{file_size}",
            "{filename}"
        ]
        ttk.Combobox(self.settings_frame, textvariable=self.metadata_tag, values=metadata_options, 
                    state="readonly", width=30, font=('Robot', 9)).pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Позиция:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.metadata_pos = tk.StringVar(value="end")
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.metadata_pos, value="start", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.metadata_pos, value="end", font=('Robot', 9)).pack(anchor=tk.W, pady=1)
    
    def create_regex_settings(self) -> None:
        """Создание настроек для метода Регулярные выражения."""
        ttk.Label(self.settings_frame, text="Регулярное выражение:", font=('Robot', 9)).pack(anchor=tk.W, pady=(0, 2))
        self.regex_pattern = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.regex_pattern.pack(fill=tk.X, pady=(0, 4))
        
        ttk.Label(self.settings_frame, text="Замена:", font=('Robot', 9)).pack(anchor=tk.W, pady=(4, 2))
        self.regex_replace = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.regex_replace.pack(fill=tk.X, pady=(0, 4))
        
        btn_test = self.create_rounded_button(
            self.settings_frame, "Тест Regex", self.test_regex,
            '#818CF8', 'white',
            font=('Robot', 9, 'bold'), padx=8, pady=6,
            active_bg='#6366F1')
        btn_test.pack(pady=8, fill=tk.X)
    
    def test_regex(self) -> None:
        """Тестирование регулярного выражения."""
        pattern = self.regex_pattern.get()
        replace = self.regex_replace.get()
        
        if not pattern:
            messagebox.showwarning("Предупреждение", "Введите регулярное выражение")
            return
        
        try:
            test_string = "test_file_name_123"
            result = re.sub(pattern, replace, test_string)
            messagebox.showinfo(
                "Результат теста",
                f"Исходная строка: {test_string}\nРезультат: {result}"
            )
        except re.error as e:
            messagebox.showerror("Ошибка", f"Неверное регулярное выражение: {e}")
    
    def _create_new_name_method(self, template: str) -> NewNameMethod:
        """Создание метода 'Новое имя' с заданным шаблоном"""
        if not template:
            raise ValueError("Введите шаблон нового имени")
        
        # Получаем начальный номер из поля ввода
        start_number = 1
        if hasattr(self, 'new_name_start_number'):
            try:
                start_number = int(self.new_name_start_number.get() or "1")
                if start_number < 1:
                    start_number = 1
            except ValueError:
                start_number = 1
        
        return NewNameMethod(
            template=template,
            metadata_extractor=self.metadata_extractor,
            file_number=start_number
        )
    
    def add_method(self):
        """Добавление метода в список применяемых"""
        method_name = self.method_var.get()
        
        try:
            if method_name == "Новое имя":
                template = self.new_name_template.get()
                if not template:
                    raise ValueError("Введите шаблон нового имени")
                method = self._create_new_name_method(template)
            elif method_name == "Добавить/Удалить":
                method = AddRemoveMethod(
                    operation=self.add_remove_op.get(),
                    text=self.add_remove_text.get(),
                    position=self.add_remove_pos.get(),
                    remove_type=(
                        self.remove_type.get()
                        if self.add_remove_op.get() == "remove"
                        else None
                    ),
                    remove_start=(
                        self.remove_start.get()
                        if self.add_remove_op.get() == "remove"
                        else None
                    ),
                    remove_end=(
                        self.remove_end.get()
                        if self.add_remove_op.get() == "remove"
                        else None
                    )
                )
            elif method_name == "Замена":
                method = ReplaceMethod(
                    find=self.replace_find.get(),
                    replace=self.replace_with.get(),
                    case_sensitive=self.replace_case.get(),
                    full_match=self.replace_full.get() or self.replace_whole_name.get()
                )
            elif method_name == "Регистр":
                method = CaseMethod(
                    case_type=self.case_type.get(),
                    apply_to=self.case_apply.get()
                )
            elif method_name == "Нумерация":
                try:
                    start = int(self.numbering_start.get() or "1")
                    step = int(self.numbering_step.get() or "1")
                    digits = int(self.numbering_digits.get() or "3")
                except ValueError:
                    raise ValueError("Нумерация: неверные числовые значения")
                method = NumberingMethod(
                    start=start,
                    step=step,
                    digits=digits,
                    format_str=self.numbering_format.get(),
                    position=self.numbering_pos.get()
                )
            elif method_name == "Метаданные":
                if not self.metadata_extractor:
                    messagebox.showerror("Ошибка", "Модуль метаданных недоступен")
                    return
                method = MetadataMethod(
                    tag=self.metadata_tag.get(),
                    position=self.metadata_pos.get(),
                    extractor=self.metadata_extractor
                )
            elif method_name == "Регулярные выражения":
                method = RegexMethod(
                    pattern=self.regex_pattern.get(),
                    replace=self.regex_replace.get()
                )
            else:
                return
            
            self.methods_manager.add_method(method)
            self.methods_listbox.insert(tk.END, method_name)
            self.log(f"Добавлен метод: {method_name}")
            
            # Автоматически применяем методы
            self.apply_methods()
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить метод: {e}")
    
    def remove_method(self):
        """Удаление метода из списка"""
        selection = self.methods_listbox.curselection()
        if selection:
            index = selection[0]
            self.methods_listbox.delete(index)
            self.methods_manager.remove_method(index)
            self.log(f"Удален метод: {index + 1}")
            # Автоматически применяем методы после удаления
            self.apply_methods()
    
    def clear_methods(self):
        """Очистка всех методов"""
        if self.methods_manager.get_methods():
            if messagebox.askyesno("Подтверждение", "Очистить все методы?"):
                self.methods_manager.clear_methods()
                self.methods_listbox.delete(0, tk.END)
                self.log("Все методы очищены")
    
    
    def apply_methods(self):
        """Применение всех методов к файлам"""
        if not self.files:
            # Если нет файлов, просто выходим без ошибки
            return
        
        if not self.methods_manager.get_methods():
            # Если нет методов, просто выходим без ошибки
            return
        
        # Сброс счетчиков нумерации перед применением
        for method in self.methods_manager.get_methods():
            if isinstance(method, NumberingMethod):
                method.reset()
            elif isinstance(method, NewNameMethod):
                method.reset()
        
        # Применение методов к каждому файлу
        for i, file_data in enumerate(self.files):
            new_name = file_data['old_name']
            extension = file_data['extension']
            
            # Применяем все методы последовательно
            for method in self.methods_manager.get_methods():
                try:
                    new_name, extension = method.apply(new_name, extension, file_data['full_path'])
                except Exception as e:
                    self.log(f"Ошибка при применении метода к {file_data['old_name']}: {e}")
            
            file_data['new_name'] = new_name
            file_data['extension'] = extension
            
            # Проверка на валидность имени
            status = validate_filename(new_name, extension, file_data['path'], i)
            file_data['status'] = status
            
            # Обновление в таблице
            try:
                children = self.tree.get_children()
                if i < len(children):
                    item = children[i]
                    self.tree.item(item, values=(
                        file_data['old_name'],
                        new_name,
                        extension,
                        file_data['path'],
                        status
                    ))
                else:
                    # Если индекс не совпадает, ищем элемент по старому имени
                    for item in children:
                        item_values = self.tree.item(item, 'values')
                        if len(item_values) > 0 and item_values[0] == file_data['old_name']:
                            self.tree.item(item, values=(
                                file_data['old_name'],
                                new_name,
                                extension,
                                file_data['path'],
                                status
                            ))
                            break
            except Exception as e:
                # Если не удалось обновить элемент, обновляем всю таблицу
                self.refresh_treeview()
            
            # Цветовое выделение в зависимости от статуса
            if status == "Готов":
                self.tree.item(item, tags=('ready',))
            elif "Ошибка" in status or "Конфликт" in status:
                tag = 'error' if "Ошибка" in status else 'conflict'
                self.tree.item(item, tags=(tag,))
            else:
                self.tree.item(item, tags=('error',))
        
        # Проверка на конфликты
        check_conflicts(self.files)
        self.log(f"Методы применены к {len(self.files)} файлам")
    
    
    def start_rename(self):
        """Начало процесса переименования"""
        if not self.files:
            messagebox.showwarning("Предупреждение", "Нет файлов для переименования")
            return
        
        # Подсчет готовых файлов
        ready_files = [f for f in self.files if f['status'] == 'Готов']
        
        if not ready_files:
            messagebox.showwarning(
                "Предупреждение",
                "Нет файлов готовых к переименованию"
            )
            return
        
        # Подтверждение
        if not messagebox.askyesno("Подтверждение", 
                                   f"Вы собираетесь переименовать {len(ready_files)} файлов. Выполнить?"):
            return
        
        # Сохранение состояния для отмены
        undo_state = [f.copy() for f in self.files]
        self.undo_stack.append(undo_state)
        
        # Запуск переименования в отдельном потоке
        rename_files_thread(
            ready_files,
            self.rename_complete,
            self.log
        )
    
    def _rename_files_thread_old(self, files_to_rename: List[Dict]):
        """Переименование файлов в отдельном потоке"""
        total = len(files_to_rename)
        success_count = 0
        error_count = 0
        
        # Множество уже переименованных путей в этой сессии (для отслеживания конфликтов)
        renamed_paths = set()
        
        self.progress['maximum'] = total
        self.progress['value'] = 0
        # Синхронизация прогресс-бара в окне действий, если оно открыто
        if hasattr(self, 'progress_window') and self.progress_window is not None:
            try:
                self.progress_window['maximum'] = total
                self.progress_window['value'] = 0
            except (AttributeError, tk.TclError):
                # Прогресс-бар может быть уничтожен
                pass
        
        for i, file_data in enumerate(files_to_rename):
            try:
                old_path = file_data['full_path']
                # Сохраняем оригинальный путь для последующего удаления из списка
                file_data['original_full_path'] = old_path
                new_name = file_data['new_name'] + file_data['extension']
                new_path = os.path.join(file_data['path'], new_name)
                new_path = os.path.normpath(new_path)
                
                # Проверка существования исходного файла
                if not os.path.exists(old_path):
                    error_count += 1
                    self.log(f"Файл не найден: {old_path}")
                    continue
                
                # Проверка, что новый путь не существует (кроме случая, когда это тот же файл)
                if old_path != new_path:
                    # Проверяем конфликт только если файл существует И это не файл, который мы уже переименовали
                    # Также проверяем, что этот путь не занят другим файлом из нашей сессии
                    if os.path.exists(new_path) and new_path not in renamed_paths:
                        # Генерация уникального имени с суффиксом
                        base_name = file_data['new_name']
                        extension = file_data['extension']
                        counter = 1
                        new_path = os.path.join(
                            file_data['path'],
                            f"{base_name}_{counter}{extension}"
                        )
                        new_path = os.path.normpath(new_path)
                        
                        # Ищем свободное имя (не занятое другими файлами
                        # и не переименованными в этой сессии)
                        while ((os.path.exists(new_path) or
                                new_path in renamed_paths) and
                               counter < 1000):
                            counter += 1
                            new_path = os.path.join(
                                file_data['path'],
                                f"{base_name}_{counter}{extension}"
                            )
                            new_path = os.path.normpath(new_path)
                        
                        if counter >= 1000:
                            error_count += 1
                            self.log(
                                f"Не удалось найти свободное имя для: "
                                f"{file_data['old_name']}"
                            )
                            continue
                        
                        # Обновляем имя в данных файла
                        file_data['new_name'] = f"{base_name}_{counter}"
                        new_name = file_data['new_name'] + extension
                        self.log(f"Использовано уникальное имя (конфликт): {new_name}")
                    
                    try:
                        os.rename(old_path, new_path)
                        # Добавляем переименованный путь в множество
                        renamed_paths.add(new_path)
                        file_data['full_path'] = new_path
                        file_data['old_name'] = file_data['new_name']
                        old_basename = os.path.basename(old_path)
                        new_basename = os.path.basename(new_path)
                        self.log(
                            f"Переименован: {old_basename} -> {new_basename}"
                        )
                        success_count += 1
                    except OSError as e:
                        error_count += 1
                        self.log(f"Ошибка переименования {file_data['old_name']}: {e}")
                else:
                    # Файл не меняется, но добавляем его путь в множество
                    renamed_paths.add(new_path)
                    self.log(f"Без изменений: {new_name}")
                    success_count += 1
                
            except Exception as e:
                error_count += 1
                self.log(f"Ошибка при переименовании {file_data.get('old_name', 'unknown')}: {e}")
            
            self.progress['value'] = i + 1
            # Синхронизация прогресс-бара в окне действий, если оно открыто
            if hasattr(self, 'progress_window') and self.progress_window is not None:
                try:
                    self.progress_window['value'] = i + 1
                except (AttributeError, tk.TclError):
                    # Некоторые виджеты не поддерживают операции с canvas
                    pass
        
        # Собираем список успешно переименованных файлов
        renamed_files = []
        for file_data in files_to_rename:
            new_path = os.path.join(
                file_data['path'],
                file_data['new_name'] + file_data['extension']
            )
            new_path = os.path.normpath(new_path)
            old_path = file_data.get('original_full_path', file_data['full_path'])
            # Если файл был переименован (пути разные) и новый файл существует
            if old_path != new_path and os.path.exists(new_path):
                renamed_files.append(file_data)
        
        # Обновление интерфейса
        self.root.after(0, lambda: self.rename_complete(success_count, error_count, renamed_files))
    
    def rename_complete(self, success: int, error: int, renamed_files: list = None):
        """Завершение переименования"""
        messagebox.showinfo("Завершено", f"Переименование завершено.\nУспешно: {success}\nОшибок: {error}")
        self.progress['value'] = 0
        # Синхронизация прогресс-бара в окне действий, если оно открыто
        if hasattr(self, 'progress_window') and self.progress_window is not None:
            try:
                self.progress_window['value'] = 0
            except (AttributeError, tk.TclError):
                # Прогресс-бар может быть уничтожен
                pass
        
        # Автоматически очищаем все файлы из списка после переименования
        # (если было хотя бы одно успешное переименование)
        if success > 0:
            self.files.clear()
        
        # Обновление списка файлов в таблице
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for file_data in self.files:
            self.tree.insert("", tk.END, values=(
                file_data['old_name'],
                file_data['new_name'],
                file_data['extension'],
                file_data['path'],
                file_data['status']
            ))
        
        # Обновляем статус
        self.update_status()
    
    def undo_rename(self):
        """Отмена последнего переименования"""
        if not self.undo_stack:
            messagebox.showinfo("Информация", "Нет операций для отмены")
            return
        
        undo_state = self.undo_stack.pop()
        
        # Восстановление файлов
        for i, old_file_data in enumerate(undo_state):
            if i < len(self.files):
                current_file = self.files[i]
                old_path = old_file_data['full_path']
                new_path = current_file['full_path']
                
                if old_path != new_path and os.path.exists(new_path):
                    try:
                        os.rename(new_path, old_path)
                        self.files[i] = old_file_data.copy()
                        new_basename = os.path.basename(new_path)
                        old_basename = os.path.basename(old_path)
                        self.log(
                            f"Отменено: {new_basename} -> {old_basename}"
                        )
                    except Exception as e:
                        self.log(f"Ошибка при отмене: {e}")
        
        # Обновление интерфейса
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for file_data in self.files:
            self.tree.insert("", tk.END, values=(
                file_data['old_name'],
                file_data['new_name'],
                file_data['extension'],
                file_data['path'],
                file_data['status']
            ))
        
        messagebox.showinfo("Отменено", "Последняя операция переименования отменена")


def main():
    """Главная функция запуска приложения."""
    # Используем TkinterDnD если доступно
    if HAS_TKINTERDND2:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
    else:
        root = tk.Tk()
    
    app = FileRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

