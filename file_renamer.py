import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
        
        # Инициализация модуля метаданных
        self.metadata_extractor = MetadataExtractor()
        
        # Создание интерфейса
        self.create_widgets()
        
        # Привязка горячих клавиш
        self.setup_hotkeys()
    
    def setup_styles(self) -> None:
        """Настройка современных стилей интерфейса."""
        style = ttk.Style()
        
        # Используем современную тему
        try:
            style.theme_use('vista')  # Windows Vista/7 стиль
        except Exception:
            try:
                style.theme_use('clam')  # Альтернативный стиль
            except Exception:
                pass
        
        # Современная цветовая схема
        self.colors = {
            'primary': '#6366F1',      # Индиго (современный синий)
            'primary_hover': '#4F46E5',
            'primary_light': '#818CF8',
            'success': '#10B981',      # Изумрудный зеленый
            'success_hover': '#059669',
            'warning': '#F59E0B',      # Янтарный
            'danger': '#EF4444',       # Красный
            'danger_hover': '#DC2626',
            'bg_main': '#F8FAFC',      # Светло-серый основной фон
            'bg_secondary': '#F1F5F9', # Еще светлее
            'bg_card': '#FFFFFF',      # Белый фон карточек
            'bg_hover': '#F1F5F9',     # Фон при наведении
            'bg_input': '#FFFFFF',     # Фон полей ввода
            'border': '#E2E8F0',       # Светло-серый цвет границ
            'border_focus': '#6366F1',  # Синяя рамка при фокусе
            'text_primary': '#1E293B', # Темно-синий основной текст
            'text_secondary': '#64748B', # Серый вторичный текст
            'text_muted': '#94A3B8',   # Приглушенный текст
            'header_bg': '#1E293B',    # Темно-синий фон заголовка
            'header_text': '#FFFFFF',  # Белый текст в заголовке
            'accent': '#8B5CF6',       # Фиолетовый акцент
            'shadow': '#E2E8F0'        # Цвет тени
        }
        
        # Настройка стилей кнопок - современный дизайн с четким текстом
        style.configure('Primary.TButton', 
                       background=self.colors['primary'],
                       foreground='white',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(16, 10),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Primary.TButton',
                 background=[('active', self.colors['primary_hover']), 
                           ('pressed', self.colors['primary_hover']),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        style.configure('Success.TButton',
                       background=self.colors['success'],
                       foreground='white',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(16, 10),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Success.TButton',
                 background=[('active', self.colors['success_hover']), 
                           ('pressed', self.colors['success_hover']),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        style.configure('Danger.TButton',
                       background=self.colors['danger'],
                       foreground='white',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(14, 9),
                       borderwidth=0,
                       focuscolor='none',
                       relief='flat',
                       anchor='center')
        style.map('Danger.TButton',
                 background=[('active', self.colors['danger_hover']), 
                           ('pressed', self.colors['danger_hover']),
                           ('disabled', '#94A3B8')],
                 foreground=[('active', 'white'), 
                          ('pressed', 'white'),
                          ('disabled', '#E2E8F0')],
                 relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для обычных кнопок - цветной (оранжевый/янтарный)
        style.configure('TButton',
                       font=('Segoe UI', 9, 'bold'),
                       padding=(14, 9),
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
                       padding=(14, 9),
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
                       padding=(14, 9),
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
        
        # Стиль для LabelFrame - карточки с тенью
        style.configure('Card.TLabelframe', 
                       background=self.colors['bg_card'],
                       borderwidth=1,
                       relief='flat',
                       bordercolor=self.colors['border'],
                       padding=20)
        style.configure('Card.TLabelframe.Label',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 12, 'bold'))
        
        # Стиль для обычных меток
        style.configure('TLabel',
                       background=self.colors['bg_card'],
                       foreground=self.colors['text_primary'],
                       font=('Segoe UI', 9))
        
        # Стиль для Frame
        style.configure('TFrame',
                       background=self.colors['bg_main'])
        
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
                       padding=10,
                       font=('Segoe UI', 10))
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
                       padding=10,
                       font=('Segoe UI', 10))
        style.map('TCombobox',
                 bordercolor=[('focus', self.colors['border_focus']),
                            ('!focus', self.colors['border'])],
                 selectbackground=[('focus', 'white')],
                 selectforeground=[('focus', self.colors['text_primary'])])
        
        # Стиль для Treeview - современная таблица
        style.configure('Custom.Treeview',
                       rowheight=32,
                       font=('Segoe UI', 10),
                       background='white',
                       foreground=self.colors['text_primary'],
                       fieldbackground='white',
                       borderwidth=0)
        style.configure('Custom.Treeview.Heading',
                       font=('Segoe UI', 10, 'bold'),
                       background=self.colors['bg_secondary'],
                       foreground=self.colors['text_primary'],
                       borderwidth=1,
                       relief='flat')
        style.map('Custom.Treeview.Heading',
                 background=[('active', self.colors['bg_hover'])])
        
        # Настройка фона окна
        self.root.configure(bg=self.colors['bg_main'])
        
        # Привязка изменения размера окна
        self.root.bind('<Configure>', self.on_window_resize)
    
    def create_widgets(self):
        """Создание всех виджетов интерфейса"""
        
        # === ЗАГОЛОВОК ===
        header_frame = tk.Frame(self.root, bg=self.colors['header_bg'], height=70)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        header_content = tk.Frame(header_frame, bg=self.colors['header_bg'])
        header_content.pack(fill=tk.BOTH, expand=True, padx=25, pady=15)
        
        # Заголовок слева
        title_label = tk.Label(header_content, text="📝 Назови", 
                              font=('Segoe UI', 24, 'bold'),
                              bg=self.colors['header_bg'],
                              fg=self.colors['header_text'])
        title_label.pack(side=tk.LEFT)
        
        # Статус справа
        status_container = tk.Frame(header_content, bg=self.colors['header_bg'])
        status_container.pack(side=tk.RIGHT)
        
        self.status_label = tk.Label(status_container, text=f"📊 Файлов: {len(self.files)}", 
                                     font=('Segoe UI', 12, 'bold'),
                                     bg=self.colors['header_bg'],
                                     fg=self.colors['header_text'])
        self.status_label.pack()
        
        # === ОСНОВНОЙ КОНТЕЙНЕР ===
        main_container = tk.Frame(self.root, bg=self.colors['bg_main'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=25, pady=25)
        
        # Левая часть - список файлов
        left_panel = ttk.LabelFrame(main_container, text="📋 Список файлов", 
                                    style='Card.TLabelframe', padding=20)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 20))
        
        
        # Панель управления файлами
        control_panel = tk.Frame(left_panel, bg=self.colors['bg_card'])
        control_panel.pack(fill=tk.X, pady=(0, 15))
        
        # Кнопки управления - адаптивные с правильным отображением текста (цветные)
        btn_add_files = tk.Button(control_panel, text="📁 Добавить файлы", 
                                  command=self.add_files,
                                  bg=self.colors['primary'],
                                  fg='white',
                                  font=('Segoe UI', 10, 'bold'),
                                  relief='flat',
                                  borderwidth=0,
                                  padx=16, pady=10,
                                  cursor='hand2',
                                  activebackground=self.colors['primary_hover'],
                                  activeforeground='white')
        btn_add_files.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        btn_add_folder = tk.Button(control_panel, text="📂 Добавить папку", 
                                   command=self.add_folder,
                                   bg=self.colors['primary'],
                                   fg='white',
                                   font=('Segoe UI', 10, 'bold'),
                                   relief='flat',
                                   borderwidth=0,
                                   padx=16, pady=10,
                                   cursor='hand2',
                                   activebackground=self.colors['primary_hover'],
                                   activeforeground='white')
        btn_add_folder.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        btn_clear = tk.Button(control_panel, text="🗑️ Очистить", 
                              command=self.clear_files,
                              bg=self.colors['danger'],
                              fg='white',
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              borderwidth=0,
                              padx=14, pady=9,
                              cursor='hand2',
                              activebackground=self.colors['danger_hover'],
                              activeforeground='white')
        btn_clear.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        btn_undo = tk.Button(control_panel, text="↶ Отменить", 
                             command=self.undo_rename,
                             bg='#818CF8',
                             fg='white',
                             font=('Segoe UI', 9, 'bold'),
                             relief='flat',
                             borderwidth=0,
                             padx=14, pady=9,
                             cursor='hand2',
                             activebackground='#6366F1',
                             activeforeground='white')
        btn_undo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
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
        
        self.tree.column("old_name", width=220, anchor='w')
        self.tree.column("new_name", width=220, anchor='w')
        self.tree.column("extension", width=90, anchor='center')
        self.tree.column("path", width=300, anchor='w')
        self.tree.column("status", width=120, anchor='center')
        
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
        
        # === ПАНЕЛЬ МЕТОДОВ ПЕРЕИМЕНОВАНИЯ (справа) ===
        right_panel = ttk.LabelFrame(main_container, text="⚙️ Методы переименования", 
                                     style='Card.TLabelframe', padding=20)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(20, 0))
        right_panel.configure(width=420)
        
        
        methods_frame = right_panel
        
        # Выбор метода
        method_label = tk.Label(methods_frame, text="🔧 Выберите метод:", 
                               font=('Segoe UI', 11, 'bold'),
                               bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        method_label.pack(anchor=tk.W, pady=(0, 10))
        
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
            font=('Segoe UI', 10)
        )
        self.method_combo.pack(fill=tk.X, pady=(0, 15))
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
        
        btn_add_method = tk.Button(method_buttons_frame, text="➕ Добавить", 
                                    command=self.add_method,
                                    bg=self.colors['primary'],
                                    fg='white',
                                    font=('Segoe UI', 10, 'bold'),
                                    relief='flat',
                                    borderwidth=0,
                                    padx=14, pady=9,
                                    cursor='hand2',
                                    activebackground=self.colors['primary_hover'],
                                    activeforeground='white')
        btn_add_method.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        btn_remove_method = tk.Button(method_buttons_frame, text="➖ Удалить", 
                                       command=self.remove_method,
                                       bg='#818CF8',
                                       fg='white',
                                       font=('Segoe UI', 9, 'bold'),
                                       relief='flat',
                                       borderwidth=0,
                                       padx=14, pady=9,
                                       cursor='hand2',
                                       activebackground='#6366F1',
                                       activeforeground='white')
        btn_remove_method.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        btn_clear_methods = tk.Button(method_buttons_frame, text="🗑️ Очистить", 
                                       command=self.clear_methods,
                                       bg=self.colors['danger'],
                                       fg='white',
                                       font=('Segoe UI', 10, 'bold'),
                                       relief='flat',
                                       borderwidth=0,
                                       padx=14, pady=9,
                                       cursor='hand2',
                                       activebackground=self.colors['danger_hover'],
                                       activeforeground='white')
        btn_clear_methods.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        
        # Список примененных методов
        applied_label = tk.Label(methods_frame, text="📝 Примененные методы:", 
                                font=('Segoe UI', 11, 'bold'),
                                bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        applied_label.pack(anchor=tk.W, pady=(0, 10))
        
        listbox_frame = tk.Frame(methods_frame, bg=self.colors['bg_card'], 
                                relief='flat', borderwidth=1,
                                highlightbackground=self.colors['border'],
                                highlightthickness=1)
        listbox_frame.pack(fill=tk.X, pady=(0, 0))
        
        self.methods_listbox = tk.Listbox(listbox_frame, height=5, 
                                         font=('Segoe UI', 10),
                                         relief='flat', borderwidth=0,
                                         bg='white', fg=self.colors['text_primary'],
                                         selectbackground=self.colors['primary'],
                                         selectforeground='white',
                                         highlightthickness=0)
        self.methods_listbox.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # === ПАНЕЛЬ ДЕЙСТВИЙ (внизу) ===
        action_frame = ttk.LabelFrame(self.root, text="🚀 Действия", 
                                     style='Card.TLabelframe', padding=20)
        action_frame.pack(fill=tk.X, padx=25, pady=(0, 25))
        
        
        buttons_frame = tk.Frame(action_frame, bg=self.colors['bg_card'])
        buttons_frame.pack(fill=tk.X, pady=(0, 15))
        
        btn_apply = tk.Button(buttons_frame, text="✨ Применить метод", 
                              command=self.apply_methods,
                              bg=self.colors['primary'],
                              fg='white',
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              borderwidth=0,
                              padx=18, pady=11,
                              cursor='hand2',
                              activebackground=self.colors['primary_hover'],
                              activeforeground='white')
        btn_apply.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        
        btn_start = tk.Button(buttons_frame, text="▶️ Начать переименование", 
                              command=self.start_rename,
                              bg=self.colors['success'],
                              fg='white',
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              borderwidth=0,
                              padx=18, pady=11,
                              cursor='hand2',
                              activebackground=self.colors['success_hover'],
                              activeforeground='white')
        btn_start.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)
        
        # Прогресс бар
        progress_container = tk.Frame(action_frame, bg=self.colors['bg_card'])
        progress_container.pack(fill=tk.X, pady=(0, 15))
        
        progress_label = tk.Label(progress_container, text="Прогресс:", 
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        progress_label.pack(anchor=tk.W, pady=(0, 8))
        
        self.progress = ttk.Progressbar(progress_container, mode='determinate')
        self.progress.pack(fill=tk.X)
        
        # Лог операций
        log_frame = tk.Frame(action_frame, bg=self.colors['bg_card'])
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        log_label = tk.Label(log_frame, text="📋 Лог операций:", 
                            font=('Segoe UI', 11, 'bold'),
                            bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        log_label.pack(anchor=tk.W, pady=(0, 10))
        
        log_container = tk.Frame(log_frame, bg=self.colors['bg_card'], 
                                relief='flat', borderwidth=1,
                                highlightbackground=self.colors['border'],
                                highlightthickness=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        log_scroll = ttk.Scrollbar(log_container, orient=tk.VERTICAL)
        self.log_text = tk.Text(log_container, height=8, yscrollcommand=log_scroll.set,
                               font=('Consolas', 10),
                               bg='white', fg=self.colors['text_primary'],
                               relief='flat', borderwidth=0,
                               padx=12, pady=10,
                               wrap=tk.WORD)
        log_scroll.config(command=self.log_text.yview)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Инициализация первого метода (Новое имя)
        self.on_method_selected()
    
    def on_window_resize(self, event=None) -> None:
        """Обработка изменения размера окна.
        
        Args:
            event: Событие изменения размера (опционально)
        """
        if event and event.widget == self.root:
            # Обновление размеров колонок таблицы при изменении размера окна
            try:
                width = self.root.winfo_width()
                if width > 100:
                    # Адаптивная ширина колонок
                    tree_width = width - 600  # Учитываем правую панель и отступы
                    if tree_width > 400:
                        self.tree.column("old_name", width=int(tree_width * 0.3))
                        self.tree.column("new_name", width=int(tree_width * 0.3))
                        self.tree.column("path", width=int(tree_width * 0.25))
            except Exception:
                pass
    
    def switch_tab(self, tab_name):
        """Переключение вкладок"""
        self.current_tab.set(tab_name)
        # Обновление визуального состояния вкладок
        for name, tab_widget in self.tabs.items():
            if name == tab_name:
                tab_widget.config(fg=self.colors['tab_active'])
            else:
                tab_widget.config(fg=self.colors['tab_inactive'])
    
    def setup_hotkeys(self):
        """Настройка горячих клавиш"""
        self.root.bind('<Control-a>', lambda e: self.add_files())
        self.root.bind('<Control-z>', lambda e: self.undo_rename())
        self.root.bind('<Delete>', lambda e: self.delete_selected())
        self.root.bind('<Control-o>', lambda e: self.add_folder())
    
    def log(self, message: str):
        """Добавление сообщения в лог"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
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
                    file_path = os.path.join(root_dir, file)
                    self.add_file(file_path)
                    count += 1
            self.update_status()
            self.log(f"Добавлено файлов из папки: {count}")
    
    def add_file(self, file_path: str):
        """Добавление одного файла в список"""
        if not os.path.isfile(file_path):
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
        
        btn_quick = tk.Button(quick_frame, text="📋 Быстрые шаблоны", 
                              command=self.show_quick_templates,
                              bg=self.colors['primary'],
                              fg='white',
                              font=('Segoe UI', 10, 'bold'),
                              relief='flat',
                              borderwidth=0,
                              padx=18, pady=11,
                              cursor='hand2',
                              activebackground=self.colors['primary_hover'],
                              activeforeground='white')
        btn_quick.pack(fill=tk.X)
        
        # Поле ввода шаблона
        template_label = tk.Label(self.settings_frame, text="✏️ Новое имя (шаблон):", 
                                 font=('Segoe UI', 10, 'bold'),
                                 bg=self.colors['bg_card'], fg=self.colors['text_primary'])
        template_label.pack(anchor=tk.W, pady=(0, 10))
        
        self.new_name_template = ttk.Entry(self.settings_frame, width=30, font=('Segoe UI', 10))
        self.new_name_template.pack(fill=tk.X, pady=(0, 12))
        
        # Кнопка применения шаблона
        apply_template_btn = tk.Button(self.settings_frame, 
                                      text="✅ Применить шаблон", 
                                      command=self.apply_template_quick,
                                      bg=self.colors['success'],
                                      fg='white',
                                      font=('Segoe UI', 10, 'bold'),
                                      relief='flat',
                                      borderwidth=0,
                                      padx=18, pady=11,
                                      cursor='hand2',
                                      activebackground=self.colors['success_hover'],
                                      activeforeground='white')
        apply_template_btn.pack(fill=tk.X, pady=(0, 15))
        
        # Предупреждение
        warning_frame = tk.Frame(self.settings_frame, bg='#FEF3C7', 
                                relief='flat', borderwidth=1,
                                highlightbackground='#FCD34D',
                                highlightthickness=1)
        warning_frame.pack(fill=tk.X, pady=(0, 15))
        
        warning_label = tk.Label(warning_frame, text="⚠ БЕЗ {name} - имя полностью заменяется!", 
                               font=('Segoe UI', 9, 'bold'),
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
                                 font=('Segoe UI', 9),
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
        
        btn_select = tk.Button(btn_frame, text="Выбрать", 
                               command=select_template,
                               bg=self.colors['primary'],
                               fg='white',
                               font=('Segoe UI', 10, 'bold'),
                               relief='flat',
                               borderwidth=0,
                               padx=14, pady=9,
                               cursor='hand2',
                               activebackground=self.colors['primary_hover'],
                               activeforeground='white')
        btn_select.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        btn_cancel = tk.Button(btn_frame, text="Отмена", 
                               command=template_window.destroy,
                               bg='#818CF8',
                               fg='white',
                               font=('Segoe UI', 9, 'bold'),
                               relief='flat',
                               borderwidth=0,
                               padx=14, pady=9,
                               cursor='hand2',
                               activebackground='#6366F1',
                               activeforeground='white')
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
        
        btn_test = tk.Button(self.settings_frame, text="Тест Regex", 
                             command=self.test_regex,
                             bg='#818CF8',
                             fg='white',
                             font=('Segoe UI', 9, 'bold'),
                             relief='flat',
                             borderwidth=0,
                             padx=14, pady=9,
                             cursor='hand2',
                             activebackground='#6366F1',
                             activeforeground='white')
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
        
        # Обновление интерфейса
        self.root.after(0, lambda: self.rename_complete(success_count, error_count))
    
    def rename_complete(self, success: int, error: int):
        """Завершение переименования"""
        messagebox.showinfo("Завершено", f"Переименование завершено.\nУспешно: {success}\nОшибок: {error}")
        self.progress['value'] = 0
        
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
    root = tk.Tk()
    app = FileRenamerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

