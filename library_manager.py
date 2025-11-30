"""Модуль для управления установкой библиотек."""

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Dict, Callable, Optional


class LibraryManager:
    """Класс для управления установкой библиотек."""
    
    REQUIRED_LIBRARIES = {
        'Pillow': 'PIL',
        'tkinterdnd2': 'tkinterdnd2',
    }
    
    def __init__(self, root: tk.Tk, log_callback: Optional[Callable[[str], None]] = None):
        """Инициализация менеджера библиотек.
        
        Args:
            root: Корневое окно Tkinter
            log_callback: Функция для логирования сообщений
        """
        self.root = root
        self.log = log_callback or (lambda msg: print(msg))
        self.libs_check_file = os.path.join(
            os.path.expanduser("~"), ".nazovi_libs_installed.json"
        )
    
    def check_libraries(self) -> List[str]:
        """Проверка наличия необходимых библиотек.
        
        Returns:
            Список отсутствующих библиотек
        """
        missing_libraries = []
        
        for lib_name, import_name in self.REQUIRED_LIBRARIES.items():
            try:
                __import__(import_name)
            except ImportError:
                missing_libraries.append(lib_name)
            except Exception as e:
                if "ImportError" in str(type(e)) or "ModuleNotFoundError" in str(type(e)):
                    missing_libraries.append(lib_name)
                else:
                    self.log(f"Предупреждение при проверке {lib_name}: {str(e)[:100]}")
                    missing_libraries.append(lib_name)
        
        return missing_libraries
    
    def get_installed_libraries(self) -> List[str]:
        """Получение списка ранее установленных библиотек.
        
        Returns:
            Список установленных библиотек
        """
        try:
            if os.path.exists(self.libs_check_file):
                with open(self.libs_check_file, 'r', encoding='utf-8') as f:
                    installed_data = json.load(f)
                    return installed_data.get('installed', [])
        except Exception:
            pass
        return []
    
    def save_installed_libraries(self, libraries: List[str]):
        """Сохранение списка установленных библиотек.
        
        Args:
            libraries: Список установленных библиотек
        """
        try:
            installed_data = {'installed': libraries}
            with open(self.libs_check_file, 'w', encoding='utf-8') as f:
                json.dump(installed_data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def check_and_install(self):
        """Проверка и автоматическая установка необходимых библиотек."""
        try:
            missing_libraries = self.check_libraries()
            
            if not missing_libraries:
                return
            
            installed_libs = self.get_installed_libraries()
            libs_to_install = [lib for lib in missing_libraries if lib not in installed_libs]
            
            if libs_to_install:
                self._show_install_window(libs_to_install)
            else:
                try:
                    messagebox.showinfo(
                        "Требуется перезапуск",
                        f"Библиотеки {', '.join(missing_libraries)} были установлены ранее.\n"
                        f"Пожалуйста, перезапустите программу для их загрузки."
                    )
                except:
                    pass
        except Exception as e:
            self.log(f"Ошибка при проверке библиотек: {str(e)}")
    
    def _show_install_window(self, libraries: List[str]):
        """Показ окна установки библиотек.
        
        Args:
            libraries: Список библиотек для установки
        """
        install_window = tk.Toplevel(self.root)
        install_window.title("Установка библиотек")
        install_window.geometry("600x200")
        install_window.transient(self.root)
        install_window.grab_set()
        
        # Центрируем окно
        install_window.update_idletasks()
        x = (install_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (install_window.winfo_screenheight() // 2) - (200 // 2)
        install_window.geometry(f"600x200+{x}+{y}")
        
        info_label = tk.Label(
            install_window,
            text=f"Установка необходимых библиотек:\n{', '.join(libraries)}\n\n"
                 f"Это займет некоторое время...",
            font=('Segoe UI', 10),
            justify=tk.LEFT,
            pady=20
        )
        info_label.pack(pady=20)
        
        install_window.update()
        
        self.install_libraries_auto(libraries, install_window)
    
    def install_libraries_auto(self, libraries: List[str], parent_window: tk.Toplevel):
        """Автоматическая установка библиотек.
        
        Args:
            libraries: Список библиотек для установки
            parent_window: Родительское окно
        """
        progress_window = tk.Toplevel(parent_window)
        progress_window.title("Установка библиотек")
        progress_window.geometry("600x300")
        progress_window.transient(parent_window)
        progress_window.grab_set()
        
        # Центрируем окно
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (600 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (300 // 2)
        progress_window.geometry(f"600x300+{x}+{y}")
        
        status_label = tk.Label(
            progress_window,
            text="Установка библиотек...",
            font=('Segoe UI', 11, 'bold'),
            pady=15
        )
        status_label.pack()
        
        progress_text = tk.Text(
            progress_window,
            height=10,
            wrap=tk.WORD,
            font=('Consolas', 9),
            bg='#f0f0f0'
        )
        progress_text.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        
        progress_bar = ttk.Progressbar(
            progress_window,
            mode='indeterminate',
            length=550
        )
        progress_bar.pack(pady=10)
        progress_bar.start()
        
        installed_libs = []
        
        def install_thread():
            """Установка библиотек в отдельном потоке."""
            nonlocal installed_libs
            success_count = 0
            error_count = 0
            
            # Проверяем доступность pip
            try:
                self.root.after(0, lambda: progress_text.insert(tk.END, "Проверка доступности pip...\n"))
                check_pip = subprocess.run(
                    [sys.executable, '-m', 'pip', '--version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if check_pip.returncode != 0:
                    self.root.after(0, lambda: progress_text.insert(tk.END, "✗ pip не доступен. Установите pip вручную.\n"))
                    self.root.after(0, lambda: progress_bar.stop())
                    self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
                    return
                else:
                    pip_version = check_pip.stdout.strip() if check_pip.stdout else "доступен"
                    self.root.after(0, lambda v=pip_version: progress_text.insert(tk.END, f"✓ pip {v}\n"))
            except Exception as e:
                self.root.after(0, lambda: progress_text.insert(tk.END, f"✗ Ошибка проверки pip: {str(e)}\n"))
                self.root.after(0, lambda: progress_bar.stop())
                self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
                return
            
            for lib in libraries:
                try:
                    self.root.after(0, lambda l=lib: status_label.config(text=f"Установка {l}..."))
                    self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"Установка {l}...\n"))
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
                    
                    result = subprocess.run(
                        [sys.executable, '-m', 'pip', 'install', lib, '--user', '--upgrade'],
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    
                    if result.returncode == 0:
                        self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"✓ {l} установлен успешно\n"))
                        success_count += 1
                        installed_libs.append(lib)
                    else:
                        error_msg = result.stderr if result.stderr else result.stdout or f"Код возврата: {result.returncode}"
                        error_display = error_msg[:300] if len(error_msg) > 300 else error_msg
                        self.root.after(0, lambda l=lib, e=error_display: progress_text.insert(tk.END, f"✗ Ошибка установки {l}:\n{e}\n"))
                        error_count += 1
                        try:
                            self.log(f"Ошибка установки {lib}: {error_msg[:500]}")
                        except:
                            pass
                    
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
                    
                except subprocess.TimeoutExpired:
                    self.root.after(0, lambda l=lib: progress_text.insert(tk.END, f"✗ Таймаут при установке {l}\n"))
                    error_count += 1
                except Exception as e:
                    self.root.after(0, lambda l=lib, err=str(e): progress_text.insert(tk.END, f"✗ Ошибка {l}: {err[:100]}\n"))
                    error_count += 1
                    self.root.after(0, lambda: progress_text.see(tk.END))
                    self.root.after(0, lambda: progress_window.update())
            
            # Останавливаем прогресс-бар
            self.root.after(0, lambda: progress_bar.stop())
            
            # Сохраняем информацию об установленных библиотеках
            self.save_installed_libraries(installed_libs)
            
            # Финальное сообщение
            if error_count == 0:
                self.root.after(0, lambda: status_label.config(text="Все библиотеки установлены успешно!"))
                self.root.after(0, lambda: progress_text.insert(tk.END, "\n✓ Установка завершена.\n"))
            else:
                self.root.after(0, lambda sc=success_count, ec=error_count: status_label.config(
                    text=f"Установлено: {sc}, Ошибок: {ec}"))
                self.root.after(0, lambda: progress_text.insert(tk.END, f"\n⚠ Некоторые библиотеки не установлены.\n"))
                self.root.after(0, lambda: progress_text.insert(tk.END, f"\nПопробуйте установить вручную через командную строку:\n"))
                self.root.after(0, lambda: progress_text.insert(tk.END, f"pip install --user {' '.join([lib for lib in libraries if lib not in installed_libs])}\n"))
            
            self.root.after(0, lambda: progress_text.see(tk.END))
            self.root.after(0, lambda: progress_window.update())
            
            # Активируем кнопку закрытия
            self.root.after(0, lambda: close_btn.config(state=tk.NORMAL))
        
        def close_window():
            parent_window.destroy()
            progress_window.destroy()
            if installed_libs:
                messagebox.showinfo(
                    "Установка завершена",
                    "Библиотеки установлены успешно.\n"
                    "Перезапустите программу для применения изменений."
                )
        
        close_btn = tk.Button(
            progress_window,
            text="Закрыть",
            command=close_window,
            font=('Segoe UI', 10),
            padx=20,
            pady=5,
            state=tk.DISABLED
        )
        close_btn.pack(pady=10)
        
        threading.Thread(target=install_thread, daemon=True).start()

