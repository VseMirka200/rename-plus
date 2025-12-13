"""Модуль для переименования файлов с графическим интерфейсом."""

# Стандартная библиотека
import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Сторонние библиотеки
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

# Опциональные сторонние библиотеки
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

HAS_TKINTERDND2 = False
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKINTERDND2 = True
except ImportError:
    pass

HAS_PYSTRAY = False
try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image as PILImage
    HAS_PYSTRAY = True
except ImportError:
    pass

# Локальные импорты - core
from core.file_operations import (
    add_file_to_list,
    check_conflicts,
    rename_files_thread,
    validate_filename,
)
from core.metadata import MetadataExtractor
from core.file_converter import FileConverter
from core.methods_manager import MethodsManager
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

# Локальные импорты - managers
from managers.library_manager import LibraryManager
from managers.settings_manager import SettingsManager, TemplatesManager
from managers.tray_manager import TrayManager

# Локальные импорты - ui
from ui.drag_drop import (
    setup_drag_drop as setup_drag_drop_util,
    setup_treeview_drag_drop,
)
from ui.ui_components import StyleManager, UIComponents
from ui.window_utils import (
    bind_mousewheel,
    set_window_icon,
    setup_window_resize_handler,
)

# Локальные импорты - utils
from utils.logger import Logger

# Опциональные локальные импорты
HAS_BACKUP_MANAGER = False
try:
    from core.backup_manager import BackupManager
    HAS_BACKUP_MANAGER = True
except ImportError:
    pass

HAS_HISTORY = False
try:
    from core.history_manager import HistoryManager
    HAS_HISTORY = True
except ImportError:
    pass

HAS_THEME = False
try:
    from ui.theme_manager import ThemeManager
    HAS_THEME = True
except ImportError:
    pass

HAS_NOTIFICATIONS = False
try:
    from utils.notifications import NotificationManager
    HAS_NOTIFICATIONS = True
except ImportError:
    pass

HAS_STATISTICS = False
try:
    from utils.statistics import StatisticsManager
    HAS_STATISTICS = True
except ImportError:
    pass

HAS_ERROR_HANDLER = False
try:
    from utils.error_handler import ErrorHandler
    HAS_ERROR_HANDLER = True
except ImportError:
    pass

HAS_PLUGINS = False
try:
    from core.plugins import PluginManager
    HAS_PLUGINS = True
except ImportError:
    pass

HAS_I18N = False
try:
    from utils.i18n import I18nManager
    HAS_I18N = True
except ImportError:
    pass

HAS_UPDATE_CHECKER = False
try:
    from utils.update_checker import UpdateChecker
    HAS_UPDATE_CHECKER = True
except ImportError:
    pass

# Настройка логирования
logger = logging.getLogger(__name__)


