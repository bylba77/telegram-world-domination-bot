# global_events.py

import random
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from events_base import BaseEvent
import game_state  # Нам нужен доступ к состоянию игры



# --- ОПРЕДЕЛЯЕМ ЛОГИКУ КАЖДОГО СОБЫТИЯ КАК ОТДЕЛЬНЫЙ КЛАСС ---

class PandemicEvent(BaseEvent):
    ID = "PANDEMIC"
    name = "Глобальная Пандемия"
    button_text = "💉 Сделать взнос в фонд"
    duration = 3
    goal_amount = 20000
    type = 'crisis'
    on_start_effect = {"type": "income_modifier", "value": -0.20}

    async def get_start_message(self):
        return (f"🚨 **ГЛОБАЛЬНАЯ УГРОЗА!** В мире началась пандемия! "
                f"Доход всех городов снижен на 20%, пока не будет собран "
                f"фонд здравоохранения в размере **${self.goal_amount}**.")

    async def on_fail(self, players):
        fail_message = ("**КОЛЛАПС!** Мировым лидерам не удалось договориться. Пандемия выходит из-под контроля. "
                        "В следующие 2 раунда мировая экономика будет в рецессии (-50% ко всему доходу).")
        for player_id, p_data in players.items():
            if p_data.get("country"):
                p_data['temp_effects']['recession'] = {'rounds_left': 2}
                try:
                    await self.bot.send_message(player_id, fail_message, parse_mode="Markdown")
                except Exception:
                    pass

    async def on_success(self, players, winner_player=None):
        success_message = ("**ПОБЕДА НАД БОЛЕЗНЬЮ!** Глобальный фонд собран! Учёные разработали вакцину. "
                           "Экономические санкции снимаются!")
        qol_bonus = random.randint(3, 5)
        for player_id, p_data in players.items():
            if p_data.get("country"):
                for city in p_data['cities'].values():
                    city['qol'] = min(100, city['qol'] + qol_bonus)
                try:
                    await self.bot.send_message(player_id, success_message)
                except Exception:
                    pass

    async def handle_interaction(self, message, state, player):
        from states import GlobalEvent
        goal = self.goal_amount
        progress = self.data['progress']
        await message.answer(
            f"**{self.name}**\n\nСобрано: **${progress} / ${goal}**\n\n"
            f"Ваш бюджет: ${player['budget']}\nСколько вы хотите внести в общий фонд?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        )
        await state.set_state(GlobalEvent.entering_contribution)


class TechBreakthroughEvent(BaseEvent):
    ID = "TECH_BREAKTHROUGH"
    name = "Технологический Прорыв"
    button_text = "✅ Инвестировать в проект"
    duration = 3
    goal_amount = 10000
    type = 'opportunity'

    async def get_start_message(self):
        return (f"💡 **ШАНС ВЕКА!** Учёные на пороге открытия термоядерного синтеза. "
                f"Нация, которая первой суммарно инвестирует **${self.goal_amount}**, "
                f"получит вечный бонус +15% к доходу всех своих городов!")

    async def on_fail(self, players):
        fail_message = "УПУЩЕННАЯ ВОЗМОЖНОСТЬ! Никто не успел полностью профинансировать проект. Все вложенные средства утеряны."
        for player_id, p_data in players.items():
            if p_data.get("country"):
                try:
                    await self.bot.send_message(player_id, fail_message)
                except Exception:
                    pass

    async def on_success(self, players, winner_player=None):
        winner_player['income_modifier'] = winner_player.get('income_modifier', 1.0) + 0.15
        success_msg = (f"🏆 **{self.name} ЗАВЕРШЕНО!**\n\n"
                       f"Страна **{winner_player['country']}** первой достигла цели инвестиций и получает вечный бонус к доходу!")
        for player_id, p_data in players.items():
            if p_data.get("country"):
                try:
                    await self.bot.send_message(player_id, success_msg, parse_mode="Markdown")
                except Exception:
                    pass

    async def handle_interaction(self, message, state, player):
        from states import GlobalEvent
        goal = self.goal_amount
        investors = self.data.get('investors', {})
        my_progress = investors.get(message.from_user.id, 0)
        await message.answer(
            f"**{self.name}**\n\nЦель инвестиций: **${goal}**\n"
            f"Ваш текущий вклад: **${my_progress}**\n\n"
            f"Ваш бюджет: ${player['budget']}\nСколько вы хотите инвестировать?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        )
        await state.set_state(GlobalEvent.entering_investment)


class SolarFlareEvent(BaseEvent):
    ID = "SOLAR_FLARE"
    name = "Солнечная Вспышка"
    duration = 1
    type = 'shift'

    async def get_start_message(self):
        return ("💥 **КОСМИЧЕСКАЯ АНОМАЛИЯ!** Мощный выброс корональной массы обрушился на планету. "
                "**Все защитные щиты в мире временно отключены** на этот раунд!")


class EnergyCrisisEvent(BaseEvent):
    ID = "ENERGY_CRISIS"
    name = "Энергетический коллапс"
    button_text = "💉 Сделать взнос в фонд"
    duration = 3
    goal_amount = 15000
    type = 'crisis'

    async def get_start_message(self):
        return (f"📉 **ЭНЕРГЕТИЧЕСКИЙ КОЛЛАПС!** Глобальный сбой в энергосетях привел к остановке промышленности. "
                f"**Производство щитов и ядерных ракет невозможно**, пока не будет собрана сумма в **${self.goal_amount}** на ремонт инфраструктуры.")

    async def on_fail(self, players):
        fail_message = ("**ПРОМЫШЛЕННЫЙ КОЛЛАПС!** Восстановить энергосеть не удалось. "
                        "В следующем раунде стоимость производства щитов и ракет будет удвоена из-за дефицита ресурсов.")
        # Здесь в будущем можно будет добавить эффект повышения цен
        for player_id, p_data in players.items():
            if p_data.get("country"):
                try:
                    await self.bot.send_message(player_id, fail_message, parse_mode="Markdown")
                except Exception:
                    pass

    async def on_success(self, players, winner_player=None):
        success_message = ("**СИСТЕМА ВОССТАНОВЛЕНА!** Энергосеть снова в строю! "
                           "Промышленность возвращается к работе. В благодарность за сотрудничество, "
                           "все страны получают +1 очко действия в следующем раунде.")
        # Здесь в будущем будет эффект +1 ОД
        for player_id, p_data in players.items():
            if p_data.get("country"):
                try:
                    await self.bot.send_message(player_id, success_message)
                except Exception:
                    pass

    async def handle_interaction(self, message, state, player):
        from states import GlobalEvent
        goal = self.goal_amount
        progress = self.data.get('progress', 0)
        await message.answer(
            f"**{self.name}**\n\nСобрано на ремонт: **${progress} / ${goal}**\n\n"
            f"Ваш бюджет: ${player['budget']}\nСколько вы хотите пожертвовать на восстановление?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        )
        await state.set_state(GlobalEvent.entering_contribution)


class BlackMarketEvent(BaseEvent):
    ID = "BLACK_MARKET"
    name = "Чёрный рынок"
    button_text = "✅ Инвестировать в проект"
    duration = 2
    goal_amount = 7500 # Цена за 2 ракеты
    type = 'opportunity'

    async def get_start_message(self):
        return (f"🤫 **ЧЁРНЫЙ РЫНОК!** В нейтральных водах появился торговец оружием. "
                f"Первый, кто заплатит ему **${self.goal_amount}**, немедленно получит **2 готовые ядерные ракеты** в обход производственных циклов!")

    async def on_fail(self, players):
        fail_message = "Торговец оружием покинул регион, не дождавшись покупателей. Возможность упущена."
        for player_id, p_data in players.items():
             if p_data.get("country"):
                try: await self.bot.send_message(player_id, fail_message)
                except Exception: pass

    async def on_success(self, players, winner_player=None):
        winner_player['ready_nukes'] += 2
        success_msg = (f"🚀 **СДЕЛКА СОСТОЯЛАСЬ!**\n\n"
                       f"Страна **{winner_player['country']}** заключила контракт на чёрном рынке и немедленно получила 2 готовые боеголовки!")
        for player_id, p_data in players.items():
            if p_data.get("country"):
                try: await self.bot.send_message(player_id, success_msg, parse_mode="Markdown")
                except Exception: pass

    async def handle_interaction(self, message, state, player):
        cost = self.goal_amount
        from keyboards import main_menu
        if player['budget'] >= cost:
            # Сразу проводим транзакцию, так как это одиночная покупка
            player['budget'] -= cost
            await self.on_success(players=game_state.players, winner_player=player)
            game_state.active_global_event = None # Завершаем событие
            await message.answer(f"✅ Контракт подписан! Вы потратили ${cost}. Ваш новый бюджет: ${player['budget']}", reply_markup=main_menu(message.from_user.id))
        else:
            await message.answer(f"У вас недостаточно средств для заключения контракта. Требуется: ${cost}, у вас: ${player['budget']}", reply_markup=main_menu(message.from_user.id))

# global_events.py

class GlobalEspionageEvent(BaseEvent):
    ID = "GLOBAL_ESPIONAGE"
    name = "Глобальный шпионаж"
    duration = 1
    type = 'shift'

    async def get_start_message(self):
        return ("👁️ **ТОТАЛЬНАЯ СЛЕЖКА!** Произошла утечка финансовых данных всех мировых держав. "
                "На этот раунд **бюджет каждой страны становится известен всем** в меню 'Обзор стран'!")

# --- РЕЕСТР ВСЕХ СОБЫТИЙ ---
EVENT_CLASSES = {
    "PANDEMIC": PandemicEvent,
    "TECH_BREAKTHROUGH": TechBreakthroughEvent,
    "SOLAR_FLARE": SolarFlareEvent,
    "ENERGY_CRISIS": EnergyCrisisEvent,
    "BLACK_MARKET": BlackMarketEvent,
    "GLOBAL_ESPIONAGE": GlobalEspionageEvent,
}