"""Модуль для управления резервным копированием файлов."""

import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BackupManager:
    """Класс для управления резервным копированием."""
    
    def __init__(self, backup_dir: Optional[str] = None):
        """Инициализация менеджера резервных копий.
        
        Args:
            backup_dir: Директория для хранения резервных копий
        """
        if backup_dir is None:
            # Используем подпапку в домашней директории
            home_dir = os.path.expanduser("~")
            backup_dir = os.path.join(home_dir, ".rename_plus_backups")
        
        self.backup_dir = backup_dir
        self._ensure_backup_dir()
    
    def _ensure_backup_dir(self):
        """Создание директории для резервных копий, если её нет."""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Не удалось создать директорию для резервных копий: {e}")
    
    def create_backup(self, file_path: str) -> Optional[str]:
        """Создание резервной копии файла.
        
        Args:
            file_path: Путь к файлу для резервного копирования
            
        Returns:
            Путь к резервной копии или None в случае ошибки
        """
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            logger.warning(f"Файл не существует для резервного копирования: {file_path}")
            return None
        
        try:
            # Создаем имя резервной копии с временной меткой
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = os.path.basename(file_path)
            name, ext = os.path.splitext(file_name)
            backup_name = f"{name}_{timestamp}{ext}"
            
            # Создаем подпапку по дате
            date_folder = datetime.now().strftime("%Y-%m-%d")
            date_backup_dir = os.path.join(self.backup_dir, date_folder)
            os.makedirs(date_backup_dir, exist_ok=True)
            
            backup_path = os.path.join(date_backup_dir, backup_name)
            
            # Копируем файл
            shutil.copy2(file_path, backup_path)
            logger.debug(f"Создана резервная копия: {backup_path}")
            
            return backup_path
        except Exception as e:
            logger.error(f"Ошибка при создании резервной копии {file_path}: {e}")
            return None
    
    def create_backups(self, files: List[Dict]) -> Dict[str, str]:
        """Создание резервных копий для списка файлов.
        
        Args:
            files: Список файлов с данными {path, full_path, ...}
            
        Returns:
            Словарь {оригинальный_путь: путь_к_резервной_копии}
        """
        backups = {}
        
        for file_data in files:
            file_path = file_data.get('full_path') or file_data.get('path')
            if file_path:
                backup_path = self.create_backup(file_path)
                if backup_path:
                    backups[file_path] = backup_path
        
        return backups
    
    def restore_from_backup(self, backup_path: str, target_path: str) -> bool:
        """Восстановление файла из резервной копии.
        
        Args:
            backup_path: Путь к резервной копии
            target_path: Путь для восстановления
            
        Returns:
            True если успешно, False в противном случае
        """
        if not os.path.exists(backup_path):
            logger.error(f"Резервная копия не найдена: {backup_path}")
            return False
        
        try:
            # Создаем директорию для целевого файла, если её нет
            target_dir = os.path.dirname(target_path)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)
            
            shutil.copy2(backup_path, target_path)
            logger.debug(f"Восстановлен файл из резервной копии: {target_path}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при восстановлении из резервной копии: {e}")
            return False
    
    def cleanup_old_backups(self, days: int = 30):
        """Очистка старых резервных копий.
        
        Args:
            days: Количество дней для хранения резервных копий
        """
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for root, dirs, files in os.walk(self.backup_dir):
                # Проверяем дату папки
                folder_name = os.path.basename(root)
                try:
                    folder_date = datetime.strptime(folder_name, "%Y-%m-%d")
                    if folder_date < cutoff_date:
                        shutil.rmtree(root)
                        logger.debug(f"Удалена старая папка резервных копий: {root}")
                except ValueError:
                    # Не папка с датой, пропускаем
                    continue
        except Exception as e:
            logger.error(f"Ошибка при очистке старых резервных копий: {e}")
    
    def get_backup_info(self) -> Dict:
        """Получение информации о резервных копиях.
        
        Returns:
            Словарь с информацией о резервных копиях
        """
        info = {
            'backup_dir': self.backup_dir,
            'total_backups': 0,
            'total_size': 0,
            'oldest_backup': None,
            'newest_backup': None
        }
        
        try:
            oldest_date = None
            newest_date = None
            
            for root, dirs, files in os.walk(self.backup_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        info['total_backups'] += 1
                        info['total_size'] += os.path.getsize(file_path)
                        
                        file_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                        if oldest_date is None or file_date < oldest_date:
                            oldest_date = file_date
                            info['oldest_backup'] = file_path
                        if newest_date is None or file_date > newest_date:
                            newest_date = file_date
                            info['newest_backup'] = file_path
        except Exception as e:
            logger.error(f"Ошибка при получении информации о резервных копиях: {e}")
        
        return info

