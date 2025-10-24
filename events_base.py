# events_base.py

class BaseEvent:
    """
    Базовый класс (интерфейс) для всех глобальных событий.
    Определяет, какие "кнопки" должен иметь каждый пульт.
    """
    def __init__(self, bot, event_data):
        self.bot = bot
        self.data = event_data # Данные из game_state.active_global_event

    async def get_start_message(self):
        """Возвращает сообщение, которое видят игроки при старте события."""
        pass

    async def apply_start_effect(self, players):
        """Применяет немедленный эффект при старте события (например, отключает щиты)."""
        pass

    async def apply_round_effect(self, players):
        """Применяет эффект, который действует каждый раунд (например, снижение дохода)."""
        pass

    async def handle_interaction(self, message, state, player):
        """Обрабатывает нажатие игроком на кнопку события."""
        pass

    async def on_success(self, players, winner_player=None):
        """Выполняется, когда событие успешно завершается."""
        pass

    async def on_fail(self, players):
        """Выполняется, когда время события истекает."""
        pass