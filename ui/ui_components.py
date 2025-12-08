"""Модуль для UI компонентов и стилей."""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Tuple


class UIComponents:
    """Класс для создания переиспользуемых UI компонентов."""
    
    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
        """Конвертация hex в RGB.
        
        Args:
            hex_color: Цвет в формате hex (например, "#FF0000")
            
        Returns:
            Кортеж (R, G, B) с значениями от 0 до 255
        """
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    @staticmethod
    def create_rounded_button(
        parent,
        text: str,
        command: Callable,
        bg_color: str,
        fg_color: str = 'white',
        font: Tuple[str, int, str] = ('Segoe UI', 10, 'bold'),
        padx: int = 16,
        pady: int = 10,
        active_bg: Optional[str] = None,
        active_fg: str = 'white',
        width: Optional[int] = None,
        expand: bool = True
    ) -> tk.Frame:
        """Создание кнопки с закругленными углами через Canvas.
        
        Args:
            parent: Родительский виджет
            text: Текст кнопки
            command: Функция-обработчик клика
            bg_color: Цвет фона
            fg_color: Цвет текста
            font: Шрифт (семейство, размер, стиль)
            padx: Горизонтальный отступ
            pady: Вертикальный отступ
            active_bg: Цвет фона при наведении
            active_fg: Цвет текста при наведении
            width: Ширина кнопки
            expand: Растягивать ли кнопку
            
        Returns:
            Фрейм с кнопкой
        """
        if active_bg is None:
            active_bg = bg_color
        
        # Проверка, что command передан
        if command is None:
            def empty_command():
                pass
            command = empty_command
        
        # Фрейм для кнопки
        btn_frame = tk.Frame(parent, bg=parent.cget('bg'))
        
        # Вычисляем ширину текста для компактных кнопок
        if not expand and width is None:
            temp_label = tk.Label(parent, text=text, font=font)
            temp_label.update_idletasks()
            text_width = temp_label.winfo_reqwidth()
            temp_label.destroy()
            width = text_width + padx * 2 + 10
        
        # Canvas для закругленного фона
        canvas_height = pady * 2 + 16
        canvas = tk.Canvas(
            btn_frame, 
            highlightthickness=0, 
            borderwidth=0,
            bg=parent.cget('bg'), 
            height=canvas_height,
            cursor='hand2'
        )
        
        if expand:
            canvas.pack(fill=tk.BOTH, expand=True)
        else:
            if width:
                canvas.config(width=width)
                btn_frame.config(width=width)
            canvas.pack(fill=tk.NONE, expand=False)
        
        # Сохраняем параметры
        canvas.btn_text = text
        canvas.btn_command = command
        # Проверяем, что команда передана
        if command is None:
            print("Предупреждение: команда кнопки не передана!")
        elif not callable(command):
            print(f"Предупреждение: команда кнопки не является вызываемой: {type(command)}")
        canvas.btn_bg = bg_color
        canvas.btn_fg = fg_color
        canvas.btn_active_bg = active_bg
        canvas.btn_active_fg = active_fg
        canvas.btn_font = font
        canvas.btn_state = 'normal'
        canvas.btn_width = width
        canvas.btn_expand = expand
        
        # Флаг для предотвращения бесконечных вызовов
        canvas._drawing = False
        canvas._pending_draw = None
        canvas._click_processing = False  # Флаг для предотвращения двойных кликов
        
        # Определяем обработчики событий сначала
        def on_click(e=None):
            # Защита от двойных кликов
            if canvas._click_processing:
                return
            canvas._click_processing = True
            try:
                # Проверяем, что команда существует и вызываем её
                if hasattr(canvas, 'btn_command') and canvas.btn_command:
                    # Вызываем команду без аргументов
                    if callable(canvas.btn_command):
                        canvas.btn_command()
                    else:
                        # Показываем ошибку пользователю
                        try:
                            import tkinter.messagebox as mb
                            mb.showerror("Ошибка", "Команда кнопки не является вызываемой функцией")
                        except Exception:
                            pass
                else:
                    # Показываем ошибку пользователю
                    try:
                        import tkinter.messagebox as mb
                        mb.showerror("Ошибка", "Команда кнопки не найдена")
                    except Exception:
                        pass
            except Exception as ex:
                # Логируем ошибку в файл, так как консоль может быть недоступна
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Ошибка при нажатии кнопки: {ex}", exc_info=True)
                # Также показываем сообщение пользователю
                try:
                    import tkinter.messagebox as mb
                    mb.showerror("Ошибка", f"Ошибка при выполнении команды кнопки:\n{ex}")
                except Exception:
                    pass
            finally:
                # Сбрасываем флаг после небольшой задержки (300мс)
                canvas.after(300, lambda: setattr(canvas, '_click_processing', False))
        
        def on_enter(e):
            if canvas.btn_state != 'active':
                canvas.btn_state = 'active'
                draw_button('active')
        
        def on_leave(e):
            if canvas.btn_state != 'normal':
                canvas.btn_state = 'normal'
                draw_button('normal')
        
        def on_configure(e):
            if not canvas.btn_expand and canvas.btn_width:
                if canvas.winfo_width() != canvas.btn_width:
                    canvas.config(width=canvas.btn_width)
                if btn_frame.winfo_width() != canvas.btn_width:
                    btn_frame.config(width=canvas.btn_width)
            draw_button(canvas.btn_state)
        
        def draw_button(state: str = 'normal'):
            # Защита от одновременных вызовов
            if canvas._drawing:
                return
            
            # Отменяем предыдущий отложенный вызов, если есть
            if canvas._pending_draw:
                try:
                    canvas.after_cancel(canvas._pending_draw)
                except (tk.TclError, ValueError):
                    pass
                canvas._pending_draw = None
            
            canvas._drawing = True
            try:
                canvas.delete('all')
                if canvas.btn_expand:
                    w = canvas.winfo_width()
                else:
                    w = canvas.btn_width if canvas.btn_width else canvas.winfo_width()
                h = canvas.winfo_height()
                
                if w <= 1 or h <= 1:
                    # Отложенный вызов с ограничением попыток
                    canvas._pending_draw = canvas.after(50, lambda: draw_button(state))
                    return
                
                if canvas.btn_expand and w < 50:
                    w = 50
                
                radius = 8
                color = canvas.btn_active_bg if state == 'active' else canvas.btn_bg
                text_color = canvas.btn_active_fg if state == 'active' else canvas.btn_fg
                
                # Конвертируем цвет в hex для Canvas
                if isinstance(color, tuple):
                    color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
                elif isinstance(color, str) and color.startswith('#'):
                    color_hex = color
                else:
                    # Если цвет не распознан, используем значение по умолчанию
                    try:
                        # Пробуем преобразовать в строку и использовать как есть
                        color_hex = str(color) if color else '#6366F1'
                        if not color_hex.startswith('#'):
                            color_hex = '#6366F1'
                    except Exception:
                        color_hex = '#6366F1'
                
                # Рисуем закругленный прямоугольник с тегом для привязки событий
                tag = 'button_item'
                canvas.create_arc(0, 0, radius*2, radius*2, start=90, extent=90, 
                                fill=color_hex, outline=color_hex, tags=tag)
                canvas.create_arc(w-radius*2, 0, w, radius*2, start=0, extent=90, 
                                fill=color_hex, outline=color_hex, tags=tag)
                canvas.create_arc(0, h-radius*2, radius*2, h, start=180, extent=90, 
                                fill=color_hex, outline=color_hex, tags=tag)
                canvas.create_arc(w-radius*2, h-radius*2, w, h, start=270, extent=90, 
                                fill=color_hex, outline=color_hex, tags=tag)
                canvas.create_rectangle(radius, 0, w-radius, h, fill=color_hex, outline=color_hex, tags=tag)
                canvas.create_rectangle(0, radius, w, h-radius, fill=color_hex, outline=color_hex, tags=tag)
                
                canvas.create_text(w//2, h//2, text=canvas.btn_text, 
                                 fill=text_color, font=canvas.btn_font, width=max(w-20, 50), tags=tag)
                
                # Привязываем события клика к элементам через тег
                # Это важно, чтобы клики на текст и фигуры тоже обрабатывались
                # Используем только Button-1, чтобы избежать двойных вызовов
                # Убираем старые привязки перед добавлением новых
                try:
                    canvas.tag_unbind(tag, '<Button-1>')
                except:
                    pass
                try:
                    canvas.tag_bind(tag, '<Button-1>', on_click)
                except Exception:
                    pass
            finally:
                canvas._drawing = False
        
        # Привязка событий мыши к canvas
        # Важно: привязываем только к canvas, чтобы избежать двойных вызовов
        # Убираем старую привязку перед добавлением новой
        try:
            canvas.unbind('<Button-1>')
        except:
            pass
        canvas.bind('<Button-1>', on_click)
        canvas.bind('<Enter>', on_enter)
        canvas.bind('<Leave>', on_leave)
        canvas.bind('<Configure>', on_configure)
        
        # Убеждаемся, что canvas может получать события
        canvas.update_idletasks()
        
        # Привязываем события после первой отрисовки
        canvas.after(50, lambda: draw_button('normal'))
        
        return btn_frame


