"""Модуль для работы с логированием."""

import logging
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Optional

# Настройка логирования для модуля
module_logger = logging.getLogger(__name__)


class Logger:
    """Класс для управления логированием."""
    
    def __init__(self, log_text_widget: Optional[tk.Text] = None):
        """Инициализация логгера.
        
        Args:
            log_text_widget: Виджет Text для отображения лога (опционально)
        """
        self.log_text = log_text_widget
    
    def set_log_widget(self, log_text_widget: tk.Text):
        """Установка виджета для логирования.
        
        Args:
            log_text_widget: Виджет Text для отображения лога
        """
        self.log_text = log_text_widget
    
    def log(self, message: str) -> None:
        """Добавление сообщения в лог.
        
        Args:
            message: Сообщение для логирования
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        
        # Выводим в консоль для отладки
        print(log_message.strip())
        
        # Добавляем в лог, если виджет доступен
        if self.log_text is not None:
            try:
                self.log_text.insert(tk.END, log_message)
                self.log_text.see(tk.END)
            except tk.TclError:
                # Окно было закрыто
                self.log_text = None
    
    def clear(self) -> None:
        """Очистка лога операций."""
        if self.log_text is not None:
            try:
                self.log_text.delete(1.0, tk.END)
                self.log("Лог очищен")
            except tk.TclError:
                self.log_text = None
    
    def save(self) -> None:
        """Сохранение/выгрузка лога в файл."""
        if self.log_text is None:
            messagebox.showwarning("Предупреждение", "Окно лога не открыто.")
            return
        
        try:
            log_content = self.log_text.get(1.0, tk.END)
            if not log_content.strip():
                messagebox.showwarning("Предупреждение", "Лог пуст, нечего сохранять.")
                return
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[
                    ("Текстовые файлы", "*.txt"),
                    ("Лог файлы", "*.log"),
                    ("Все файлы", "*.*")
                ],
                title="Выгрузить лог"
            )
            
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("Успех", f"Лог успешно выгружен в файл:\n{filename}")
                self.log(f"Лог выгружен в файл: {filename}")
        except Exception as e:
            module_logger.error(f"Не удалось выгрузить лог: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось выгрузить лог:\n{str(e)}")

