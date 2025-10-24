# filters.py

from aiogram import types
import config

class PlayerFilter:
    """Фильтр для разделения команд админа и обычного игрока."""
    def __init__(self, is_admin: bool):
        self.is_admin = is_admin
    def __call__(self, message: types.Message) -> bool:
        if message.from_user is None: return False
        is_user_admin = message.from_user.id == config.ADMIN_ID
        return is_user_admin == self.is_admin