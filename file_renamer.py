import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Попытка импортировать PIL для закругленных углов
try:
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Попытка импортировать поддержку drag and drop для Windows
has_dragdrop = False
if sys.platform == 'win32':
    try:
        import ctypes
        from ctypes import wintypes
        has_dragdrop = True
    except ImportError:
        has_dragdrop = False

# Попытка импортировать tkinterdnd2 для лучшей поддержки drag and drop
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_TKINTERDND2 = True
except ImportError:
    HAS_TKINTERDND2 = False

from metadata import MetadataExtractor
from rename_methods import (
    AddRemoveMethod,
    CaseMethod,
    MetadataMethod,
    NewNameMethod,
    NumberingMethod,
    RegexMethod,
    RenameMethod,
    ReplaceMethod,
)


class FileRenamerApp:
    """Главный класс приложения для переименования файлов"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Назови")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 700)
        
        # Настройка адаптивности
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # Настройка цветовой схемы
        self.setup_styles()
        
        # Данные приложения
        # Список файлов: {path, old_name, new_name, extension, status}
        self.files: List[Dict] = []
        self.undo_stack: List[List[Dict]] = []  # Стек для отмены
        self.current_methods: List[RenameMethod] = []  # Методы
        
        # Окна для вкладок
        self.windows = {
            'actions': None,
            'tabs': None  # Окно с вкладками для логов, настроек и т.д.
        }
        self.tabs_window_notebook = None  # Notebook для вкладок
        self.log_text = None  # Ссылка на текстовое поле лога
        
        # Инициализация модуля метаданных
        self.metadata_extractor = MetadataExtractor()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Привязка горячих клавиш
        self.setup_hotkeys()
        
        # Настройка drag and drop для файлов из проводника
        self.setup_drag_drop()
        
        # Настройка перестановки файлов в таблице
        self.setup_treeview_drag_drop()
    
    def create_rounded_button(self, parent, text, command, bg_color, fg_color='white', 
                             font=('Segoe UI', 9, 'bold'), padx=10, pady=6, 
                             active_bg=None, active_fg='white', width=None):
        """Создание кнопки с закругленными углами через Canvas"""
        if active_bg is None:
            active_bg = bg_color
        
        # Фрейм для кнопки
        btn_frame = tk.Frame(parent, bg=parent.cget('bg'))
        
        # Canvas для закругленного фона
        canvas = tk.Canvas(btn_frame, highlightthickness=0, borderwidth=0,
                          bg=parent.cget('bg'), height=pady*2 + 16)
        canvas.pack(fill=tk.BOTH, expand=True)
        
        # Сохраняем параметры
        canvas.btn_text = text
        canvas.btn_command = command
        canvas.btn_bg = bg_color
        canvas.btn_fg = fg_color
        canvas.btn_active_bg = active_bg
        canvas.btn_active_fg = active_fg
        canvas.btn_font = font
        canvas.btn_state = 'normal'
        
        def hex_to_rgb(hex_color):
            """Конвертация hex в RGB"""
            hex_color = hex_color.lstrip('#')
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        def draw_button(state='normal'):
            canvas.delete('all')
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w <= 1 or h <= 1:
                # Если размер еще не установлен, ждем и перерисовываем
                canvas.after(10, lambda: draw_button(state))
                return
            
            # Минимальная ширина для кнопки
            if w < 50:
                w = 50
            
            radius = 8
            color = canvas.btn_active_bg if state == 'active' else canvas.btn_bg
            text_color = canvas.btn_active_fg if state == 'active' else canvas.btn_fg
            
            # Конвертируем цвет в hex для Canvas
            if isinstance(color, tuple):
                color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
            elif color.startswith('#'):
                color_hex = color
            else:
                color_hex = '#6366F1'  # По умолчанию
            
            # Рисуем закругленный прямоугольник через дуги и прямоугольники
            # Верхние углы
            canvas.create_arc(0, 0, radius*2, radius*2, start=90, extent=90, 
                            fill=color_hex, outline=color_hex)
            canvas.create_arc(w-radius*2, 0, w, radius*2, start=0, extent=90, 
                            fill=color_hex, outline=color_hex)
            # Нижние углы
            canvas.create_arc(0, h-radius*2, radius*2, h, start=180, extent=90, 
                            fill=color_hex, outline=color_hex)
            canvas.create_arc(w-radius*2, h-radius*2, w, h, start=270, extent=90, 
                            fill=color_hex, outline=color_hex)
            # Центральные прямоугольники
            canvas.create_rectangle(radius, 0, w-radius, h, fill=color_hex, outline=color_hex)
            canvas.create_rectangle(0, radius, w, h-radius, fill=color_hex, outline=color_hex)
            
            # Текст с автоматическим переносом для маленьких кнопок
            text = canvas.btn_text
            # Используем width для автоматического переноса текста
            canvas.create_text(w//2, h//2, text=text, 
                             fill=text_color, font=canvas.btn_font, width=max(w-20, 50))
        
        def on_enter(e):
            canvas.btn_state = 'active'
            draw_button('active')
        
        def on_leave(e):
            canvas.btn_state = 'normal'
            draw_button('normal')
        
        def on_click(e):
            canvas.btn_command()
        
        def on_configure(e):
            draw_button(canvas.btn_state)
        
        canvas.bind('<Button-1>', on_click)
        canvas.bind('<Enter>', on_enter)
        canvas.bind('<Leave>', on_leave)
        canvas.bind('<Configure>', on_configure)
        
        # Инициализация
        canvas.after(10, lambda: draw_button('normal'))
        
        return btn_frame
    
    def setup_styles(self) -> None:
        """Настройка современных стилей интерфейса."""
        self.style = ttk.Style()
        style = self.style
        
        # Используем современную тему
        try:
            style.theme_use('vista')  # Windows Vista/7 стиль
        except Exception:
            try:
                style.theme_use('clam')  # Альтернативный стиль
            except Exception:
                pass
        
        # Современная цветовая схема (Material Design / Fluent Design)
        self.colors = {
            'primary': '#6366F1',           # Индиго (современный синий)
            'primary_hover': '#4F46E5',     # Более насыщенный при наведении
            'primary_light': '#818CF8',     # Светлый вариант
            'primary_dark': '#4338CA',      # Темный вариант
            'success': '#10B981',           # Изумрудный зеленый
            'success_hover': '#059669',
            'warning': '#F59E0B',           # Янтарный
            'danger': '#EF4444',            # Красный
            'danger_hover': '#DC2626',
            'info': '#3B82F6',              # Синий информационный
            'bg_main': '#F8FAFC',           # Очень светло-серый фон
            'bg_secondary': '#F1F5F9',      # Вторичный фон
            'bg_card': '#FFFFFF',           # Белый фон карточек
            'bg_hover': '#F1F5F9',          # Фон при наведении
            'bg_input': '#FFFFFF',          # Фон полей ввода
            'bg_elevated': '#FFFFFF',       # Приподнятый элемент
            'border': '#E2E8F0',            # Светло-серый цвет границ
            'border_focus': '#6366F1',      # Синяя рамка при фокусе
            'border_light': '#F1F5F9',      # Очень светлая граница
            'text_primary': '#0F172A',      # Почти черный для текста
            'text_secondary': '#475569',    # Серый вторичный текст
            'text_muted': '#94A3B8',        # Приглушенный текст
            'header_bg': '#FFFFFF',         # Белый фон заголовка (с тенью)
            'header_text': '#0F172A',       # Темный текст в заголовке
            'accent': '#8B5CF6',            # Фиолетовый акцент
            'shadow': 'rgba(0,0,0,0.1)',    # Прозрачная тень
            'shadow_lg': 'rgba(0,0,0,0.15)', # Большая тень
            'glow': 'rgba(99, 102, 241, 0.5)', # Свечение
            'gradient_start': '#6366F1',    # Начало градиента
            'gradient_end': '#8B5CF6'       # Конец градиента
        }
        
        # Настройка стилей кнопок - современный дизайн с четким текстом
        style.configure('Primary.TButton', 
                       background=self.colors['primary'],
                       foreground='white',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Primary.TButton',
                 background=[('active', self.colors['primary_hover']), 
                           ('pressed', self.colors['primary_dark']),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        style.configure('Success.TButton',
                       background=self.colors['success'],
                       foreground='white',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Success.TButton',
                 background=[('active', self.colors['success_hover']), 
                           ('pressed', '#047857'),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        style.configure('Danger.TButton',
                       background=self.colors['danger'],
                       foreground='white',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Danger.TButton',
                 background=[('active', self.colors['danger_hover']), 
                           ('pressed', '#B91C1C'),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для обычных кнопок - цветной (оранжевый/янтарный)
        style.configure('TButton',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       relief='flat',
                       background='#F59E0B',
                       foreground='white',
                       anchor='center')
        style.map('TButton',
                 background=[('active', '#D97706'), 
                           ('pressed', '#B45309'),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'),
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для вторичных кнопок (светло-синий)
        style.configure('Secondary.TButton',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       relief='flat',
                       background='#818CF8',
                       foreground='white',
                       anchor='center')
        style.map('Secondary.TButton',
                 background=[('active', '#6366F1'), 
                           ('pressed', '#4F46E5'),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'),
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для предупреждающих кнопок (янтарный)
        style.configure('Warning.TButton',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(10, 6),
                       borderwidth=0,
                       relief='flat',
                       background='#F59E0B',
                       foreground='white',
                       anchor='center')
        style.map('Warning.TButton',
                 background=[('active', '#D97706'), 
                           ('pressed', '#B45309'),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'),
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для LabelFrame - карточки с тенью (минималистичный с закруглениями)
        style.configure('Card.TLabelframe', 
                       background=self.colors['bg_card'],
                       borderwidth=1,
                       relief='flat',
                       bordercolor=self.colors['border'],
                       padding=10)
        style.configure('Card.TLabelframe.Label',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 9, 'bold'),
                       padding=(0, 0, 0, 5))
        
        # Стиль для PanedWindow (разделитель панелей)
        style.configure('TPanedwindow',
                       background=self.colors['bg_main'])
        style.configure('TPanedwindow.Sash',
                       sashthickness=6,
                       sashrelief='flat',
                       sashpad=0)
        style.map('TPanedwindow.Sash',
                 background=[('hover', self.colors['primary_light']),
                           ('active', self.colors['primary'])])
        
        # Стиль для обычных меток
        style.configure('TLabel',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 9))
        
        # Стиль для Frame
        style.configure('TFrame',
                       background=self.colors['bg_main'])
        
        # Стиль для Notebook (вкладок) - такой же размер как у кнопок
        style.configure('TNotebook',
                       background=self.colors['bg_main'],
                       borderwidth=0)
        style.configure('TNotebook.Tab',
                       padding=(10, 6),
                       font=('Segoe UI', 9, 'bold'),
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'])
        style.map('TNotebook.Tab',
                 background=[('selected', self.colors['bg_card']),
                           ('active', self.colors['bg_hover'])],
                 expand=[('selected', [1, 1, 1, 0])])
        
        # Стиль для Radiobutton
        style.configure('TRadiobutton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 9),
                       selectcolor='white')
        
        # Стиль для Checkbutton
        style.configure('TCheckbutton',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 9),
                       selectcolor='white')
        
        # Стиль для Entry - современные поля ввода
        style.configure('TEntry',
                       fieldbackground='white',
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       relief='flat',
                       padding=8,
                       font=('Segoe UI', 9))
        style.map('TEntry',
                 bordercolor=[('focus', self.colors['border_focus']),
                            ('!focus', self.colors['border'])],
                 lightcolor=[('focus', self.colors['border_focus']),
                           ('!focus', self.colors['border'])],
                 darkcolor=[('focus', self.colors['border_focus']),
                          ('!focus', self.colors['border'])])
        
        # Стиль для Combobox
        style.configure('TCombobox',
                       fieldbackground='white',
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       relief='flat',
                       padding=8,
                       font=('Segoe UI', 9))
        style.map('TCombobox',
                 bordercolor=[('focus', self.colors['border_focus']),
                            ('!focus', self.colors['border'])],
                 selectbackground=[('focus', 'white')],
                 selectforeground=[('focus', self.colors['text_primary'])])
        
        # Стиль для Treeview - современная таблица
        style.configure('Custom.Treeview',
                       rowheight=32,
                       font=('Segoe UI', 9),
                       background='white',
                       foreground=self.colors['text_primary'],
                       fieldbackground='white',
                       borderwidth=0)
        style.configure('Custom.Treeview.Heading',
                       font=('Segoe UI', 9, 'bold'),
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       borderwidth=0,
                       relief='flat',
                       padding=6)
        style.map('Custom.Treeview.Heading',
                 background=[('active', self.colors['bg_hover'])])
        
        # Стиль для выделенных строк
        style.map('Custom.Treeview',
                 background=[('selected', self.colors['primary_light'])],
                 foreground=[('selected', 'white')])
        
        # Настройка фона окна
        self.root.configure(bg=self.colors['bg_main'])
        
        # Привязка изменения размера окна для адаптивного масштабирования
        self.root.bind('<Configure>', self.on_window_resize)
        
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
                except:
                    pass
    
    def setup_window_resize_handler(self, window, canvas=None, canvas_window=None):
        """Настройка обработчика изменения размера для окна с canvas"""
        def on_resize(event):
            if canvas and canvas_window is not None:
                try:
                    canvas_width = event.width
                    canvas.itemconfig(canvas_window, width=canvas_width)
                except:
                    pass
        
        if canvas:
            window.bind('<Configure>', on_resize)
    
    def update_tree_columns(self):
        """Обновление размеров колонок таблицы в соответствии с размером окна"""
        if hasattr(self, 'list_frame') and hasattr(self, 'tree') and self.list_frame and self.tree:
            try:
                list_frame_width = self.list_frame.winfo_width()
                if list_frame_width > 100:  # Минимальная ширина для расчетов
                    # Вычитаем ширину скроллбара (примерно 20px) и отступы
                    available_width = max(list_frame_width - 50, 400)
                    
                    self.tree.column("old_name", width=int(available_width * 0.22))
                    self.tree.column("new_name", width=int(available_width * 0.22))
                    self.tree.column("extension", width=int(available_width * 0.10))
                    self.tree.column("path", width=int(available_width * 0.35))
                    self.tree.column("status", width=int(available_width * 0.11))
            except Exception as e:
                pass
    
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        
        # === ЗАГОЛОВОК (современный дизайн) ===
        header_frame = tk.Frame(self.root, bg=self.colors['header_bg'], height=85)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        header_content = tk.Frame(header_frame, bg=self.colors['header_bg'])
        header_content.pack(fill=tk.BOTH, expand=True, padx=30, pady=22)
        
        # Настройка масштабирования заголовка
        header_frame.grid_columnconfigure(0, weight=1)
        
        # Заголовок слева с улучшенной типографикой
        title_container = tk.Frame(header_content, bg=self.colors['header_bg'])
        title_container.pack(side=tk.LEFT)
        
        title_label = tk.Label(title_container, text="📝 Назови", 
                              font=('Segoe UI', 24, 'bold'),
                              bg=self.colors['header_bg'],
                              fg=self.colors['primary'],
                              cursor='hand2')
        title_label.pack(side=tk.LEFT)
        
        # Подзаголовок
        subtitle_label = tk.Label(title_container, text="Переименование файлов", 
                                 font=('Segoe UI', 9),
                                 bg=self.colors['header_bg'],
                                 fg=self.colors['text_secondary'])
        subtitle_label.pack(side=tk.LEFT, padx=(15, 0))
        
        # Статус справа в стильной карточке
        status_container = tk.Frame(header_content, bg=self.colors['header_bg'])
        status_container.pack(side=tk.RIGHT)
        
        # Статус в карточке
        status_card = tk.Frame(status_container, bg=self.colors['bg_secondary'], 
                              relief='flat', borderwidth=0)
        status_card.pack()
        
        self.status_label = tk.Label(status_card, text=f"📊 Файлов: {len(self.files)}", 
                                     font=('Segoe UI', 9, 'bold'),
                                     bg=self.colors['bg_secondary'],
                                     fg=self.colors['text_primary'],
                                     padx=12, pady=6)
        self.status_label.pack()
        
        # === ОСНОВНОЙ КОНТЕЙНЕР С ВКЛАДКАМИ ===
        # Создаем Notebook для вкладок
        main_notebook = ttk.Notebook(self.root)
        main_notebook.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
        
        # Сохраняем ссылку на notebook
        self.main_notebook = main_notebook
        
        # === ВКЛАДКА 1: ОСНОВНОЕ СОДЕРЖИМОЕ (файлы и методы) ===
        main_tab = tk.Frame(main_notebook, bg=self.colors['bg_main'])
        main_notebook.add(main_tab, text="📁 Файлы")
        
        # Используем PanedWindow для изменения размеров панелей внутри основной вкладки
        main_container = ttk.PanedWindow(main_tab, orient=tk.HORIZONTAL)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Сохраняем ссылку для доступа
        self.main_paned = main_container
        
        # Обработчик изменения размера PanedWindow для обновления колонок таблицы
        def on_paned_resize(event=None):
            if hasattr(self, 'update_tree_columns'):
                self.root.after(100, self.update_tree_columns)
        
        main_container.bind('<ButtonRelease-1>', on_paned_resize)  # После перемещения разделителя
        main_container.bind('<Configure>', on_paned_resize)  # При изменении размера
        
        # Левая часть - список файлов
        left_panel = ttk.LabelFrame(main_container, text="📋 Список файлов", 
                                    style='Card.TLabelframe', padding=20)
        main_container.add(left_panel, weight=2)  # weight=2 означает, что левая панель будет занимать больше места
        
        
        # Панель управления файлами
        control_panel = tk.Frame(left_panel, bg=self.colors['bg_card'])
        control_panel.pack(fill=tk.X, pady=(0, 10))
        control_panel.columnconfigure(0, weight=1)
        control_panel.columnconfigure(1, weight=1)
        control_panel.columnconfigure(2, weight=1)
        control_panel.columnconfigure(3, weight=1)
        
        # Кнопки управления - компактный дизайн с закругленными углами
        btn_add_files = self.create_rounded_button(
            control_panel, "📁 Добавить файлы", self.add_files,
            self.colors['primary'], 'white', 
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_files.grid(row=0, column=0, padx=3, sticky="ew")
        
        btn_add_folder = self.create_rounded_button(
            control_panel, "📂 Добавить папку", self.add_folder,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_folder.grid(row=0, column=1, padx=3, sticky="ew")
        
        btn_clear = self.create_rounded_button(
            control_panel, "🗑️ Очистить", self.clear_files,
            self.colors['danger'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear.grid(row=0, column=2, padx=3, sticky="ew")
        
        btn_undo = self.create_rounded_button(
            control_panel, "↶ Отменить", self.undo_rename,
            self.colors['primary_light'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary'])
        btn_undo.grid(row=0, column=3, padx=3, sticky="ew")
        
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
        self.tree.heading("old_name", text="📄 Исходное имя")
        self.tree.heading("new_name", text="✨ Новое имя")
        self.tree.heading("extension", text="📎 Расширение")
        self.tree.heading("path", text="📁 Путь")
        self.tree.heading("status", text="✓ Статус")
        
        # Настройка колонок с адаптивными размерами (процент от ширины)
        list_frame.update_idletasks()  # Обновляем размеры
        frame_width = list_frame.winfo_width() if list_frame.winfo_width() > 1 else 800
        
        self.tree.column("old_name", width=int(frame_width * 0.22), anchor='w', minwidth=100)
        self.tree.column("new_name", width=int(frame_width * 0.22), anchor='w', minwidth=100)
        self.tree.column("extension", width=int(frame_width * 0.10), anchor='center', minwidth=60)
        self.tree.column("path", width=int(frame_width * 0.35), anchor='w', minwidth=150)
        self.tree.column("status", width=int(frame_width * 0.11), anchor='center', minwidth=80)
        
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
        
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # Привязка сортировки
        for col in ("old_name", "new_name", "extension", "path", "status"):
            self.tree.heading(col, command=lambda c=col: self.sort_column(c))
        
        # === КНОПКИ (под списком файлов слева) ===
        buttons_frame = tk.Frame(left_panel, bg=self.colors['bg_card'])
        buttons_frame.pack(fill=tk.X, pady=(10, 10))
        buttons_frame.columnconfigure(0, weight=1)
        buttons_frame.columnconfigure(1, weight=1)
        
        btn_apply = self.create_rounded_button(
            buttons_frame, "✨ Применить метод", self.apply_methods,
            self.colors['primary'], 'white',
            font=('Segoe UI', 11, 'bold'), padx=15, pady=10,
            active_bg=self.colors['primary_hover'])
        btn_apply.grid(row=0, column=0, padx=4, sticky="ew")
        
        btn_start = self.create_rounded_button(
            buttons_frame, "▶️ Начать переименование", self.start_rename,
            self.colors['success'], 'white',
            font=('Segoe UI', 11, 'bold'), padx=15, pady=10,
            active_bg=self.colors['success_hover'])
        btn_start.grid(row=0, column=1, padx=4, sticky="ew")
        
        # === ПРОГРЕСС БАР (под кнопками слева) ===
        progress_container = tk.Frame(left_panel, bg=self.colors['bg_card'])
        progress_container.pack(fill=tk.X, pady=(0, 0))
        
        progress_label = tk.Label(progress_container, text="Прогресс:", 
                                 font=('Segoe UI', 9, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        progress_label.pack(anchor=tk.W, pady=(0, 6))
        
        self.progress = ttk.Progressbar(progress_container, mode='determinate')
        self.progress.pack(fill=tk.X)
        
        # === ПРАВАЯ ПАНЕЛЬ (только методы) ===
        right_panel = ttk.LabelFrame(main_container, text="⚙️ Методы переименования", 
                                     style='Card.TLabelframe', padding=0)
        main_container.add(right_panel, weight=1)
        right_panel.configure(width=350)
        
        # Внутренний Frame для содержимого с отступами
        methods_frame = tk.Frame(right_panel, bg=self.colors['bg_card'])
        methods_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Выбор метода
        method_label = tk.Label(methods_frame, text="🔧 Выберите метод:", 
                               font=('Segoe UI', 9, 'bold'),
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
            width=30,
            font=('Segoe UI', 9)
        )
        self.method_combo.pack(fill=tk.X, pady=(0, 12))
        self.method_combo.bind("<<ComboboxSelected>>", self.on_method_selected)
        self.method_combo.current(0)  # "Новое имя" по умолчанию
        
        # Область настроек метода с прокруткой
        settings_container = tk.Frame(methods_frame, bg=self.colors['bg_card'])
        settings_container.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        # Canvas для прокрутки настроек
        settings_canvas = tk.Canvas(settings_container, bg=self.colors['bg_card'], 
                                    highlightthickness=0)
        settings_scrollbar = ttk.Scrollbar(settings_container, orient="vertical", 
                                           command=settings_canvas.yview)
        scrollable_frame = tk.Frame(settings_canvas, bg=self.colors['bg_card'])
        
        def on_frame_configure(event):
            settings_canvas.configure(scrollregion=settings_canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", on_frame_configure)
        
        settings_canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        settings_canvas.configure(yscrollcommand=settings_scrollbar.set)
        
        # Привязка прокрутки колесом мыши
        def on_mousewheel(event):
            settings_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        settings_canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        settings_canvas.pack(side="left", fill="both", expand=True)
        settings_scrollbar.pack(side="right", fill="y")
        
        self.settings_frame = scrollable_frame
        
        # Кнопки управления методами
        method_buttons_frame = tk.Frame(methods_frame, bg=self.colors['bg_card'])
        method_buttons_frame.pack(fill=tk.X, pady=(0, 15))
        method_buttons_frame.columnconfigure(0, weight=1)
        method_buttons_frame.columnconfigure(1, weight=1)
        method_buttons_frame.columnconfigure(2, weight=1)
        
        btn_add_method = self.create_rounded_button(
            method_buttons_frame, "➕ Добавить", self.add_method,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_add_method.grid(row=0, column=0, padx=3, sticky="ew")
        
        btn_remove_method = self.create_rounded_button(
            method_buttons_frame, "➖ Удалить", self.remove_method,
            '#818CF8', 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg='#6366F1')
        btn_remove_method.grid(row=0, column=1, padx=3, sticky="ew")
        
        btn_clear_methods = self.create_rounded_button(
            method_buttons_frame, "🗑️ Очистить", self.clear_methods,
            self.colors['danger'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear_methods.grid(row=0, column=2, padx=3, sticky="ew")
        
        # Список примененных методов
        applied_label = tk.Label(methods_frame, text="📝 Примененные методы:", 
                                font=('Segoe UI', 9, 'bold'),
                                bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        applied_label.pack(anchor=tk.W, pady=(0, 6))
        
        listbox_frame = tk.Frame(methods_frame, bg=self.colors['bg_card'], 
                                relief='flat', borderwidth=1,
                                highlightbackground=self.colors['border'],
                                highlightthickness=1)
        listbox_frame.pack(fill=tk.X, pady=(0, 0))
        
        self.methods_listbox = tk.Listbox(listbox_frame, height=5, 
                                         font=('Segoe UI', 9),
                                         relief='flat', borderwidth=0,
                                         bg='white', fg=self.colors['text_primary'],
                                         selectbackground=self.colors['primary'],
                                         selectforeground='white',
                                         highlightthickness=0)
        self.methods_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        
        # Создаем log_text для логирования (будет использоваться в окне лога)
        self.log_text = None
        
        # Инициализация первого метода (Новое имя)
        self.on_method_selected()
        
        # === СОЗДАНИЕ ВКЛАДОК НА ГЛАВНОМ ЭКРАНЕ ===
        # Создаем вкладки для логов, настроек, о программе и поддержки
        self._create_main_log_tab()
        self._create_main_settings_tab()
        self._create_main_about_tab()
        self._create_main_support_tab()
    
    def open_actions_window(self):
        """Открытие окна действий"""
        if self.windows['actions'] is not None and self.windows['actions'].winfo_exists():
            self.windows['actions'].lift()
            self.windows['actions'].focus_force()
            return
        
        window = tk.Toplevel(self.root)
        window.title("🚀 Действия")
        window.geometry("600x180")
        window.minsize(500, 150)
        window.configure(bg=self.colors['bg_card'])
        
        # Настройка адаптивности окна
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)
        
        # Обработчик изменения размера окна
        def on_actions_window_resize(event):
            if event.widget == window:
                try:
                    # Обновляем размеры кнопок и прогресс-бара
                    window.update_idletasks()
                except:
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
        
        btn_apply = self.create_rounded_button(
            buttons_frame, "✨ Применить метод", self.apply_methods,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_apply.grid(row=0, column=0, sticky="ew", padx=4)

        btn_start = self.create_rounded_button(
            buttons_frame, "▶️ Начать переименование", self.start_rename,
            self.colors['success'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['success_hover'])
        btn_start.grid(row=0, column=1, sticky="ew", padx=4)
        
        # Прогресс бар
        progress_container = tk.Frame(main_frame, bg=self.colors['bg_card'])
        progress_container.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        progress_container.columnconfigure(0, weight=1)
        
        progress_label = tk.Label(progress_container, text="Прогресс:", 
                                 font=('Segoe UI', 9, 'bold'),
                            bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        progress_label.pack(anchor=tk.W, pady=(0, 6))
        
        self.progress_window = ttk.Progressbar(progress_container, mode='determinate')
        self.progress_window.pack(fill=tk.X)
        
        # Обработчик закрытия окна
        window.protocol("WM_DELETE_WINDOW", lambda: self.close_window('actions'))
    
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
            self.log_text = None
            self.close_window('tabs')
        
        window.protocol("WM_DELETE_WINDOW", on_close)
    
    def open_log_window(self):
        """Переключение на вкладку лога операций в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(1)  # Индекс 1 - вкладка лога
    
    def open_settings_window(self):
        """Переключение на вкладку настроек в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(2)  # Индекс 2 - вкладка настроек
    
    def open_about_window(self):
        """Переключение на вкладку о программе в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(3)  # Индекс 3 - вкладка о программе
    
    def open_support_window(self):
        """Переключение на вкладку поддержки в главном окне"""
        if hasattr(self, 'main_notebook') and self.main_notebook:
            self.main_notebook.select(4)  # Индекс 4 - вкладка поддержки
    
    def _create_main_log_tab(self):
        """Создание вкладки лога операций на главном экране"""
        log_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        self.main_notebook.add(log_tab, text="📋 Лог операций")
        
        # Панель управления логом
        log_controls = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_controls.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        log_controls.columnconfigure(1, weight=1)
        log_controls.columnconfigure(2, weight=1)
        
        # Заголовок
        log_title = tk.Label(log_controls, text="📋 Лог операций",
                            font=('Segoe UI', 11, 'bold'),
                            bg=self.colors['bg_card'],
                            fg=self.colors['text_primary'])
        log_title.grid(row=0, column=0, padx=(0, 12), sticky="w")
        
        btn_clear_log = self.create_rounded_button(
            log_controls, "🗑️ Очистить лог", self.clear_log,
            self.colors['danger'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear_log.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Кнопка сохранения лога
        btn_save_log = self.create_rounded_button(
            log_controls, "💾 Сохранить лог", self.save_log,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
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
                               bg='white', fg=self.colors['text_primary'],
                               relief='flat', borderwidth=0,
                               padx=12, pady=10,
                               wrap=tk.WORD)
        log_scroll.config(command=log_text_widget.yview)
        
        log_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Сохраняем ссылку на log_text
        self.log_text = log_text_widget
    
    def _create_main_settings_tab(self):
        """Создание вкладки настроек на главном экране"""
        settings_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(settings_tab, text="⚙️ Настройки")
        
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == settings_tab:
                try:
                    canvas_width = settings_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
        
        settings_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        settings_tab.rowconfigure(0, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Заголовок
        title_label = tk.Label(content_frame, text="⚙️ Настройки", 
                              font=('Segoe UI', 20, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['text_primary'])
        title_label.pack(anchor=tk.W, pady=(0, 25))
        
        # Секция: Общие настройки
        general_frame = ttk.LabelFrame(content_frame, text="Общие настройки", 
                                      style='Card.TLabelframe', padding=15)
        general_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Автоматическое применение методов
        auto_apply_var = tk.BooleanVar(value=False)
        auto_apply_check = tk.Checkbutton(general_frame, 
                                         text="Автоматически применять методы при добавлении",
                                         variable=auto_apply_var,
                                         font=('Segoe UI', 10),
                                         bg=self.colors['bg_card'],
                                         fg=self.colors['text_primary'],
                                         selectcolor='white',
                                         activebackground=self.colors['bg_card'],
                                         activeforeground=self.colors['text_primary'])
        auto_apply_check.pack(anchor=tk.W, pady=5)
        
        # Показывать предупреждения
        show_warnings_var = tk.BooleanVar(value=True)
        show_warnings_check = tk.Checkbutton(general_frame, 
                                            text="Показывать предупреждения перед переименованием",
                                            variable=show_warnings_var,
                                            font=('Segoe UI', 10),
                                            bg=self.colors['bg_card'],
                                            fg=self.colors['text_primary'],
                                            selectcolor='white',
                                            activebackground=self.colors['bg_card'],
                                            activeforeground=self.colors['text_primary'])
        show_warnings_check.pack(anchor=tk.W, pady=5)
        
        # Секция: Интерфейс
        ui_frame = ttk.LabelFrame(content_frame, text="Интерфейс", 
                                 style='Card.TLabelframe', padding=15)
        ui_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Размер шрифта
        font_size_label = tk.Label(ui_frame, text="Размер шрифта:",
                                   font=('Segoe UI', 10, 'bold'),
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['text_primary'])
        font_size_label.pack(anchor=tk.W, pady=(0, 5))
        
        font_size_var = tk.StringVar(value="10")
        font_size_combo = ttk.Combobox(ui_frame, textvariable=font_size_var,
                                      values=["8", "9", "10", "11", "12"],
                                      state="readonly", width=10)
        font_size_combo.pack(anchor=tk.W, pady=(0, 10))
        
        # Секция: Файлы
        files_frame = ttk.LabelFrame(content_frame, text="Работа с файлами", 
                                    style='Card.TLabelframe', padding=15)
        files_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Резервное копирование
        backup_var = tk.BooleanVar(value=False)
        backup_check = tk.Checkbutton(files_frame, 
                                      text="Создавать резервные копии перед переименованием",
                                      variable=backup_var,
                                      font=('Segoe UI', 10),
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['text_primary'],
                                      selectcolor='white',
                                      activebackground=self.colors['bg_card'],
                                      activeforeground=self.colors['text_primary'])
        backup_check.pack(anchor=tk.W, pady=5)
        
        # Кнопка сохранения
        save_btn = self.create_rounded_button(
            content_frame, "💾 Сохранить настройки",
            lambda: messagebox.showinfo("Настройки", "Настройки сохранены!"),
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        save_btn.pack(pady=(10, 0))
    
    def _create_main_about_tab(self):
        """Создание вкладки о программе на главном экране"""
        about_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(about_tab, text="ℹ️ О программе")
        
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == about_tab:
                try:
                    canvas_width = about_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
        
        about_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        about_tab.rowconfigure(0, weight=1)
        about_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Логотип/Название
        title_label = tk.Label(content_frame, text="📝 Назови", 
                              font=('Segoe UI', 32, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['primary'])
        title_label.pack(pady=(10, 5))
        
        # Версия
        version_label = tk.Label(content_frame, 
                                text="Версия 1.0.0",
                                font=('Segoe UI', 11),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['text_secondary'])
        version_label.pack(pady=(0, 25))
        
        # Описание
        desc_text = """Программа для удобного переименования файлов
        
Возможности:
• Переименование по различным методам
• Поддержка метаданных (EXIF, ID3 и др.)
• Предпросмотр изменений перед применением
• Drag & Drop для добавления файлов
• Перестановка файлов в списке
• Отмена операций
        
Используемые технологии:
• Python 3
• Tkinter
• tkinterdnd2"""
        
        desc_label = tk.Label(content_frame, 
                             text=desc_text,
                             font=('Segoe UI', 10),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_primary'],
                             justify=tk.LEFT,
                             anchor=tk.W)
        desc_label.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Разделитель
        separator = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator.pack(fill=tk.X, pady=10)
        
        # Разработчики
        dev_title = tk.Label(content_frame, 
                            text="Разработчики:",
                            font=('Segoe UI', 11, 'bold'),
                            bg=self.colors['bg_card'], 
                            fg=self.colors['text_primary'],
                            justify=tk.LEFT)
        dev_title.pack(anchor=tk.W, pady=(10, 5))
        
        dev_org_label = tk.Label(content_frame, 
                                text="Urban SOLUTION",
                                font=('Segoe UI', 10),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['text_primary'],
                                justify=tk.LEFT)
        dev_org_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Разработал
        dev_by_label = tk.Label(content_frame, 
                               text="Разработал:",
                               font=('Segoe UI', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_primary'],
                               justify=tk.LEFT)
        dev_by_label.pack(anchor=tk.W, pady=(0, 5))
        
        # Ссылка на профиль разработчика
        def open_vk_profile(event):
            import webbrowser
            webbrowser.open("https://vk.com/vsemirka200")
        
        dev_name_label = tk.Label(content_frame, 
                                 text="Олюшин Владислав Викторович",
                                 font=('Segoe UI', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['primary'],
                                 cursor='hand2',
                                 justify=tk.LEFT)
        dev_name_label.pack(anchor=tk.W, pady=(0, 15))
        dev_name_label.bind("<Button-1>", open_vk_profile)
        
        # Разделитель
        separator2 = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator2.pack(fill=tk.X, pady=10)
        
        # Наши соц сети
        social_title = tk.Label(content_frame, 
                               text="Наши соц сети:",
                               font=('Segoe UI', 11, 'bold'),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_primary'],
                               justify=tk.LEFT)
        social_title.pack(anchor=tk.W, pady=(10, 5))
        
        def open_vk_social(event):
            import webbrowser
            webbrowser.open("https://vk.com/urban_solution")
        
        vk_label = tk.Label(content_frame, 
                           text="ВКонтакте: https://vk.com/urban_solution",
                           font=('Segoe UI', 10),
                           bg=self.colors['bg_card'], 
                           fg=self.colors['primary'],
                           cursor='hand2',
                           justify=tk.LEFT)
        vk_label.pack(anchor=tk.W, pady=(0, 5))
        vk_label.bind("<Button-1>", open_vk_social)
        
        def open_tg_channel(event):
            import webbrowser
            webbrowser.open("https://t.me/+n1JeH5DS-HQ2NjYy")
        
        tg_label = tk.Label(content_frame, 
                           text="TG-канал: https://t.me/+n1JeH5DS-HQ2NjYy",
                           font=('Segoe UI', 10),
                           bg=self.colors['bg_card'], 
                           fg=self.colors['primary'],
                           cursor='hand2',
                           justify=tk.LEFT)
        tg_label.pack(anchor=tk.W, pady=(0, 10))
        tg_label.bind("<Button-1>", open_tg_channel)
        
        # Разделитель
        separator3 = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator3.pack(fill=tk.X, pady=10)
        
        # GitHub
        def open_github(event):
            import webbrowser
            webbrowser.open("https://github.com/VseMirka200/nazovi")
        
        github_label = tk.Label(content_frame, 
                               text="GitHub: https://github.com/VseMirka200/nazovi",
                               font=('Segoe UI', 10),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['primary'],
                               cursor='hand2',
                               justify=tk.LEFT)
        github_label.pack(anchor=tk.W, pady=(10, 15))
        github_label.bind("<Button-1>", open_github)
        
        # Разделитель
        separator4 = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator4.pack(fill=tk.X, pady=10)
        
        # Автор
        author_label = tk.Label(content_frame, 
                               text="© 2024 Назови. Все права защищены.",
                               font=('Segoe UI', 9),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_muted'],
                               justify=tk.CENTER)
        author_label.pack(pady=(10, 0))
    
    def _create_main_support_tab(self):
        """Создание вкладки поддержки на главном экране"""
        support_tab = tk.Frame(self.main_notebook, bg=self.colors['bg_card'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        self.main_notebook.add(support_tab, text="💝 Поддержать")
        
        # Содержимое поддержки с прокруткой
        canvas = tk.Canvas(support_tab, bg=self.colors['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(support_tab, orient="vertical", command=canvas.yview)
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == support_tab:
                try:
                    canvas_width = support_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
        
        support_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        support_tab.rowconfigure(0, weight=1)
        support_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Заголовок
        title_label = tk.Label(content_frame, text="💝 Поддержать проект", 
                              font=('Segoe UI', 24, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['primary'])
        title_label.pack(pady=(10, 20))
        
        # Описание
        desc_text = """Если вам нравится эта программа и она помогает вам в работе, 
вы можете поддержать её развитие!

Ваша поддержка поможет:
• Добавлять новые функции
• Улучшать существующие возможности
• Исправлять ошибки
• Поддерживать проект активным

Способы поддержки:"""
        
        desc_label = tk.Label(content_frame, 
                             text=desc_text,
                             font=('Segoe UI', 10),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_primary'],
                             justify=tk.LEFT)
        desc_label.pack(anchor=tk.W, pady=(0, 20))
        
        # Способы поддержки
        support_frame = tk.Frame(content_frame, bg=self.colors['bg_card'])
        support_frame.pack(fill=tk.X, pady=(0, 20))
        
        support_methods = [
            ("⭐", "Оставить отзыв и оценку"),
            ("🐛", "Сообщить об ошибках"),
            ("💡", "Предложить новые функции"),
            ("📢", "Рассказать друзьям о программе")
        ]
        
        for icon, text in support_methods:
            method_frame = tk.Frame(support_frame, bg=self.colors['bg_card'])
            method_frame.pack(fill=tk.X, pady=8)
            
            icon_label = tk.Label(method_frame, text=icon,
                                 font=('Segoe UI', 16),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['primary'])
            icon_label.pack(side=tk.LEFT, padx=(0, 10))
            
            text_label = tk.Label(method_frame, text=text,
                                 font=('Segoe UI', 10),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['text_primary'])
            text_label.pack(side=tk.LEFT)
        
        # Разделитель
        separator = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator.pack(fill=tk.X, pady=15)
        
        # Донат
        def open_donation(event):
            import webbrowser
            webbrowser.open("https://pay.cloudtips.ru/p/1fa22ea5")
        
        donation_title = tk.Label(content_frame, 
                                 text="💰 Финансовая поддержка:",
                                 font=('Segoe UI', 11, 'bold'),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['text_primary'],
                                 justify=tk.LEFT)
        donation_title.pack(anchor=tk.W, pady=(10, 5))
        
        donation_label = tk.Label(content_frame, 
                                 text="Поддержать проект: https://pay.cloudtips.ru/p/1fa22ea5",
                                 font=('Segoe UI', 10),
                                 bg=self.colors['bg_card'], 
                                 fg=self.colors['primary'],
                                 cursor='hand2',
                                 justify=tk.LEFT)
        donation_label.pack(anchor=tk.W, pady=(0, 15))
        donation_label.bind("<Button-1>", open_donation)
        
        # Разделитель
        separator2 = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator2.pack(fill=tk.X, pady=15)
        
        # Благодарность
        thanks_label = tk.Label(content_frame, 
                               text="Спасибо за использование программы! 🙏",
                            font=('Segoe UI', 11, 'bold'),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_secondary'],
                               justify=tk.CENTER)
        thanks_label.pack(pady=(10, 0))
    
    def _create_log_tab(self, notebook):
        """Создание вкладки лога операций"""
        # Фрейм для вкладки лога
        log_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        log_tab.columnconfigure(0, weight=1)
        log_tab.rowconfigure(1, weight=1)
        notebook.add(log_tab, text="📋 Лог операций")
        
        # Панель управления логом
        log_controls = tk.Frame(log_tab, bg=self.colors['bg_card'])
        log_controls.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        log_controls.columnconfigure(1, weight=1)
        log_controls.columnconfigure(2, weight=1)
        
        # Заголовок
        log_title = tk.Label(log_controls, text="📋 Лог операций",
                            font=('Segoe UI', 11, 'bold'),
                            bg=self.colors['bg_card'],
                            fg=self.colors['text_primary'])
        log_title.grid(row=0, column=0, padx=(0, 12), sticky="w")
        
        btn_clear_log = self.create_rounded_button(
            log_controls, "🗑️ Очистить лог", self.clear_log,
            self.colors['danger'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['danger_hover'])
        btn_clear_log.grid(row=0, column=1, padx=3, sticky="ew")
        
        # Кнопка сохранения лога
        btn_save_log = self.create_rounded_button(
            log_controls, "💾 Сохранить лог", self.save_log,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
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
                               bg='white', fg=self.colors['text_primary'],
                               relief='flat', borderwidth=0,
                               padx=12, pady=10,
                               wrap=tk.WORD)
        log_scroll.config(command=log_text_widget.yview)
        
        log_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Сохраняем ссылку на log_text
        self.log_text = log_text_widget
    
    def _create_settings_tab(self, notebook):
        """Создание вкладки настроек"""
        # Фрейм для вкладки настроек
        settings_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        settings_tab.columnconfigure(0, weight=1)
        settings_tab.rowconfigure(0, weight=1)
        notebook.add(settings_tab, text="⚙️ Настройки")
        
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == settings_tab:
                try:
                    canvas_width = settings_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
        
        settings_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        settings_tab.rowconfigure(0, weight=1)
        settings_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Заголовок
        title_label = tk.Label(content_frame, text="⚙️ Настройки", 
                              font=('Segoe UI', 20, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['text_primary'])
        title_label.pack(anchor=tk.W, pady=(0, 25))
        
        # Секция: Общие настройки
        general_frame = ttk.LabelFrame(content_frame, text="Общие настройки", 
                                      style='Card.TLabelframe', padding=15)
        general_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Автоматическое применение методов
        auto_apply_var = tk.BooleanVar(value=False)
        auto_apply_check = tk.Checkbutton(general_frame, 
                                         text="Автоматически применять методы при добавлении",
                                         variable=auto_apply_var,
                                         font=('Segoe UI', 10),
                                         bg=self.colors['bg_card'],
                                         fg=self.colors['text_primary'],
                                         selectcolor='white',
                                         activebackground=self.colors['bg_card'],
                                         activeforeground=self.colors['text_primary'])
        auto_apply_check.pack(anchor=tk.W, pady=5)
        
        # Показывать предупреждения
        show_warnings_var = tk.BooleanVar(value=True)
        show_warnings_check = tk.Checkbutton(general_frame, 
                                            text="Показывать предупреждения перед переименованием",
                                            variable=show_warnings_var,
                                            font=('Segoe UI', 10),
                                            bg=self.colors['bg_card'],
                                            fg=self.colors['text_primary'],
                                            selectcolor='white',
                                            activebackground=self.colors['bg_card'],
                                            activeforeground=self.colors['text_primary'])
        show_warnings_check.pack(anchor=tk.W, pady=5)
        
        # Секция: Интерфейс
        ui_frame = ttk.LabelFrame(content_frame, text="Интерфейс", 
                                 style='Card.TLabelframe', padding=15)
        ui_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Размер шрифта
        font_size_label = tk.Label(ui_frame, text="Размер шрифта:",
                                   font=('Segoe UI', 10, 'bold'),
                                   bg=self.colors['bg_card'],
                                   fg=self.colors['text_primary'])
        font_size_label.pack(anchor=tk.W, pady=(0, 5))
        
        font_size_var = tk.StringVar(value="10")
        font_size_combo = ttk.Combobox(ui_frame, textvariable=font_size_var,
                                      values=["8", "9", "10", "11", "12"],
                                      state="readonly", width=10)
        font_size_combo.pack(anchor=tk.W, pady=(0, 10))
        
        # Секция: Файлы
        files_frame = ttk.LabelFrame(content_frame, text="Работа с файлами", 
                                    style='Card.TLabelframe', padding=15)
        files_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Резервное копирование
        backup_var = tk.BooleanVar(value=False)
        backup_check = tk.Checkbutton(files_frame, 
                                      text="Создавать резервные копии перед переименованием",
                                      variable=backup_var,
                                      font=('Segoe UI', 10),
                                      bg=self.colors['bg_card'],
                                      fg=self.colors['text_primary'],
                                      selectcolor='white',
                                      activebackground=self.colors['bg_card'],
                                      activeforeground=self.colors['text_primary'])
        backup_check.pack(anchor=tk.W, pady=5)
        
        # Кнопка сохранения
        save_btn = self.create_rounded_button(
            content_frame, "💾 Сохранить настройки",
            lambda: messagebox.showinfo("Настройки", "Настройки сохранены!"),
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        save_btn.pack(pady=(10, 0))
    
    def _create_about_tab(self, notebook):
        """Создание вкладки о программе"""
        # Фрейм для вкладки о программе
        about_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        about_tab.columnconfigure(0, weight=1)
        about_tab.rowconfigure(0, weight=1)
        notebook.add(about_tab, text="ℹ️ О программе")
        
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == about_tab:
                try:
                    canvas_width = about_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
        
        about_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        about_tab.rowconfigure(0, weight=1)
        about_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Логотип/Название
        title_label = tk.Label(content_frame, text="📝 Назови", 
                              font=('Segoe UI', 32, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['primary'])
        title_label.pack(pady=(10, 5))
        
        # Версия
        version_label = tk.Label(content_frame, 
                                text="Версия 1.0.0",
                                font=('Segoe UI', 11),
                                bg=self.colors['bg_card'], 
                                fg=self.colors['text_secondary'])
        version_label.pack(pady=(0, 25))
        
        # Описание
        desc_text = """Программа для удобного переименования файлов
        
Возможности:
• Переименование по различным методам
• Поддержка метаданных (EXIF, ID3 и др.)
• Предпросмотр изменений перед применением
• Drag & Drop для добавления файлов
• Перестановка файлов в списке
• Отмена операций
        
Используемые технологии:
• Python 3
• Tkinter
• tkinterdnd2"""
        
        desc_label = tk.Label(content_frame, 
                             text=desc_text,
                             font=('Segoe UI', 10),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_primary'],
                             justify=tk.LEFT,
                             anchor=tk.W)
        desc_label.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Разделитель
        separator = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator.pack(fill=tk.X, pady=10)
        
        # Автор
        author_label = tk.Label(content_frame, 
                               text="© 2024 Назови. Все права защищены.",
                               font=('Segoe UI', 9),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_muted'],
                               justify=tk.CENTER)
        author_label.pack(pady=(10, 0))
    
    def _create_support_tab(self, notebook):
        """Создание вкладки поддержки"""
        # Фрейм для вкладки поддержки
        support_tab = tk.Frame(notebook, bg=self.colors['bg_card'])
        support_tab.columnconfigure(0, weight=1)
        support_tab.rowconfigure(0, weight=1)
        notebook.add(support_tab, text="💝 Поддержать")
        
        # Содержимое поддержки с прокруткой
        canvas = tk.Canvas(support_tab, bg=self.colors['bg_card'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(support_tab, orient="vertical", command=canvas.yview)
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
                except:
                    pass
        
        canvas.bind('<Configure>', on_canvas_configure)
        def on_window_configure(event):
            if event.widget == support_tab:
                try:
                    canvas_width = support_tab.winfo_width() - scrollbar.winfo_width() - 4
                    canvas.itemconfig(canvas_window, width=max(canvas_width, 100))
                except:
                    pass
    
        support_tab.bind('<Configure>', on_window_configure)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        support_tab.rowconfigure(0, weight=1)
        support_tab.columnconfigure(0, weight=1)
        
        content_frame = scrollable_frame
        content_frame.columnconfigure(0, weight=1)
        scrollable_frame.configure(padx=30, pady=30)
        
        # Заголовок
        title_label = tk.Label(content_frame, text="💝 Поддержать проект", 
                              font=('Segoe UI', 24, 'bold'),
                              bg=self.colors['bg_card'], 
                              fg=self.colors['primary'])
        title_label.pack(pady=(10, 20))
        
        # Описание
        desc_text = """Если вам нравится эта программа и она помогает вам в работе, 
вы можете поддержать её развитие!

Ваша поддержка поможет:
• Добавлять новые функции
• Улучшать существующие возможности
• Исправлять ошибки
• Поддерживать проект активным

Способы поддержки:"""
        
        desc_label = tk.Label(content_frame, 
                             text=desc_text,
                             font=('Segoe UI', 10),
                             bg=self.colors['bg_card'], 
                             fg=self.colors['text_primary'],
                             justify=tk.LEFT)
        desc_label.pack(anchor=tk.W, pady=(0, 20))
        
        # Способы поддержки
        support_frame = tk.Frame(content_frame, bg=self.colors['bg_card'])
        support_frame.pack(fill=tk.X, pady=(0, 20))
        
        support_methods = [
            ("⭐", "Оставить отзыв и оценку"),
            ("🐛", "Сообщить об ошибках"),
            ("💡", "Предложить новые функции"),
            ("📢", "Рассказать друзьям о программе")
        ]
        
        for icon, text in support_methods:
            method_frame = tk.Frame(support_frame, bg=self.colors['bg_card'])
            method_frame.pack(fill=tk.X, pady=8)
            
            icon_label = tk.Label(method_frame, text=icon,
                                 font=('Segoe UI', 16),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['primary'])
            icon_label.pack(side=tk.LEFT, padx=(0, 10))
            
            text_label = tk.Label(method_frame, text=text,
                                 font=('Segoe UI', 10),
                                 bg=self.colors['bg_card'],
                                 fg=self.colors['text_primary'])
            text_label.pack(side=tk.LEFT)
        
        # Разделитель
        separator = tk.Frame(content_frame, bg=self.colors['border'], height=1)
        separator.pack(fill=tk.X, pady=15)
        
        # Благодарность
        thanks_label = tk.Label(content_frame, 
                               text="Спасибо за использование программы! 🙏",
                               font=('Segoe UI', 11, 'bold'),
                               bg=self.colors['bg_card'], 
                               fg=self.colors['text_secondary'],
                               justify=tk.CENTER)
        thanks_label.pack(pady=(10, 0))
    
    def close_window(self, window_name: str):
        """Закрытие окна"""
        if window_name in self.windows and self.windows[window_name] is not None:
            if window_name == 'tabs':
                # Сохраняем log_text для логирования
                self.log_text = None
            try:
                self.windows[window_name].destroy()
            except:
                pass
            self.windows[window_name] = None
    
    
    def setup_hotkeys(self):
        """Настройка горячих клавиш"""
        self.root.bind('<Control-a>', lambda e: self.add_files())
        self.root.bind('<Control-z>', lambda e: self.undo_rename())
        self.root.bind('<Delete>', lambda e: self.delete_selected())
        self.root.bind('<Control-o>', lambda e: self.add_folder())
    
    def setup_drag_drop(self):
        """Настройка drag and drop для файлов из проводника"""
        # Используем tkinterdnd2 если доступно
        if HAS_TKINTERDND2:
            try:
                # Регистрируем окно как цель для перетаскивания файлов
                self.root.drop_target_register(DND_FILES)
                self.root.dnd_bind('<<Drop>>', self._on_drop_files)
                
                # Также регистрируем таблицу для перетаскивания файлов
                self.tree.drop_target_register(DND_FILES)
                self.tree.dnd_bind('<<Drop>>', self._on_drop_files)
                
                # Регистрируем левую панель (где находится таблица)
                # Получаем родительский фрейм таблицы
                try:
                    left_panel = self.tree.master.master if hasattr(self.tree.master, 'master') else self.tree.master
                    if hasattr(left_panel, 'drop_target_register'):
                        left_panel.drop_target_register(DND_FILES)
                        left_panel.dnd_bind('<<Drop>>', self._on_drop_files)
                except:
                    pass  # Если не получилось, не критично
                
                # Логируем успешную настройку (только при первом запуске)
                if not hasattr(self, '_drag_drop_logged'):
                    msg = "✅ Drag and drop файлов включен - можно перетаскивать файлы из проводника"
                    print(f"DEBUG: {msg}")
                    self.log(msg)
                    self._drag_drop_logged = True
                return
            except Exception as e:
                error_msg = f"Ошибка настройки drag and drop (tkinterdnd2): {e}"
                print(f"DEBUG ERROR: {error_msg}")
                import traceback
                print(traceback.format_exc())
                self.log(error_msg)
        
        # Используем Windows API как резервный вариант - отключаем для избежания ошибок
        # Полный перехват WindowProc может вызывать проблемы, лучше использовать tkinterdnd2
        if sys.platform == 'win32' and has_dragdrop and False:  # Отключено для стабильности
            try:
                self._setup_windows_drag_drop()
                if not hasattr(self, '_drag_drop_logged'):
                    self.log("✅ Drag and drop файлов включен через Windows API")
                    self.log("💡 Перетащите файлы из проводника в окно программы")
                    self._drag_drop_logged = True
                return
            except Exception as e:
                import traceback
                error_msg = str(e)
                error_trace = traceback.format_exc()
                if not hasattr(self, '_drag_drop_logged'):
                    self.log(f"⚠️ Не удалось включить drag and drop: {error_msg}")
                    self.log("💡 Установите библиотеку: pip install tkinterdnd2")
                    # Логируем полную ошибку для отладки
                    print(f"Ошибка drag and drop:\n{error_trace}")
                    self._drag_drop_logged = True
        
        # Если ничего не сработало
        if not hasattr(self, '_drag_drop_logged'):
            self.log("⚠️ Перетаскивание файлов из проводника недоступно")
            self.log("💡 Для включения установите: pip install tkinterdnd2")
            self.log("💡 Перестановка файлов в таблице доступна - перетащите строку мышью")
            self._drag_drop_logged = True
    
    def _setup_windows_drag_drop(self):
        """Настройка drag and drop через Windows API"""
        # Эта функция оставлена для совместимости, но не используется
        # для избежания проблем с перехватом WindowProc
        # Для полной поддержки drag-and-drop рекомендуется установить tkinterdnd2
        pass
    
    def _on_drop_files(self, event):
        """Обработка события перетаскивания файлов"""
        # Сразу выводим в консоль для отладки
        print("=== DRAG AND DROP EVENT TRIGGERED ===")
        
        try:
            # Получаем данные из события
            data = event.data
            print(f"Event data received: {type(data)}, length: {len(data) if data else 0}")
            
            # tkinterdnd2 на Windows возвращает файлы в формате: {file1} {file2} {file3}
            # Где каждый файл заключен в фигурные скобки
            processed_files = []
            
            # Логируем исходные данные для отладки
            if data:
                data_preview = data[:200] + ("..." if len(data) > 200 else "")
                log_msg = f"Получено данных: {len(data)} символов"
                print(f"DEBUG: {log_msg}")
                self.log(log_msg)
                self.log(f"Начало данных: {data_preview}")
            else:
                error_msg = "⚠️ Данные не получены из события перетаскивания"
                print(f"DEBUG: {error_msg}")
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
                    self.log(f"⚠️ Ошибка нормализации пути '{original_path}': {e}")
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
                            self.log(f"✓ Из папки '{os.path.basename(file_path)}' найдено: {folder_file_count} файлов")
                        except Exception as e:
                            self.log(f"⚠️ Ошибка при обработке папки '{file_path}': {e}")
                else:
                    # Логируем несуществующие пути
                    skipped_count += 1
                    self.log(f"⚠️ Путь не найден: {file_path}")
            
            # Выводим итоговую статистику
            if skipped_count > 0:
                self.log(f"⚠️ Пропущено несуществующих/ошибочных путей: {skipped_count}")
            
            if files_found > 0:
                self.log(f"✓ Найдено файлов: {files_found}")
            if folders_found > 0:
                self.log(f"✓ Обработано папок: {folders_found}")
            
            self.log(f"✓ Всего файлов готово к добавлению: {len(processed_files)}")
            
            if processed_files:
                self._process_dropped_files(processed_files)
            else:
                self.log("⚠️ Не найдено файлов для добавления. Проверьте пути в логе выше.")
                
        except Exception as e:
            import traceback
            error_msg = str(e)
            self.log(f"❌ Ошибка при обработке перетащенных файлов: {error_msg}")
            print(f"Ошибка drag and drop:\n{traceback.format_exc()}")
    
    def _process_dropped_files(self, files):
        """Обработка перетащенных файлов"""
        print(f"DEBUG: _process_dropped_files вызван с {len(files)} файлами")
        
        if not files:
            self.log("⚠️ Список файлов пуст")
            return
        
        count = 0
        skipped = 0
        for file_path in files:
            if os.path.isfile(file_path):
                self.add_file(file_path)
                count += 1
            else:
                skipped += 1
                self.log(f"⚠️ Пропущен (не файл): {file_path}")
        
        if count > 0:
            self.update_status()
            msg = f"✅ Добавлено файлов перетаскиванием: {count}"
            if skipped > 0:
                msg += f" (пропущено: {skipped})"
            print(f"DEBUG: {msg}")
            self.log(msg)
        else:
            msg = "⚠️ Не удалось добавить файлы"
            print(f"DEBUG: {msg}")
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
    
    def log(self, message: str):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # Выводим в консоль для отладки
        print(log_message.strip())
        
        # Добавляем в лог, если окно лога открыто
        if hasattr(self, 'log_text') and self.log_text is not None:
            try:
                self.log_text.insert(tk.END, log_message)
                self.log_text.see(tk.END)
            except tk.TclError:
                # Окно было закрыто
                self.log_text = None
    
    def clear_log(self):
        """Очистка лога операций"""
        if hasattr(self, 'log_text') and self.log_text is not None:
            try:
                self.log_text.delete(1.0, tk.END)
                self.log("Лог очищен")
            except tk.TclError:
                self.log_text = None
    
    def save_log(self):
        """Сохранение лога в файл"""
        if hasattr(self, 'log_text') and self.log_text is not None:
            try:
                log_content = self.log_text.get(1.0, tk.END)
                if not log_content.strip():
                    messagebox.showwarning("Предупреждение", "Лог пуст, нечего сохранять.")
                    return
                
                filename = filedialog.asksaveasfilename(
                    defaultextension=".txt",
                    filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")],
                    title="Сохранить лог"
                )
                
                if filename:
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(log_content)
                    messagebox.showinfo("Успех", f"Лог сохранен в файл:\n{filename}")
                    self.log(f"Лог сохранен в файл: {filename}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить лог: {e}")
        else:
            messagebox.showwarning("Предупреждение", "Окно лога не открыто.")
    
    def add_files(self):
        """Добавление файлов через диалог выбора"""
        files = filedialog.askopenfilenames(title="Выберите файлы")
        if files:
            for file_path in files:
                self.add_file(file_path)
            self.update_status()
            self.log(f"Добавлено файлов: {len(files)}")
    
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
        print(f"DEBUG add_file: проверяю файл {file_path}")
        
        if not os.path.isfile(file_path):
            print(f"DEBUG add_file: {file_path} не является файлом")
            return
        
        # Нормализуем путь для проверки дубликатов
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # Проверяем, нет ли уже такого файла в списке
        for existing_file in self.files:
            existing_path = os.path.normpath(os.path.abspath(existing_file.get('full_path', '')))
            if existing_path == file_path:
                # Файл уже есть в списке, пропускаем
                print(f"DEBUG add_file: файл {file_path} уже в списке, пропускаю")
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
        item = self.tree.insert("", tk.END, values=(
            old_name, old_name, extension, path, 'Готов'
        ), tags=('ready',))
        
        print(f"DEBUG add_file: файл {old_name} добавлен в список")
    
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
        self.status_label.config(text=f"📊 Файлов: {count}")
    
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
    
    def create_add_remove_settings(self):
        """Создание настроек для метода Добавить/Удалить"""
        ttk.Label(self.settings_frame, text="Операция:").pack(anchor=tk.W)
        self.add_remove_op = tk.StringVar(value="add")
        ttk.Radiobutton(self.settings_frame, text="Добавить текст", variable=self.add_remove_op, value="add").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Удалить текст", variable=self.add_remove_op, value="remove").pack(anchor=tk.W)
        
        ttk.Label(self.settings_frame, text="Текст:").pack(anchor=tk.W, pady=(5, 0))
        self.add_remove_text = ttk.Entry(self.settings_frame, width=30)
        self.add_remove_text.pack(fill=tk.X, pady=2)
        
        ttk.Label(self.settings_frame, text="Позиция:").pack(anchor=tk.W, pady=(5, 0))
        self.add_remove_pos = tk.StringVar(value="before")
        ttk.Radiobutton(self.settings_frame, text="Перед именем", variable=self.add_remove_pos, value="before").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="После имени", variable=self.add_remove_pos, value="after").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.add_remove_pos, value="start").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.add_remove_pos, value="end").pack(anchor=tk.W)
        
        # Для удаления
        ttk.Label(self.settings_frame, text="Удалить (если выбрано удаление):").pack(anchor=tk.W, pady=(5, 0))
        self.remove_type = tk.StringVar(value="chars")
        ttk.Radiobutton(self.settings_frame, text="N символов", variable=self.remove_type, value="chars").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Диапазон", variable=self.remove_type, value="range").pack(anchor=tk.W)
        
        ttk.Label(self.settings_frame, text="Количество/Начало:").pack(anchor=tk.W, pady=(5, 0))
        self.remove_start = ttk.Entry(self.settings_frame, width=10)
        self.remove_start.pack(anchor=tk.W, pady=2)
        
        ttk.Label(self.settings_frame, text="Конец (для диапазона):").pack(anchor=tk.W, pady=(5, 0))
        self.remove_end = ttk.Entry(self.settings_frame, width=10)
        self.remove_end.pack(anchor=tk.W, pady=2)
    
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
                ("Фото_{n}", "Фото_1, Фото_2, ..."),
                ("Изображение_{n}", "Изображение_1, Изображение_2, ..."),
                ("IMG_{n:03d}", "IMG_001, IMG_002, ..."),
                ("Photo_{n}", "Photo_1, Photo_2, ..."),
                ("{date_created}_{n}", "2024-01-01_1, 2024-01-01_2, ..."),
            ])
        
        # Шаблоны для документов
        doc_exts = ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt']
        if main_ext in doc_exts:
            templates.extend([
                ("Документ_{n}", "Документ_1, Документ_2, ..."),
                ("Doc_{n:03d}", "Doc_001, Doc_002, ..."),
                ("Файл_{n}", "Файл_1, Файл_2, ..."),
            ])
        
        # Шаблоны для видео
        video_exts = ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm']
        if main_ext in video_exts:
            templates.extend([
                ("Видео_{n}", "Видео_1, Видео_2, ..."),
                ("Video_{n:03d}", "Video_001, Video_002, ..."),
                ("Clip_{n}", "Clip_1, Clip_2, ..."),
            ])
        
        # Шаблоны для аудио
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']
        if main_ext in audio_exts:
            templates.extend([
                ("Аудио_{n}", "Аудио_1, Аудио_2, ..."),
                ("Audio_{n:03d}", "Audio_001, Audio_002, ..."),
                ("Track_{n:02d}", "Track_01, Track_02, ..."),
            ])
        
        # Универсальные шаблоны
        templates.extend([
            ("Файл_{n}", "Файл_1, Файл_2, ..."),
            ("{n}", "1, 2, 3, ..."),
            ("Новый_{n:03d}", "Новый_001, Новый_002, ..."),
        ])
        
        return templates
    
    def create_new_name_settings(self):
        """Создание настроек для метода Новое имя"""
        # Кнопка быстрых шаблонов
        quick_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        quick_frame.pack(fill=tk.X, pady=(0, 15))
        
        btn_quick = self.create_rounded_button(
            quick_frame, "📋 Быстрые шаблоны", self.show_quick_templates,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_quick.pack(fill=tk.X)
        
        # Поле ввода шаблона
        template_label = tk.Label(self.settings_frame, text="✏️ Новое имя (шаблон):", 
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        template_label.pack(anchor=tk.W, pady=(0, 10))
        
        self.new_name_template = ttk.Entry(self.settings_frame, width=30, font=('Segoe UI', 10))
        self.new_name_template.pack(fill=tk.X, pady=(0, 12))
        
        # Кнопка применения шаблона
        apply_template_btn = self.create_rounded_button(
            self.settings_frame, "✅ Применить шаблон", self.apply_template_quick,
            self.colors['success'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['success_hover'])
        apply_template_btn.pack(fill=tk.X, pady=(0, 15))
        
        # Предупреждение
        warning_frame = tk.Frame(self.settings_frame, bg='#FEF3C7', 
                                relief='flat', borderwidth=1,
                                highlightbackground='#FCD34D',
                                highlightthickness=1)
        warning_frame.pack(fill=tk.X, pady=(0, 15))
        
        warning_label = tk.Label(warning_frame, text="⚠ БЕЗ {name} - имя полностью заменяется!", 
                               font=('Segoe UI', 10, 'bold'),
                               bg='#FEF3C7', fg='#92400E',
                               padx=12, pady=10)
        warning_label.pack(anchor=tk.W)
        
        # Кликабельные переменные
        vars_label = tk.Label(self.settings_frame, 
                             text="🔗 Доступные переменные (кликните для вставки):", 
                             font=('Segoe UI', 10, 'bold'),
                             bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        vars_label.pack(anchor=tk.W, pady=(0, 10))
        
        variables_frame = tk.Frame(self.settings_frame, bg=self.colors['bg_card'])
        variables_frame.pack(fill=tk.X, pady=2)
        
        # Контейнер для переменных с фоном
        vars_container = tk.Frame(variables_frame, bg=self.colors['bg_secondary'], 
                                 relief='flat', borderwidth=1,
                                 highlightbackground=self.colors['border'],
                                 highlightthickness=1)
        vars_container.pack(fill=tk.X, padx=0, pady=0)
        
        # Список переменных с описаниями
        variables = [
            ("{name}", "старое имя"),
            ("{ext}", "расширение"),
            ("{n}", "номер файла"),
            ("{n:03d}", "номер с нулями (001, 002)"),
            ("{width}x{height}", "размеры изображения"),
            ("{date_created}", "дата создания"),
            ("{date_modified}", "дата изменения"),
            ("{file_size}", "размер файла")
        ]
        
        # Создание кликабельных меток для переменных
        for i, (var, desc) in enumerate(variables):
            var_frame = tk.Frame(vars_container, bg=self.colors['bg_secondary'])
            var_frame.pack(anchor=tk.W, pady=3, padx=10, fill=tk.X)
            
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
                                 font=('Segoe UI', 10),
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
    
    def show_quick_templates(self):
        """Показать окно с быстрыми шаблонами"""
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
        
        # Информация о типах файлов
        extensions = self.get_file_types()
        ext_info = ", ".join([f"{ext} ({count})" for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:5]])
        ttk.Label(template_window, text=f"Типы файлов: {ext_info}", font=("Arial", 9)).pack(pady=5)
        
        # Список шаблонов
        listbox_frame = ttk.Frame(template_window)
        listbox_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(listbox_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        listbox = tk.Listbox(listbox_frame, yscrollcommand=scrollbar.set, font=("Arial", 10))
        scrollbar.config(command=listbox.yview)
        
        for template, description in templates:
            listbox.insert(tk.END, f"{template:30s} → {description}")
        
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Кнопки
        btn_frame = ttk.Frame(template_window)
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
        
        btn_select = self.create_rounded_button(
            btn_frame, "Выбрать", select_template,
            self.colors['primary'], 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg=self.colors['primary_hover'])
        btn_select.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        btn_cancel = self.create_rounded_button(
            btn_frame, "Отмена", template_window.destroy,
            '#818CF8', 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
            active_bg='#6366F1')
        btn_cancel.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Двойной клик для выбора
        listbox.bind('<Double-Button-1>', lambda e: select_template())
    
    def apply_template_quick(self):
        """Быстрое применение шаблона: добавление метода и применение"""
        template = self.new_name_template.get().strip()
        
        if not template:
            messagebox.showwarning(
                "Предупреждение",
                "Введите шаблон или выберите из быстрых шаблонов"
            )
            return
        
        try:
            method = NewNameMethod(
                template=template,
                metadata_extractor=self.metadata_extractor,
                file_number=1
            )
            
            # Добавляем метод
            self.current_methods.append(method)
            self.methods_listbox.insert(tk.END, "Новое имя")
            self.log(f"Добавлен метод: Новое имя (шаблон: {template})")
            
            # Автоматически применяем метод
            self.apply_methods()
            
            messagebox.showinfo(
                "Готово",
                f"Шаблон '{template}' применен!\n"
                f"Проверьте предпросмотр в таблице."
            )
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось применить шаблон: {e}")
    
    def create_replace_settings(self):
        """Создание настроек для метода Замена"""
        ttk.Label(self.settings_frame, text="Найти:").pack(anchor=tk.W)
        self.replace_find = ttk.Entry(self.settings_frame, width=30)
        self.replace_find.pack(fill=tk.X, pady=2)
        
        ttk.Label(self.settings_frame, text="Заменить на:").pack(anchor=tk.W, pady=(5, 0))
        self.replace_with = ttk.Entry(self.settings_frame, width=30)
        self.replace_with.pack(fill=tk.X, pady=2)
        
        self.replace_case = tk.BooleanVar()
        ttk.Checkbutton(self.settings_frame, text="Учитывать регистр", variable=self.replace_case).pack(anchor=tk.W, pady=2)
        
        self.replace_full = tk.BooleanVar()
        ttk.Checkbutton(self.settings_frame, text="Только полное совпадение", variable=self.replace_full).pack(anchor=tk.W, pady=2)
        
        self.replace_whole_name = tk.BooleanVar()
        ttk.Checkbutton(
            self.settings_frame,
            text="Заменить все имя (если 'Найти' = полное имя)",
            variable=self.replace_whole_name
        ).pack(anchor=tk.W, pady=2)
    
    def create_case_settings(self) -> None:
        """Создание настроек для метода Регистр."""
        self.case_type = tk.StringVar(value="lower")
        ttk.Radiobutton(self.settings_frame, text="Верхний регистр", variable=self.case_type, value="upper").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Нижний регистр", variable=self.case_type, value="lower").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Первая заглавная", variable=self.case_type, value="capitalize").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Заглавные каждого слова", variable=self.case_type, value="title").pack(anchor=tk.W)
        
        ttk.Label(self.settings_frame, text="Применить к:").pack(anchor=tk.W, pady=(5, 0))
        self.case_apply = tk.StringVar(value="name")
        ttk.Radiobutton(self.settings_frame, text="Имени", variable=self.case_apply, value="name").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Расширению", variable=self.case_apply, value="ext").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="Всему", variable=self.case_apply, value="all").pack(anchor=tk.W)
    
    def create_numbering_settings(self) -> None:
        """Создание настроек для метода Нумерация."""
        ttk.Label(self.settings_frame, text="Начальный индекс:").pack(anchor=tk.W)
        self.numbering_start = ttk.Entry(self.settings_frame, width=10)
        self.numbering_start.insert(0, "1")
        self.numbering_start.pack(anchor=tk.W, pady=2)
        
        ttk.Label(self.settings_frame, text="Шаг:").pack(anchor=tk.W, pady=(5, 0))
        self.numbering_step = ttk.Entry(self.settings_frame, width=10)
        self.numbering_step.insert(0, "1")
        self.numbering_step.pack(anchor=tk.W, pady=2)
        
        ttk.Label(self.settings_frame, text="Количество цифр:").pack(anchor=tk.W, pady=(5, 0))
        self.numbering_digits = ttk.Entry(self.settings_frame, width=10)
        self.numbering_digits.insert(0, "3")
        self.numbering_digits.pack(anchor=tk.W, pady=2)
        
        ttk.Label(self.settings_frame, text="Формат:").pack(anchor=tk.W, pady=(5, 0))
        self.numbering_format = tk.StringVar(value="({n})")
        ttk.Entry(self.settings_frame, textvariable=self.numbering_format, width=20).pack(anchor=tk.W, pady=2)
        ttk.Label(
            self.settings_frame,
            text="(используйте {n} для номера)",
            font=("Arial", 8)
        ).pack(anchor=tk.W)
        
        ttk.Label(self.settings_frame, text="Позиция:").pack(anchor=tk.W, pady=(5, 0))
        self.numbering_pos = tk.StringVar(value="end")
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.numbering_pos, value="start").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.numbering_pos, value="end").pack(anchor=tk.W)
    
    def create_metadata_settings(self) -> None:
        """Создание настроек для метода Метаданные."""
        if not self.metadata_extractor:
            ttk.Label(self.settings_frame, text="Модуль метаданных недоступен.\nУстановите Pillow: pip install Pillow", 
                     foreground="#000000").pack(pady=10)
            return
        
        ttk.Label(self.settings_frame, text="Тег метаданных:").pack(anchor=tk.W)
        self.metadata_tag = tk.StringVar(value="{width}x{height}")
        metadata_options = [
            "{width}x{height}",
            "{date_created}",
            "{date_modified}",
            "{file_size}",
            "{filename}"
        ]
        ttk.Combobox(self.settings_frame, textvariable=self.metadata_tag, values=metadata_options, 
                    state="readonly", width=30).pack(fill=tk.X, pady=2)
        
        ttk.Label(self.settings_frame, text="Позиция:").pack(anchor=tk.W, pady=(5, 0))
        self.metadata_pos = tk.StringVar(value="end")
        ttk.Radiobutton(self.settings_frame, text="В начале", variable=self.metadata_pos, value="start").pack(anchor=tk.W)
        ttk.Radiobutton(self.settings_frame, text="В конце", variable=self.metadata_pos, value="end").pack(anchor=tk.W)
    
    def create_regex_settings(self) -> None:
        """Создание настроек для метода Регулярные выражения."""
        ttk.Label(self.settings_frame, text="Регулярное выражение:").pack(anchor=tk.W)
        self.regex_pattern = ttk.Entry(self.settings_frame, width=30)
        self.regex_pattern.pack(fill=tk.X, pady=2)
        
        ttk.Label(self.settings_frame, text="Замена:").pack(anchor=tk.W, pady=(5, 0))
        self.regex_replace = ttk.Entry(self.settings_frame, width=30)
        self.regex_replace.pack(fill=tk.X, pady=2)
        
        btn_test = self.create_rounded_button(
            self.settings_frame, "Тест Regex", self.test_regex,
            '#818CF8', 'white',
            font=('Segoe UI', 9, 'bold'), padx=10, pady=6,
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
    
    def add_method(self):
        """Добавление метода в список применяемых"""
        method_name = self.method_var.get()
        
        try:
            if method_name == "Новое имя":
                template = self.new_name_template.get()
                if not template:
                    raise ValueError("Введите шаблон нового имени")
                method = NewNameMethod(
                    template=template,
                    metadata_extractor=self.metadata_extractor,
                    file_number=1
                )
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
            
            self.current_methods.append(method)
            self.methods_listbox.insert(tk.END, method_name)
            self.log(f"Добавлен метод: {method_name}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось добавить метод: {e}")
    
    def remove_method(self):
        """Удаление метода из списка"""
        selection = self.methods_listbox.curselection()
        if selection:
            index = selection[0]
            self.methods_listbox.delete(index)
            self.current_methods.pop(index)
            self.log(f"Удален метод: {index + 1}")
    
    def clear_methods(self):
        """Очистка всех методов"""
        if self.current_methods:
            if messagebox.askyesno("Подтверждение", "Очистить все методы?"):
                self.current_methods.clear()
                self.methods_listbox.delete(0, tk.END)
                self.log("Все методы очищены")
    
    def apply_methods(self):
        """Применение всех методов к файлам"""
        if not self.files:
            messagebox.showwarning("Предупреждение", "Нет файлов для обработки")
            return
        
        if not self.current_methods:
            messagebox.showwarning("Предупреждение", "Нет методов для применения")
            return
        
        # Сброс счетчиков нумерации перед применением
        for method in self.current_methods:
            if isinstance(method, NumberingMethod):
                method.reset()
            elif isinstance(method, NewNameMethod):
                method.reset()
        
        # Применение методов к каждому файлу
        for i, file_data in enumerate(self.files):
            new_name = file_data['old_name']
            extension = file_data['extension']
            
            # Применяем все методы последовательно
            for method in self.current_methods:
                try:
                    new_name, extension = method.apply(new_name, extension, file_data['full_path'])
                except Exception as e:
                    self.log(f"Ошибка при применении метода к {file_data['old_name']}: {e}")
            
            file_data['new_name'] = new_name
            file_data['extension'] = extension
            
            # Проверка на валидность имени
            status = self.validate_filename(new_name, extension, file_data['path'], i)
            file_data['status'] = status
            
            # Обновление в таблице
            item = self.tree.get_children()[i]
            self.tree.item(item, values=(
                file_data['old_name'],
                new_name,
                extension,
                file_data['path'],
                status
            ))
            
            # Цветовое выделение в зависимости от статуса
            if status == "Готов":
                self.tree.item(item, tags=('ready',))
            elif "Ошибка" in status or "Конфликт" in status:
                tag = 'error' if "Ошибка" in status else 'conflict'
                self.tree.item(item, tags=(tag,))
            else:
                self.tree.item(item, tags=('error',))
        
        # Проверка на конфликты
        self.check_conflicts()
        self.log(f"Методы применены к {len(self.files)} файлам")
    
    def validate_filename(self, name: str, extension: str, path: str, index: int) -> str:
        """Проверка валидности имени файла"""
        # Запрещенные символы
        forbidden = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        
        full_name = name + extension
        for char in forbidden:
            if char in full_name:
                return f"Ошибка: запрещенный символ '{char}'"
        
        # Проверка на пустое имя
        if not name.strip():
            return "Ошибка: пустое имя"
        
        # Проверка длины (Windows ограничение ~260 символов)
        full_path = os.path.join(path, full_name)
        if len(full_path) > 260:
            return "Ошибка: слишком длинный путь"
        
        return "Готов"
    
    def check_conflicts(self):
        """Проверка на конфликты имен (внутри списка и с существующими файлами)"""
        name_map = {}
        conflicts = []
        
        for i, file_data in enumerate(self.files):
            if file_data['status'] != "Готов":
                continue
            
            full_name = file_data['new_name'] + file_data['extension']
            full_path = os.path.join(file_data['path'], full_name)
            
            # Нормализация пути для сравнения
            full_path = os.path.normpath(full_path)
            
            # Проверка конфликта с другими файлами в списке
            if full_path in name_map:
                conflicts.append(i)
                conflicts.append(name_map[full_path])
            else:
                name_map[full_path] = i
            
            # Проверка конфликта с существующими файлами на диске
            # (только если новый путь отличается от исходного)
            old_path = file_data.get('full_path', '')
            if old_path != full_path and os.path.exists(full_path):
                conflicts.append(i)
                if full_path not in name_map:
                    name_map[full_path] = i
        
        # Выделение конфликтов
        conflict_set = set(conflicts)
        for conflict_index in conflict_set:
            if conflict_index < len(self.files):
                self.files[conflict_index]['status'] = "Конфликт имен"
                # Обновление в дереве
                children = self.tree.get_children()
                if conflict_index < len(children):
                    item = children[conflict_index]
                    self.tree.item(item, values=(
                        self.files[conflict_index]['old_name'],
                        self.files[conflict_index]['new_name'],
                        self.files[conflict_index]['extension'],
                        self.files[conflict_index]['path'],
                        "Конфликт имен"
                    ), tags=('conflict',))
        
        if conflicts:
            self.log(f"Обнаружено конфликтов имен: {len(conflict_set)}")
    
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
        thread = threading.Thread(
            target=self.rename_files_thread,
            args=(ready_files,)
        )
        thread.daemon = True
        thread.start()
    
    def rename_files_thread(self, files_to_rename: List[Dict]):
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
            except:
                pass
        
        for i, file_data in enumerate(files_to_rename):
            try:
                old_path = file_data['full_path']
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
                except:
                    pass
        
        # Обновление интерфейса
        self.root.after(0, lambda: self.rename_complete(success_count, error_count))
    
    def rename_complete(self, success: int, error: int):
        """Завершение переименования"""
        messagebox.showinfo("Завершено", f"Переименование завершено.\nУспешно: {success}\nОшибок: {error}")
        self.progress['value'] = 0
        # Синхронизация прогресс-бара в окне действий, если оно открыто
        if hasattr(self, 'progress_window') and self.progress_window is not None:
            try:
                self.progress_window['value'] = 0
            except:
                pass
        
        # Обновление списка файлов
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
    """Главная функция запуска приложения"""
    # Используем TkinterDnD если доступно
    if HAS_TKINTERDND2:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = FileRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