class StyleManager:
    """Класс для управления стилями интерфейса."""
    
    def __init__(self):
        """Инициализация менеджера стилей."""
        self.style = ttk.Style()
        self.colors = self._get_color_scheme()
        self._setup_theme()
        self._setup_styles()
    
    def _get_color_scheme(self) -> dict:
        """Получение цветовой схемы."""
        return {
            'primary': '#667EEA',
            'primary_hover': '#5568D3',
            'primary_light': '#818CF8',
            'primary_dark': '#4C51BF',
            'success': '#10B981',
            'success_hover': '#059669',
            'danger': '#EF4444',
            'danger_hover': '#DC2626',
            'warning': '#F59E0B',
            'warning_hover': '#D97706',
            'info': '#3B82F6',
            'info_hover': '#2563EB',
            'bg_main': '#F5F7FA',
            'bg_card': '#FFFFFF',
            'bg_secondary': '#EDF2F7',
            'bg_hover': '#F7FAFC',
            'bg_input': '#FFFFFF',
            'bg_elevated': '#FFFFFF',
            'border': '#E2E8F0',
            'border_focus': '#667EEA',
            'border_light': '#F1F5F9',
            'text_primary': '#1A202C',
            'text_secondary': '#4A5568',
            'text_muted': '#718096',
            'header_bg': '#FFFFFF',
            'header_text': '#1A202C',
            'accent': '#9F7AEA',
            'shadow': 'rgba(0,0,0,0.08)',
            'shadow_lg': 'rgba(0,0,0,0.12)',
            'shadow_xl': 'rgba(0,0,0,0.16)',
            'glow': 'rgba(102, 126, 234, 0.4)',
            'gradient_start': '#667EEA',
            'gradient_end': '#764BA2'
        }
    
    def _setup_theme(self):
        """Настройка темы."""
        try:
            self.style.theme_use('vista')
        except Exception:
            try:
                self.style.theme_use('clam')
            except Exception:
                pass
    
    def _setup_styles(self):
        """Настройка стилей виджетов."""
        # Стиль для основных кнопок
        self.style.configure('Primary.TButton', 
                           background=self.colors['primary'],
                           foreground='white',
                           font=('Segoe UI', 10, 'bold'),
                           padding=(16, 10),
                           borderwidth=0,
                           focuscolor='none',
                           relief='flat',
                           anchor='center')
        self.style.map('Primary.TButton',
                     background=[('active', self.colors['primary_hover']), 
                               ('pressed', self.colors['primary_dark']),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'), 
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для кнопок успеха
        self.style.configure('Success.TButton',
                           background=self.colors['success'],
                           foreground='white',
                           font=('Segoe UI', 9, 'bold'),
                           padding=(10, 6),
                           borderwidth=0,
                           focuscolor='none',
                           relief='flat',
                           anchor='center')
        self.style.map('Success.TButton',
                     background=[('active', self.colors['success_hover']), 
                               ('pressed', '#047857'),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'), 
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для кнопок опасности
        self.style.configure('Danger.TButton',
                           background=self.colors['danger'],
                           foreground='white',
                           font=('Segoe UI', 9, 'bold'),
                           padding=(10, 6),
                           borderwidth=0,
                           focuscolor='none',
                           relief='flat',
                           anchor='center')
        self.style.map('Danger.TButton',
                     background=[('active', self.colors['danger_hover']), 
                               ('pressed', '#B91C1C'),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'), 
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для обычных кнопок
        self.style.configure('TButton',
                           font=('Segoe UI', 9, 'bold'),
                           padding=(10, 6),
                           borderwidth=0,
                           relief='flat',
                           background='#F59E0B',
                           foreground='white',
                           anchor='center')
        self.style.map('TButton',
                     background=[('active', '#D97706'), 
                               ('pressed', '#B45309'),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'),
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для вторичных кнопок
        self.style.configure('Secondary.TButton',
                           font=('Segoe UI', 9, 'bold'),
                           padding=(10, 6),
                           borderwidth=0,
                           relief='flat',
                           background='#818CF8',
                           foreground='white',
                           anchor='center')
        self.style.map('Secondary.TButton',
                     background=[('active', '#6366F1'), 
                               ('pressed', '#4F46E5'),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'),
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для предупреждающих кнопок
        self.style.configure('Warning.TButton',
                           font=('Segoe UI', 9, 'bold'),
                           padding=(10, 6),
                           borderwidth=0,
                           relief='flat',
                           background='#F59E0B',
                           foreground='white',
                           anchor='center')
        self.style.map('Warning.TButton',
                     background=[('active', '#D97706'), 
                               ('pressed', '#B45309'),
                               ('disabled', '#94A3B8')],
                     foreground=[('active', 'white'),
                              ('pressed', 'white'),
                              ('disabled', '#E2E8F0')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Стиль для LabelFrame
        self.style.configure('Card.TLabelframe', 
                           background=self.colors['bg_card'],
                           borderwidth=0,
                           relief='flat',
                           bordercolor=self.colors['border'],
                           padding=24)
        self.style.configure('Card.TLabelframe.Label',
                           background=self.colors['bg_card'],
                           foreground=self.colors['text_primary'],
                           font=('Segoe UI', 11, 'bold'),
                           padding=(0, 0, 0, 12))
        
        # Стиль для PanedWindow
        self.style.configure('TPanedwindow',
                           background=self.colors['bg_main'])
        self.style.configure('TPanedwindow.Sash',
                           sashthickness=6,
                           sashrelief='flat',
                           sashpad=0)
        self.style.map('TPanedwindow.Sash',
                     background=[('hover', self.colors['primary_light']),
                               ('active', self.colors['primary'])])
        
        # Стиль для меток
        self.style.configure('TLabel',
                           background=self.colors['bg_card'],
                           foreground=self.colors['text_primary'],
                           font=('Segoe UI', 9))
        
        # Стиль для Frame
        self.style.configure('TFrame',
                           background=self.colors['bg_main'])
        
        # Стиль для Notebook
        self.style.configure('TNotebook',
                           background=self.colors['bg_main'],
                           borderwidth=0)
        self.style.configure('TNotebook.Tab',
                           padding=(14, 8),
                           font=('Segoe UI', 9, 'bold'),
                           background=self.colors['bg_secondary'],
                           foreground=self.colors['text_secondary'])
        self.style.map('TNotebook.Tab',
                     background=[('selected', self.colors['bg_card']),
                               ('active', self.colors['bg_hover'])],
                     foreground=[('selected', self.colors['text_primary']),
                               ('active', self.colors['text_primary'])],
                     expand=[('selected', [1, 1, 1, 0])])
        
        # Стиль для Radiobutton
        self.style.configure('TRadiobutton',
                           background=self.colors['bg_card'],
                           foreground=self.colors['text_primary'],
                           font=('Segoe UI', 9),
                           selectcolor='white')
        
        # Стиль для Checkbutton
        self.style.configure('TCheckbutton',
                           background=self.colors['bg_card'],
                           foreground=self.colors['text_primary'],
                           font=('Segoe UI', 9),
                           selectcolor='white')
        
        # Стиль для Entry
        self.style.configure('TEntry',
                           fieldbackground=self.colors['bg_input'],
                           foreground=self.colors['text_primary'],
                           borderwidth=2,
                           relief='flat',
                           padding=10,
                           font=('Segoe UI', 10))
        self.style.map('TEntry',
                     bordercolor=[('focus', self.colors['border_focus']),
                                ('!focus', self.colors['border'])],
                     lightcolor=[('focus', self.colors['border_focus']),
                               ('!focus', self.colors['border'])],
                     darkcolor=[('focus', self.colors['border_focus']),
                              ('!focus', self.colors['border'])])
        
        # Стиль для Combobox
        self.style.configure('TCombobox',
                           fieldbackground=self.colors['bg_input'],
                           foreground=self.colors['text_primary'],
                           borderwidth=2,
                           relief='flat',
                           padding=10,
                           font=('Segoe UI', 10))
        self.style.map('TCombobox',
                     bordercolor=[('focus', self.colors['border_focus']),
                                ('!focus', self.colors['border'])],
                     selectbackground=[('focus', self.colors['bg_input'])],
                     selectforeground=[('focus', self.colors['text_primary'])])
        
        # Стиль для Treeview
        self.style.configure('Custom.Treeview',
                           rowheight=40,
                           font=('Segoe UI', 10),
                           background=self.colors['bg_card'],
                           foreground=self.colors['text_primary'],
                           fieldbackground=self.colors['bg_card'],
                           borderwidth=0)
        self.style.configure('Custom.Treeview.Heading',
                           font=('Segoe UI', 10, 'bold'),
                           background=self.colors['bg_secondary'],
                           foreground=self.colors['text_primary'],
                           borderwidth=0,
                           relief='flat',
                           padding=(12, 10))
        self.style.map('Custom.Treeview.Heading',
                     background=[('active', self.colors['bg_hover'])])
        self.style.map('Custom.Treeview',
                     background=[('selected', self.colors['primary'])],
                     foreground=[('selected', 'white')])

