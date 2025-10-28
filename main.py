# main.py

import asyncio
import time
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage


import config
import game_state
from handlers import router as player_router # <-- Переименовываем для ясности
from admin_handlers import admin_router
# Инициализация Aiogram
storage = MemoryStorage()
bot = Bot(token=config.TOKEN)
dp = Dispatcher(storage=storage)


# =====================================================================================
# --- ФОНОВЫЕ ЗАДАЧИ (ТАЙМЕР РАУНДА) ---
# =====================================================================================

async def broadcast_to_active_players(message_text, parse_mode=None, exclude_admin=False):
    """Отправляет сообщение всем активным игрокам."""
    p_ids = [uid for uid, p in game_state.players.items() if p.get("country") and not p.get("eliminated")]
    if exclude_admin: p_ids = [uid for uid in p_ids if uid != config.ADMIN_ID]
    for uid in p_ids:
        try:
            await bot.send_message(uid, message_text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Ошибка широковещательной рассылки игроку {uid}: {e}")


async def round_timer_task():
    """Фоновая задача, отслеживающая время раунда."""
    while True:
        if game_state.round_end_time:
            time_left = game_state.round_end_time - time.time()
            notifications = {'5_min': 300, '3_min': 180, '1_min': 60, 'end': 0}
            for key, value in notifications.items():
                if time_left <= value and not game_state.round_notifications.get(key):
                    msg = f"⏳ Осталось {value // 60} минут до конца раунда." if value > 0 else "⏰ Время раунда вышло!"
                    await broadcast_to_active_players(msg, exclude_admin=True)
                    game_state.round_notifications[key] = True
                    if key == 'end': game_state.round_end_time = None
        await asyncio.sleep(1)


# =====================================================================================
# --- ЗАПУСК БОТА ---
# =====================================================================================

async def main():
    print("Бот запущен...")
    dp.include_router(player_router)
    dp.include_router(admin_router)

    asyncio.create_task(round_timer_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())