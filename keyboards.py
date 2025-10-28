# keyboards.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
import config
import game_state
from global_events import EVENT_CLASSES


def construction_menu():
    """Меню для строительства и развития."""
    keyboard = [
        [KeyboardButton(text="Улучшить город"), KeyboardButton(text="🧱 Построить бункер")],
        [KeyboardButton(text="🎉 Соц. программа")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def military_menu():
    """Меню для военных действий."""
    keyboard = [
        [KeyboardButton(text="Произвести ядерную бомбу"), KeyboardButton(text="Создать щит")],
        [KeyboardButton(text="Атаковать страну"), KeyboardButton(text="👁️ Запустить шпионаж")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def diplomacy_menu():
    """Меню для дипломатии и внешней политики."""
    keyboard = [
        [KeyboardButton(text="🤝 Оказать помощь"), KeyboardButton(text="Начать переговоры")],
        [KeyboardButton(text="Капитулировать")],
        [KeyboardButton(text="⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def main_menu(user_id):
    """Генерирует ГЛАВНОЕ меню (наш "рабочий стол")."""
    if user_id == config.ADMIN_ID:
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Админка")]], resize_keyboard=True)

    p = game_state.players.get(user_id, {})
    if not p or not p.get("country"):
        return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="/start")]], resize_keyboard=True)



    ready_button_text = "❌ Отменить готовность" if p.get("ready_for_next_round") else "✅ Я готов"


    base_keyboard_rows = [

        [KeyboardButton(text="Обзор стран"), KeyboardButton(text="Статистика")],

        [KeyboardButton(text="🏢 Строительство"), KeyboardButton(text="💥 Военное дело"),
         KeyboardButton(text="🏛️ Политика")],

        [KeyboardButton(text=ready_button_text), KeyboardButton(text="Вызвать админа")]

    ]

    # The dynamic button for global events remains here
    if game_state.active_global_event:
        event_id = game_state.active_global_event.get('id')
        event_class = EVENT_CLASSES.get(event_id)
        if event_class and hasattr(event_class, 'type') and event_class.type in ['crisis', 'opportunity']:
            button_text = getattr(event_class, "button_text", "🌍 Глобальное событие")
            base_keyboard_rows.insert(0, [KeyboardButton(text=button_text)])

    return ReplyKeyboardMarkup(keyboard=base_keyboard_rows, resize_keyboard=True)