class FileRenamerApp:
    """Главный класс приложения для переименования файлов.
    
    Управляет всем жизненным циклом приложения, включая:
    - Создание и управление пользовательским интерфейсом
    - Операции с файлами (переименование, конвертация)
    - Управление настройками и шаблонами
    - Интеграция системы плагинов
    - Управление библиотеками и зависимостями
    
    Attributes:
        root: Корневое окно Tkinter
        files: Список файлов для обработки
        methods_manager: Менеджер методов переименования
        settings_manager: Менеджер настроек приложения
        colors: Цветовая схема интерфейса
    """
    
    def __init__(self, root, library_manager=None, files_from_args=None):
        """Инициализация приложения.
        
        Args:
            root: Корневое окно Tkinter
            library_manager: Менеджер библиотек (опционально)
            files_from_args: Список файлов из аргументов командной строки (опционально)
        """
        self.root = root
        self.files_from_args = files_from_args or []
        
        # Устанавливаем версию программы из констант
        try:
            from config.constants import APP_VERSION
        except ImportError:
            APP_VERSION = "1.0.0"  # Fallback если константы недоступны
        
        self.root.title(f"Ренейм+ v{APP_VERSION}")
        self.library_manager = library_manager
        
        # Используем константы для размеров окна
        try:
            from config.constants import (
                DEFAULT_WINDOW_HEIGHT,
                DEFAULT_WINDOW_WIDTH,
                MIN_WINDOW_HEIGHT,
                MIN_WINDOW_WIDTH,
            )
            window_size = f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}"
            self.root.geometry(window_size)
            self.root.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        except ImportError:
            # Fallback если константы недоступны
            self.root.geometry("1000x600")
            self.root.minsize(1000, 600)
        
        # Установка иконки приложения
        self._icon_photos = []
        set_window_icon(self.root, self._icon_photos)
        
        # Настройка адаптивности
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Менеджеры настроек и шаблонов (нужно создать раньше для использования в теме)
        self.settings_manager = SettingsManager()
        self.settings = self.settings_manager.settings
        self.templates_manager = TemplatesManager()
        self.saved_templates = self.templates_manager.templates
        
        # Настройка цветовой схемы и стилей
        self.style_manager = StyleManager()
        # Менеджер тем
        if HAS_THEME:
            theme_name = self.settings_manager.get('theme', 'light')
            self.theme_manager = ThemeManager(theme_name)
            self.colors = self.theme_manager.colors
        else:
            self.colors = self.style_manager.colors
        self.style = self.style_manager.style
        self.ui_components = UIComponents()
        
        # Настройка фона окна - единый цвет для всего приложения
        self.root.configure(bg=self.colors['bg_main'])
        # Устанавливаем bg_main как основной цвет для всех виджетов
        
        # Привязка изменения размера окна для адаптивного масштабирования
        self.root.bind('<Configure>', self.on_window_resize)
        
        # Данные приложения
        # Список файлов: {path, old_name, new_name, extension, status}
        self.files: List[Dict] = []
        self.undo_stack: List[List[Dict]] = []  # Стек для отмены
        self.redo_stack: List[List[Dict]] = []  # Стек для повтора
        # Методы переименования (используем methods_manager)
        
        # Флаг отмены переименования
        self.cancel_rename_var = None
        
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
        
        # Инициализация модуля конвертации файлов
        self.file_converter = FileConverter()
        
        # Инициализация списков для новых вкладок
        self.converter_files = []
        self.sorter_filters = []  # Список фильтров для сортировки
        
        # Инициализация менеджера методов
        self.methods_manager = MethodsManager(self.metadata_extractor)
        
        # Трей-иконка
        self.tray_manager = None
        # По умолчанию закрывать приложение при закрытии окна
        self.minimize_to_tray = False
        
        # Менеджер библиотек
        self.library_manager = LibraryManager(
            self.root, 
            log_callback=lambda msg: self.logger.log(msg)
        )
        
        # Менеджер резервных копий
        self.backup_manager = None
        if HAS_BACKUP_MANAGER:
            try:
                backup_enabled = self.settings_manager.get('backup', False)
                if backup_enabled:
                    self.backup_manager = BackupManager()
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер резервных копий: {e}")
        
        # Менеджер истории операций
        self.history_manager = None
        if HAS_HISTORY:
            try:
                self.history_manager = HistoryManager()
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер истории: {e}")
        
        # Менеджер уведомлений
        self.notification_manager = None
        if HAS_NOTIFICATIONS:
            try:
                notifications_enabled = self.settings_manager.get('notifications', True)
                self.notification_manager = NotificationManager(enabled=notifications_enabled)
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер уведомлений: {e}")
        
        # Менеджер статистики
        self.statistics_manager = None
        if HAS_STATISTICS:
            try:
                self.statistics_manager = StatisticsManager()
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер статистики: {e}")
        
        # Обработчик ошибок
        self.error_handler = None
        if HAS_ERROR_HANDLER:
            try:
                self.error_handler = ErrorHandler()
            except Exception as e:
                logger.debug(f"Не удалось инициализировать обработчик ошибок: {e}")
        
        # Менеджер плагинов
        self.plugin_manager = None
        if HAS_PLUGINS:
            try:
                self.plugin_manager = PluginManager()
                logger.debug(f"Загружено плагинов: {len(self.plugin_manager.list_plugins())}")
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер плагинов: {e}")
        
        # Менеджер переводов
        self.i18n_manager = None
        if HAS_I18N:
            try:
                language = self.settings_manager.get('language', 'ru')
                self.i18n_manager = I18nManager(language=language)
            except Exception as e:
                logger.debug(f"Не удалось инициализировать менеджер переводов: {e}")
        
        # Проверка обновлений
        self.update_checker = None
        if HAS_UPDATE_CHECKER:
            try:
                check_updates = self.settings_manager.get('check_updates', True)
                if check_updates:
                    self.update_checker = UpdateChecker()
                    # Проверяем обновления в фоне
                    self.root.after(5000, self._check_updates_background)
            except Exception as e:
                logger.debug(f"Не удалось инициализировать проверку обновлений: {e}")
        
        # Создание интерфейса
        self.create_widgets()
        
        # Привязка горячих клавиш
        self.setup_hotkeys()
    
    def _check_updates_background(self):
        """Проверка обновлений в фоновом режиме."""
        if self.update_checker:
            try:
                update_info = self.update_checker.check_for_updates()
                if update_info and update_info.get('available'):
                    # Показываем уведомление об обновлении
                    if self.notification_manager:
                        self.notification_manager.notify_info(
                            f"Доступно обновление {update_info['latest_version']}"
                        )
            except Exception as e:
                logger.debug(f"Ошибка проверки обновлений: {e}")
        
        # Настройка drag and drop для файлов из проводника
        self.setup_drag_drop()
        
        # Настройка перестановки файлов в таблице
        self.setup_treeview_drag_drop()
        
        # Инициализация трей-иконки
        self.setup_tray_icon()
        
        # Обработчик закрытия окна - сворачивание в трей
        self.root.protocol("WM_DELETE_WINDOW", self.on_close_window)
        
        # LibraryManager доступен для ручной установки библиотек при необходимости
        # Автоматическая установка при запуске отключена
    
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
        has_list_frame = hasattr(self, 'list_frame')
        has_tree = hasattr(self, 'tree')
        if has_list_frame and has_tree and self.list_frame and self.tree:
            try:
                list_frame_width = self.list_frame.winfo_width()
                if list_frame_width > 100:  # Минимальная ширина для расчетов
                    # Вычитаем ширину скроллбара (примерно 20px) и отступы
                    # Минимальная ширина уменьшена
                    available_width = max(list_frame_width - 30, 200)
                    
                    # Убеждаемся, что минимальные ширины не слишком большие
                    min_width_old = max(50, int(available_width * 0.20))
                    min_width_new = max(50, int(available_width * 0.20))
                    min_width_path = max(60, int(available_width * 0.50))
                    min_width_status = max(40, int(available_width * 0.10))
                    
                    self.tree.column(
                        "old_name",
                        width=int(available_width * 0.25),
                        minwidth=min_width_old
                    )
                    self.tree.column(
                        "new_name",
                        width=int(available_width * 0.25),
                        minwidth=min_width_new
                    )
                    self.tree.column(
                        "path",
                        width=int(available_width * 0.40),
                        minwidth=min_width_path
                    )
                    self.tree.column(
                        "status",
                        width=int(available_width * 0.10),
                        minwidth=min_width_status
                    )
            except Exception as e:
                # Логируем ошибку, но не прерываем работу приложения
                logger.debug(f"Ошибка обновления колонок таблицы: {e}")
    
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
        # Левая панель занимает 60%, правая - 40%
        main_container.columnconfigure(0, weight=6, uniform="panels")
        main_container.columnconfigure(1, weight=4, uniform="panels")
        main_container.rowconfigure(0, weight=1)
        
        # Сохраняем ссылку на main_container для обновления размеров
        self.main_container = main_container
        
        # Принудительно обновляем конфигурацию колонок после создания
        def update_column_config():
            main_container.columnconfigure(0, weight=6, uniform="panels")
            main_container.columnconfigure(1, weight=4, uniform="panels")
            main_container.update_idletasks()
            # Дополнительное обновление после создания всех виджетов
            def configure_columns():
                main_container.columnconfigure(0, weight=6, uniform="panels")
                main_container.columnconfigure(1, weight=4, uniform="panels")
            
            self.root.after(500, configure_columns)
        
        # Оптимизация: один вызов вместо трех
        self.root.after(300, update_column_config)
        
        # Обработчик изменения размера для обновления колонок таблицы (только для этой вкладки)
        def on_resize(event=None):
            # Проверяем, что событие относится к этой вкладке и она активна
            if event and event.widget == main_container:
                # Проверяем, активна ли вкладка "Файлы"
                if hasattr(self, 'main_notebook') and self.main_notebook:
                    try:
                        selected_tab = self.main_notebook.index(
                            self.main_notebook.select()
                        )
                        # Если не активна вкладка "Файлы", не обновляем
                        if selected_tab != 0:
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
        def on_main_tab_configure(e):
            if e.widget == main_tab:
                on_resize(e)
        
        main_tab.bind('<Configure>', on_main_tab_configure)
        
        # Левая часть - список файлов
        files_count = len(self.files)
        left_panel = ttk.LabelFrame(
            main_container,
            text=f"Список файлов (Файлов: {files_count})",
            style='Card.TLabelframe',
            padding=6
        )
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
        
        columns = ("old_name", "new_name", "path", "status")
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
        self.tree.heading("path", text="Путь")
        self.tree.heading("status", text="Статус")
        
        # Настройка тегов для цветового выделения
        # Светло-зеленый для готовых
        self.tree.tag_configure('ready', background='#D1FAE5', foreground='#065F46')
        # Светло-красный для ошибок
        self.tree.tag_configure('error', background='#FEE2E2', foreground='#991B1B')
        # Светло-желтый для конфликтов
        self.tree.tag_configure('conflict', background='#FEF3C7', foreground='#92400E')
        # Подсветка измененных имен
        self.tree.tag_configure('changed', foreground='#1E40AF')
        
        # Восстановление состояния сортировки
        if hasattr(self, 'settings_manager'):
            saved_sort = self.settings_manager.get('sort_column')
            saved_reverse = self.settings_manager.get('sort_reverse', False)
            if saved_sort:
                self.sort_column_name = saved_sort
                self.sort_reverse = saved_reverse
        
        # Настройка колонок с адаптивными размерами (процент от ширины)
        # Используем минимальные ширины, которые будут обновлены при изменении размера
        self.tree.column("old_name", width=120, anchor='w', minwidth=60)
        self.tree.column("new_name", width=120, anchor='w', minwidth=60)
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
        
        # Контекстное меню для таблицы файлов
        self.tree.bind('<Button-3>', self.show_file_context_menu)
        
        # Привязка сортировки
        self.sort_column_name = None
        self.sort_reverse = False
        for col in ("old_name", "new_name", "path", "status"):
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
        
        # Устанавливаем метод "Новое имя" по умолчанию
        self.method_var = tk.StringVar()
        self.method_var.set("Новое имя")
        
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
        # Флаг для отслеживания, нужна ли прокрутка
        _needs_scrolling_settings = True
        
        def update_scroll_region():
            """Обновление области прокрутки и видимости скроллбара"""
            nonlocal _updating_scroll, _needs_scrolling_settings
            if _updating_scroll:
                return
            _updating_scroll = True
            try:
                settings_canvas.update_idletasks()
                bbox = settings_canvas.bbox("all")
                if bbox:
                    canvas_height = settings_canvas.winfo_height()
                    if canvas_height > 1:
                        # Высота содержимого
                        content_height = bbox[3] - bbox[1]
                        # Если содержимое помещается (с небольшим запасом), скрываем скроллбар
                        if content_height <= canvas_height + 2:  # Небольшой запас для погрешности
                            # Устанавливаем scrollregion равным видимой области, чтобы запретить прокрутку
                            settings_canvas.configure(scrollregion=(0, 0, bbox[2], canvas_height))
                            # Сбрасываем позицию прокрутки в начало
                            settings_canvas.yview_moveto(0)
                            _needs_scrolling_settings = False
                            # Скрываем скроллбар
                            try:
                                if settings_scrollbar.winfo_viewable():
                                    settings_scrollbar.grid_remove()
                            except (tk.TclError, AttributeError):
                                pass
                        else:
                            # Обновляем scrollregion для прокрутки
                            settings_canvas.configure(scrollregion=bbox)
                            _needs_scrolling_settings = True
                            # Показываем скроллбар, если он был скрыт
                            try:
                                if not settings_scrollbar.winfo_viewable():
                                    settings_scrollbar.grid(row=0, column=1, sticky="ns")
                            except (tk.TclError, AttributeError):
                                pass
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
        
        # Кастомная функция прокрутки с проверкой необходимости
        def on_mousewheel_settings(event):
            """Обработчик прокрутки с проверкой необходимости"""
            if not _needs_scrolling_settings:
                return  # Не прокручиваем, если содержимое помещается
            scroll_amount = int(-1 * (event.delta / 120))
            settings_canvas.yview_scroll(scroll_amount, "units")
        
        def on_mousewheel_linux_settings(event):
            """Обработчик прокрутки для Linux"""
            if not _needs_scrolling_settings:
                return  # Не прокручиваем, если содержимое помещается
            if event.num == 4:
                settings_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                settings_canvas.yview_scroll(1, "units")
        
        # Привязка прокрутки колесом мыши с проверкой
        settings_canvas.bind("<MouseWheel>", on_mousewheel_settings)
        settings_canvas.bind("<Button-4>", on_mousewheel_linux_settings)
        settings_canvas.bind("<Button-5>", on_mousewheel_linux_settings)
        
        # Привязка к дочерним виджетам
        def bind_to_children_settings(parent):
            """Рекурсивная привязка прокрутки к дочерним виджетам."""
            for child in parent.winfo_children():
                try:
                    child.bind("<MouseWheel>", on_mousewheel_settings)
                    child.bind("<Button-4>", on_mousewheel_linux_settings)
                    child.bind("<Button-5>", on_mousewheel_linux_settings)
                    bind_to_children_settings(child)
                except (AttributeError, tk.TclError):
                    pass
        
        bind_to_children_settings(scrollable_frame)
        
        settings_canvas.grid(row=0, column=0, sticky="nsew")
        settings_scrollbar.grid(row=0, column=1, sticky="ns")
        
        self.settings_frame = scrollable_frame
        
        # Объединенная группа кнопок
        method_buttons_frame = tk.Frame(methods_frame, bg=self.colors['bg_card'])
        method_buttons_frame.pack(fill=tk.X, pady=(0, 0))
        
        font = ('Robot', 9, 'bold')
        padx = 6  # Компактные отступы
        
        # Кнопки шаблонов будут созданы в create_new_name_settings под полем ввода
        
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
        # Создаем вкладки для конвертации, настроек, о программе и поддержки
        self._create_main_file_converter_tab()
        self._create_main_file_sorter_tab()
        self._create_main_settings_tab()
        self._create_main_about_tab()
        self._create_main_support_tab()
        
        # Обработка файлов из аргументов командной строки
        if self.files_from_args:
            # Увеличиваем задержку, чтобы все вкладки успели инициализироваться
            self.root.after(1000, self._process_files_from_args)
            # Логируем для отладки
            self.log(f"Получено файлов из аргументов: {len(self.files_from_args)}")
            for f in self.files_from_args[:5]:  # Показываем первые 5 файлов
                self.log(f"  - {f}")
        
    
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
        
        # Информация о текущем файле
        self.current_file_label = tk.Label(
            progress_container,
            text="Ожидание...",
            font=('Robot', 8),
            bg=self.colors['bg_card'],
            fg=self.colors['text_secondary'],
            anchor=tk.W
        )
        self.current_file_label.pack(anchor=tk.W, pady=(4, 0))
        
        # Кнопка отмены
        self.cancel_rename_var = tk.BooleanVar(value=False)
        btn_cancel = self.create_rounded_button(
            progress_container, "Отменить", lambda: self.cancel_rename_var.set(True),
            self.colors['danger'], 'white',
            font=('Robot', 8, 'bold'), padx=8, pady=4,
            active_bg=self.colors['danger_hover'])
        btn_cancel.pack(anchor=tk.E, pady=(4, 0))
        
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
        
        # Флаг для отслеживания, нужна ли прокрутка
        _needs_scrolling_methods = True
        
        def update_methods_scroll_region():
            """Обновление области прокрутки и видимости скроллбара"""
            nonlocal _needs_scrolling_methods
            try:
                settings_canvas.update_idletasks()
                bbox = settings_canvas.bbox("all")
                if bbox:
                    canvas_height = settings_canvas.winfo_height()
                    if canvas_height > 1:
                        # Высота содержимого
                        content_height = bbox[3] - bbox[1]
                        # Если содержимое помещается (с небольшим запасом), скрываем скроллбар
                        if content_height <= canvas_height + 2:  # Небольшой запас для погрешности
                            # Устанавливаем scrollregion равным видимой области, чтобы запретить прокрутку
                            settings_canvas.configure(scrollregion=(0, 0, bbox[2], canvas_height))
                            # Сбрасываем позицию прокрутки в начало
                            settings_canvas.yview_moveto(0)
                            _needs_scrolling_methods = False
                            # Скрываем скроллбар
                            try:
                                if settings_scrollbar.winfo_viewable():
                                    settings_scrollbar.grid_remove()
                            except (tk.TclError, AttributeError):
                                pass
                        else:
                            # Обновляем scrollregion для прокрутки
                            settings_canvas.configure(scrollregion=bbox)
                            _needs_scrolling_methods = True
                            # Показываем скроллбар, если он был скрыт
                            try:
                                if not settings_scrollbar.winfo_viewable():
                                    settings_scrollbar.grid(row=1, column=1, sticky="ns")
                            except (tk.TclError, AttributeError):
                                pass
                            # Используем универсальную функцию для управления скроллбаром
                            self.update_scrollbar_visibility(settings_canvas, settings_scrollbar, 'vertical')
            except (AttributeError, tk.TclError):
                pass
        
        self.methods_window_settings_frame.bind(
            "<Configure>",
            lambda e: update_methods_scroll_region())
        
        canvas_win = settings_canvas.create_window((0, 0), 
                                                   window=self.methods_window_settings_frame, 
                                                   anchor="nw")
        
        def on_canvas_configure(event):
            if event.widget == settings_canvas:
                try:
                    settings_canvas.itemconfig(canvas_win, width=event.width)
                    # Обновляем scrollregion и видимость скроллбара
                    window.after(10, update_methods_scroll_region)
                except (AttributeError, tk.TclError):
                    pass
        
        settings_canvas.bind('<Configure>', on_canvas_configure)
        
        def on_scroll_methods(*args):
            """Обработчик прокрутки"""
            settings_scrollbar.set(*args)
            # Обновляем видимость скроллбара после прокрутки
            window.after(10, update_methods_scroll_region)
        
        settings_canvas.configure(yscrollcommand=on_scroll_methods)
        
        # Кастомная функция прокрутки с проверкой необходимости
        def on_mousewheel_methods(event):
            """Обработчик прокрутки с проверкой необходимости"""
            if not _needs_scrolling_methods:
                return  # Не прокручиваем, если содержимое помещается
            scroll_amount = int(-1 * (event.delta / 120))
            settings_canvas.yview_scroll(scroll_amount, "units")
        
        def on_mousewheel_linux_methods(event):
            """Обработчик прокрутки для Linux"""
            if not _needs_scrolling_methods:
                return  # Не прокручиваем, если содержимое помещается
            if event.num == 4:
                settings_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                settings_canvas.yview_scroll(1, "units")
        
        # Привязка прокрутки колесом мыши с проверкой
        settings_canvas.bind("<MouseWheel>", on_mousewheel_methods)
        settings_canvas.bind("<Button-4>", on_mousewheel_linux_methods)
        settings_canvas.bind("<Button-5>", on_mousewheel_linux_methods)
        
        # Привязка к дочерним виджетам
        def bind_to_children_methods(parent):
            """Рекурсивная привязка прокрутки к дочерним виджетам."""
            for child in parent.winfo_children():
                try:
                    child.bind("<MouseWheel>", on_mousewheel_methods)
                    child.bind("<Button-4>", on_mousewheel_linux_methods)
                    child.bind("<Button-5>", on_mousewheel_linux_methods)
                    bind_to_children_methods(child)
                except (AttributeError, tk.TclError):
                    pass
        
        bind_to_children_methods(self.methods_window_settings_frame)
        
        settings_canvas.grid(row=1, column=0, sticky="nsew")
        settings_scrollbar.grid(row=1, column=1, sticky="ns")
        
        # Обновляем scrollregion после создания всех элементов
        def finalize_methods_scroll():
            update_methods_scroll_region()
        
        window.after(100, finalize_methods_scroll)
        
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
        """Переключение на вкладку настроек (логи теперь в настройках)"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(3)  # Индекс 3 - вкладка настроек (логи внутри)
    
    def open_settings_window(self):
        """Переключение на вкладку настроек в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(3)  # Индекс 3 - вкладка настроек
    
    def open_about_window(self):
        """Переключение на вкладку о программе в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(4)  # Индекс 4 - вкладка о программе
    
    def open_support_window(self):
        """Переключение на вкладку поддержки в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(5)  # Индекс 5 - вкладка поддержки
    
    def _create_main_file_converter_tab(self):
        """Создание вкладки конвертации файлов на главном экране"""
        converter_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_main'])
        converter_tab.columnconfigure(0, weight=1)
        converter_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(converter_tab, text="Конвертация файлов")
        
        # Основной контейнер (как во вкладке "Файлы")
        main_container = tk.Frame(converter_tab, bg=self.colors['bg_main'])
        main_container.grid(row=0, column=0, sticky="nsew")
        # Левая панель занимает 60%, правая - 40%
        main_container.columnconfigure(0, weight=6, uniform="panels")
        main_container.columnconfigure(1, weight=4, uniform="panels")
        main_container.rowconfigure(0, weight=1)
        
        # Левая часть - список файлов (как во вкладке "Файлы")
        files_count = len(self.converter_files) if hasattr(self, 'converter_files') else 0
        left_panel = ttk.LabelFrame(
            main_container,
            text=f"Список файлов (Файлов: {files_count})",
            style='Card.TLabelframe',
            padding=6
        )
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 2))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)  # Строка с таблицей файлов
        
        # Сохраняем ссылку на left_panel для обновления заголовка
        self.converter_left_panel = left_panel
        
        # Кнопки управления под заголовком "Список файлов"
        buttons_frame_left = tk.Frame(left_panel, bg=self.colors['bg_card'])
        buttons_frame_left.pack(fill=tk.X, pady=(0, 6))
        
        btn_add_files_left = self.create_rounded_button(
            buttons_frame_left, "Добавить файлы", self._add_files_for_conversion,
            self.colors['primary'], 'white', 
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_files_left.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        
        btn_clear_left = self.create_rounded_button(
            buttons_frame_left, "Очистить", self._clear_converter_files_list,
            self.colors['warning'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['warning_hover'])
        btn_clear_left.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Таблица файлов
        list_frame = ttk.Frame(left_panel)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Создание таблицы с прокруткой
        scrollbar_y = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar_x = ttk.Scrollbar(list_frame, orient=tk.HORIZONTAL)
        
        columns = ('file', 'status')
        tree = ttk.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            style='Custom.Treeview'
        )
        
        scrollbar_y.config(command=tree.yview)
        scrollbar_x.config(command=tree.xview)
        
        # Настройка колонок
        tree.heading("file", text="Файл")
        tree.heading("status", text="Статус")
        
        tree.column("file", width=400, anchor='w', minwidth=200)
        tree.column("status", width=100, anchor='w', minwidth=80)
        
        # Размещение таблицы и скроллбаров
        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Сохраняем ссылку на tree
        self.converter_tree = tree
        self.converter_files = []
        
        # Привязка обработчика выбора файлов для обновления доступных форматов
        tree.bind('<<TreeviewSelect>>', lambda e: self._update_available_formats())
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(tree, tree)
        
        # Прогресс-бар внизу
        progress_container = tk.Frame(left_panel, bg=self.colors['bg_card'])
        progress_container.pack(fill=tk.X, pady=(6, 0))
        progress_container.columnconfigure(1, weight=1)
        
        # Название прогресс-бара и прогресс-бар на одной строке
        progress_title = tk.Label(progress_container, text="Прогресс:",
                                 font=('Robot', 9, 'bold'),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['text_primary'],
                                 anchor='w')
        progress_title.grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        self.converter_progress_bar = ttk.Progressbar(progress_container, mode='determinate')
        self.converter_progress_bar.grid(row=0, column=1, sticky="ew", padx=(0, 10))
        self.converter_progress_bar['value'] = 0
        
        self.converter_progress_label = tk.Label(progress_container, text="",
                                                font=('Robot', 8),
                                                bg=self.colors['bg_card'],
                                                fg=self.colors['text_secondary'],
                                                anchor='w')
        self.converter_progress_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        
        # Настройка drag and drop для вкладки конвертации
        self._setup_converter_drag_drop(list_frame, tree, converter_tab)
        
        # === ПРАВАЯ ПАНЕЛЬ (настройки конвертации) ===
        right_panel = ttk.LabelFrame(main_container, text="Настройки конвертации", 
                                     style='Card.TLabelframe', padding=6)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)  # Настройки теперь в строке 0
        
        # Внутренний Frame для содержимого (настройки сверху)
        settings_frame = tk.Frame(right_panel, bg=self.colors['bg_card'])
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        
        # Фильтр по типу файла
        filter_label = tk.Label(settings_frame, text="Фильтр по типу:",
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_primary'],
                               anchor='w')
        filter_label.pack(anchor=tk.W, pady=(0, 6))
        
        # Combobox для фильтра по типу файла
        filter_var = tk.StringVar(value="Все")
        filter_combo = ttk.Combobox(settings_frame, textvariable=filter_var,
                                   values=["Все", "Изображения", "Документы", "Аудио", "Видео"],
                                   state='readonly', width=15)
        filter_combo.pack(fill=tk.X, pady=(0, 10))
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self._filter_converter_files_by_type())
        self.converter_filter_var = filter_var
        self.converter_filter_combo = filter_combo
        
        # Применяем фильтр при инициализации
        self.root.after(100, lambda: self._filter_converter_files_by_type())
        
        # Выбор формата
        format_label = tk.Label(settings_frame, text="Целевой формат:",
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_primary'],
                               anchor='w')
        format_label.pack(anchor=tk.W, pady=(0, 6))
        
        # Combobox для выбора формата
        formats = self.file_converter.get_supported_formats()
        format_var = tk.StringVar(value=formats[0] if formats else '.png')
        format_combo = ttk.Combobox(settings_frame, textvariable=format_var,
                                   values=formats, state='readonly', width=15)
        format_combo.pack(fill=tk.X, pady=(0, 10))
        self.converter_format_var = format_var
        self.converter_format_combo = format_combo
        
        # Чекбокс для сжатия PDF (показывается только для PDF)
        compress_pdf_var = tk.BooleanVar(value=False)
        compress_pdf_check = tk.Checkbutton(
            settings_frame, 
            text="Сжимать PDF после конвертации",
            variable=compress_pdf_var,
            bg=self.colors['bg_card'],
            fg=self.colors['text_primary'],
            font=('Robot', 9),
            anchor='w'
        )
        compress_pdf_check.pack(fill=tk.X, pady=(0, 10))
        self.compress_pdf_var = compress_pdf_var
        self.compress_pdf_check = compress_pdf_check
        
        # Функция для обновления видимости чекбокса сжатия
        def update_compress_checkbox(*args):
            target_format = format_var.get()
            if target_format == '.pdf':
                compress_pdf_check.pack(fill=tk.X, pady=(0, 10))
            else:
                compress_pdf_check.pack_forget()
        
        format_var.trace('w', update_compress_checkbox)
        update_compress_checkbox()  # Вызываем сразу для установки начального состояния
        
        # Разделитель перед кнопками
        separator_buttons = tk.Frame(right_panel, height=2, bg=self.colors['border'])
        separator_buttons.pack(fill=tk.X, padx=6, pady=(6, 0))
        
        # Кнопки управления в правой панели (внизу)
        buttons_frame = tk.Frame(right_panel, bg=self.colors['bg_card'])
        buttons_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        
        btn_convert = self.create_rounded_button(
            buttons_frame, "Конвертировать", self._convert_files,
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['success_hover'])
        btn_convert.pack(fill=tk.X)
    
    def _create_main_settings_tab(self):
        """Создание вкладки настроек на главном экране"""
        settings_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_main'])
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(settings_tab, text="Настройки")
        
        # Используем код из _create_settings_tab, но адаптируем для главного окна
        self._create_settings_tab_content(settings_tab)
    
    def _create_settings_tab_content(self, settings_tab):
        """Создание содержимого вкладки настроек (используется и в главном окне, и в отдельном)"""
        # Определяем цвет фона в зависимости от того, где используется
        try:
            bg_color = settings_tab.cget('bg')
        except (tk.TclError, AttributeError):
            bg_color = self.colors['bg_main']
        # Содержимое настроек с прокруткой
        canvas = tk.Canvas(settings_tab, bg=bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(settings_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=bg_color)
        
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
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == settings_tab:
                try:
                    canvas_width = settings_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except (AttributeError, tk.TclError):
                    pass
        
        settings_tab.bind('<Configure>', on_window_configure)
        
        # Функция для автоматического управления видимостью скроллбара
        def update_settings_scrollbar_visibility():
            """Обновление видимости скроллбара в настройках"""
            try:
                canvas.update_idletasks()
                bbox = canvas.bbox("all")
                if bbox:
                    canvas_height = canvas.winfo_height()
                    if canvas_height > 1:
                        content_height = bbox[3] - bbox[1]
                        # Если содержимое помещается, скрываем скроллбар
                        if content_height <= canvas_height + 2:
                            canvas.configure(scrollregion=(0, 0, bbox[2], canvas_height))
                            canvas.yview_moveto(0)
                            try:
                                if scrollbar.winfo_viewable():
                                    scrollbar.grid_remove()
                            except (tk.TclError, AttributeError):
                                pass
                        else:
                            canvas.configure(scrollregion=bbox)
                            try:
                                if not scrollbar.winfo_viewable():
                                    scrollbar.grid(row=0, column=1, sticky="ns")
                            except (tk.TclError, AttributeError):
                                pass
            except (tk.TclError, AttributeError):
                pass
        
        def on_settings_scroll(*args):
            scrollbar.set(*args)
            self.root.after(10, update_settings_scrollbar_visibility)
        
        canvas.configure(yscrollcommand=on_settings_scroll)
        
        # Обновляем scrollregion при изменении содержимого
        def on_scrollable_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            self.root.after(10, update_settings_scrollbar_visibility)
        
        scrollable_frame.bind("<Configure>", on_scrollable_configure)
        
        # Привязка прокрутки колесом мыши
        self.bind_mousewheel(canvas, canvas)
        self.bind_mousewheel(scrollable_frame, canvas)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        settings_tab.rowconfigure(0, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        
        # Первоначальная проверка видимости скроллбара
        self.root.after(100, update_settings_scrollbar_visibility)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=20, pady=20)
        
        # Заголовок убран - настройки начинаются сразу с секций
        
        # Функция для создания сворачиваемой секции
        def create_collapsible_frame(parent, title, default_expanded=True):
            """Создание сворачиваемой секции"""
            # Основной контейнер
            container = tk.Frame(parent, bg=bg_color)
            container.pack(fill=tk.X, pady=(0, 10))
            
            # Заголовок с кнопкой сворачивания
            header_frame = tk.Frame(container, bg=self.colors['bg_card'], cursor='hand2')
            header_frame.pack(fill=tk.X)
            
            # Индикатор сворачивания
            indicator = "▼" if default_expanded else "▶"
            indicator_label = tk.Label(header_frame, text=indicator, 
                                     font=('Robot', 12), 
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['text_primary'])
            indicator_label.pack(side=tk.LEFT, padx=(10, 10))
            
            # Заголовок секции
            title_label = tk.Label(header_frame, text=title,
                                  font=('Robot', 12, 'bold'),
                                  bg=self.colors['bg_card'],
                                  fg=self.colors['text_primary'])
            title_label.pack(side=tk.LEFT)
            
            # Контент секции
            content_frame = ttk.LabelFrame(container, text="", 
                                          style='Card.TLabelframe', padding=20)
            is_expanded = default_expanded
            
            def toggle():
                nonlocal is_expanded
                is_expanded = not is_expanded
                if is_expanded:
                    content_frame.pack(fill=tk.BOTH, expand=True)
                    indicator_label.config(text="▼")
                else:
                    content_frame.pack_forget()
                    indicator_label.config(text="▶")
            
            if default_expanded:
                content_frame.pack(fill=tk.BOTH, expand=True)
            else:
                content_frame.pack_forget()
            
            # Привязка клика к заголовку
            header_frame.bind("<Button-1>", lambda e: toggle())
            indicator_label.bind("<Button-1>", lambda e: toggle())
            title_label.bind("<Button-1>", lambda e: toggle())
            
            return content_frame
        
        # Секция: Управление библиотеками
        # Копируем логику из существующего метода
        if hasattr(self, 'library_manager') and self.library_manager:
            libs_frame = create_collapsible_frame(content_frame, "Управление библиотеками", default_expanded=True)
            
            libs_info_label = tk.Label(libs_frame,
                                     text="Управление библиотеками программы. Установка и удаление библиотек.",
                                     font=('Robot', 9),
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['text_secondary'],
                                     wraplength=600,
                                     justify=tk.LEFT)
            libs_info_label.pack(anchor=tk.W, pady=(0, 15))
            
            # Фрейм для таблицы библиотек
            libs_table_frame = tk.Frame(libs_frame, bg=self.colors['bg_card'])
            libs_table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # Scrollbar для таблицы
            libs_scrollbar = ttk.Scrollbar(libs_table_frame, orient=tk.VERTICAL)
            libs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Treeview для отображения библиотек
            libs_tree = ttk.Treeview(
                libs_table_frame,
                columns=('status', 'type', 'action'),
                show='tree headings',
                yscrollcommand=libs_scrollbar.set,
                height=12
            )
            libs_scrollbar.config(command=libs_tree.yview)
            
            # Настройка колонок
            libs_tree.heading('#0', text='Библиотека')
            libs_tree.heading('status', text='Статус')
            libs_tree.heading('type', text='Тип')
            libs_tree.heading('action', text='Действие')
            
            libs_tree.column('#0', width=250, minwidth=150)
            libs_tree.column('status', width=120, minwidth=100)
            libs_tree.column('type', width=120, minwidth=100)
            libs_tree.column('action', width=200, minwidth=150)
            
            libs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            def refresh_libraries_table():
                """Обновление таблицы библиотек."""
                # Инвалидируем кэш для актуальной проверки
                self.library_manager.invalidate_cache()
                
                for item in libs_tree.get_children():
                    libs_tree.delete(item)
                
                # Принудительно обновляем sys.path перед проверкой
                try:
                    import site
                    user_site = site.getusersitepackages()
                    if user_site and user_site not in sys.path:
                        sys.path.insert(0, user_site)
                        site.addsitedir(user_site)
                except Exception:
                    pass
                
                # Добавляем обязательные библиотеки
                required_node = libs_tree.insert('', 'end', text='Обязательные', tags=('category',))
                for lib_name in self.library_manager.REQUIRED_LIBRARIES.keys():
                    # Принудительно проверяем библиотеку, игнорируя кэш
                    import_name = self.library_manager.REQUIRED_LIBRARIES.get(lib_name)
                    if import_name:
                        # Очищаем кэш модулей для этой библиотеки перед проверкой
                        modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
                        for m in modules_to_remove:
                            try:
                                del sys.modules[m]
                            except KeyError:
                                pass
                        is_installed = self.library_manager._check_library(lib_name, import_name)
                    else:
                        is_installed = False
                    status = "✓ Установлена" if is_installed else "✗ Отсутствует"
                    libs_tree.insert(required_node, 'end', text=lib_name, 
                                   values=(status, 'Обязательная', ''),
                                   tags=('required', 'installed' if is_installed else 'missing'))
                
                # Добавляем опциональные библиотеки
                optional_node = libs_tree.insert('', 'end', text='Опциональные', tags=('category',))
                for lib_name in self.library_manager.OPTIONAL_LIBRARIES.keys():
                    # Принудительно проверяем библиотеку, игнорируя кэш
                    import_name = self.library_manager.OPTIONAL_LIBRARIES.get(lib_name)
                    if import_name:
                        # Очищаем кэш модулей для этой библиотеки перед проверкой
                        modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
                        for m in modules_to_remove:
                            try:
                                del sys.modules[m]
                            except KeyError:
                                pass
                        is_installed = self.library_manager._check_library(lib_name, import_name)
                    else:
                        is_installed = False
                    status = "✓ Установлена" if is_installed else "○ Не установлена"
                    libs_tree.insert(optional_node, 'end', text=lib_name,
                                   values=(status, 'Опциональная', ''),
                                   tags=('optional', 'installed' if is_installed else 'missing'))
                
                # Добавляем Windows-специфичные библиотеки
                if sys.platform == 'win32':
                    windows_node = libs_tree.insert('', 'end', text='Windows-специфичные', tags=('category',))
                    for lib_name in self.library_manager.WINDOWS_OPTIONAL_LIBRARIES.keys():
                        # Принудительно проверяем библиотеку, игнорируя кэш
                        import_name = self.library_manager.WINDOWS_OPTIONAL_LIBRARIES.get(lib_name)
                        if import_name:
                            # Очищаем кэш модулей для этой библиотеки перед проверкой
                            modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
                            for m in modules_to_remove:
                                try:
                                    del sys.modules[m]
                                except KeyError:
                                    pass
                            is_installed = self.library_manager._check_library(lib_name, import_name)
                        else:
                            is_installed = False
                        status = "✓ Установлена" if is_installed else "○ Не установлена"
                        libs_tree.insert(windows_node, 'end', text=lib_name,
                                       values=(status, 'Windows', ''),
                                       tags=('windows', 'installed' if is_installed else 'missing'))
                
                # Раскрываем все категории
                for item in libs_tree.get_children():
                    libs_tree.item(item, open=True)
                
                # Настройка цветов
                libs_tree.tag_configure('category', font=('Robot', 10, 'bold'))
                libs_tree.tag_configure('installed', foreground='green')
                libs_tree.tag_configure('missing', foreground='gray')
            
            refresh_libraries_table()
            
            # Фрейм для кнопок действий
            libs_actions_frame = tk.Frame(libs_frame, bg=self.colors['bg_card'])
            libs_actions_frame.pack(fill=tk.X, pady=(10, 0))
            
            def install_selected_handler():
                selected = libs_tree.selection()
                if not selected:
                    messagebox.showwarning("Внимание", "Выберите библиотеку для установки")
                    return
                
                item = selected[0]
                if libs_tree.get_children(item):
                    messagebox.showwarning("Внимание", "Выберите конкретную библиотеку, а не категорию")
                    return
                
                lib_name = libs_tree.item(item, 'text')
                
                if self.library_manager.is_library_installed(lib_name):
                    messagebox.showinfo("Информация", f"Библиотека {lib_name} уже установлена")
                    return
                
                def install_thread():
                    success, message = self.library_manager.install_single_library(lib_name)
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Результат установки" if success else "Ошибка",
                        message
                    ))
                    self.root.after(0, refresh_libraries_table)
                
                threading.Thread(target=install_thread, daemon=True).start()
            
            install_btn = self.create_rounded_button(
                libs_actions_frame, "Установить", install_selected_handler,
                self.colors['primary'], 'white',
                font=('Robot', 9, 'bold'), padx=15, pady=8,
                active_bg=self.colors['primary_hover'])
            install_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            def uninstall_selected_handler():
                selected = libs_tree.selection()
                if not selected:
                    messagebox.showwarning("Внимание", "Выберите библиотеку для удаления")
                    return
                
                item = selected[0]
                if libs_tree.get_children(item):
                    messagebox.showwarning("Внимание", "Выберите конкретную библиотеку, а не категорию")
                    return
                
                lib_name = libs_tree.item(item, 'text')
                
                if not self.library_manager.is_library_installed(lib_name):
                    messagebox.showinfo("Информация", f"Библиотека {lib_name} не установлена")
                    return
                
                if not messagebox.askyesno("Подтверждение", 
                                          f"Вы уверены, что хотите удалить библиотеку {lib_name}?"):
                    return
                
                def uninstall_thread():
                    success, message = self.library_manager.uninstall_library(lib_name)
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Результат удаления" if success else "Ошибка",
                        message
                    ))
                    self.root.after(0, refresh_libraries_table)
                
                threading.Thread(target=uninstall_thread, daemon=True).start()
            
            uninstall_btn = self.create_rounded_button(
                libs_actions_frame, "Удалить", uninstall_selected_handler,
                '#dc3545', 'white',
                font=('Robot', 9), padx=15, pady=8,
                active_bg='#c82333')
            uninstall_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            refresh_btn = self.create_rounded_button(
                libs_actions_frame, "Обновить", refresh_libraries_table,
                self.colors.get('secondary', '#6B7280'), 'white',
                font=('Robot', 9), padx=15, pady=8,
                active_bg=self.colors.get('secondary_hover', '#4B5563'))
            refresh_btn.pack(side=tk.LEFT)
            
            def check_all_handler():
                def run_check():
                    try:
                        self.library_manager.check_and_install(
                            install_optional=True, silent=False, force_check=True)
                        self.root.after(0, refresh_libraries_table)
                    except Exception as e:
                        logger.error(f"Ошибка при проверке библиотек: {e}", exc_info=True)
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось проверить библиотеки: {e}"))
                
                threading.Thread(target=run_check, daemon=True).start()
            
            check_all_btn = self.create_rounded_button(
                libs_actions_frame, "Проверить все", check_all_handler,
                self.colors['info'] if 'info' in self.colors else self.colors['primary'],
                'white', font=('Robot', 9), padx=15, pady=8,
                active_bg=self.colors['primary_hover'])
            check_all_btn.pack(side=tk.LEFT, padx=(10, 0))
        
        # Секция: Контекстное меню Windows
        if sys.platform == 'win32':
            context_menu_frame = create_collapsible_frame(content_frame, "Контекстное меню Windows", default_expanded=True)
            
            context_menu_info_label = tk.Label(context_menu_frame,
                                             text="Добавление пункта 'Добавить в конвертер Ренейм+' в контекстное меню Windows. "
                                                  "Позволяет быстро добавлять файлы в конвертер прямо из Проводника.",
                                             font=('Robot', 9),
                                             bg=self.colors['bg_card'],
                                             fg=self.colors['text_secondary'],
                                             wraplength=600,
                                             justify=tk.LEFT)
            context_menu_info_label.pack(anchor=tk.W, pady=(0, 15))
            
            # Импортируем менеджер контекстного меню
            try:
                from utils.context_menu import ContextMenuManager
                context_menu_manager = ContextMenuManager()
                
                # Фрейм для статуса и кнопок
                context_menu_controls = tk.Frame(context_menu_frame, bg=self.colors['bg_card'])
                context_menu_controls.pack(fill=tk.X, pady=(0, 10))
                
                # Статус установки
                status_label = tk.Label(context_menu_controls,
                                       text="Статус: Проверка...",
                                       font=('Robot', 9),
                                       bg=self.colors['bg_card'],
                                       fg=self.colors['text_primary'])
                status_label.pack(side=tk.LEFT, padx=(0, 15))
                
                # Кнопка установки
                def install_context_menu():
                    """Установка контекстного меню"""
                    success, message = context_menu_manager.install()
                    if success:
                        messagebox.showinfo("Успех", message)
                    else:
                        messagebox.showerror("Ошибка", message)
                    update_context_menu_status()
                
                install_btn = self.create_rounded_button(
                    context_menu_controls, "Установить", install_context_menu,
                    self.colors['primary'], 'white',
                    font=('Robot', 9), padx=15, pady=8,
                    active_bg=self.colors['primary_hover'])
                install_btn.pack(side=tk.LEFT, padx=(0, 10))
                
                # Кнопка удаления
                def uninstall_context_menu():
                    """Удаление контекстного меню"""
                    success, message = context_menu_manager.uninstall()
                    if success:
                        messagebox.showinfo("Успех", message)
                    else:
                        messagebox.showerror("Ошибка", message)
                    update_context_menu_status()
                
                uninstall_btn = self.create_rounded_button(
                    context_menu_controls, "Удалить", uninstall_context_menu,
                    self.colors['danger'], 'white',
                    font=('Robot', 9), padx=15, pady=8,
                    active_bg=self.colors['danger_hover'])
                uninstall_btn.pack(side=tk.LEFT)
                
                def update_context_menu_status():
                    """Обновление статуса контекстного меню"""
                    if context_menu_manager.is_installed():
                        status_label.config(text="Статус: ✓ Установлено", fg='green')
                        # Для rounded_button изменяем команду и визуальный вид
                        try:
                            # Получаем canvas из фрейма кнопки
                            install_canvas = install_btn.winfo_children()[0] if install_btn.winfo_children() else None
                            uninstall_canvas = uninstall_btn.winfo_children()[0] if uninstall_btn.winfo_children() else None
                            
                            # Делаем кнопку установки неактивной
                            if install_canvas:
                                install_canvas.btn_command = lambda: None  # Пустая команда
                                install_canvas.config(cursor='arrow')
                            
                            # Делаем кнопку удаления активной
                            if uninstall_canvas:
                                uninstall_canvas.btn_command = uninstall_context_menu
                                uninstall_canvas.config(cursor='hand2')
                        except Exception:
                            pass
                    else:
                        status_label.config(text="Статус: ✗ Не установлено", fg='gray')
                        # Обратное состояние
                        try:
                            install_canvas = install_btn.winfo_children()[0] if install_btn.winfo_children() else None
                            uninstall_canvas = uninstall_btn.winfo_children()[0] if uninstall_btn.winfo_children() else None
                            
                            # Делаем кнопку установки активной
                            if install_canvas:
                                install_canvas.btn_command = install_context_menu
                                install_canvas.config(cursor='hand2')
                            
                            # Делаем кнопку удаления неактивной
                            if uninstall_canvas:
                                uninstall_canvas.btn_command = lambda: None  # Пустая команда
                                uninstall_canvas.config(cursor='arrow')
                        except Exception:
                            pass
                
                # Обновляем статус при создании
                update_context_menu_status()
                
            except ImportError as e:
                error_label = tk.Label(context_menu_frame,
                                      text=f"Не удалось загрузить модуль контекстного меню: {e}",
                                      font=('Robot', 9),
                                      bg=self.colors['bg_card'],
                                      fg='red',
                                      wraplength=600,
                                      justify=tk.LEFT)
                error_label.pack(anchor=tk.W, pady=(0, 15))
        
    
    def _create_main_about_tab(self):
        """Создание вкладки о программе на главном экране"""
        about_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_main'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(about_tab, text="О программе")
        
        # Содержимое о программе с прокруткой
        canvas = tk.Canvas(about_tab, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(about_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
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
        scrollable_frame.configure(padx=20, pady=20)
        
        # Описание программы - карточка
        about_card = ttk.LabelFrame(content_frame, text="О программе", 
                                    style='Card.TLabelframe', padding=20)
        about_card.pack(fill=tk.X, pady=(10, 20))
        
        # Контейнер для изображения и описания (горизонтальный layout)
        about_content_frame = tk.Frame(about_card, bg=self.colors['bg_card'])
        about_content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Левая часть: контейнер для изображения, названия и версии (с вертикальным центрированием)
        left_container = tk.Frame(about_content_frame, bg=self.colors['bg_card'])
        left_container.pack(side=tk.LEFT, fill=tk.Y, expand=False, padx=(0, 20))
        
        # Внутренний контейнер для центрирования содержимого по вертикали
        left_inner = tk.Frame(left_container, bg=self.colors['bg_card'])
        left_inner.pack(expand=True, fill=tk.NONE)
        
        # Изображение программы
        image_frame = tk.Frame(left_inner, bg=self.colors['bg_card'])
        image_frame.pack(anchor=tk.CENTER, pady=(0, 10))
        
        # Сохраняем ссылку на изображение в списке
        if not hasattr(self, '_about_icons'):
            self._about_icons = []
        
        # Получаем версию программы из констант
        try:
            from config.constants import APP_VERSION
        except ImportError:
            APP_VERSION = "1.0.0"  # Fallback если константы недоступны
        
        try:
            # Используем существующий логотип приложения
            possible_paths = [
                os.path.join(os.path.dirname(__file__), "materials", "icon", "Логотип.png"),
                os.path.join(os.path.dirname(__file__), "materials", "icon", "Логотип.ico"),
            ]
            image_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    image_path = path
                    logger.debug(f"Найдено изображение приложения: {path}")
                    break
            
            if image_path and HAS_PIL:
                img = Image.open(image_path)
                # Размер изображения (чуть меньше)
                img = img.resize((250, 250), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._about_icons.append(photo)  # Сохраняем в список
                image_label = tk.Label(image_frame, image=photo, bg=self.colors['bg_card'])
                image_label.pack(anchor=tk.CENTER)
            elif not HAS_PIL:
                logger.warning("PIL (Pillow) не установлен, изображение приложения не может быть загружено")
            else:
                logger.warning(f"Изображение приложения не найдено. Проверенные пути: {possible_paths}")
        except Exception as e:
            logger.error(f"Ошибка загрузки изображения приложения: {e}", exc_info=True)
            # При ошибке просто не показываем изображение
        
        # Название программы под изображением (по центру)
        app_name_label = tk.Label(left_inner,
                                 text="Ренейм+",
                                 font=('Robot', 20, 'bold'),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['primary'])
        app_name_label.pack(anchor=tk.CENTER, pady=(0, 5))
        
        # Версия программы под названием (по центру)
        version_label = tk.Label(left_inner,
                                text=f"Версия {APP_VERSION}",
                                font=('Robot', 10),
                                bg=self.colors['bg_card'],
                                fg=self.colors['text_secondary'])
        version_label.pack(anchor=tk.CENTER)
        
        # Правая часть: описание программы
        desc_frame = tk.Frame(about_content_frame, bg=self.colors['bg_card'])
        desc_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        desc_text = """Ренейм+ - это мощная и удобная программа для массового переименования файлов. 

Программа предоставляет широкий набор инструментов для работы с именами файлов: 
переименование по различным шаблонам, поддержка метаданных (EXIF, ID3 и др.), 
предпросмотр изменений перед применением, удобный интерфейс с поддержкой Drag & Drop, 
возможность перестановки файлов в списке и многое другое.

Программа поможет вам быстро и эффективно организовать ваши файлы.

Используемые библиотеки:
• Python 3 - основной язык программирования
• Tkinter - графический интерфейс
• tkinterdnd2 - поддержка Drag & Drop
• Pillow (PIL) - работа с изображениями
• python-docx - работа с документами Word
• pydub - конвертация аудио
• moviepy - конвертация видео
• pywin32/comtypes - работа с COM (Windows)
• docx2pdf - конвертация DOCX в PDF
• pdf2docx - конвертация PDF в DOCX
• pystray - системный трей
• и другие библиотеки для расширенной функциональности"""
        
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
        dev_card = ttk.LabelFrame(content_frame, text="Разработчики", 
                                  style='Card.TLabelframe', padding=20)
        dev_card.pack(fill=tk.X, pady=(0, 20))
        
        # Разработчики
        def open_vk_group(event):
            import webbrowser
            webbrowser.open("https://vk.com/urban_solution")
        
        dev_frame = tk.Frame(dev_card, bg=self.colors['bg_card'])
        dev_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 8))
        
        dev_prefix = tk.Label(dev_frame, 
                            text="Разработчики: ",
                            font=('Robot', 10),
                            bg=self.colors['bg_card'], 
                            fg=self.colors['text_primary'],
                            justify=tk.LEFT)
        dev_prefix.pack(side=tk.LEFT)
        
        dev_name = tk.Label(dev_frame, 
                           text="Urban SOLUTION",
                           font=('Robot', 10),
                           bg=self.colors['bg_card'], 
                           fg=self.colors['primary'],
                           cursor='hand2',
                           justify=tk.LEFT)
        dev_name.pack(side=tk.LEFT)
        dev_name.bind("<Button-1>", open_vk_group)
        
        # Разработал
        def open_vk_profile(event):
            import webbrowser
            webbrowser.open("https://vk.com/vsemirka200")
        
        dev_by_frame = tk.Frame(dev_card, bg=self.colors['bg_card'])
        dev_by_frame.pack(anchor=tk.W, fill=tk.X)
        
        dev_by_prefix = tk.Label(dev_by_frame, 
                                text="Автор идеи: ",
                                font=('Robot', 10),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['text_primary'],
                                justify=tk.LEFT)
        dev_by_prefix.pack(side=tk.LEFT)
        
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
        social_card = ttk.LabelFrame(content_frame, text="Социальные сети", 
                                     style='Card.TLabelframe', padding=20)
        social_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_vk_social(event):
            import webbrowser
            webbrowser.open("https://vk.com/urban_solution")
        
        vk_frame = tk.Frame(social_card, bg=self.colors['bg_card'])
        vk_frame.pack(anchor=tk.W, fill=tk.X, pady=(0, 3))
        
        # Иконка VK - сохраняем в список для предотвращения удаления
        if not hasattr(self, '_about_icons'):
            self._about_icons = []
        try:
            vk_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "ВКонтакте.png")
            if os.path.exists(vk_icon_path) and HAS_PIL:
                vk_img = Image.open(vk_icon_path)
                vk_img = vk_img.resize((24, 24), Image.Resampling.LANCZOS)
                vk_photo = ImageTk.PhotoImage(vk_img)
                self._about_icons.append(vk_photo)  # Сохраняем в список
                vk_icon_label = tk.Label(vk_frame, image=vk_photo, bg=self.colors['bg_card'], cursor='hand2')
                vk_icon_label.pack(side=tk.LEFT, padx=(0, 8))
                vk_icon_label.bind("<Button-1>", open_vk_social)  # Делаем иконку кликабельной
            else:
                if not HAS_PIL:
                    logger.warning("PIL (Pillow) не установлен, иконка VK не может быть загружена")
                else:
                    logger.warning(f"Иконка VK не найдена: {vk_icon_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки иконки VK: {e}", exc_info=True)
        
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
        
        # Иконка Telegram - сохраняем в список
        try:
            tg_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "Telegram.png")
            if os.path.exists(tg_icon_path) and HAS_PIL:
                tg_img = Image.open(tg_icon_path)
                tg_img = tg_img.resize((24, 24), Image.Resampling.LANCZOS)
                tg_photo = ImageTk.PhotoImage(tg_img)
                self._about_icons.append(tg_photo)  # Сохраняем в список
                tg_icon_label = tk.Label(tg_frame, image=tg_photo, bg=self.colors['bg_card'], cursor='hand2')
                tg_icon_label.pack(side=tk.LEFT, padx=(0, 8))
                tg_icon_label.bind("<Button-1>", open_tg_channel)  # Делаем иконку кликабельной
            else:
                if not HAS_PIL:
                    logger.warning("PIL (Pillow) не установлен, иконка Telegram не может быть загружена")
                else:
                    logger.warning(f"Иконка Telegram не найдена: {tg_icon_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки иконки Telegram: {e}", exc_info=True)
        
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
        github_card = ttk.LabelFrame(content_frame, text="Посмотреть код", 
                                     style='Card.TLabelframe', padding=20)
        github_card.pack(fill=tk.X, pady=(0, 20))
        
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/VseMirka200/nazovi")
        
        github_frame = tk.Frame(github_card, bg=self.colors['bg_card'])
        github_frame.pack(anchor=tk.W, fill=tk.X)
        
        # Иконка GitHub - сохраняем в список
        try:
            github_icon_path = os.path.join(os.path.dirname(__file__), "materials", "icon", "GitHUB.png")
            if os.path.exists(github_icon_path) and HAS_PIL:
                github_img = Image.open(github_icon_path)
                github_img = github_img.resize((24, 24), Image.Resampling.LANCZOS)
                github_photo = ImageTk.PhotoImage(github_img)
                self._about_icons.append(github_photo)  # Сохраняем в список
                github_icon_label = tk.Label(github_frame, image=github_photo, bg=self.colors['bg_card'], cursor='hand2')
                github_icon_label.pack(side=tk.LEFT, padx=(0, 8))
                github_icon_label.bind("<Button-1>", open_github)  # Делаем иконку кликабельной
            else:
                if not HAS_PIL:
                    logger.warning("PIL (Pillow) не установлен, иконка GitHub не может быть загружена")
                else:
                    logger.warning(f"Иконка GitHub не найдена: {github_icon_path}")
        except Exception as e:
            logger.error(f"Ошибка загрузки иконки GitHub: {e}", exc_info=True)
        
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
        contact_card = ttk.LabelFrame(content_frame, text="Связаться с разработчиками", 
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
        support_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_main'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(support_tab, text="Поддержка")
        
        # Содержимое поддержки без скроллбара
        content_frame = tk.Frame(support_tab, bg=self.colors['bg_main'])
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
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
    
    def _process_files_from_args(self):
        """Обработка файлов из аргументов командной строки"""
        if not self.files_from_args:
            self.log("Нет файлов для обработки из аргументов")
            return
        
        self.log(f"Начинаем обработку {len(self.files_from_args)} файлов из контекстного меню")
        
        # Переключаемся на вкладку конвертации
        if hasattr(self, 'main_notebook') and self.main_notebook:
            # Находим индекс вкладки "Конвертация файлов"
            tab_found = False
            for i in range(self.main_notebook.index('end')):
                tab_text = self.main_notebook.tab(i, 'text')
                if tab_text == 'Конвертация файлов':
                    self.main_notebook.select(i)
                    tab_found = True
                    self.log("Переключились на вкладку 'Конвертация файлов'")
                    break
            
            if not tab_found:
                self.log("Вкладка 'Конвертация файлов' не найдена!")
                # Пробуем найти по другому названию или создаем заново
                for i in range(self.main_notebook.index('end')):
                    tab_text = self.main_notebook.tab(i, 'text')
                    self.log(f"Найдена вкладка: {tab_text}")
        else:
            self.log("main_notebook не найден!")
        
        # Добавляем файлы
        for file_path in self.files_from_args:
            if not os.path.exists(file_path) or not os.path.isfile(file_path):
                continue
            
            if not hasattr(self, 'converter_files'):
                self.converter_files = []
            
            # Проверяем, что файл еще не добавлен
            normalized_path = os.path.normpath(os.path.abspath(file_path))
            if any(os.path.normpath(os.path.abspath(f.get('path', ''))) == normalized_path 
                   for f in self.converter_files):
                continue
            
            ext = os.path.splitext(file_path)[1].lower()
            
            # Определяем доступные форматы конвертации
            available_formats = []
            all_formats = self.file_converter.get_supported_formats()
            for target_format in all_formats:
                if self.file_converter.can_convert(file_path, target_format):
                    available_formats.append(target_format)
            
            # Определяем категорию файла
            file_category = self.file_converter.get_file_type_category(file_path)
            
            # Определяем статус файла
            if available_formats:
                status = 'Готов'
            else:
                status = 'Не поддерживается'
            
            file_data = {
                'path': file_path,
                'format': ext,
                'status': status,
                'available_formats': available_formats,
                'category': file_category
            }
            self.converter_files.append(file_data)
        
        # Обновляем заголовок панели
        if hasattr(self, 'converter_left_panel'):
            count = len(self.converter_files)
            self.converter_left_panel.config(text=f"Список файлов (Файлов: {count})")
        
        # Применяем фильтр
        if hasattr(self, '_filter_converter_files_by_type'):
            self._filter_converter_files_by_type()
        
        added_count = len(self.converter_files) if hasattr(self, 'converter_files') else 0
        self.log(f"Добавлено файлов из контекстного меню: {added_count} из {len(self.files_from_args)}")
    
    def _add_files_for_conversion(self):
        """Добавление файлов для конвертации"""
        files = filedialog.askopenfilenames(
            title="Выберите файлы для конвертации",
            filetypes=[
                ("Все файлы", "*.*"),
                ("Изображения", "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff *.tif *.ico *.svg *.heic *.heif *.avif *.dng *.cr2 *.nef *.raw"),
                ("Документы", "*.pdf *.docx *.doc *.xlsx *.xls *.pptx *.ppt *.txt *.rtf *.csv *.html *.htm *.odt *.ods *.odp"),
                ("Аудио", "*.mp3 *.wav *.flac *.aac *.ogg *.m4a *.wma *.opus"),
                ("Видео", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.3gp"),
            ]
        )
        if files:
            for file_path in files:
                if not hasattr(self, 'converter_files'):
                    self.converter_files = []
                # Проверяем, что файл еще не добавлен
                normalized_path = os.path.normpath(os.path.abspath(file_path))
                if any(os.path.normpath(os.path.abspath(f.get('path', ''))) == normalized_path 
                       for f in self.converter_files):
                    continue
                
                ext = os.path.splitext(file_path)[1].lower()
                
                # Определяем доступные форматы конвертации
                available_formats = []
                all_formats = self.file_converter.get_supported_formats()
                for target_format in all_formats:
                    if self.file_converter.can_convert(file_path, target_format):
                        available_formats.append(target_format)
                
                # Определяем категорию файла
                file_category = self.file_converter.get_file_type_category(file_path)
                
                # Определяем статус файла
                if available_formats:
                    status = 'Готов'
                else:
                    status = 'Не поддерживается'
                
                file_data = {
                    'path': file_path,
                    'format': ext,
                    'status': status,
                    'available_formats': available_formats,  # Сохраняем список форматов, а не строку
                    'category': file_category  # Сохраняем категорию файла
                }
                self.converter_files.append(file_data)
            
            # Обновляем заголовок панели
            if hasattr(self, 'converter_left_panel'):
                count = len(self.converter_files)
                self.converter_left_panel.config(text=f"Список файлов (Файлов: {count})")
            # Применяем фильтр - это обновит treeview и доступные форматы
            self._filter_converter_files_by_type()
            self.log(f"Добавлено файлов для конвертации: {len(files)}")
    
    def _update_available_formats(self):
        """Обновление списка доступных форматов в combobox на основе выбранных файлов"""
        if not hasattr(self, 'converter_format_combo') or not self.converter_format_combo:
            return
        
        # Получаем выбранные файлы или все файлы, если ничего не выбрано
        selected_items = self.converter_tree.selection()
        if selected_items:
            # Если есть выбранные файлы, используем их
            indices = [self.converter_tree.index(item) for item in selected_items]
            files_to_check = [self.converter_files[i] for i in indices if 0 <= i < len(self.converter_files)]
        else:
            # Если ничего не выбрано, используем все файлы
            files_to_check = self.converter_files
        
        if not files_to_check:
            # Если нет файлов, показываем все форматы
            all_formats = self.file_converter.get_supported_formats()
            self.converter_format_combo['values'] = all_formats
            if all_formats and not self.converter_format_var.get() in all_formats:
                self.converter_format_var.set(all_formats[0] if all_formats else '')
            return
        
        # Находим общие форматы для всех выбранных файлов
        common_formats = None
        for file_data in files_to_check:
            available_formats = file_data.get('available_formats', [])
            if isinstance(available_formats, str):
                # Если это строка (старый формат), пропускаем
                continue
            if common_formats is None:
                common_formats = set(available_formats)
            else:
                common_formats = common_formats.intersection(set(available_formats))
        
        # Преобразуем в отсортированный список
        if common_formats:
            common_formats_list = sorted(list(common_formats))
            self.converter_format_combo['values'] = common_formats_list
            # Если текущий формат не в списке, выбираем первый доступный
            if not self.converter_format_var.get() in common_formats_list:
                self.converter_format_var.set(common_formats_list[0] if common_formats_list else '')
        else:
            # Если нет общих форматов, показываем все форматы
            all_formats = self.file_converter.get_supported_formats()
            self.converter_format_combo['values'] = all_formats
            if all_formats and not self.converter_format_var.get() in all_formats:
                self.converter_format_var.set(all_formats[0] if all_formats else '')
    
    def _filter_converter_files_by_type(self):
        """Фильтрация файлов в конвертере по типу"""
        if not hasattr(self, 'converter_tree') or not hasattr(self, 'converter_files'):
            return
        
        filter_type = self.converter_filter_var.get()
        
        # Очищаем дерево
        for item in self.converter_tree.get_children():
            self.converter_tree.delete(item)
        
        # Маппинг типов фильтра на категории
        filter_mapping = {
            "Все": None,
            "Изображения": "image",
            "Документы": "document",
            "Аудио": "audio",
            "Видео": "video"
        }
        
        target_category = filter_mapping.get(filter_type)
        
        # Добавляем только файлы, соответствующие фильтру
        visible_count = 0
        visible_files = []
        for file_data in self.converter_files:
            file_category = file_data.get('category')
            
            # Если фильтр "Все" или категория совпадает
            if target_category is None or file_category == target_category:
                file_name = os.path.basename(file_data['path'])
                self.converter_tree.insert("", tk.END, values=(file_name, file_data.get('status', 'Готов')))
                visible_count += 1
                visible_files.append(file_data)
        
        # Обновляем доступные форматы на основе фильтра типа
        if hasattr(self, 'converter_format_combo'):
            # Получаем все поддерживаемые форматы
            all_supported_formats = self.file_converter.get_supported_formats()
            
            # Формируем список форматов в зависимости от типа фильтра
            if target_category == "image":
                # Для изображений показываем только форматы изображений
                image_formats = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif',
                               '.ico', '.svg', '.heic', '.heif', '.avif', '.dng', '.cr2', '.nef', '.raw']
                filtered_formats = [f for f in all_supported_formats if f in image_formats]
            elif target_category == "document":
                # Для документов показываем только форматы документов
                doc_formats = ['.pdf', '.docx']
                filtered_formats = [f for f in all_supported_formats if f in doc_formats]
            elif target_category == "audio":
                # Для аудио показываем только форматы аудио (если они поддерживаются)
                # Используем все форматы из file_converter, а не хардкод
                audio_formats = list(self.file_converter.supported_audio_formats.keys())
                filtered_formats = [f for f in all_supported_formats if f in audio_formats]
            elif target_category == "video":
                # Для видео показываем только форматы видео (если они поддерживаются)
                # Используем все форматы из file_converter, а не хардкод
                video_formats = list(self.file_converter.supported_video_formats.keys())
                filtered_formats = [f for f in all_supported_formats if f in video_formats]
            else:
                # Для "Все" показываем все поддерживаемые форматы
                filtered_formats = all_supported_formats.copy()
            
            # Если есть видимые файлы, дополнительно фильтруем по их доступным форматам
            if visible_files:
                # Собираем все доступные форматы для видимых файлов
                all_available_formats = set()
                for file_data in visible_files:
                    available_formats = file_data.get('available_formats', [])
                    if isinstance(available_formats, list):
                        all_available_formats.update(available_formats)
                
                # Пересекаем форматы фильтра с доступными форматами файлов
                if all_available_formats:
                    filtered_formats = [f for f in filtered_formats if f in all_available_formats]
            
            # Всегда обновляем список форматов на основе фильтра
            # Если отфильтрованный список пустой, показываем его (это покажет, что для типа нет форматов)
            # Но если фильтр "Все", всегда показываем все форматы
            if target_category is None:
                # Для "Все" показываем все поддерживаемые форматы
                final_formats = all_supported_formats
            else:
                # Для конкретного типа показываем отфильтрованные форматы (даже если пусто)
                final_formats = filtered_formats if filtered_formats else []
            
            self.converter_format_combo['values'] = final_formats
            
            # Обновляем выбранное значение, если текущее не в списке
            current_value = self.converter_format_var.get()
            if final_formats:
                if current_value not in final_formats:
                    self.converter_format_var.set(final_formats[0] if final_formats else '')
            else:
                # Если список пустой, сбрасываем значение
                self.converter_format_var.set('')
        
        # Обновляем заголовок панели
        if hasattr(self, 'converter_left_panel'):
            total_count = len(self.converter_files)
            if filter_type == "Все":
                self.converter_left_panel.config(text=f"Список файлов (Файлов: {total_count})")
            else:
                self.converter_left_panel.config(text=f"Список файлов (Файлов: {visible_count} / {total_count})")
    
    def _convert_files(self):
        """Конвертация выбранных файлов"""
        # Защита от повторных вызовов
        if hasattr(self, '_converting_files') and self._converting_files:
            return
        
        if not hasattr(self, 'converter_files') or not self.converter_files:
            messagebox.showwarning("Предупреждение", "Список файлов пуст")
            return
        
        target_format = self.converter_format_var.get()
        if not target_format:
            messagebox.showwarning("Предупреждение", "Выберите целевой формат")
            return
        
        selected_items = self.converter_tree.selection()
        files_to_convert = self.converter_files
        
        # Если ничего не выбрано, конвертируем все
        if not selected_items:
            if not messagebox.askyesno("Подтверждение", 
                                      f"Конвертировать все {len(files_to_convert)} файл(ов) в {target_format}?"):
                return
        else:
            if not messagebox.askyesno("Подтверждение", 
                                      f"Конвертировать {len(selected_items)} файл(ов) в {target_format}?"):
                return
            # Фильтруем только выбранные файлы
            indices = [self.converter_tree.index(item) for item in selected_items]
            files_to_convert = [self.converter_files[i] for i in indices if 0 <= i < len(self.converter_files)]
        
        # Устанавливаем флаг обработки
        self._converting_files = True
        
        # Инициализируем прогресс-бар
        total_files = len(files_to_convert)
        self.root.after(0, lambda: self.converter_progress_bar.config(maximum=total_files, value=0))
        self.root.after(0, lambda: self.converter_progress_label.config(text=f"Обработка файлов: 0 / {total_files}"))
        
        # Обрабатываем файлы в отдельном потоке
        def process_files():
            success_count = 0
            error_count = 0
            processed = 0
            
            for file_data in files_to_convert:
                file_path = file_data['path']
                
                # Обновляем прогресс
                processed += 1
                file_name = os.path.basename(file_path)
                self.root.after(0, lambda p=processed, t=total_files, fn=file_name: 
                               self._update_converter_progress(p, t, fn))
                
                # Получаем значение чекбокса сжатия PDF
                compress_pdf = getattr(self, 'compress_pdf_var', tk.BooleanVar(value=False)).get()
                success, message, output_path = self.file_converter.convert(
                    file_path, target_format, compress_pdf=compress_pdf
                )
                
                # Находим индекс файла
                try:
                    index = self.converter_files.index(file_data)
                except ValueError:
                    index = -1
                
                # Обновляем статус в UI
                if index >= 0:
                    self.root.after(0, lambda idx=index, s=success, m=message, op=output_path: 
                                   self._update_converter_status(idx, s, m, op))
                
                if success:
                    success_count += 1
                    self.log(f"Файл конвертирован: {os.path.basename(file_path)} -> {os.path.basename(output_path) if output_path else 'N/A'}")
                else:
                    error_count += 1
                    self.log(f"Ошибка при конвертации {os.path.basename(file_path)}: {message}")
            
            # Сбрасываем прогресс-бар
            self.root.after(0, lambda: self.converter_progress_bar.config(value=0))
            self.root.after(0, lambda: self.converter_progress_label.config(text=""))
            
            # Показываем результат только один раз
            if success_count + error_count > 0:
                def show_converter_result():
                    # Проверяем, не было ли уже показано сообщение
                    if not hasattr(self, '_converter_result_shown'):
                        self._converter_result_shown = True
                        messagebox.showinfo(
                            "Результат",
                            f"Обработано файлов: {success_count + error_count}\n"
                            f"Успешно: {success_count}\n"
                            f"Ошибок: {error_count}"
                        )
                        # Сбрасываем флаг показа сообщения
                        self.root.after(100, lambda: setattr(self, '_converter_result_shown', False))
                    # Сбрасываем флаг обработки
                    self._converting_files = False
                
                self.root.after(0, show_converter_result)
            else:
                # Если не было файлов для обработки, сбрасываем флаг
                self._converting_files = False
        
        thread = threading.Thread(target=process_files, daemon=True)
        thread.start()
    
    def _update_converter_progress(self, current: int, total: int, filename: str):
        """Обновление прогресс-бара конвертации"""
        try:
            self.converter_progress_bar['value'] = current
            self.converter_progress_label.config(text=f"Обработка: {current} / {total} - {filename[:50]}")
        except Exception:
            pass
    
    def _update_converter_status(self, index: int, success: bool, message: str, output_path: Optional[str]):
        """Обновление статуса файла в списке конвертации"""
        if not hasattr(self, 'converter_tree'):
            return
        
        items = self.converter_tree.get_children()
        if 0 <= index < len(items):
            item = items[index]
            # Обрезаем сообщение до 50 символов для лучшего отображения
            status = "Успешно" if success else f"Ошибка: {message[:50]}"
            current_values = self.converter_tree.item(item, 'values')
            self.converter_tree.item(item, values=(current_values[0], status))
    
    def _clear_converter_files_list(self):
        """Очистка списка файлов для конвертации"""
        if not hasattr(self, 'converter_tree'):
            return
        
        if messagebox.askyesno("Подтверждение", "Очистить список файлов?"):
            self.converter_tree.delete(*self.converter_tree.get_children())
            self.converter_files = []
            # Обновляем заголовок панели
            if hasattr(self, 'converter_left_panel'):
                self.converter_left_panel.config(text=f"Список файлов (Файлов: 0)")
            self.log("Список файлов для конвертации очищен")
    
    def _setup_converter_drag_drop(self, list_frame, tree, tab_frame):
        """Настройка drag and drop для вкладки конвертации"""
        if not HAS_TKINTERDND2:
            return
        
        try:
            # Регистрируем фрейм списка файлов
            if hasattr(list_frame, 'drop_target_register'):
                list_frame.drop_target_register(DND_FILES)
                list_frame.dnd_bind('<<Drop>>', lambda e: self._on_drop_converter_files(e))
            
            # Регистрируем treeview
            if hasattr(tree, 'drop_target_register'):
                tree.drop_target_register(DND_FILES)
                tree.dnd_bind('<<Drop>>', lambda e: self._on_drop_converter_files(e))
            
            # Регистрируем всю вкладку
            if hasattr(tab_frame, 'drop_target_register'):
                tab_frame.drop_target_register(DND_FILES)
                tab_frame.dnd_bind('<<Drop>>', lambda e: self._on_drop_converter_files(e))
        except Exception as e:
            logger.debug(f"Не удалось настроить drag and drop для вкладки конвертации: {e}")
    
    def _on_drop_converter_files(self, event):
        """Обработка перетаскивания файлов на вкладку конвертации"""
        try:
            data = event.data
            if not data:
                return
            
            # Используем надежную логику парсинга из ui/drag_drop.py
            import re
            file_paths = []
            
            # Обрабатываем строку с путями (формат зависит от платформы)
            if sys.platform == 'win32':
                # Windows: пути могут быть в фигурных скобках {path1} {path2}
                # Используем regex для более надежного парсинга
                file_paths = re.findall(r'\{([^}]+)\}', data)
                if not file_paths:
                    # Если нет фигурных скобок, пробуем разделить по пробелам
                    # Но это может быть проблематично для путей с пробелами
                    file_paths = data.split()
            else:
                # Linux/Mac: пути разделены пробелами
                file_paths = data.split()
            
            # Очищаем пути от лишних пробелов и кавычек
            file_paths = [f.strip().strip('"').strip("'") for f in file_paths if f.strip()]
            
            # Фильтруем только существующие файлы
            valid_file_paths = [f for f in file_paths if os.path.exists(f) and os.path.isfile(f)]
            
            # Обрабатываем файлы
            added_count = 0
            for file_path in valid_file_paths:
                if not file_path:
                    continue
                
                try:
                    if not os.path.isabs(file_path):
                        file_path = os.path.abspath(file_path)
                    else:
                        file_path = os.path.normpath(file_path)
                except Exception:
                    continue
                
                if not os.path.exists(file_path) or not os.path.isfile(file_path):
                    continue
                
                # Проверяем, что файл еще не добавлен
                normalized_path = os.path.normpath(os.path.abspath(file_path))
                if any(os.path.normpath(os.path.abspath(f.get('path', ''))) == normalized_path 
                       for f in self.converter_files):
                    continue
                
                ext = os.path.splitext(file_path)[1].lower()
                
                # Определяем доступные форматы конвертации
                available_formats = []
                all_formats = self.file_converter.get_supported_formats()
                for target_format in all_formats:
                    if self.file_converter.can_convert(file_path, target_format):
                        available_formats.append(target_format)
                
                # Определяем категорию файла
                file_category = self.file_converter.get_file_type_category(file_path)
                
                # Определяем статус файла
                if available_formats:
                    status = 'Готов'
                else:
                    status = 'Не поддерживается'
                
                file_data = {
                    'path': file_path,
                    'format': ext,
                    'status': status,
                    'available_formats': available_formats,  # Сохраняем список форматов, а не строку
                    'category': file_category  # Сохраняем категорию файла
                }
                self.converter_files.append(file_data)
                added_count += 1
            
            if added_count > 0:
                # Обновляем заголовок панели
                if hasattr(self, 'converter_left_panel'):
                    count = len(self.converter_files)
                    self.converter_left_panel.config(text=f"Список файлов (Файлов: {count})")
                # Применяем фильтр - это обновит treeview и доступные форматы
                self._filter_converter_files_by_type()
                self.log(f"✅ Добавлено файлов для конвертации перетаскиванием: {added_count}")
        except Exception as e:
            logger.error(f"Ошибка при обработке перетаскивания файлов для конвертации: {e}", exc_info=True)
    
    def _create_settings_tab(self, notebook):
        """Создание вкладки настроек"""
        # Фрейм для вкладки настроек
        settings_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        notebook.add(settings_tab, text="Настройки")
        
        # Используем общий метод для создания содержимого
        self._create_settings_tab_content(settings_tab)
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
        scrollable_frame.configure(padx=20, pady=20)
        
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
                                         font=('Robot', 11),
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
                                            font=('Robot', 11),
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
                                      font=('Robot', 11),
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['text_primary'],
                                      selectcolor='white',
                                      activebackground=self.colors['bg_card'],
                                      activeforeground=self.colors['text_primary'])
        backup_check.pack(anchor=tk.W, pady=5)
        
        # Секция: Управление библиотеками
        if hasattr(self, 'library_manager') and self.library_manager:
            libs_frame = ttk.LabelFrame(content_frame, text="Управление библиотеками", 
                                      style='Card.TLabelframe', padding=20)
            libs_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
            
            libs_info_label = tk.Label(libs_frame,
                                     text="Управление библиотеками программы. Установка и удаление библиотек.",
                                     font=('Robot', 9),
                                     bg=self.colors['bg_card'],
                                     fg=self.colors['text_secondary'],
                                     wraplength=600,
                                     justify=tk.LEFT)
            libs_info_label.pack(anchor=tk.W, pady=(0, 15))
            
            # Фрейм для таблицы библиотек
            libs_table_frame = tk.Frame(libs_frame, bg=self.colors['bg_card'])
            libs_table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # Scrollbar для таблицы
            libs_scrollbar = ttk.Scrollbar(libs_table_frame, orient=tk.VERTICAL)
            libs_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Treeview для отображения библиотек
            libs_tree = ttk.Treeview(
                libs_table_frame,
                columns=('status', 'type', 'action'),
                show='tree headings',
                yscrollcommand=libs_scrollbar.set,
                height=12
            )
            libs_scrollbar.config(command=libs_tree.yview)
            
            # Настройка колонок
            libs_tree.heading('#0', text='Библиотека')
            libs_tree.heading('status', text='Статус')
            libs_tree.heading('type', text='Тип')
            libs_tree.heading('action', text='Действие')
            
            libs_tree.column('#0', width=250, minwidth=150)
            libs_tree.column('status', width=120, minwidth=100)
            libs_tree.column('type', width=120, minwidth=100)
            libs_tree.column('action', width=200, minwidth=150)
            
            libs_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            def refresh_libraries_table():
                """Обновление таблицы библиотек."""
                # Инвалидируем кэш для принудительной проверки всех библиотек
                self.library_manager.invalidate_cache()
                
                # Обновляем sys.path для обнаружения установленных библиотек
                try:
                    import site
                    user_site = site.getusersitepackages()
                    if user_site and user_site not in sys.path:
                        sys.path.insert(0, user_site)
                        site.addsitedir(user_site)
                except Exception:
                    pass
                
                # Очищаем кэш импортов для всех библиотек перед проверкой
                all_libs_dict = self.library_manager.get_all_libraries()
                for lib_name, import_name in all_libs_dict.items():
                    modules_to_remove = [m for m in list(sys.modules.keys()) if m.startswith(import_name)]
                    for m in modules_to_remove:
                        try:
                            del sys.modules[m]
                        except KeyError:
                            pass
                
                # Очистка таблицы
                for item in libs_tree.get_children():
                    libs_tree.delete(item)
                
                # Получаем все библиотеки
                all_libs_dict = self.library_manager.get_all_libraries()
                
                # Добавляем обязательные библиотеки
                required_node = libs_tree.insert('', 'end', text='Обязательные', tags=('category',))
                for lib_name in self.library_manager.REQUIRED_LIBRARIES.keys():
                    is_installed = self.library_manager.is_library_installed(lib_name)
                    status = "✓ Установлена" if is_installed else "✗ Отсутствует"
                    libs_tree.insert(required_node, 'end', text=lib_name, 
                                   values=(status, 'Обязательная', ''),
                                   tags=('required', 'installed' if is_installed else 'missing'))
                
                # Добавляем опциональные библиотеки
                optional_node = libs_tree.insert('', 'end', text='Опциональные', tags=('category',))
                for lib_name in self.library_manager.OPTIONAL_LIBRARIES.keys():
                    is_installed = self.library_manager.is_library_installed(lib_name)
                    status = "✓ Установлена" if is_installed else "○ Не установлена"
                    libs_tree.insert(optional_node, 'end', text=lib_name,
                                   values=(status, 'Опциональная', ''),
                                   tags=('optional', 'installed' if is_installed else 'missing'))
                
                # Добавляем Windows-специфичные библиотеки
                if sys.platform == 'win32':
                    windows_node = libs_tree.insert('', 'end', text='Windows-специфичные', tags=('category',))
                    for lib_name in self.library_manager.WINDOWS_OPTIONAL_LIBRARIES.keys():
                        is_installed = self.library_manager.is_library_installed(lib_name)
                        status = "✓ Установлена" if is_installed else "○ Не установлена"
                        libs_tree.insert(windows_node, 'end', text=lib_name,
                                       values=(status, 'Windows', ''),
                                       tags=('windows', 'installed' if is_installed else 'missing'))
                
                # Раскрываем все категории
                for item in libs_tree.get_children():
                    libs_tree.item(item, open=True)
                
                # Настройка цветов
                libs_tree.tag_configure('category', font=('Robot', 10, 'bold'))
                libs_tree.tag_configure('installed', foreground='green')
                libs_tree.tag_configure('missing', foreground='gray')
            
            # Первоначальная загрузка таблицы
            refresh_libraries_table()
            
            # Фрейм для кнопок действий
            libs_actions_frame = tk.Frame(libs_frame, bg=self.colors['bg_card'])
            libs_actions_frame.pack(fill=tk.X, pady=(10, 0))
            
            def install_selected_handler():
                """Установка выбранной библиотеки."""
                selected = libs_tree.selection()
                if not selected:
                    messagebox.showwarning("Внимание", "Выберите библиотеку для установки")
                    return
                
                item = selected[0]
                # Проверяем, что это не категория
                if libs_tree.get_children(item):
                    messagebox.showwarning("Внимание", "Выберите конкретную библиотеку, а не категорию")
                    return
                
                lib_name = libs_tree.item(item, 'text')
                
                # Проверяем, не установлена ли уже
                if self.library_manager.is_library_installed(lib_name):
                    messagebox.showinfo("Информация", f"Библиотека {lib_name} уже установлена")
                    return
                
                def install_thread():
                    success, message = self.library_manager.install_single_library(lib_name)
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Результат установки" if success else "Ошибка",
                        message
                    ))
                    self.root.after(0, refresh_libraries_table)
                
                threading.Thread(target=install_thread, daemon=True).start()
            
            install_btn = self.create_rounded_button(
                libs_actions_frame,
                "Установить",
                install_selected_handler,
                self.colors['primary'],
                'white',
                font=('Robot', 9, 'bold'),
                padx=15,
                pady=8,
                active_bg=self.colors['primary_hover'])
            install_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            def uninstall_selected_handler():
                """Удаление выбранной библиотеки."""
                selected = libs_tree.selection()
                if not selected:
                    messagebox.showwarning("Внимание", "Выберите библиотеку для удаления")
                    return
                
                item = selected[0]
                # Проверяем, что это не категория
                if libs_tree.get_children(item):
                    messagebox.showwarning("Внимание", "Выберите конкретную библиотеку, а не категорию")
                    return
                
                lib_name = libs_tree.item(item, 'text')
                
                # Проверяем, установлена ли
                if not self.library_manager.is_library_installed(lib_name):
                    messagebox.showinfo("Информация", f"Библиотека {lib_name} не установлена")
                    return
                
                # Подтверждение удаления
                if not messagebox.askyesno("Подтверждение", 
                                          f"Вы уверены, что хотите удалить библиотеку {lib_name}?"):
                    return
                
                def uninstall_thread():
                    success, message = self.library_manager.uninstall_library(lib_name)
                    self.root.after(0, lambda: messagebox.showinfo(
                        "Результат удаления" if success else "Ошибка",
                        message
                    ))
                    self.root.after(0, refresh_libraries_table)
                
                threading.Thread(target=uninstall_thread, daemon=True).start()
            
            uninstall_btn = self.create_rounded_button(
                libs_actions_frame,
                "Удалить",
                uninstall_selected_handler,
                '#dc3545',
                'white',
                font=('Robot', 9),
                padx=15,
                pady=8,
                active_bg='#c82333')
            uninstall_btn.pack(side=tk.LEFT, padx=(0, 10))
            
            refresh_btn = self.create_rounded_button(
                libs_actions_frame,
                "Обновить",
                refresh_libraries_table,
                self.colors.get('secondary', self.colors.get('bg_secondary', '#EDF2F7')),
                'white',
                font=('Robot', 9),
                padx=15,
                pady=8,
                active_bg=self.colors.get('secondary_hover', '#4B5563'))
            refresh_btn.pack(side=tk.LEFT)
            
            def check_all_handler():
                """Проверка всех библиотек."""
                def run_check():
                    try:
                        self.library_manager.check_and_install(
                            install_optional=True, 
                            silent=False,
                            force_check=True
                        )
                        self.root.after(0, refresh_libraries_table)
                    except Exception as e:
                        logger.error(f"Ошибка при проверке библиотек: {e}", exc_info=True)
                        self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Не удалось проверить библиотеки: {e}"))
                
                threading.Thread(target=run_check, daemon=True).start()
            
            check_all_btn = self.create_rounded_button(
                libs_actions_frame,
                "Проверить все",
                check_all_handler,
                self.colors['info'] if 'info' in self.colors else self.colors['primary'],
                'white',
                font=('Robot', 9),
                padx=15,
                pady=8,
                active_bg=self.colors['primary_hover'])
            check_all_btn.pack(side=tk.LEFT, padx=(10, 0))
        
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
        
        # Переключатель темы
        if HAS_THEME:
            theme_frame = tk.Frame(scrollable_frame, bg=self.colors['bg_card'])
            theme_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
            
            theme_label = tk.Label(
                theme_frame,
                text="Тема интерфейса:",
                font=('Robot', 10, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']
            )
            theme_label.pack(anchor=tk.W, pady=(0, 5))
            
            theme_var = tk.StringVar(value=self.settings_manager.get('theme', 'light'))
            
            def on_theme_change():
                theme = theme_var.get()
                if hasattr(self, 'theme_manager'):
                    self.theme_manager.set_theme(theme)
                    self.colors = self.theme_manager.colors
                    self.settings_manager.set('theme', theme)
                    self.settings_manager.save_settings()
                    messagebox.showinfo(
                        "Тема изменена",
                        "Тема изменена. Перезапустите приложение для применения изменений."
                    )
            
            light_radio = tk.Radiobutton(
                theme_frame,
                text="Светлая",
                variable=theme_var,
                value='light',
                command=on_theme_change,
                font=('Robot', 11),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary'],
                selectcolor=self.colors['bg_card'],
                activebackground=self.colors['bg_card'],
                activeforeground=self.colors['text_primary']
            )
            light_radio.pack(anchor=tk.W, pady=2)
            
            dark_radio = tk.Radiobutton(
                theme_frame,
                text="Темная",
                variable=theme_var,
                value='dark',
                command=on_theme_change,
                font=('Robot', 11),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary'],
                selectcolor=self.colors['bg_card'],
                activebackground=self.colors['bg_card'],
                activeforeground=self.colors['text_primary']
            )
            dark_radio.pack(anchor=tk.W, pady=2)
        
        # Настройка резервного копирования
        if HAS_BACKUP_MANAGER:
            backup_frame = tk.Frame(scrollable_frame, bg=self.colors['bg_card'])
            backup_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
            
            backup_label = tk.Label(
                backup_frame,
                text="Резервное копирование:",
                font=('Robot', 10, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']
            )
            backup_label.pack(anchor=tk.W, pady=(0, 5))
            
            backup_var = tk.BooleanVar(value=self.settings_manager.get('backup', False))
            
            def on_backup_change():
                backup_enabled = backup_var.get()
                self.settings_manager.set('backup', backup_enabled)
                self.settings_manager.save_settings()
                if backup_enabled and not self.backup_manager:
                    try:
                        self.backup_manager = BackupManager()
                        messagebox.showinfo("Резервное копирование", "Резервное копирование включено")
                    except Exception as e:
                        messagebox.showerror("Ошибка", f"Не удалось включить резервное копирование: {e}")
                        backup_var.set(False)
                elif not backup_enabled:
                    self.backup_manager = None
            
            backup_check = tk.Checkbutton(
                backup_frame,
                text="Создавать резервные копии перед переименованием",
                variable=backup_var,
                command=on_backup_change,
                font=('Robot', 11),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary'],
                selectcolor=self.colors['bg_card'],
                activebackground=self.colors['bg_card'],
                activeforeground=self.colors['text_primary']
            )
            backup_check.pack(anchor=tk.W, pady=2)
    
    def _create_about_tab(self, notebook):
        """Создание вкладки о программе"""
        # Фрейм для вкладки о программе
        about_tab = tk.Frame(notebook, bg=self.colors['bg_main'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        notebook.add(about_tab, text="О программе")
        
        # Содержимое о программе с прокруткой
        canvas = tk.Canvas(about_tab, bg=self.colors['bg_main'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(about_tab, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['bg_main'])
        
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
        scrollable_frame.configure(padx=20, pady=20)
        
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
            logger.debug(f"Ошибка загрузки иконки: {e}")
        
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
        contact_card = ttk.LabelFrame(content_frame, text="Связаться с разработчиками", 
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
        support_tab = tk.Frame(notebook, bg=self.colors['bg_main'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        notebook.add(support_tab, text="Поддержка")
        
        # Содержимое поддержки без скроллбара
        content_frame = tk.Frame(support_tab, bg=self.colors['bg_main'])
        content_frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
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
        self.root.bind('<Control-Shift-A>', lambda e: self.add_files())  # Изменено на Ctrl+Shift+A
        self.root.bind('<Control-z>', lambda e: self.undo_rename())
        self.root.bind('<Control-y>', lambda e: self.redo_rename())
        self.root.bind('<Control-Shift-Z>', lambda e: self.redo_rename())
        self.root.bind('<Delete>', lambda e: self.delete_selected())
        self.root.bind('<Control-o>', lambda e: self.add_folder())
        self.root.bind('<Control-s>', lambda e: self.save_template_quick())
        self.root.bind('<Control-f>', lambda e: self.focus_search())
        self.root.bind('<F5>', lambda e: self.refresh_treeview())
        self.root.bind('<Control-r>', lambda e: self.apply_methods())
    
    def save_template_quick(self):
        """Быстрое сохранение шаблона (Ctrl+S)"""
        self.save_current_template()
    
    def focus_search(self):
        """Фокус на поле поиска (Ctrl+F)"""
        if hasattr(self, 'search_entry'):
            self.search_entry.focus()
            self.search_entry.select_range(0, tk.END)
    
    def on_search_change(self, event=None):
        """Обработка изменения текста поиска"""
        self.refresh_treeview()
    
    def clear_search(self):
        """Очистка поля поиска"""
        if hasattr(self, 'search_entry'):
            self.search_entry.delete(0, tk.END)
            self.refresh_treeview()
    
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
        try:
            # Получаем данные из события
            data = event.data
            
            # tkinterdnd2 на Windows возвращает файлы в формате: {file1} {file2} {file3}
            # Где каждый файл заключен в фигурные скобки
            processed_files = []
            
            # Логируем исходные данные для отладки
            if not data:
                error_msg = "Данные не получены из события перетаскивания"
                self.log(error_msg)
                return
            
            # Логируем первые 200 символов данных для отладки
            data_preview = data[:200] + "..." if len(data) > 200 else data
            self.log(f"Получены данные drag&drop (первые 200 символов): {data_preview}")
            
            # Разбираем по фигурным скобкам (стандартный формат tkinterdnd2)
            # Формат: {C:\path\file1.ext} {C:\path\file2.ext} ...
            file_paths = []
            
            # Используем более надёжный метод разбора путей
            # tkinterdnd2 на Windows возвращает файлы в формате: {file1} {file2} {file3}
            # Где каждый файл заключен в фигурные скобки
            
            # Метод 1: Ищем все паттерны {путь} - основной формат tkinterdnd2
            # Используем нежадное совпадение для правильной обработки множественных путей
            pattern = r'\{([^}]+)\}'
            matches = re.findall(pattern, data)
            
            if matches:
                # Найдены пути в фигурных скобках - это основной формат tkinterdnd2
                file_paths = [match.strip() for match in matches if match.strip()]
                self.log(f"Найдено путей в фигурных скобках: {len(file_paths)}")
                # Логируем первые несколько путей для отладки
                if file_paths:
                    preview_paths = file_paths[:3]
                    for i, path in enumerate(preview_paths, 1):
                        self.log(f"  Путь {i}: {path}")
                    if len(file_paths) > 3:
                        self.log(f"  ... и еще {len(file_paths) - 3} путей")
            else:
                # Метод 2: Если нет фигурных скобок, пробуем другие форматы
                # На Windows пути могут быть в кавычках и разделены пробелами
                if sys.platform == 'win32':
                    # Пробуем найти пути в кавычках: "C:\path1" "C:\path2"
                    quoted_paths = re.findall(r'"([^"]+)"', data)
                    if quoted_paths:
                        file_paths = [p.strip() for p in quoted_paths if p.strip()]
                        self.log(f"Найдено путей в кавычках: {len(file_paths)}")
                    else:
                        # Пробуем найти пути, начинающиеся с буквы диска
                        # Паттерн: C:\... или C:/... (до следующего пробела или конца строки)
                        win_path_pattern = r'([A-Za-z]:[\\/][^\s"]+)'
                        win_matches = re.findall(win_path_pattern, data)
                        if win_matches:
                            file_paths = [m.strip() for m in win_matches if m.strip()]
                            self.log(f"Найдено Windows путей по паттерну: {len(file_paths)}")
                        else:
                            # Последняя попытка: пробуем как один путь
                            data_clean = data.strip().strip('"').strip("'")
                            if data_clean and os.path.exists(data_clean):
                                file_paths = [data_clean]
                                self.log("Найден один путь без скобок")
                else:
                    # Linux/Mac: пути разделены пробелами
                    if data.strip():
                        data_clean = data.strip().strip('"').strip("'")
                        if os.path.exists(data_clean):
                            file_paths = [data_clean]
                        else:
                            parts = data.split()
                            for part in parts:
                                part_clean = part.strip('"').strip("'")
                                if part_clean and os.path.exists(part_clean):
                                    file_paths.append(part_clean)
            
            # Метод 3: Если всё ещё пусто, пробуем как один файл
            if not file_paths and data.strip():
                data_clean = data.strip().strip('"').strip("'").strip('{}')
                if data_clean and os.path.exists(data_clean):
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
            error_msg = str(e)
            self.log(f"❌ Ошибка при обработке перетащенных файлов: {error_msg}")
            logger.error(f"Ошибка drag and drop: {error_msg}", exc_info=True)
    
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
        
        # Применяем методы (включая шаблон), если они есть
        if self.methods_manager.get_methods():
            self.apply_methods()
        else:
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
        
        # Контекстное меню для таблицы файлов
        self.tree.bind('<Button-3>', self.show_file_context_menu)
    
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
                        # Сохраняем новое имя с исходной позиции (оно должно остаться на месте)
                        preserved_new_name = self.files[start_idx].get('new_name', '')
                        
                        # Сохраняем новое имя целевой позиции (его получит перемещенный файл)
                        target_new_name = self.files[target_idx].get('new_name', '')
                        
                        # Перемещаем файл (старое имя, путь, расширение)
                        file_data = self.files.pop(start_idx)
                        
                        # Если перемещаем вниз, корректируем target_idx после удаления
                        if start_idx < target_idx:
                            target_idx -= 1
                        
                        # Вставляем файл на новую позицию с новым именем целевой позиции
                        file_data['new_name'] = target_new_name
                        self.files.insert(target_idx, file_data)
                        
                        # Новое имя исходной позиции остается на месте и привязывается к файлу,
                        # который теперь находится на этой позиции
                        if start_idx < len(self.files):
                            self.files[start_idx]['new_name'] = preserved_new_name
                        
                        # Обновляем дерево
                        self.refresh_treeview()
                        
                        # Выделяем перемещенный элемент
                        children = self.tree.get_children()
                        if target_idx < len(children):
                            self.tree.selection_set(children[target_idx])
                            self.tree.see(children[target_idx])  # Прокручиваем к элементу
                        
                        old_name = file_data.get('old_name', 'unknown')
                        self.log(f"Файл '{old_name}' перемещен с позиции {start_idx + 1} на {target_idx + 1}")
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
        
        # Получаем текст поиска
        search_text = ""
        use_regex = False
        if hasattr(self, 'search_entry'):
            search_text = self.search_entry.get().strip()
            if hasattr(self, 'search_regex_var'):
                use_regex = self.search_regex_var.get()
        
        # Компилируем regex паттерн, если включен regex
        search_pattern = None
        if search_text and use_regex:
            try:
                search_pattern = re.compile(search_text, re.IGNORECASE)
            except re.error:
                # Если regex невалидный, используем обычный поиск
                use_regex = False
        
        # Добавляем элементы в правильном порядке
        for file_data in self.files:
            # Фильтрация по поисковому запросу
            if search_text:
                if use_regex and search_pattern:
                    # Поиск по regex
                    old_name = file_data.get('old_name', '')
                    new_name = file_data.get('new_name', '')
                    path = file_data.get('path', '')
                    extension = file_data.get('extension', '')
                    full_text = f"{old_name} {new_name} {path} {extension}"
                    
                    if not search_pattern.search(full_text):
                        continue
                else:
                    # Обычный поиск
                    search_lower = search_text.lower()
                    old_name = file_data.get('old_name', '').lower()
                    new_name = file_data.get('new_name', '').lower()
                    path = file_data.get('path', '').lower()
                    extension = file_data.get('extension', '').lower()
                    
                    if (search_lower not in old_name and 
                        search_lower not in new_name and 
                        search_lower not in path and 
                        search_lower not in extension):
                        continue
            
            status = file_data.get('status', 'Готов')
            tags = ()
            if status == "Готов":
                tags = ('ready',)
            elif "Ошибка" in status:
                tags = ('error',)
            elif "Конфликт" in status:
                tags = ('conflict',)
            
            # Подсветка изменений
            old_name = file_data.get('old_name', '')
            new_name = file_data.get('new_name', '')
            extension = file_data.get('extension', '')
            
            # Определяем, изменилось ли имя
            if old_name != new_name:
                # Имя изменилось - добавляем специальный тег
                if 'ready' in tags:
                    tags = ('ready', 'changed')
                elif 'error' in tags:
                    tags = ('error', 'changed')
                elif 'conflict' in tags:
                    tags = ('conflict', 'changed')
            
            self.tree.insert("", tk.END, values=(
                old_name,
                new_name,
                file_data.get('path', ''),
                status
            ), tags=tags)
        
        # Обновляем видимость скроллбаров после обновления содержимого
        if hasattr(self, 'tree_scrollbar_y') and hasattr(self, 'tree_scrollbar_x'):
            self.root.after_idle(lambda: self.update_scrollbar_visibility(self.tree, self.tree_scrollbar_y, 'vertical'))
            self.root.after_idle(lambda: self.update_scrollbar_visibility(self.tree, self.tree_scrollbar_x, 'horizontal'))
    
    def log(self, message: str):
        """Добавление сообщения в лог"""
        self.logger.log(message)
    
    def _copy_selected_text(self, text_widget):
        """Копирование выделенного текста в буфер обмена"""
        try:
            if text_widget.tag_ranges(tk.SEL):
                # Есть выделенный текст
                selected_text = text_widget.get(tk.SEL_FIRST, tk.SEL_LAST)
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                self.root.update()
            else:
                # Нет выделенного текста, копируем всё
                self._copy_all_text(text_widget)
        except Exception as e:
            logger.debug(f"Ошибка при копировании текста: {e}")
    
    def _copy_all_text(self, text_widget):
        """Копирование всего текста в буфер обмена"""
        try:
            all_text = text_widget.get(1.0, tk.END)
            if all_text.strip():
                self.root.clipboard_clear()
                self.root.clipboard_append(all_text.strip())
                self.root.update()
                # Не логируем, чтобы не дублировать сообщения
                messagebox.showinfo("Успех", "Весь лог скопирован в буфер обмена")
        except Exception as e:
            logger.debug(f"Ошибка при копировании всего текста: {e}")
    
    def _select_all_text(self, text_widget):
        """Выделение всего текста"""
        try:
            text_widget.tag_add(tk.SEL, "1.0", tk.END)
            text_widget.mark_set(tk.INSERT, "1.0")
            text_widget.see(tk.INSERT)
        except Exception as e:
            logger.debug(f"Ошибка при выделении текста: {e}")
    
    def add_files(self):
        """Добавление файлов через диалог выбора"""
        files = filedialog.askopenfilenames(
            title="Выберите файлы",
            filetypes=[
                ("Все файлы", "*.*"),
                ("Изображения", "*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff *.tif *.ico *.svg *.heic *.heif *.avif *.dng *.cr2 *.nef *.raw"),
                ("Документы", "*.pdf *.docx *.doc *.xlsx *.xls *.pptx *.ppt *.txt *.rtf *.csv *.html *.htm *.odt *.ods *.odp"),
                ("Аудио", "*.mp3 *.wav *.flac *.aac *.ogg *.m4a *.wma *.opus"),
                ("Видео", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.3gp"),
            ]
        )
        if files:
            files_before = len(self.files)
            for file_path in files:
                self.add_file(file_path)
            # Применяем методы (включая шаблон), если они есть
            if self.methods_manager.get_methods():
                self.apply_methods()
            else:
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
            # Применяем методы (включая шаблон), если они есть
            if self.methods_manager.get_methods():
                self.apply_methods()
            else:
                # Обновляем интерфейс
                self.refresh_treeview()
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
            existing_path = existing_file.get('full_path') or existing_file.get('path', '')
            if existing_path:
                existing_path = os.path.normpath(os.path.abspath(existing_path))
            else:
                continue
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
            # Сортируем индексы в обратном порядке для корректного удаления
            indices = sorted([self.tree.index(item) for item in selected], reverse=True)
            for index in indices:
                if index < len(self.files):
                    self.files.pop(index)
                # Удаляем из дерева
                children = list(self.tree.get_children())
                if index < len(children):
                    self.tree.delete(children[index])
            self.refresh_treeview()
            self.update_status()
            self.log(f"Удалено файлов из списка: {len(selected)}")
    
    def select_all(self):
        """Выделение всех файлов"""
        for item in self.tree.get_children():
            self.tree.selection_add(item)
    
    def deselect_all(self):
        """Снятие выделения со всех файлов"""
        self.tree.selection_set(())
    
    def apply_to_selected(self):
        """Применение методов только к выбранным файлам"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите файлы для применения методов")
            return
        
        # Получаем индексы выбранных файлов
        selected_indices = [self.tree.index(item) for item in selected]
        selected_files = [self.files[i] for i in selected_indices if i < len(self.files)]
        
        if not selected_files:
            return
        
        # Применяем методы только к выбранным файлам
        for file_data in selected_files:
            try:
                new_name, extension = self.methods_manager.apply_methods(
                    file_data.get('old_name', ''),
                    file_data.get('extension', ''),
                    file_data.get('full_path') or file_data.get('path', '')
                )
                file_data['new_name'] = new_name
                file_data['extension'] = extension
                
                # Валидация
                file_path = file_data.get('path') or file_data.get('full_path', '')
                status = validate_filename(new_name, extension, file_path, 0)
                file_data['status'] = status
            except Exception as e:
                file_data['status'] = f"Ошибка: {str(e)}"
                logger.error(f"Ошибка применения методов к файлу: {e}", exc_info=True)
        
        # Проверка конфликтов
        check_conflicts(selected_files)
        self.refresh_treeview()
        self.log(f"Методы применены к {len(selected_files)} выбранным файлам")
    
    def show_file_context_menu(self, event):
        """Показ контекстного меню для файла"""
        item = self.tree.identify_row(event.y)
        if not item:
            return
        
        # Выделяем элемент, если он не выделен
        if item not in self.tree.selection():
            self.tree.selection_set(item)
        
        # Создаем контекстное меню
        context_menu = tk.Menu(self.root, tearoff=0, 
                              bg=self.colors.get('bg_card', '#ffffff'),
                              fg=self.colors.get('text_primary', '#000000'),
                              activebackground=self.colors.get('primary', '#4a90e2'),
                              activeforeground='white')
        
        context_menu.add_command(label="Удалить из списка", command=self.delete_selected)
        context_menu.add_separator()
        context_menu.add_command(label="Открыть папку", command=self.open_file_folder)
        context_menu.add_command(label="Переименовать вручную", command=self.rename_file_manually)
        context_menu.add_separator()
        context_menu.add_command(label="Копировать путь", command=self.copy_file_path)
        
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    def open_file_folder(self):
        """Открытие папки с выбранным файлом"""
        selected = self.tree.selection()
        if not selected:
            return
        
        try:
            import subprocess
            import platform
            
            item = selected[0]
            index = self.tree.index(item)
            if index < len(self.files):
                file_data = self.files[index]
                file_path = file_data.get('full_path') or file_data.get('path', '')
                if file_path:
                    folder_path = os.path.dirname(file_path)
                    if platform.system() == 'Windows':
                        subprocess.Popen(f'explorer "{folder_path}"')
                    elif platform.system() == 'Darwin':
                        subprocess.Popen(['open', folder_path])
                    else:
                        subprocess.Popen(['xdg-open', folder_path])
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть папку:\n{str(e)}")
            logger.error(f"Ошибка открытия папки: {e}", exc_info=True)
    
    def rename_file_manually(self):
        """Ручное переименование выбранного файла"""
        selected = self.tree.selection()
        if not selected:
            return
        
        item = selected[0]
        index = self.tree.index(item)
        if index >= len(self.files):
            return
        
        file_data = self.files[index]
        old_name = file_data.get('old_name', '')
        extension = file_data.get('extension', '')
        
        new_name = simpledialog.askstring(
            "Переименовать файл",
            f"Введите новое имя для файла:",
            initialvalue=old_name
        )
        
        if new_name and new_name.strip():
            new_name = new_name.strip()
            file_data['new_name'] = new_name
            file_data['extension'] = extension
            self.refresh_treeview()
            self.log(f"Имя файла изменено вручную: {old_name} -> {new_name}")
    
    def copy_file_path(self):
        """Копирование пути файла в буфер обмена"""
        selected = self.tree.selection()
        if not selected:
            return
        
        try:
            item = selected[0]
            index = self.tree.index(item)
            if index < len(self.files):
                file_data = self.files[index]
                file_path = file_data.get('full_path') or file_data.get('path', '')
                if file_path:
                    self.root.clipboard_clear()
                    self.root.clipboard_append(file_path)
                    self.log(f"Путь скопирован в буфер обмена: {file_path}")
        except Exception as e:
            logger.error(f"Ошибка копирования пути: {e}", exc_info=True)
    
    def update_status(self):
        """Обновление статусной строки"""
        count = len(self.files)
        if hasattr(self, 'left_panel'):
            self.left_panel.config(text=f"Список файлов (Файлов: {count})")
    
    def export_files_list(self):
        """Экспорт списка файлов в файл"""
        if not self.files:
            messagebox.showwarning("Предупреждение", "Список файлов пуст")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON файлы", "*.json"),
                ("CSV файлы", "*.csv"),
                ("Все файлы", "*.*")
            ],
            title="Экспорт списка файлов"
        )
        
        if not filename:
            return
        
        try:
            if filename.endswith('.csv'):
                # Экспорт в CSV
                import csv
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Старое имя', 'Новое имя', 'Расширение', 'Путь', 'Статус'])
                    for file_data in self.files:
                        writer.writerow([
                            file_data.get('old_name', ''),
                            file_data.get('new_name', ''),
                            file_data.get('path', ''),
                            file_data.get('status', 'Готов')
                        ])
            else:
                # Экспорт в JSON
                import json
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.files, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("Успех", f"Список файлов экспортирован в:\n{filename}")
            self.log(f"Список файлов экспортирован: {filename}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось экспортировать список файлов:\n{str(e)}")
            logger.error(f"Ошибка экспорта списка файлов: {e}", exc_info=True)
    
    def import_files_list(self):
        """Импорт списка файлов из файла"""
        filename = filedialog.askopenfilename(
            filetypes=[
                ("JSON файлы", "*.json"),
                ("CSV файлы", "*.csv"),
                ("Все файлы", "*.*")
            ],
            title="Импорт списка файлов"
        )
        
        if not filename:
            return
        
        try:
            imported_files = []
            
            if filename.endswith('.csv'):
                # Импорт из CSV
                import csv
                with open(filename, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        file_path = row.get('Путь', '')
                        if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                            file_data = {
                                'path': file_path,
                                'full_path': file_path,
                                'old_name': row.get('Старое имя', ''),
                                'new_name': row.get('Новое имя', ''),
                                'extension': row.get('Расширение', ''),
                                'status': row.get('Статус', 'Готов')
                            }
                            imported_files.append(file_data)
            else:
                # Импорт из JSON
                import json
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for file_data in data:
                            file_path = file_data.get('path') or file_data.get('full_path', '')
                            if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
                                imported_files.append(file_data)
            
            if imported_files:
                # Добавляем файлы в список
                for file_data in imported_files:
                    # Проверяем на дубликаты
                    is_duplicate = False
                    file_path = file_data.get('full_path') or file_data.get('path', '')
                    if file_path:
                        file_path = os.path.normpath(os.path.abspath(file_path))
                        for existing_file in self.files:
                            existing_path = existing_file.get('full_path') or existing_file.get('path', '')
                            if existing_path:
                                existing_path = os.path.normpath(os.path.abspath(existing_path))
                                if existing_path == file_path:
                                    is_duplicate = True
                                    break
                    
                    if not is_duplicate:
                        self.files.append(file_data)
                
                # Применяем методы (включая шаблон), если они есть
                if self.methods_manager.get_methods():
                    self.apply_methods()
                else:
                    # Обновляем интерфейс
                    self.refresh_treeview()
                self.update_status()
                messagebox.showinfo("Успех", f"Импортировано файлов: {len(imported_files)}")
                self.log(f"Импортировано файлов: {len(imported_files)}")
            else:
                messagebox.showwarning("Предупреждение", "Не найдено валидных файлов для импорта")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось импортировать список файлов:\n{str(e)}")
            logger.error(f"Ошибка импорта списка файлов: {e}", exc_info=True)
    
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
        
        # Кнопки шаблонов теперь создаются в create_new_name_settings
        
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
            ext = file_data.get('extension', '').lower()
            if not ext:
                continue
            if ext:
                extensions[ext] = extensions.get(ext, 0) + 1
        
        return extensions
    
    def create_new_name_settings(self):
        """Создание настроек для метода Новое имя"""
        # Поле ввода шаблона
        template_label_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        template_label_frame.pack(fill=tk.X, pady=(0, 2))
        
        template_label = tk.Label(template_label_frame, text="Новое имя (шаблон):", 
                                 font=('Robot', 9, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        template_label.pack(side=tk.LEFT)
        
        self.new_name_template = ttk.Entry(self.settings_frame, width=18, font=('Robot', 9))
        self.new_name_template.pack(fill=tk.X, pady=(0, 4))
        
        # Кнопки шаблонов под полем ввода в одну линию
        font = ('Robot', 9, 'bold')
        padx = 6
        pady = 6
        
        self.template_buttons_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        self.template_buttons_frame.pack(fill=tk.X, pady=(0, 6))
        self.template_buttons_frame.columnconfigure(0, weight=1)
        self.template_buttons_frame.columnconfigure(1, weight=1)
        
        self.btn_save_template = self.create_rounded_button(
            self.template_buttons_frame, "Сохранить шаблон", self.save_current_template,
            '#10B981', 'white',
            font=font, padx=padx, pady=pady,
            active_bg='#059669', expand=True)
        self.btn_save_template.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        
        self.btn_saved = self.create_rounded_button(
            self.template_buttons_frame, "Сохраненные шаблоны", self.show_saved_templates,
            self.colors['primary'], 'white',
            font=font, padx=padx, pady=pady,
            active_bg=self.colors['primary_hover'], expand=True)
        self.btn_saved.grid(row=0, column=1, sticky="ew")
        
        # Настройка начального номера
        number_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        number_frame.pack(fill=tk.X, pady=(0, 4))
        
        number_label = tk.Label(number_frame, text="Начальный номер для {n}:", 
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        number_label.pack(side=tk.LEFT, padx=(0, 10))
        
        self.new_name_start_number = ttk.Entry(number_frame, width=10, font=('Robot', 9))
        self.new_name_start_number.insert(0, "1")
        self.new_name_start_number.pack(side=tk.LEFT)
        
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
        def on_focus_out(e):
            self._apply_template_immediate()
        
        self.new_name_template.bind('<KeyRelease>', on_template_change)
        self.new_name_template.bind('<FocusOut>', on_focus_out)
        self.new_name_start_number.bind('<KeyRelease>', on_number_change)
        self.new_name_start_number.bind('<FocusOut>', on_focus_out)
        
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
            var_label = tk.Label(var_frame, text=f"{var} ",
                               font=('Courier New', 11, 'bold'),
                               foreground=self.colors['primary'],
                               cursor="hand2",
                               bg=self.colors['bg_secondary'])
            var_label.pack(side=tk.LEFT)
            def on_var_click(e, v=var):
                self.insert_variable(v)
            
            var_label.bind("<Button-1>", on_var_click)
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
            desc_label.pack(side=tk.LEFT)
    
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
    
    def load_templates_from_file(self):
        """Загрузка шаблонов из файла"""
        try:
            # Открываем диалог выбора файла
            file_path = filedialog.askopenfilename(
                title="Выберите файл с шаблонами",
                filetypes=[
                    ("JSON файлы", "*.json"),
                    ("Все файлы", "*.*")
                ],
                defaultextension=".json"
            )
            
            if not file_path:
                return
            
            # Загружаем шаблоны из файла
            import json
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_templates = json.load(f)
            
            if not isinstance(loaded_templates, dict):
                messagebox.showerror("Ошибка", "Неверный формат файла шаблонов")
                return
            
            if not loaded_templates:
                messagebox.showwarning("Предупреждение", "Файл не содержит шаблонов")
                return
            
            # Подсчитываем количество шаблонов для добавления
            new_templates = {}
            existing_count = 0
            added_count = 0
            
            for template_name, template_data in loaded_templates.items():
                # Проверяем формат шаблона
                if isinstance(template_data, dict):
                    if 'template' not in template_data:
                        continue
                elif isinstance(template_data, str):
                    # Преобразуем старый формат в новый
                    template_data = {'template': template_data, 'start_number': '1'}
                else:
                    continue
                
                # Если шаблон с таким именем уже существует, добавляем суффикс
                original_name = template_name
                counter = 1
                while template_name in self.saved_templates:
                    template_name = f"{original_name} ({counter})"
                    counter += 1
                    existing_count += 1
                
                new_templates[template_name] = template_data
                added_count += 1
            
            if not new_templates:
                messagebox.showwarning("Предупреждение", "Не удалось загрузить ни одного шаблона из файла")
                return
            
            # Объединяем с существующими шаблонами
            self.saved_templates.update(new_templates)
            
            # Сохраняем обновленные шаблоны
            self.templates_manager.templates = self.saved_templates
            self.save_templates()
            self.templates_manager.save_templates(self.saved_templates)
            
            # Показываем результат
            message = f"Загружено шаблонов: {added_count}"
            if existing_count > 0:
                message += f"\nПереименовано из-за совпадений: {existing_count}"
            messagebox.showinfo("Успех", message)
            self.log(f"Загружено {added_count} шаблонов из файла: {file_path}")
            
        except json.JSONDecodeError:
            messagebox.showerror("Ошибка", "Неверный формат JSON файла")
        except FileNotFoundError:
            messagebox.showerror("Ошибка", "Файл не найден")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить шаблоны:\n{e}")
            self.log(f"Ошибка загрузки шаблонов: {e}")
    
    def show_saved_templates(self):
        """Показать окно с сохраненными шаблонами"""
        try:
            # Обновляем список шаблонов из менеджера
            self.saved_templates = self.templates_manager.templates
            
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
            
            # Функция для обновления списка шаблонов
            def refresh_template_list():
                listbox.delete(0, tk.END)
                template_keys = sorted(self.saved_templates.keys())
                for template_name in template_keys:
                    template_data = self.saved_templates[template_name]
                    if isinstance(template_data, dict):
                        template = template_data.get('template', '')
                    else:
                        template = str(template_data)
                    display_text = f"{template_name} → {template}"
                    listbox.insert(tk.END, display_text)
            
            # Заполняем список шаблонов
            refresh_template_list()
            
            listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Автоматическое управление видимостью скроллбара
            def update_saved_template_scrollbar(*args):
                self.update_scrollbar_visibility(listbox, scrollbar, 'vertical')
            
            def on_template_configure(e):
                template_window.after_idle(update_saved_template_scrollbar)
            
            listbox.bind('<Configure>', on_template_configure)
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
            btn_frame.columnconfigure(5, weight=1)
            
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
            
            def load_templates_and_refresh():
                """Загрузка шаблонов с обновлением списка в окне"""
                # Вызываем метод загрузки
                self.load_templates_from_file()
                
                # Обновляем список шаблонов в окне
                self.saved_templates = self.templates_manager.templates
                
                # Обновляем listbox
                refresh_template_list()
                
                # Обновляем скроллбар
                template_window.after_idle(update_saved_template_scrollbar)
            
            btn_load = self.create_rounded_button(
                btn_frame, "Загрузить", load_templates_and_refresh,
                '#3B82F6', 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg='#2563EB')
            btn_load.grid(row=0, column=3, sticky="ew", padx=(0, 5))
            
            btn_close = self.create_rounded_button(
                btn_frame, "Закрыть", template_window.destroy,
                '#818CF8', 'white',
                font=('Robot', 9, 'bold'), padx=10, pady=6,
                active_bg='#6366F1')
            btn_close.grid(row=0, column=4, sticky="ew")
            
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
            # Безопасный доступ к данным файла
            new_name = file_data.get('old_name', '')
            extension = file_data.get('extension', '')
            
            if not new_name:
                continue
            
            # Применяем все методы последовательно
            file_path = file_data.get('full_path') or file_data.get('path', '')
            if not file_path:
                continue
            
            for method in self.methods_manager.get_methods():
                try:
                    new_name, extension = method.apply(new_name, extension, file_path)
                except Exception as e:
                    old_name = file_data.get('old_name', 'unknown')
                    self.log(f"Ошибка при применении метода к {old_name}: {e}")
            
            file_data['new_name'] = new_name
            file_data['extension'] = extension
            
            # Проверка на валидность имени
            file_path = file_data.get('path') or file_data.get('full_path', '')
            status = validate_filename(new_name, extension, file_path, i)
            file_data['status'] = status
            
            # Обновление в таблице
            item = None
            try:
                children = self.tree.get_children()
                if i < len(children):
                    item = children[i]
                    self.tree.item(item, values=(
                        file_data.get('old_name', ''),
                        new_name,
                        file_data.get('path', ''),
                        status
                    ))
                else:
                    # Если индекс не совпадает, ищем элемент по старому имени
                    for child_item in children:
                        item_values = self.tree.item(child_item, 'values')
                        old_name = file_data.get('old_name', '')
                        if len(item_values) > 0 and item_values[0] == old_name:
                            item = child_item
                            self.tree.item(item, values=(
                                file_data.get('old_name', ''),
                                new_name,
                                file_data.get('path', ''),
                                status
                            ))
                            break
            except Exception as e:
                # Если не удалось обновить элемент, обновляем всю таблицу
                self.refresh_treeview()
                item = None
            
            # Цветовое выделение в зависимости от статуса (только если элемент найден)
            if item is not None:
                try:
                    if status == "Готов":
                        self.tree.item(item, tags=('ready',))
                    elif "Ошибка" in status or "Конфликт" in status:
                        tag = 'error' if "Ошибка" in status else 'conflict'
                        self.tree.item(item, tags=(tag,))
                    else:
                        self.tree.item(item, tags=('error',))
                except Exception:
                    # Игнорируем ошибки при установке тегов
                    pass
        
        # Проверка на конфликты
        check_conflicts(self.files)
        
        # Обновляем таблицу, чтобы убедиться, что все файлы (включая новые) отображаются
        # Это особенно важно для новых файлов, которые еще не отображены в таблице
        self.refresh_treeview()
        
        self.log(f"Методы применены к {len(self.files)} файлам")
    
    def validate_all_files(self):
        """Валидация всех готовых файлов перед переименованием.
        
        Returns:
            Tuple[bool, List[str]]: (is_valid, errors) - валидны ли все файлы и список ошибок
        """
        errors = []
        ready_files = [f for f in self.files if f.get('status') == 'Готов']
        
        for i, file_data in enumerate(ready_files):
            new_name = file_data.get('new_name', '')
            extension = file_data.get('extension', '')
            file_path = file_data.get('path') or file_data.get('full_path', '')
            
            # Валидация имени файла
            status = validate_filename(new_name, extension, file_path, i)
            if status != 'Готов':
                errors.append(f"{os.path.basename(file_path)}: {status}")
        
        # Проверка на конфликты имен
        name_counts = {}
        for file_data in ready_files:
            full_name = file_data.get('new_name', '') + file_data.get('extension', '')
            if full_name not in name_counts:
                name_counts[full_name] = []
            name_counts[full_name].append(file_data)
        
        for full_name, file_list in name_counts.items():
            if len(file_list) > 1:
                file_paths = [os.path.basename(f.get('path') or f.get('full_path', '')) for f in file_list]
                errors.append(f"Конфликт: {len(file_list)} файла с именем '{full_name}': {', '.join(file_paths[:3])}")
        
        return len(errors) == 0, errors
    
    def start_rename(self):
        """Начало процесса переименования"""
        # Защита от повторного вызова (если метод уже выполняется, игнорируем новый вызов)
        if hasattr(self, '_renaming_in_progress') and self._renaming_in_progress:
            return
        self._renaming_in_progress = True
        
        if not self.files:
            messagebox.showwarning("Предупреждение", "Нет файлов для переименования")
            self._renaming_in_progress = False
            return
        
        # Подсчет готовых файлов
        ready_files = [f for f in self.files if f.get('status') == 'Готов']
        
        if not ready_files:
            messagebox.showwarning(
                "Предупреждение",
                "Нет файлов готовых к переименованию"
            )
            self._renaming_in_progress = False
            return
        
        # Валидация всех файлов перед переименованием
        is_valid, errors = self.validate_all_files()
        
        # Формируем сообщение подтверждения
        confirm_msg = f"Вы собираетесь переименовать {len(ready_files)} файлов."
        
        if not is_valid:
            error_msg = "Обнаружены ошибки валидации:\n\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... и еще {len(errors) - 10} ошибок"
            confirm_msg = f"{error_msg}\n\n{confirm_msg}\n\nПродолжить переименование несмотря на ошибки?"
            title = "Ошибки валидации"
        else:
            confirm_msg += "\n\nВыполнить?"
            title = "Подтверждение"
        
        # Единое подтверждение
        if not messagebox.askyesno(title, confirm_msg):
            self._renaming_in_progress = False
            return
        
        # Сохранение состояния для отмены
        undo_state = [f.copy() for f in self.files]
        self.undo_stack.append(undo_state)
        # Очищаем redo стек при новой операции
        self.redo_stack.clear()
        
        # Сброс флага отмены
        if not hasattr(self, 'cancel_rename_var') or not self.cancel_rename_var:
            self.cancel_rename_var = tk.BooleanVar(value=False)
        else:
            self.cancel_rename_var.set(False)
        
        # Запуск переименования в отдельном потоке
        backup_mgr = None
        if hasattr(self, 'backup_manager') and self.backup_manager:
            backup_mgr = self.backup_manager
        
        # Создаем событие для отмены
        cancel_event = threading.Event()
        
        # Функция обновления прогресса
        def update_progress(current, total, filename):
            if hasattr(self, 'progress_window') and self.progress_window:
                try:
                    self.progress_window['value'] = current
                    self.progress_window['maximum'] = total
                except (AttributeError, tk.TclError):
                    pass
            if hasattr(self, 'current_file_label') and self.current_file_label:
                try:
                    self.current_file_label.config(
                        text=f"Обрабатывается: {filename} ({current}/{total})"
                    )
                except (AttributeError, tk.TclError):
                    pass
        
        # Периодическая проверка отмены
        def check_cancel():
            if hasattr(self, 'cancel_rename_var') and self.cancel_rename_var:
                if self.cancel_rename_var.get():
                    cancel_event.set()
                    if hasattr(self, 'current_file_label') and self.current_file_label:
                        try:
                            self.current_file_label.config(text="Отмена...")
                        except (AttributeError, tk.TclError):
                            pass
                else:
                    self.root.after(100, check_cancel)
        
        check_cancel()
        
        rename_files_thread(
            ready_files,
            self.rename_complete,
            self.log,
            backup_mgr,
            update_progress,
            cancel_event
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
                # Безопасный доступ к пути файла
                old_path = file_data.get('full_path') or file_data.get('path')
                if not old_path:
                    error_msg = "Не указан путь к файлу"
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                # Сохраняем оригинальный путь для последующего удаления из списка
                file_data['original_full_path'] = old_path
                
                # Безопасный доступ к данным файла
                new_name_part = file_data.get('new_name', '')
                extension_part = file_data.get('extension', '')
                file_dir = file_data.get('path') or os.path.dirname(old_path)
                
                if not new_name_part or not file_dir:
                    error_msg = "Недостаточно данных для переименования"
                    file_data['status'] = f"Ошибка: {error_msg}"
                    error_count += 1
                    continue
                
                new_name = new_name_part + extension_part
                new_path = os.path.join(file_dir, new_name)
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
                        base_name = file_data.get('new_name', '')
                        extension = file_data.get('extension', '')
                        file_dir = file_data.get('path') or os.path.dirname(old_path)
                        
                        if not base_name or not file_dir:
                            error_msg = "Недостаточно данных для генерации уникального имени"
                            file_data['status'] = f"Ошибка: {error_msg}"
                            error_count += 1
                            continue
                        
                        counter = 1
                        new_path = os.path.join(
                            file_dir,
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
                                file_dir,
                                f"{base_name}_{counter}{extension}"
                            )
                            new_path = os.path.normpath(new_path)
                        
                        if counter >= 1000:
                            error_count += 1
                            self.log(
                                f"Не удалось найти свободное имя для: "
                                f"{file_data.get('old_name', 'unknown')}"
                            )
                            continue
                        
                        # Обновляем имя в данных файла
                        new_name_with_counter = f"{base_name}_{counter}"
                        file_data['new_name'] = new_name_with_counter
                        new_name = new_name_with_counter + extension
                        self.log(f"Использовано уникальное имя (конфликт): {new_name}")
                    
                    try:
                        os.rename(old_path, new_path)
                        # Добавляем переименованный путь в множество
                        renamed_paths.add(new_path)
                        file_data['full_path'] = new_path
                        file_data['old_name'] = file_data.get('new_name', '')
                        old_basename = os.path.basename(old_path)
                        new_basename = os.path.basename(new_path)
                        self.log(
                            f"Переименован: {old_basename} -> {new_basename}"
                        )
                        success_count += 1
                    except OSError as e:
                        error_count += 1
                        old_name = file_data.get('old_name', 'unknown')
                        self.log(f"Ошибка переименования {old_name}: {e}")
                else:
                    # Файл не меняется, но добавляем его путь в множество
                    renamed_paths.add(new_path)
                    self.log(f"Без изменений: {new_name}")
                    success_count += 1
                
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                
                # Улучшенная обработка ошибок
                if self.error_handler:
                    try:
                        error_details = self.error_handler.get_error_details(
                            e,
                            {'file': file_data.get('old_name', 'unknown')}
                        )
                        error_msg = self.error_handler.format_error_message(error_details)
                    except Exception:
                        pass
                
                self.log(f"Ошибка при переименовании {file_data.get('old_name', 'unknown')}: {error_msg}")
                logger.error(f"Ошибка переименования: {e}", exc_info=True)
            
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
            # Безопасный доступ к данным файла
            file_dir = file_data.get('path') or file_data.get('full_path', '')
            if file_dir:
                file_dir = os.path.dirname(file_dir) if os.path.isfile(file_dir) else file_dir
            
            new_name = file_data.get('new_name', '')
            extension = file_data.get('extension', '')
            
            if not file_dir or not new_name:
                continue
            
            new_path = os.path.join(file_dir, new_name + extension)
            new_path = os.path.normpath(new_path)
            old_path = file_data.get('original_full_path') or file_data.get('full_path') or file_data.get('path')
            if not old_path:
                continue
            # Если файл был переименован (пути разные) и новый файл существует
            if old_path != new_path and os.path.exists(new_path):
                renamed_files.append(file_data)
        
        # Обновление интерфейса
        self.root.after(0, lambda: self.rename_complete(success_count, error_count, renamed_files))
    
    def rename_complete(self, success: int, error: int, renamed_files: list = None):
        """Обработка завершения переименования.
        
        Args:
            success: Количество успешных операций
            error: Количество ошибок
            renamed_files: Список переименованных файлов
        """
        # Сбрасываем флаг выполнения переименования
        if hasattr(self, '_renaming_in_progress'):
            self._renaming_in_progress = False
        
        # Добавляем операцию в историю
        if self.history_manager:
            try:
                files_for_history = renamed_files if renamed_files else self.files[:100]
                self.history_manager.add_operation(
                    'rename',
                    files_for_history,
                    success,
                    error
                )
            except Exception as e:
                logger.debug(f"Не удалось добавить операцию в историю: {e}")
        
        # Записываем в статистику
        if self.statistics_manager:
            try:
                methods_used = [type(m).__name__ for m in self.methods_manager.get_methods()]
                self.statistics_manager.record_operation(
                    'rename',
                    success,
                    error,
                    methods_used,
                    renamed_files if renamed_files else []
                )
            except Exception as e:
                logger.debug(f"Не удалось записать статистику: {e}")
        
        # Показываем уведомление
        if self.notification_manager:
            try:
                if success > 0:
                    self.notification_manager.notify_success(
                        f"Переименовано файлов: {success}"
                    )
                if error > 0:
                    self.notification_manager.notify_error(
                        f"Ошибок при переименовании: {error}"
                    )
            except Exception as e:
                logger.debug(f"Не удалось показать уведомление: {e}")
        
        # Защита от дублирования сообщения
        if not hasattr(self, '_rename_complete_shown'):
            self._rename_complete_shown = True
            messagebox.showinfo("Завершено", f"Переименование завершено.\nУспешно: {success}\nОшибок: {error}")
            # Сбрасываем флаг после небольшой задержки
            self.root.after(100, lambda: setattr(self, '_rename_complete_shown', False))
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
                file_data.get('old_name', ''),
                file_data.get('new_name', ''),
                file_data.get('path', ''),
                file_data['status']
            ))
        
        # Обновляем статус
        self.update_status()
    
    def undo_rename(self):
        """Отмена последнего переименования"""
        if not self.undo_stack:
            messagebox.showinfo("Информация", "Нет операций для отмены")
            return
        
        # Сохраняем текущее состояние для redo
        current_state = [f.copy() for f in self.files]
        self.redo_stack.append(current_state)
        
        undo_state = self.undo_stack.pop()
        
        # Восстановление файлов
        for i, old_file_data in enumerate(undo_state):
            if i < len(self.files):
                current_file = self.files[i]
                # Безопасный доступ к путям
                old_path = old_file_data.get('full_path') or old_file_data.get('path')
                new_path = current_file.get('full_path') or current_file.get('path')
                
                if not old_path or not new_path:
                    continue
                
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
        self.refresh_treeview()
        messagebox.showinfo("Отменено", "Последняя операция переименования отменена")
    
    def redo_rename(self):
        """Повтор последней отмененной операции"""
        if not self.redo_stack:
            messagebox.showinfo("Информация", "Нет операций для повтора")
            return
        
        # Сохраняем текущее состояние для undo
        current_state = [f.copy() for f in self.files]
        self.undo_stack.append(current_state)
        
        redo_state = self.redo_stack.pop()
        
        # Восстановление файлов из redo
        for i, redo_file_data in enumerate(redo_state):
            if i < len(self.files):
                current_file = self.files[i]
                # Безопасный доступ к путям
                redo_path = redo_file_data.get('full_path') or redo_file_data.get('path')
                current_path = current_file.get('full_path') or current_file.get('path')
                
                if not redo_path or not current_path:
                    continue
                
                if redo_path != current_path and os.path.exists(current_path):
                    try:
                        os.rename(current_path, redo_path)
                        self.files[i] = redo_file_data.copy()
                        current_basename = os.path.basename(current_path)
                        redo_basename = os.path.basename(redo_path)
                        self.log(
                            f"Повторено: {current_basename} -> {redo_basename}"
                        )
                    except Exception as e:
                        self.log(f"Ошибка при повторе: {e}")
        
        # Обновление интерфейса
        self.refresh_treeview()
        messagebox.showinfo("Повторено", "Операция переименования повторена")
    
    def _create_main_file_sorter_tab(self):
        """Создание вкладки сортировки файлов на главном экране"""
        sorter_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_main'])
        sorter_tab.columnconfigure(0, weight=1)
        sorter_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(sorter_tab, text="Сортировка файлов")
        
        # Основной контейнер
        main_container = tk.Frame(sorter_tab, bg=self.colors['bg_main'])
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        main_container.columnconfigure(0, weight=1)
        main_container.columnconfigure(1, weight=1)
        main_container.rowconfigure(0, weight=1)
        
        # Левая панель - настройки
        left_panel = ttk.LabelFrame(
            main_container,
            text="Настройки сортировки",
            style='Card.TLabelframe',
            padding=10
        )
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.columnconfigure(0, weight=1)
        
        # Выбор папки для сортировки
        folder_frame = tk.Frame(left_panel, bg=self.colors['bg_card'])
        folder_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(folder_frame, text="Папка для сортировки:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 5))
        
        folder_path_frame = tk.Frame(folder_frame, bg=self.colors['bg_card'])
        folder_path_frame.pack(fill=tk.X)
        
        self.sorter_folder_path = tk.StringVar()
        # По умолчанию - рабочий стол
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        if os.path.exists(desktop_path):
            self.sorter_folder_path.set(desktop_path)
        else:
            # Альтернативный путь для рабочего стола
            desktop_path = os.path.join(os.path.expanduser("~"), "Рабочий стол")
            if os.path.exists(desktop_path):
                self.sorter_folder_path.set(desktop_path)
            else:
                self.sorter_folder_path.set(os.path.expanduser("~"))
        
        folder_entry = tk.Entry(folder_path_frame,
                               textvariable=self.sorter_folder_path,
                               font=('Robot', 9),
                               bg='white',
                               fg=self.colors['text_primary'],
                               relief=tk.SOLID,
                               borderwidth=1)
        folder_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_browse = self.create_rounded_button(
            folder_path_frame, "Обзор...", self._browse_sorter_folder,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=5,
            active_bg=self.colors['primary_hover'], expand=False)
        btn_browse.pack(side=tk.LEFT)
        
        # Фильтры
        filters_frame = tk.Frame(left_panel, bg=self.colors['bg_card'])
        filters_frame.pack(fill=tk.BOTH, expand=True)
        filters_frame.columnconfigure(0, weight=1)
        
        tk.Label(filters_frame, text="Правила распределения:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 10))
        
        # Canvas для прокрутки фильтров
        filters_canvas = tk.Canvas(filters_frame, bg=self.colors['bg_card'],
                                   highlightthickness=0)
        filters_scrollbar = ttk.Scrollbar(filters_frame, orient="vertical",
                                          command=filters_canvas.yview)
        filters_scrollable = tk.Frame(filters_canvas, bg=self.colors['bg_card'])
        
        filters_scrollable.bind(
            "<Configure>",
            lambda e: filters_canvas.configure(scrollregion=filters_canvas.bbox("all"))
        )
        
        filters_canvas_window = filters_canvas.create_window((0, 0),
                                                             window=filters_scrollable,
                                                             anchor="nw")
        
        def on_filters_canvas_configure(event):
            if event.widget == filters_canvas:
                canvas_width = event.width
                filters_canvas.itemconfig(filters_canvas_window, width=canvas_width)
        
        filters_canvas.bind('<Configure>', on_filters_canvas_configure)
        filters_canvas.configure(yscrollcommand=filters_scrollbar.set)
        
        # Привязка прокрутки колесом мыши
        def on_mousewheel_filters(event):
            scroll_amount = int(-1 * (event.delta / 120))
            filters_canvas.yview_scroll(scroll_amount, "units")
        
        filters_canvas.bind("<MouseWheel>", on_mousewheel_filters)
        
        filters_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        filters_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Контейнер для списка фильтров
        self.sorter_filters_frame = filters_scrollable
        self.sorter_filters = []  # Список фильтров
        
        # Кнопки управления фильтрами
        filter_buttons_frame = tk.Frame(left_panel, bg=self.colors['bg_card'])
        filter_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        btn_add_filter = self.create_rounded_button(
            filter_buttons_frame, "Добавить правило", self._add_sorter_filter,
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['success_hover'], expand=True)
        btn_add_filter.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_save_filters = self.create_rounded_button(
            filter_buttons_frame, "Сохранить", self._save_sorter_filters,
            self.colors['info'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['info_hover'], expand=True)
        btn_save_filters.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_load_filters = self.create_rounded_button(
            filter_buttons_frame, "Загрузить", self._load_sorter_filters,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'], expand=True)
        btn_load_filters.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Правая панель - действия и результаты
        right_panel = ttk.LabelFrame(
            main_container,
            text="Действия",
            style='Card.TLabelframe',
            padding=10
        )
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        
        # Внутренний Frame для содержимого (для работы с bg)
        right_panel_inner = tk.Frame(right_panel, bg=self.colors['bg_card'])
        right_panel_inner.pack(fill=tk.BOTH, expand=True)
        right_panel_inner.columnconfigure(0, weight=1)
        right_panel_inner.rowconfigure(2, weight=1)
        
        # Кнопки управления
        buttons_frame = tk.Frame(right_panel_inner, bg=self.colors['bg_card'])
        buttons_frame.pack(fill=tk.X, pady=(0, 15))
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
        
        # Кнопка предпросмотра
        btn_preview = self.create_rounded_button(
            buttons_frame, "Предпросмотр", self._preview_file_sorting,
            self.colors['info'], 'white',
            font=('Robot', 9, 'bold'), padx=12, pady=8,
            active_bg=self.colors['info_hover'], expand=True)
        btn_preview.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        # Кнопка запуска сортировки
        btn_start_sort = self.create_rounded_button(
            buttons_frame, "Начать сортировку", self._start_file_sorting,
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=12, pady=8,
            active_bg=self.colors['success_hover'], expand=True)
        btn_start_sort.grid(row=0, column=1, sticky="ew")
        
        # Прогресс-бар
        progress_frame = tk.Frame(right_panel_inner, bg=self.colors['bg_card'])
        progress_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(progress_frame, text="Прогресс:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 5))
        
        self.sorter_progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.sorter_progress.pack(fill=tk.X)
        
        self.sorter_status_label = tk.Label(progress_frame, text="Ожидание...",
                                            font=('Robot', 8),
                                            bg=self.colors['bg_card'],
                                            fg=self.colors['text_secondary'],
                                            anchor=tk.W)
        self.sorter_status_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Результаты
        results_frame = tk.Frame(right_panel_inner, bg=self.colors['bg_card'])
        results_frame.pack(fill=tk.BOTH, expand=True)
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        tk.Label(results_frame, text="Результаты:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 5))
        
        # Текстовое поле для результатов
        results_text_frame = tk.Frame(results_frame, bg=self.colors['bg_card'])
        results_text_frame.pack(fill=tk.BOTH, expand=True)
        
        results_scrollbar = ttk.Scrollbar(results_text_frame, orient=tk.VERTICAL)
        self.sorter_results_text = tk.Text(results_text_frame,
                                          yscrollcommand=results_scrollbar.set,
                                          font=('Consolas', 9),
                                          bg='white',
                                          fg=self.colors['text_primary'],
                                          relief=tk.SOLID,
                                          borderwidth=1,
                                          wrap=tk.WORD)
        results_scrollbar.config(command=self.sorter_results_text.yview)
        
        self.sorter_results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Загружаем сохраненные фильтры
        self._load_sorter_filters()
        
        # Инициализация списка фильтров
        if not self.sorter_filters:
            # Добавляем несколько примеров фильтров по умолчанию
            self._add_default_filters()
    
    def _browse_sorter_folder(self):
        """Выбор папки для сортировки"""
        folder = filedialog.askdirectory(title="Выберите папку для сортировки")
        if folder:
            self.sorter_folder_path.set(folder)
    
    def _add_sorter_filter(self):
        """Добавление нового правила фильтрации"""
        filter_window = tk.Toplevel(self.root)
        filter_window.title("Добавить правило")
        filter_window.geometry("500x400")
        filter_window.configure(bg=self.colors['bg_card'])
        
        try:
            set_window_icon(filter_window, self._icon_photos)
        except Exception:
            pass
        
        main_frame = tk.Frame(filter_window, bg=self.colors['bg_card'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Название папки назначения
        tk.Label(main_frame, text="Название папки назначения:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 5))
        
        folder_name_var = tk.StringVar()
        folder_entry = tk.Entry(main_frame, textvariable=folder_name_var,
                               font=('Robot', 9), bg='white',
                               fg=self.colors['text_primary'],
                               relief=tk.SOLID, borderwidth=1)
        folder_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Тип фильтра
        tk.Label(main_frame, text="Тип фильтра:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(0, 5))
        
        filter_type_var = tk.StringVar(value="extension")
        filter_types = [
            ("По расширению", "extension"),
            ("По имени файла", "filename"),
            ("По размеру", "size"),
            ("По дате создания", "date"),
            ("По типу MIME", "mime")
        ]
        
        for text, value in filter_types:
            tk.Radiobutton(main_frame, text=text, variable=filter_type_var,
                          value=value, bg=self.colors['bg_card'],
                          fg=self.colors['text_primary'],
                          font=('Robot', 9)).pack(anchor=tk.W, padx=20)
        
        # Значение фильтра
        tk.Label(main_frame, text="Значение фильтра:",
                font=('Robot', 9, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W, pady=(15, 5))
        
        filter_value_var = tk.StringVar()
        filter_value_entry = tk.Entry(main_frame, textvariable=filter_value_var,
                                      font=('Robot', 9), bg='white',
                                      fg=self.colors['text_primary'],
                                      relief=tk.SOLID, borderwidth=1)
        filter_value_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Подсказка
        hint_text = "Примеры:\n- Расширение: .jpg, .png, .pdf\n- Имя: содержит 'фото', начинается с 'IMG'\n- Размер: >10MB, <1MB\n- Дата: >2024-01-01, <2023-12-31"
        tk.Label(main_frame, text=hint_text,
                font=('Robot', 8),
                bg=self.colors['bg_card'],
                fg=self.colors['text_secondary'],
                justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 15))
        
        # Кнопки
        buttons_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_filter():
            folder_name = folder_name_var.get().strip()
            filter_type = filter_type_var.get()
            filter_value = filter_value_var.get().strip()
            
            if not folder_name or not filter_value:
                messagebox.showwarning("Предупреждение",
                                      "Заполните все поля")
                return
            
            filter_data = {
                'folder_name': folder_name,
                'type': filter_type,
                'value': filter_value,
                'enabled': True
            }
            
            self.sorter_filters.append(filter_data)
            self._refresh_filters_display()
            filter_window.destroy()
            messagebox.showinfo("Успешно", "Правило добавлено")
        
        btn_save = self.create_rounded_button(
            buttons_frame, "Сохранить", save_filter,
            self.colors['success'], 'white',
            font=('Robot', 9, 'bold'), padx=15, pady=8,
            active_bg=self.colors['success_hover'], expand=True)
        btn_save.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn_cancel = self.create_rounded_button(
            buttons_frame, "Отмена", filter_window.destroy,
            self.colors['danger'], 'white',
            font=('Robot', 9, 'bold'), padx=15, pady=8,
            active_bg=self.colors['danger_hover'], expand=True)
        btn_cancel.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    def _refresh_filters_display(self):
        """Обновление отображения фильтров"""
        # Очищаем текущие виджеты
        for widget in self.sorter_filters_frame.winfo_children():
            widget.destroy()
        
        # Отображаем все фильтры
        for i, filter_data in enumerate(self.sorter_filters):
            filter_frame = tk.Frame(self.sorter_filters_frame, bg=self.colors['bg_card'],
                                   relief=tk.SOLID, borderwidth=1)
            filter_frame.pack(fill=tk.X, pady=5, padx=5)
            filter_frame.columnconfigure(1, weight=1)
            
            # Чекбокс включения
            enabled_var = tk.BooleanVar(value=filter_data.get('enabled', True))
            enabled_var.trace('w', lambda *args, idx=i: self._toggle_filter(idx))
            tk.Checkbutton(filter_frame, variable=enabled_var,
                          bg=self.colors['bg_card']).grid(row=0, column=0, padx=5)
            
            # Информация о фильтре
            info_text = f"{filter_data['folder_name']} | {filter_data['type']}: {filter_data['value']}"
            tk.Label(filter_frame, text=info_text,
                    font=('Robot', 9),
                    bg=self.colors['bg_card'],
                    fg=self.colors['text_primary']).grid(row=0, column=1, sticky="w", padx=5)
            
            # Кнопка удаления
            btn_delete = self.create_rounded_button(
                filter_frame, "Удалить", lambda idx=i: self._delete_filter(idx),
                self.colors['danger'], 'white',
                font=('Robot', 8, 'bold'), padx=8, pady=4,
                active_bg=self.colors['danger_hover'], expand=False)
            btn_delete.grid(row=0, column=2, padx=5)
    
    def _toggle_filter(self, index):
        """Включение/выключение фильтра"""
        if 0 <= index < len(self.sorter_filters):
            # Обновляем состояние через чекбокс
            pass
    
    def _delete_filter(self, index):
        """Удаление фильтра"""
        if 0 <= index < len(self.sorter_filters):
            if messagebox.askyesno("Подтверждение", "Удалить это правило?"):
                del self.sorter_filters[index]
                self._refresh_filters_display()
    
    def _add_default_filters(self):
        """Добавление фильтров по умолчанию"""
        default_filters = [
            {'folder_name': 'Изображения', 'type': 'extension', 'value': '.jpg,.jpeg,.png,.gif,.bmp,.webp', 'enabled': True},
            {'folder_name': 'Документы', 'type': 'extension', 'value': '.pdf,.doc,.docx,.xls,.xlsx,.txt', 'enabled': True},
            {'folder_name': 'Видео', 'type': 'extension', 'value': '.mp4,.avi,.mkv,.mov,.wmv', 'enabled': True},
            {'folder_name': 'Аудио', 'type': 'extension', 'value': '.mp3,.wav,.flac,.ogg,.m4a', 'enabled': True},
            {'folder_name': 'Архивы', 'type': 'extension', 'value': '.zip,.rar,.7z,.tar,.gz', 'enabled': True}
        ]
        
        self.sorter_filters.extend(default_filters)
        self._refresh_filters_display()
    
    def _save_sorter_filters(self):
        """Сохранение фильтров в настройки"""
        try:
            filters_data = {
                'folder_path': self.sorter_folder_path.get(),
                'filters': self.sorter_filters
            }
            self.settings_manager.set('file_sorter_filters', filters_data)
            self.settings_manager.save_settings(self.settings_manager.settings)
            messagebox.showinfo("Успешно", "Фильтры сохранены")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить фильтры: {e}")
    
    def _load_sorter_filters(self):
        """Загрузка фильтров из настроек"""
        try:
            filters_data = self.settings_manager.get('file_sorter_filters', {})
            if filters_data:
                if 'folder_path' in filters_data:
                    self.sorter_folder_path.set(filters_data['folder_path'])
                if 'filters' in filters_data:
                    self.sorter_filters = filters_data['filters']
                    self._refresh_filters_display()
        except Exception as e:
            logger.debug(f"Не удалось загрузить фильтры: {e}")
            # Если не удалось загрузить, добавляем фильтры по умолчанию
            if not self.sorter_filters:
                self._add_default_filters()
    
    def _preview_file_sorting(self):
        """Предпросмотр сортировки файлов"""
        folder_path = self.sorter_folder_path.get()
        
        if not folder_path or not os.path.exists(folder_path):
            messagebox.showerror("Ошибка", "Укажите существующую папку для сортировки")
            return
        
        enabled_filters = [f for f in self.sorter_filters if f.get('enabled', True)]
        if not enabled_filters:
            messagebox.showwarning("Предупреждение", "Нет активных правил для сортировки")
            return
        
        # Собираем все файлы из папки
        files_to_sort = []
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path):
                files_to_sort.append(item_path)
        
        if not files_to_sort:
            messagebox.showinfo("Информация", "В выбранной папке нет файлов для сортировки")
            return
        
        # Создаем окно предпросмотра
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Предпросмотр сортировки")
        preview_window.geometry("900x600")
        preview_window.configure(bg=self.colors['bg_card'])
        
        try:
            set_window_icon(preview_window, self._icon_photos)
        except Exception:
            pass
        
        main_frame = tk.Frame(preview_window, bg=self.colors['bg_card'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # Заголовок
        header_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        tk.Label(header_frame, text="Предпросмотр сортировки файлов",
                font=('Robot', 12, 'bold'),
                bg=self.colors['bg_card'],
                fg=self.colors['text_primary']).pack(anchor=tk.W)
        
        tk.Label(header_frame, text=f"Папка: {folder_path}",
                font=('Robot', 9),
                bg=self.colors['bg_card'],
                fg=self.colors['text_secondary']).pack(anchor=tk.W, pady=(5, 0))
        
        # Таблица предпросмотра
        table_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        
        # Создаем Treeview для отображения предпросмотра
        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL)
        
        columns = ("file", "destination", "status")
        preview_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set,
            style='Custom.Treeview'
        )
        
        scrollbar_y.config(command=preview_tree.yview)
        scrollbar_x.config(command=preview_tree.xview)
        
        # Настройка колонок
        preview_tree.heading("file", text="Файл")
        preview_tree.heading("destination", text="Папка назначения")
        preview_tree.heading("status", text="Статус")
        
        preview_tree.column("file", width=300, anchor='w', minwidth=150)
        preview_tree.column("destination", width=250, anchor='w', minwidth=150)
        preview_tree.column("status", width=150, anchor='center', minwidth=100)
        
        # Теги для цветового выделения
        preview_tree.tag_configure('sorted', background='#D1FAE5', foreground='#065F46')
        preview_tree.tag_configure('unsorted', background='#FEF3C7', foreground='#92400E')
        preview_tree.tag_configure('error', background='#FEE2E2', foreground='#991B1B')
        
        # Размещение таблицы
        preview_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        
        # Статистика
        stats_frame = tk.Frame(main_frame, bg=self.colors['bg_card'])
        stats_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        
        stats_label = tk.Label(stats_frame, text="",
                               font=('Robot', 9, 'bold'),
                               bg=self.colors['bg_card'],
                               fg=self.colors['text_primary'],
                               anchor=tk.W)
        stats_label.pack(anchor=tk.W)
        
        # Обрабатываем файлы для предпросмотра
        sorted_count = 0
        unsorted_count = 0
        error_count = 0
        
        for file_path in files_to_sort:
            try:
                file_name = os.path.basename(file_path)
                matched = False
                destination = ""
                
                # Проверяем каждый фильтр
                for filter_data in enabled_filters:
                    if self._file_matches_filter(file_path, filter_data):
                        destination = filter_data['folder_name']
                        matched = True
                        sorted_count += 1
                        break
                
                if matched:
                    preview_tree.insert("", tk.END, values=(file_name, destination, "Будет отсортирован"),
                                      tags=('sorted',))
                else:
                    unsorted_count += 1
                    preview_tree.insert("", tk.END, values=(file_name, "-", "Не отсортирован"),
                                      tags=('unsorted',))
            
            except Exception as e:
                error_count += 1
                preview_tree.insert("", tk.END, values=(os.path.basename(file_path), "-", f"Ошибка: {e}"),
                                  tags=('error',))
        
        # Обновляем статистику
        total = len(files_to_sort)
        stats_text = f"Всего файлов: {total} | Будет отсортировано: {sorted_count} | Не отсортировано: {unsorted_count}"
        if error_count > 0:
            stats_text += f" | Ошибок: {error_count}"
        stats_label.config(text=stats_text)
        
        # Кнопка закрытия
        btn_close = self.create_rounded_button(
            main_frame, "Закрыть", preview_window.destroy,
            self.colors['primary'], 'white',
            font=('Robot', 9, 'bold'), padx=15, pady=8,
            active_bg=self.colors['primary_hover'], expand=False)
        btn_close.grid(row=3, column=0, pady=(15, 0))
    
    def _start_file_sorting(self):
        """Запуск сортировки файлов"""
        folder_path = self.sorter_folder_path.get()
        
        if not folder_path or not os.path.exists(folder_path):
            messagebox.showerror("Ошибка", "Укажите существующую папку для сортировки")
            return
        
        enabled_filters = [f for f in self.sorter_filters if f.get('enabled', True)]
        if not enabled_filters:
            messagebox.showwarning("Предупреждение", "Нет активных правил для сортировки")
            return
        
        if not messagebox.askyesno("Подтверждение",
                                   f"Начать сортировку файлов в папке:\n{folder_path}\n\n"
                                   f"Будет обработано {len(enabled_filters)} правил(а)?"):
            return
        
        # Запускаем сортировку в отдельном потоке
        threading.Thread(target=self._sort_files_thread,
                        args=(folder_path, enabled_filters),
                        daemon=True).start()
    
    def _sort_files_thread(self, folder_path, filters):
        """Поток для сортировки файлов"""
        try:
            total_files = 0
            moved_files = 0
            errors = []
            
            # Собираем все файлы из папки
            files_to_sort = []
            for item in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item)
                if os.path.isfile(item_path):
                    files_to_sort.append(item_path)
                    total_files += 1
            
            self.root.after(0, lambda: self.sorter_progress.configure(maximum=total_files))
            self.root.after(0, lambda: self.sorter_progress.configure(value=0))
            self.root.after(0, lambda: self.sorter_results_text.delete(1.0, tk.END))
            
            # Обрабатываем каждый файл
            for i, file_path in enumerate(files_to_sort):
                try:
                    file_name = os.path.basename(file_path)
                    file_ext = os.path.splitext(file_name)[1].lower()
                    
                    # Проверяем каждый фильтр
                    matched = False
                    for filter_data in filters:
                        if self._file_matches_filter(file_path, filter_data):
                            target_folder_name = filter_data['folder_name']
                            target_folder = os.path.join(folder_path, target_folder_name)
                            
                            # Создаем папку, если её нет
                            if not os.path.exists(target_folder):
                                os.makedirs(target_folder)
                            
                            # Перемещаем файл
                            target_path = os.path.join(target_folder, file_name)
                            
                            # Если файл с таким именем уже существует, добавляем номер
                            counter = 1
                            base_name, ext = os.path.splitext(file_name)
                            while os.path.exists(target_path):
                                new_name = f"{base_name}_{counter}{ext}"
                                target_path = os.path.join(target_folder, new_name)
                                counter += 1
                            
                            os.rename(file_path, target_path)
                            moved_files += 1
                            matched = True
                            
                            result_text = f"✓ {file_name} -> {target_folder_name}\n"
                            self.root.after(0, lambda t=result_text: self.sorter_results_text.insert(tk.END, t))
                            break
                    
                    if not matched:
                        result_text = f"○ {file_name} (не подошел ни под одно правило)\n"
                        self.root.after(0, lambda t=result_text: self.sorter_results_text.insert(tk.END, t))
                
                except Exception as e:
                    error_msg = f"Ошибка при обработке {os.path.basename(file_path)}: {e}\n"
                    errors.append(error_msg)
                    self.root.after(0, lambda t=error_msg: self.sorter_results_text.insert(tk.END, t))
                
                # Обновляем прогресс
                self.root.after(0, lambda v=i+1: self.sorter_progress.configure(value=v))
                self.root.after(0, lambda: self.sorter_status_label.config(
                    text=f"Обработано: {i+1}/{total_files}"))
            
            # Показываем итоги
            summary = f"\n{'='*50}\n"
            summary += f"Итого обработано: {total_files} файлов\n"
            summary += f"Перемещено: {moved_files} файлов\n"
            summary += f"Ошибок: {len(errors)}\n"
            self.root.after(0, lambda t=summary: self.sorter_results_text.insert(tk.END, t))
            
            self.root.after(0, lambda: self.sorter_status_label.config(
                text=f"Завершено! Перемещено {moved_files} из {total_files} файлов"))
            
            if moved_files > 0:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Сортировка завершена",
                    f"Обработано файлов: {total_files}\n"
                    f"Перемещено: {moved_files}\n"
                    f"Ошибок: {len(errors)}"))
        
        except Exception as e:
            error_msg = f"Критическая ошибка: {e}"
            self.root.after(0, lambda: messagebox.showerror("Ошибка", error_msg))
            logger.error(f"Ошибка сортировки файлов: {e}", exc_info=True)
    
    def _file_matches_filter(self, file_path, filter_data):
        """Проверка, соответствует ли файл фильтру"""
        filter_type = filter_data['type']
        filter_value = filter_data['value']
        file_name = os.path.basename(file_path)
        file_ext = os.path.splitext(file_name)[1].lower()
        
        if filter_type == 'extension':
            # Поддерживаем несколько расширений через запятую
            extensions = [ext.strip().lower() for ext in filter_value.split(',')]
            return file_ext in extensions or f".{file_ext}" in extensions
        
        elif filter_type == 'filename':
            # Проверка по имени файла
            file_name_lower = file_name.lower()
            filter_value_lower = filter_value.lower()
            
            if filter_value_lower.startswith('начинается с '):
                prefix = filter_value_lower.replace('начинается с ', '').strip()
                return file_name_lower.startswith(prefix)
            elif filter_value_lower.startswith('содержит '):
                substring = filter_value_lower.replace('содержит ', '').strip()
                return substring in file_name_lower
            else:
                # Простое совпадение
                return filter_value_lower in file_name_lower
        
        elif filter_type == 'size':
            # Проверка по размеру (требует парсинга строки типа ">10MB")
            try:
                file_size = os.path.getsize(file_path)
                # Упрощенная проверка (можно расширить)
                if '>' in filter_value or '<' in filter_value:
                    # Парсим размер
                    size_str = filter_value.replace('>', '').replace('<', '').strip().upper()
                    if 'MB' in size_str:
                        size_bytes = float(size_str.replace('MB', '')) * 1024 * 1024
                    elif 'KB' in size_str:
                        size_bytes = float(size_str.replace('KB', '')) * 1024
                    elif 'GB' in size_str:
                        size_bytes = float(size_str.replace('GB', '')) * 1024 * 1024 * 1024
                    else:
                        size_bytes = float(size_str)
                    
                    if '>' in filter_value:
                        return file_size > size_bytes
                    else:
                        return file_size < size_bytes
            except:
                return False
        
        elif filter_type == 'date':
            # Проверка по дате (упрощенная)
            try:
                file_mtime = os.path.getmtime(file_path)
                file_date = datetime.fromtimestamp(file_mtime).date()
                # Упрощенная проверка (можно расширить)
                return True  # Заглушка
            except:
                return False
        
        elif filter_type == 'mime':
            # Проверка по типу MIME (упрощенная, по расширению)
            return self._file_matches_filter(file_path, {
                'type': 'extension',
                'value': filter_value
            })
        
        return False


def main():
    """Главная функция запуска приложения."""
    # Обработка аргументов командной строки
    files_from_args = []
    
    # Логируем аргументы для отладки
    if len(sys.argv) > 1:
        logger.info(f"Аргументы командной строки: {sys.argv[1:]}")
    
    if len(sys.argv) > 1:
        # Получаем все аргументы как пути к файлам
        # Игнорируем аргументы, которые выглядят как опции (начинаются с -)
        # если они не являются существующими файлами
        for arg in sys.argv[1:]:
            # Пропускаем аргументы, которые выглядят как опции
            # но проверяем, не является ли это путем к файлу
            if arg.startswith('-') and not arg.startswith('--'):
                # Это может быть опция (например, -state) или путь к файлу, начинающийся с дефиса
                # Проверяем, существует ли это как файл
                normalized_arg = os.path.normpath(arg)
                if os.path.exists(normalized_arg) and os.path.isfile(normalized_arg):
                    files_from_args.append(normalized_arg)
                # Если это не файл, пропускаем (это опция, которую мы не знаем)
                continue
            elif arg.startswith('--'):
                # Длинная опция, пропускаем если это не файл
                normalized_arg = os.path.normpath(arg)
                if not (os.path.exists(normalized_arg) and os.path.isfile(normalized_arg)):
                    continue
            
            # Нормализуем путь и проверяем существование
            normalized_arg = os.path.normpath(arg)
            if os.path.exists(normalized_arg) and os.path.isfile(normalized_arg):
                files_from_args.append(normalized_arg)
            else:
                # Если путь содержит пробелы, он может быть в кавычках
                try:
                    cleaned_arg = arg.strip('"').strip("'")
                    normalized_cleaned = os.path.normpath(cleaned_arg)
                    if os.path.exists(normalized_cleaned) and os.path.isfile(normalized_cleaned):
                        files_from_args.append(normalized_cleaned)
                except Exception:
                    # Игнорируем ошибки при обработке пути
                    pass
    
    # Используем TkinterDnD если доступно
    if HAS_TKINTERDND2:
        try:
            root = TkinterDnD.Tk()
        except Exception:
            root = tk.Tk()
    else:
        root = tk.Tk()
    
    # Проверка и установка библиотек при первом запуске с показом окна прогресса
    library_manager = None
    try:
        library_manager = LibraryManager(
            root,
            log_callback=lambda msg: logger.info(msg)
        )
        
        # Проверяем и устанавливаем библиотеки
        # Окно установки показывается только при первом запуске (внутри check_and_install)
        # Выполняем с небольшой задержкой, чтобы окно успело инициализироваться
        root.after(500, lambda: library_manager.check_and_install(install_optional=True, silent=False))
    except Exception as e:
        logger.warning(f"Не удалось проверить библиотеки при запуске: {e}", exc_info=True)
        # Продолжаем работу даже если проверка не удалась
    
    app = FileRenamerApp(root, library_manager=library_manager, files_from_args=files_from_args)
    root.mainloop()


if __name__ == "__main__":
    main()

