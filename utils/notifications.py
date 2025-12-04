"""Модуль для системных уведомлений."""

import logging
import platform
from typing import Optional

logger = logging.getLogger(__name__)

# Попытка импортировать plyer для кроссплатформенных уведомлений
HAS_PLYER = False
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False


class NotificationManager:
    """Класс для управления системными уведомлениями."""
    
    def __init__(self, enabled: bool = True):
        """Инициализация менеджера уведомлений.
        
        Args:
            enabled: Включены ли уведомления
        """
        self.enabled = enabled
        self.platform = platform.system()
    
    def notify(self, title: str, message: str, duration: int = 5) -> bool:
        """Показ системного уведомления.
        
        Args:
            title: Заголовок уведомления
            message: Текст уведомления
            duration: Длительность показа в секундах
            
        Returns:
            True если успешно, False в противном случае
        """
        if not self.enabled:
            return False
        
        try:
            if HAS_PLYER:
                # Используем plyer для кроссплатформенных уведомлений
                notification.notify(
                    title=title,
                    message=message,
                    timeout=duration,
                    app_name="Ренейм+"
                )
                return True
            elif self.platform == 'Windows':
                # Windows 10+ уведомления через win10toast (если доступно)
                try:
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(title, message, duration=duration)
                    return True
                except ImportError:
                    logger.debug("win10toast не установлен, уведомления недоступны")
            elif self.platform == 'Darwin':
                # macOS уведомления
                try:
                    import subprocess
                    script = f'''
                    display notification "{message}" with title "{title}"
                    '''
                    subprocess.run(['osascript', '-e', script], check=False)
                    return True
                except Exception:
                    pass
            elif self.platform == 'Linux':
                # Linux уведомления через notify-send
                try:
                    import subprocess
                    subprocess.run(
                        ['notify-send', title, message, f'--expire-time={duration * 1000}'],
                        check=False
                    )
                    return True
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Ошибка показа уведомления: {e}")
        
        return False
    
    def notify_success(self, message: str) -> bool:
        """Уведомление об успешной операции.
        
        Args:
            message: Текст сообщения
            
        Returns:
            True если успешно
        """
        return self.notify("Ренейм+ - Успех", message)
    
    def notify_error(self, message: str) -> bool:
        """Уведомление об ошибке.
        
        Args:
            message: Текст сообщения
            
        Returns:
            True если успешно
        """
        return self.notify("Ренейм+ - Ошибка", message, duration=10)
    
    def notify_info(self, message: str) -> bool:
        """Информационное уведомление.
        
        Args:
            message: Текст сообщения
            
        Returns:
            True если успешно
        """
        return self.notify("Ренейм+ - Информация", message)

