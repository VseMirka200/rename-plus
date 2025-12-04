"""Модуль для проверки обновлений."""

import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class UpdateChecker:
    """Класс для проверки обновлений."""
    
    VERSION = "1.0.0"  # Текущая версия
    
    def __init__(self, update_url: Optional[str] = None):
        """Инициализация проверяющего обновления.
        
        Args:
            update_url: URL для проверки обновлений
        """
        if update_url is None:
            # Можно указать реальный URL для проверки обновлений
            update_url = "https://api.github.com/repos/your-repo/rename-plus/releases/latest"
        self.update_url = update_url
        self.check_enabled = True
    
    def check_for_updates(self) -> Optional[Dict]:
        """Проверка наличия обновлений.
        
        Returns:
            Информация об обновлении или None
        """
        if not self.check_enabled:
            return None
        
        try:
            with urllib.request.urlopen(self.update_url, timeout=5) as response:
                data = json.loads(response.read().decode())
                
                # Парсим версию из данных
                latest_version = data.get('tag_name', '').lstrip('v')
                
                if self._compare_versions(latest_version, self.VERSION) > 0:
                    return {
                        'available': True,
                        'current_version': self.VERSION,
                        'latest_version': latest_version,
                        'release_notes': data.get('body', ''),
                        'download_url': data.get('html_url', '')
                    }
        except urllib.error.URLError:
            logger.debug("Не удалось проверить обновления (нет интернета или недоступен сервер)")
        except Exception as e:
            logger.debug(f"Ошибка проверки обновлений: {e}")
        
        return None
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """Сравнение версий.
        
        Args:
            v1: Версия 1
            v2: Версия 2
            
        Returns:
            -1 если v1 < v2, 0 если равны, 1 если v1 > v2
        """
        def version_tuple(v):
            return tuple(map(int, v.split('.')))
        
        try:
            t1 = version_tuple(v1)
            t2 = version_tuple(v2)
            if t1 < t2:
                return -1
            elif t1 > t2:
                return 1
            return 0
        except Exception:
            return 0

