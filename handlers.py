# handlers.py

import random
import time
from collections import Counter
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton,
                           InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove)

# Импортируем наши модули
import config
import game_state
from keyboards import (main_menu, construction_menu, diplomacy_menu, military_menu)
from newspaper_templates import TEMPLATES
from filters import PlayerFilter
from states import (Registration, Attack, Negotiation, Surrender, Upgrade, LendLease, SocialProgram, GlobalEvent,
                    Bunker,
                    CorsairChoice, Espionage)
from global_events import EVENT_CLASSES

router = Router()


# =====================================================================================
# --- НОВАЯ ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ЛОГИРОВАНИЯ ---
# =====================================================================================

async def log_action(bot, text: str):
    """Отправляет отформатрованное сообщение в лог-канал."""
    if not hasattr(config, 'LOG_CHANNEL_ID') or not config.LOG_CHANNEL_ID:
        print(f"Log channel ID not configured. Log: {text}")
        return
    try:
        await bot.send_message(config.LOG_CHANNEL_ID, text, parse_mode="HTML")
    except Exception as e:
        print(f"Error sending log to channel: {e}")


# =====================================================================================
# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
# =====================================================================================

def calculate_upgrade_cost(city_level):
    """Рассчитывает стоимость улучшения города на основе его текущего уровня."""
    return config.BASE_UPGRADE_COST + (city_level * config.UPGRADE_COST_INCREASE)


def format_admin_message(text):
    """Красиво форматирует сообщение от админа (остается здесь для импорта в админ-файл)."""
    header = "🔔 <b>Сообщение от администратора</b>"
    line = "➖➖➖➖➖➖➖➖➖➖➖"
    return f"{line}\n{header}\n{line}\n\n{text}\n\n{line}"


def is_player_in_game(message: types.Message) -> bool:
    """Вспомогательная функция-фильтр для проверки, зарегистрирован ли игрок."""
    user_id = message.from_user.id
    return user_id in game_state.players and game_state.players[user_id].get("country")


async def not_in_game_answer(message: types.Message):
    """Стандартный ответ для незарегистрированных игроков."""
    await message.answer("Я не могу найти вас в списке игроков. Пожалуйста, отправьте /start, чтобы начать заново.")


def get_development_status(avg_level):
    """Преобразует средний уровень городов в текстовый статус."""
    status = "Неизвестно"
    for level, name in config.DEVELOPMENT_LEVELS.items():
        if avg_level >= level:
            status = name
    return status


def get_nation_status(avg_qol):
    """Преобразует средний QoL в текстовый статус."""
    status = "Неизвестно"
    for level, name in config.NATION_STATUS_LEVELS.items():
        if avg_qol >= level:
            status = name
    return status


# =====================================================================================
# --- РЕГИСТРАЦИЯ И СИСТЕМНЫЕ КОМАНДЫ ---
# =====================================================================================

@router.message(Command(commands=["start"]))
async def start_command(message: types.Message, state: FSMContext):
    """Обрабатывает команду /start, начинает процесс регистрации."""
    await state.clear()
    user_id = message.from_user.id
    if user_id not in game_state.players:
        game_state.players[user_id] = {
            "id": user_id, "country": None, "nickname": None, "budget": config.START_BUDGET, "cities": {},
            "pending_nukes": 0, "ready_nukes": 0, "shields": 0, "actions_left": 4,
            "income_modifier": 1.0, "temp_effects": {},
            "attacked_countries_this_round": [], "eliminated": False,
            "shields_built_this_round": 0, "upgrades_this_round": 0,
            "social_programs_this_round": 0, "ready_for_next_round": False
        }

    if user_id == config.ADMIN_ID:
        return await message.answer("✅ Вы вошли как администратор.", reply_markup=main_menu(user_id))
    if game_state.players[user_id].get("country"):
        return await message.answer("Вы уже в игре.", reply_markup=main_menu(user_id))

    taken_countries = {p.get("country") for p in game_state.players.values() if p.get("country")}
    available_countries = [c for c in config.countries.keys() if c not in taken_countries]

    if not available_countries:
        return await message.answer("К сожалению, все страны уже заняты.")

    kb_rows = [[KeyboardButton(text=name)] for name in available_countries]
    kb = ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)
    await message.answer("Добро пожаловать в 'Мировое Господство'! Выбери свою страну:", reply_markup=kb)
    await state.set_state(Registration.choosing_country)


@router.message(Registration.choosing_country)
async def process_country_selection(message: types.Message, state: FSMContext):
    user_id, text = message.from_user.id, message.text.strip()
    if text not in config.countries:
        return await message.answer("Пожалуйста, выберите страну из списка.")
    if any(p.get("country") == text for p in game_state.players.values()):
        return await message.answer("Эта страна уже занята. Выберите другую.")

    player = game_state.players[user_id]
    player["country"] = text
    player["cities"] = {city: {"level": 1, "income": 500, "qol": 35, "bunker_level": 0, 'ruined': False} for city in
                        config.countries[text]}

    await state.set_state(Registration.entering_nickname)
    await message.answer(f"Вы выбрали {text}. Теперь введите ваш игровой никнейм:", reply_markup=ReplyKeyboardRemove())


@router.message(Registration.entering_nickname)
async def process_nickname(message: types.Message, state: FSMContext):
    if not message.text:
        return await message.answer("Пожалуйста, отправьте ваш никнейм в виде обычного текста.")

    user_id, nickname = message.from_user.id, message.text.strip()
    if not nickname or len(nickname) > 15:
        return await message.answer("Никнейм не может быть пустым и должен быть короче 15 символов.")

    player = game_state.players[user_id]
    player["nickname"] = nickname
    await state.clear()

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"✅ <b>{player['country']} ({nickname})</b> присоединился(-ась) к игре."
    await log_action(message.bot, log_text)
    # ---------------------

    await message.answer(f"Отлично, {nickname}! Вы в игре. Удачи!", reply_markup=main_menu(user_id))


@router.message(Command(commands=["cancel"]))
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return await message.answer("Нет активных команд для отмены.", reply_markup=main_menu(message.from_user.id))
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))


# =====================================================================================
# --- ОБРАБОТЧИКИ МЕНЮ И ПОДМЕНЮ ---
# =====================================================================================

@router.message(PlayerFilter(is_admin=False), F.text == "🏢 Строительство")
async def show_construction_menu(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await message.answer("Вы вошли в меню строительства и развития.", reply_markup=construction_menu())


@router.message(PlayerFilter(is_admin=False), F.text == "💥 Военное дело")
async def show_military_menu(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    actions_left = game_state.players[message.from_user.id].get('actions_left', 0)
    await message.answer(f"Вы вошли в военный штаб. Действий осталось: {actions_left}", reply_markup=military_menu())


@router.message(PlayerFilter(is_admin=False), F.text == "🏛️ Политика")
async def show_diplomacy_menu(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await message.answer("Вы вошли в министерство иностранных дел.", reply_markup=diplomacy_menu())


@router.message(PlayerFilter(is_admin=False), F.text == "⬅️ Назад")
async def back_to_main_menu(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await message.answer("Вы вернулись в главное меню.", reply_markup=main_menu(message.from_user.id))


# =====================================================================================
# --- ОБРАБОТЧИКИ ОДИНОЧНЫХ ДЕЙСТВИЙ ИГРОКА ---
# =====================================================================================

@router.message(PlayerFilter(is_admin=False), F.text == "Статистика")
async def show_statistics_handler(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await show_statistics_logic(message)


@router.message(PlayerFilter(is_admin=False), F.text == "Обзор стран")
async def overview_countries_handler(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await overview_countries_logic(message)


@router.message(PlayerFilter(is_admin=False), F.text.in_({"✅ Я готов", "❌ Отменить готовность"}))
async def toggle_ready_status_handler(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await toggle_ready_status_logic(message)


@router.message(PlayerFilter(is_admin=False), F.text == "Вызвать админа")
async def call_admin_handler(message: types.Message):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await call_admin_logic(message)


# =====================================================================================
# --- FSM ПРОЦЕССЫ ИГРОКА ---
# =====================================================================================

# --- Шпионаж ---
@router.message(PlayerFilter(is_admin=False), F.text == "👁️ Запустить шпионаж")
async def espionage_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    player = game_state.players[user_id]

    if player['actions_left'] <= 0:
        return await message.answer("❌ Нет действий в этом раунде.", reply_markup=main_menu(user_id))
    if player['budget'] < config.SPY_COST:
        return await message.answer(f"Недостаточно средств для шпионажа. Требуется ${config.SPY_COST}.",
                                    reply_markup=main_menu(user_id))
    targets = [p["country"] for uid, p in game_state.players.items() if
               uid != user_id and p.get("country") and not p.get("eliminated")]
    if not targets:
        return await message.answer("Нет других стран для шпионажа.", reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=c)] for c in targets] + [[KeyboardButton(text="Отмена")]]
    await message.answer(f"Запуск шпионской операции будет стоить ${config.SPY_COST} и 1 очко действия.\n\n"
                         "Выберите цель для разведки:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(Espionage.choosing_target)


@router.message(Espionage.choosing_target)
async def espionage_process_target(message: types.Message, state: FSMContext):
    await state.clear()
    target_country = message.text.strip()
    user_id = message.from_user.id
    if target_country == "Отмена":
        return await message.answer("Операция отменена.", reply_markup=main_menu(user_id))
    target_player_data = next((p for p in game_state.players.values() if p.get("country") == target_country), None)
    if not target_player_data:
        return await message.answer("Цель не найдена.", reply_markup=main_menu(user_id))
    player = game_state.players[user_id]
    if player['actions_left'] <= 0 or player['budget'] < config.SPY_COST:
        return await message.answer("Недостаточно ресурсов. Операция отменена.", reply_markup=main_menu(user_id))
    player['budget'] -= config.SPY_COST
    player['actions_left'] -= 1

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"👁️ <b>{player['country']}</b> запустил(а) шпионаж против <b>{target_country}</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    intel_type = random.choice(['budget', 'nukes', 'shields', 'bunker'])
    report = f"**Секретный отчет по стране {target_country}:**\n\n"
    if intel_type == 'budget':
        report += f"💰 Наши агенты докладывают, что текущий бюджет цели составляет: **${target_player_data.get('budget', 0)}**."
    elif intel_type == 'nukes':
        report += f"🚀 Данные разведки: количество готовых к запуску ракет: **{target_player_data.get('ready_nukes', 0)}**."
    elif intel_type == 'shields':
        report += f"🛡️ Анализ обороны: количество активных щитов: **{target_player_data.get('shields', 0)}**."
    elif intel_type == 'bunker':
        highest_bunker = 0
        city_with_bunker = "Нет"
        for city, data in target_player_data.get('cities', {}).items():
            if data.get('bunker_level', 0) > highest_bunker:
                highest_bunker = data['bunker_level']
                city_with_bunker = city
        if highest_bunker > 0:
            report += f"🕳️ Система гражданской обороны: обнаружен бункер **уровня {highest_bunker}** в городе **{city_with_bunker}**."
        else:
            report += "🕳️ Система гражданской обороны: значительных бункерных сооружений не обнаружено."
    await message.answer("Шпионская операция завершена. Отчет доставлен.",
                         reply_markup=main_menu(user_id))
    await message.answer(report, parse_mode="Markdown")


# --- Строительство бункера ---
@router.message(PlayerFilter(is_admin=False), F.text == "🧱 Построить бункер")
async def bunker_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    player = game_state.players[user_id]
    if player['actions_left'] <= 0:
        return await message.answer("❌ Нет действий в этом раунде.", reply_markup=main_menu(user_id))
    city_options = []
    for city_name, city_data in player["cities"].items():
        current_level = city_data.get("bunker_level", 0)
        if current_level < config.MAX_BUNKER_LEVEL:
            next_level = current_level + 1
            cost = config.BUNKER_COSTS[next_level]
            city_options.append(f"{city_name} (ур. {current_level} -> {next_level}, ${cost})")
    if not city_options:
        return await message.answer("Все ваши города уже имеют бункеры максимального уровня.",
                                    reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=option)] for option in city_options] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выберите город для строительства/улучшения бункера:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(Bunker.choosing_city)


@router.message(Bunker.choosing_city)
async def bunker_process(message: types.Message, state: FSMContext):
    await state.clear()
    selected_option = message.text.strip()
    user_id = message.from_user.id
    if selected_option == "Отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(user_id))
    try:
        city_name = selected_option.split(" (ур.")[0]
    except:
        return await message.answer("Неверный выбор. Пожалуйста, используйте кнопки.", reply_markup=main_menu(user_id))
    player = game_state.players[user_id]
    if city_name not in player["cities"]:
        return await message.answer("Неверный город.", reply_markup=main_menu(user_id))
    city_data = player["cities"][city_name]
    current_level = city_data.get("bunker_level", 0)
    if current_level >= config.MAX_BUNKER_LEVEL:
        return await message.answer("Этот город уже имеет бункер максимального уровня.",
                                    reply_markup=main_menu(user_id))
    next_level = current_level + 1
    cost = config.BUNKER_COSTS[next_level]
    if player["budget"] < cost:
        return await message.answer(f"Недостаточно бюджета. Требуется ${cost}.", reply_markup=main_menu(user_id))
    if player['actions_left'] <= 0:
        return await message.answer("Ошибка: нет очков действий.", reply_markup=main_menu(user_id))
    player["budget"] -= cost
    player["actions_left"] -= 1
    city_data["bunker_level"] = next_level

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🧱 <b>{player['country']}</b> построил(а) бункер <b>уровня {next_level}</b> в городе <b>{city_name}</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    game_state.round_events.append({'type': 'BUNKER_BUILT', 'country': player['country']})
    await message.answer(
        f"✅ Бункер в городе **{city_name}** улучшен до **уровня {next_level}** за ${cost}!\n\n"
        f"Ваш бюджет: ${player['budget']}\n"
        f"Осталось действий: {player['actions_left']}",
        parse_mode="Markdown",
        reply_markup=main_menu(user_id)
    )


# --- Социальная программа ---
@router.message(PlayerFilter(is_admin=False), F.text == "🎉 Соц. программа")
async def social_program_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    player = game_state.players[user_id]
    if player.get("social_programs_this_round", 0) >= config.MAX_SOCIAL_PROGRAMS_PER_ROUND:
        return await message.answer(f"❌ Лимит соц. программ ({config.MAX_SOCIAL_PROGRAMS_PER_ROUND}).")
    if player['budget'] < config.SOCIAL_PROGRAM_COST:
        return await message.answer(f"Недостаточно средств. Нужно ${config.SOCIAL_PROGRAM_COST}.")
    kb_rows = [[KeyboardButton(text=city)] for city in player["cities"].keys()] + [[KeyboardButton(text="Отмена")]]
    keyboard = ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)
    await message.answer(f"Запуск соц. программы стоит ${config.SOCIAL_PROGRAM_COST}.\n"
                         "Выберите город для повышения благосостояния:",
                         reply_markup=keyboard)
    await state.set_state(SocialProgram.choosing_city)


@router.message(SocialProgram.choosing_city)
async def social_program_process_city(message: types.Message, state: FSMContext):
    await state.clear()
    city_name = message.text.strip()
    user_id = message.from_user.id
    if city_name == "Отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(user_id))
    player = game_state.players[user_id]
    if city_name not in player['cities']:
        return await message.answer("Неверный город.", reply_markup=main_menu(user_id))
    if player['budget'] < config.SOCIAL_PROGRAM_COST:
        return await message.answer(f"Недостаточно средств. Действие отменено.", reply_markup=main_menu(user_id))
    player['budget'] -= config.SOCIAL_PROGRAM_COST
    player['social_programs_this_round'] = player.get("social_programs_this_round", 0) + 1
    city_data = player['cities'][city_name]
    old_qol = city_data['qol']
    if old_qol >= 90:
        qol_increase = random.randint(2, 4)
    elif old_qol >= 80:
        qol_increase = random.randint(3, 5)
    elif old_qol >= 70:
        qol_increase = random.randint(3, 7)
    else:
        qol_increase = random.randint(5, 10)
    city_data['qol'] = min(100, old_qol + qol_increase)

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🎉 <b>{player['country']}</b> запустил(а) соц. программу в городе <b>{city_name}</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    game_state.round_events.append({'type': 'SOCIAL_PROGRAM', 'country': player['country']})
    await message.answer(f"🎉 Соц. программа в городе {city_name} запущена за ${config.SOCIAL_PROGRAM_COST}!\n"
                         f"Уровень жизни: {old_qol}% ↗️ {city_data['qol']}% (+{qol_increase}%)\n\n"
                         f"Ваш бюджет: ${player['budget']}.",
                         reply_markup=main_menu(user_id))


# --- Улучшение города ---
@router.message(PlayerFilter(is_admin=False), F.text == "Улучшить город")
async def upgrade_city_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    player = game_state.players[user_id]
    if player['actions_left'] <= 0:
        return await message.answer("❌ Нет действий в этом раунде.", reply_markup=main_menu(user_id))
    if player.get("upgrades_this_round", 0) >= config.MAX_UPGRADES_PER_ROUND:
        return await message.answer(f"❌ Лимит улучшений ({config.MAX_UPGRADES_PER_ROUND}).",
                                    reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=city)] for city in player["cities"].keys()] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выбери город для улучшения:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(Upgrade.choosing_city)


@router.message(Upgrade.choosing_city)
async def upgrade_city_process(message: types.Message, state: FSMContext):
    await state.clear()
    city_name = message.text.strip()
    user_id = message.from_user.id

    if city_name == "Отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(user_id))
    if city_name not in game_state.players[user_id]["cities"]:
        return await message.answer("Неверный город.", reply_markup=main_menu(user_id))
    await upgrade_city_logic(message)


# --- Ленд-лиз ---
@router.message(PlayerFilter(is_admin=False), F.text == "🤝 Оказать помощь")
async def lend_lease_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    player = game_state.players[user_id]
    if player['budget'] <= 0:
        return await message.answer("Ваша казна пуста.", reply_markup=main_menu(user_id))
    other_countries = [p["country"] for uid, p in game_state.players.items() if
                       uid != user_id and p.get("country") and not p.get("eliminated")]
    if not other_countries:
        return await message.answer("Нет других стран для оказания помощи.", reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=c)] for c in other_countries] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выберите страну для оказания помощи:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(LendLease.choosing_target)


@router.message(LendLease.choosing_target)
async def lend_lease_choose_target(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))
    target_uid = next((uid for uid, pl in game_state.players.items() if pl.get("country") == text), None)
    if not target_uid:
        return await message.answer("Страна не найдена. Пожалуйста, выберите из списка.")
    await state.update_data(target_uid=target_uid, target_country=text)
    sender_budget = game_state.players[message.from_user.id]['budget']
    max_amount = int(sender_budget * 0.5)
    kb_buttons = [KeyboardButton(text=str(int(sender_budget * p))) for p in [0.1, 0.25]] + [
        KeyboardButton(text=str(max_amount))]
    keyboard = ReplyKeyboardMarkup(keyboard=[kb_buttons, [KeyboardButton(text="Отмена")]], resize_keyboard=True,
                                   one_time_keyboard=True)
    await message.answer(
        f"Ваш бюджет: ${sender_budget}.\nВы можете отправить максимум 50% (${max_amount}).\n\nСколько вы хотите отправить в страну {text}?",
        reply_markup=keyboard)
    await state.set_state(LendLease.entering_amount)


@router.message(LendLease.entering_amount)
async def lend_lease_enter_amount(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))
    try:
        amount = int(text)
        if amount <= 0: raise ValueError
    except ValueError:
        return await message.answer("Пожалуйста, введите корректное число.")
    sender_id = message.from_user.id
    sender_budget = game_state.players[sender_id]['budget']
    max_amount = int(sender_budget * 0.5)
    if amount > max_amount:
        return await message.answer(f"Сумма превышает лимит в 50% (${max_amount}).")
    user_data = await state.get_data()
    target_country = user_data.get('target_country')
    await state.update_data(amount=amount)
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="✅ Подтвердить"), KeyboardButton(text="❌ Отмена")]],
                                   resize_keyboard=True)
    await message.answer(f"Вы уверены, что хотите отправить ${amount} в страну {target_country}?",
                         reply_markup=keyboard)
    await state.set_state(LendLease.confirming)


@router.message(LendLease.confirming, F.text.in_({"✅ Подтвердить", "❌ Отмена"}))
async def lend_lease_confirm(message: types.Message, state: FSMContext):
    text = message.text.strip()
    user_data = await state.get_data()
    await state.clear()
    if text == "❌ Отмена":
        return await message.answer("Транзакция отменена.", reply_markup=main_menu(message.from_user.id))
    sender_id = message.from_user.id
    amount = user_data.get('amount')
    target_uid = user_data.get('target_uid')
    sender = game_state.players[sender_id]
    receiver = game_state.players[target_uid]
    if sender['budget'] < amount:
        return await message.answer("Недостаточно средств. Действие отменено.", reply_markup=main_menu(sender_id))
    sender['budget'] -= amount
    receiver['budget'] += amount
    sender['actions_left'] -= 1

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🤝 <b>{sender['country']}</b> отправил(а) <code>${amount}</code> помощи стране <b>{receiver['country']}</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    await message.answer(f"✅ Успешно! Вы отправили ${amount} в страну {receiver['country']}.\n"
                         f"Ваш новый бюджет: ${sender['budget']}.\n"
                         f"Осталось действий: {sender['actions_left']}.",
                         reply_markup=main_menu(sender_id))
    try:
        await message.bot.send_message(target_uid, f"🤝 Вам поступила финансовая помощь от **{sender['country']}**!\n"
                                                   f"Сумма: ${amount}.\nВаш новый бюджет: ${receiver['budget']}.",
                                       parse_mode="Markdown")
    except Exception as e:
        print(f"Не удалось уведомить получателя ({target_uid}) о Ленд-лизе: {e}")


# --- Атака ---
@router.message(PlayerFilter(is_admin=False), F.text.startswith("Атаковать страну"))
async def attack_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    p = game_state.players[user_id]
    if p['actions_left'] <= 0:
        return await message.answer("❌ Нет действий.", reply_markup=main_menu(user_id))
    if p["ready_nukes"] <= 0:
        return await message.answer("У тебя нет готовых ядерных бомб.", reply_markup=main_menu(user_id))
    attacked_this_round = p.get("attacked_countries_this_round", [])
    targets = [pl["country"] for uid, pl in game_state.players.items() if
               pl.get("country") and uid != user_id and not pl.get('eliminated') and pl[
                   "country"] not in attacked_this_round]
    if not targets:
        return await message.answer("Нет доступных целей для атаки.", reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=t)] for t in targets] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выбери страну для атаки:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(Attack.choosing_target)


@router.message(Attack.choosing_target)
async def attack_choose_target(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Атака отменена.", reply_markup=main_menu(message.from_user.id))
    target_uid = next((uid for uid, pl in game_state.players.items() if pl.get("country") == text), None)
    if not target_uid:
        return await message.answer("Страна не найдена. Выбери из списка.")
    await state.update_data(target_uid=target_uid)
    target_player = game_state.players[target_uid]
    kb_rows = [[KeyboardButton(text=c + (" (разрушен)" if d.get("level", 0) == 0 else ""))] for c, d in
               target_player["cities"].items()]
    await message.answer(f"Цель — {text}. Выбери город для удара:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows + [[KeyboardButton(text="Отмена")]],
                                                          resize_keyboard=True))
    await state.set_state(Attack.choosing_city)


@router.message(Attack.choosing_city)
async def attack_choose_city(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    target_uid = user_data.get("target_uid")
    if message.text.strip() == "Отмена":
        await state.clear()
        return await message.answer("Атака отменена.", reply_markup=main_menu(message.from_user.id))
    # Важно: Не очищаем state здесь, так как он нужен в attack_final_step_logic
    await attack_final_step_logic(message, target_uid, state)


# --- Переговоры ---
@router.message(PlayerFilter(is_admin=False), F.text == "Начать переговоры")
async def negotiation_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    user_id = message.from_user.id
    other_countries = [p["country"] for uid, p in game_state.players.items() if
                       uid != user_id and p.get("country") and not p.get("eliminated")]
    if not other_countries:
        return await message.answer("Нет других стран для переговоров.", reply_markup=main_menu(user_id))
    kb_rows = [[KeyboardButton(text=c)] for c in other_countries] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выбери страну для переговоров:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(Negotiation.choosing_target)


@router.message(Negotiation.choosing_target)
async def negotiation_process(message: types.Message, state: FSMContext):
    await state.clear()
    if message.text.strip() == "Отмена":
        return await message.answer("Отменено.", reply_markup=main_menu(message.from_user.id))
    await negotiation_logic(message)


# --- Капитуляция ---
@router.message(PlayerFilter(is_admin=False), F.text == "Капитулировать")
async def surrender_start(message: types.Message, state: FSMContext):
    if not is_player_in_game(message): return await not_in_game_answer(message)
    await message.answer(
        "Чтобы подтвердить капитуляцию, напишите слово `сбежать`.\nДля отмены нажмите кнопку 'Отмена'.",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True),
        parse_mode="Markdown")
    await state.set_state(Surrender.confirming)


@router.message(Surrender.confirming)
async def surrender_process(message: types.Message, state: FSMContext):
    await state.clear()
    await surrender_logic(message)


# =====================================================================================
# --- ГЛОБАЛЬНЫЕ СОБЫТИЯ ---
# =====================================================================================

@router.message(PlayerFilter(is_admin=False), F.text.in_(
    {"💉 Сделать взнос в фонд", "✅ Инвестировать в проект", "🔧 Помочь в восстановлении", "💰 Связаться с торговцем"}))
async def handle_global_event_interaction(message: types.Message, state: FSMContext):
    """Единый обработчик для всех кнопок глобальных событий."""
    if not is_player_in_game(message): return await not_in_game_answer(message)
    if not game_state.active_global_event:
        return await message.answer("Событие уже закончилось.", reply_markup=main_menu(message.from_user.id))

    user_id = message.from_user.id
    player = game_state.players[user_id]
    event_id = game_state.active_global_event['id']
    event_class = EVENT_CLASSES.get(event_id)

    if event_class:
        event_object = event_class(message.bot, game_state.active_global_event)
        await event_object.handle_interaction(message, state, player)


@router.message(GlobalEvent.entering_investment)
async def global_event_process_investment(message: types.Message, state: FSMContext):
    await state.clear()
    if message.text.strip().lower() == "отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))
    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        return await message.answer("Пожалуйста, введите корректное положительное число.",
                                    reply_markup=main_menu(message.from_user.id))

    user_id = message.from_user.id
    player = game_state.players[user_id]
    if player['budget'] < amount:
        return await message.answer(f"У вас недостаточно средств.", reply_markup=main_menu(user_id))

    player['budget'] -= amount
    if 'investors' not in game_state.active_global_event:
        game_state.active_global_event['investors'] = {}

    current_investment = game_state.active_global_event['investors'].get(user_id, 0)
    new_total_investment = current_investment + amount
    game_state.active_global_event['investors'][user_id] = new_total_investment

    event_id = game_state.active_global_event['id']
    event_class = EVENT_CLASSES[event_id]
    goal = event_class.goal_amount

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"💡 <b>{player['country']}</b> инвестировал(а) <code>${amount}</code> в проект <b>'{event_class.name}'</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    await message.answer(f"✅ Вы инвестировали ${amount}.\nВаш общий вклад: **${new_total_investment} / ${goal}**\n"
                         f"Ваш новый бюджет: ${player['budget']}",
                         parse_mode="Markdown", reply_markup=main_menu(user_id))

    if new_total_investment >= goal:
        log_text = f"🏆 Событие <b>'{event_class.name}'</b> успешно завершено! Победитель: <b>{player['country']}</b>."
        await log_action(message.bot, log_text)
        await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
        event_object = event_class(message.bot, game_state.active_global_event)
        await event_object.on_success(game_state.players, winner_player=player)
        game_state.active_global_event = None


@router.message(GlobalEvent.confirming_black_market)
async def global_event_process_black_market(message: types.Message, state: FSMContext):
    """Обрабатывает подтверждение сделки на Чёрном рынке."""
    await state.clear()
    user_id = message.from_user.id

    if message.text != "✅ Подтвердить сделку":
        return await message.answer("Сделка отменена.", reply_markup=main_menu(user_id))

    if not game_state.active_global_event or game_state.active_global_event.get('id') != 'BLACK_MARKET':
        return await message.answer("Торговец уже уплыл. Сделка невозможна.", reply_markup=main_menu(user_id))

    player = game_state.players[user_id]
    event_class = EVENT_CLASSES['BLACK_MARKET']
    cost = event_class.goal_amount

    if player['budget'] < cost:
        return await message.answer(f"За время раздумий у вас стало недостаточно средств. Сделка отменена.",
                                    reply_markup=main_menu(user_id))

    player['budget'] -= cost
    log_text = f"🏆 Событие <b>'{event_class.name}'</b> успешно завершено! Победитель: <b>{player['country']}</b>."
    await log_action(message.bot, log_text)
    await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🤫 <b>{player['country']}</b> заключил(а) сделку на чёрном рынке, получив 2 ракеты за <code>${cost}</code>."
    await log_action(message.bot, log_text)
    # ---------------------

    event_object = event_class(message.bot, game_state.active_global_event)
    await event_object.on_success(players=game_state.players, winner_player=player)

    game_state.active_global_event = None

    await message.answer(
        f"✅ Контракт подписан! Вы потратили ${cost}. 2 ракеты добавлены в ваш арсенал.\n"
        f"Ваш новый бюджет: ${player['budget']}",
        reply_markup=main_menu(user_id)
    )


@router.message(GlobalEvent.entering_contribution)
async def global_event_process_contribution(message: types.Message, state: FSMContext):
    """Универсальный обработчик для всех событий-кризисов."""
    await state.clear()
    if message.text.strip().lower() == "отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(message.from_user.id))

    try:
        amount = int(message.text.strip())
        if amount <= 0: raise ValueError
    except ValueError:
        return await message.answer("Пожалуйста, введите корректное положительное число.",
                                    reply_markup=main_menu(message.from_user.id))

    player = game_state.players[message.from_user.id]
    if player['budget'] < amount:
        return await message.answer(f"У вас недостаточно средств.", reply_markup=main_menu(message.from_user.id))

    if not game_state.active_global_event:
        return await message.answer("Событие уже закончилось.", reply_markup=main_menu(message.from_user.id))

    player['budget'] -= amount
    game_state.active_global_event['progress'] = game_state.active_global_event.get('progress', 0) + amount

    event_id = game_state.active_global_event['id']
    event_class = EVENT_CLASSES[event_id]
    goal = event_class.goal_amount

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🌍 <b>{player['country']}</b> внёс(внесла) <code>${amount}</code> в общий фонд события <b>'{event_class.name}'</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    progress = game_state.active_global_event['progress']
    await message.answer(f"✅ Вы внесли ${amount} в общий фонд.\nПрогресс: **${progress} / ${goal}**\n"
                         f"Ваш новый бюджет: ${player['budget']}",
                         parse_mode="Markdown", reply_markup=main_menu(message.from_user.id))

    if progress >= goal:
        log_text = f"✅ Кризис <b>'{event_class.name}'</b> успешно преодолён общими усилиями."
        await log_action(message.bot, log_text)
        await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
        event_object = event_class(message.bot, game_state.active_global_event)
        await event_object.on_success(game_state.players)
        game_state.active_global_event = None


# =====================================================================================
# --- КОЛЛБЭКИ (ИНЛАЙН-КНОПКИ) ---
# =====================================================================================

@router.callback_query(F.data.startswith("neg_"))
async def handle_negotiation_response(callback: types.CallbackQuery):
    await negotiation_response_logic(callback)


@router.callback_query(CorsairChoice.making_choice)
async def handle_corsair_choice(callback: types.CallbackQuery, state: FSMContext):
    """Обрабатывает выбор агрессора: разграбить или сжечь город."""
    user_data = await state.get_data()
    await state.clear()

    attacker_id = user_data.get('attacker_id')
    target_id = user_data.get('target_id')
    city_name = user_data.get('city_name')

    if not all([attacker_id, target_id, city_name]):
        await callback.message.edit_text("Произошла ошибка. Данные об атаке утеряны.")
        return await callback.answer("Ошибка", show_alert=True)

    attacker = game_state.players[attacker_id]
    target = game_state.players[target_id]
    city = target["cities"][city_name]

    if callback.data == 'corsair_loot':
        stolen_amount = int(target['budget'] * 0.25)
        attacker['budget'] += stolen_amount
        target['budget'] -= stolen_amount
        city['level'], city['income'] = 0, 0
        city['qol'] = max(0, city['qol'] - random.randint(25, 40))

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"💰 <b>{attacker['country']}</b> разграбил(а) город <b>{city_name}</b> ({target['country']}), украв <code>${stolen_amount}</code>."
        await log_action(callback.bot, log_text)
        # ---------------------

        await callback.message.edit_text(
            f"✅ Город разграблен! Вы украли ${stolen_amount} из казны {target['country']}.")
        try:
            await callback.bot.send_message(target_id,
                                            f"❗️**ВАШ ГОРОД {city_name} БЫЛ РАЗГРАБЛЕН!**\n"
                                            f"{attacker['country']} украла ${stolen_amount} из вашей казны! Город разрушен."
                                            )
        except Exception as e:
            print(f"Error notifying target about loot: {e}")

    elif callback.data == 'corsair_burn':
        city['level'], city['income'] = 0, 0
        city['ruined'] = True
        bunker_level = city.get("bunker_level", 0)
        min_qol = 0
        if bunker_level > 0:
            min_qol = config.BUNKER_EFFECTS[bunker_level][0]
            city['qol'] = min_qol
        else:
            city['qol'] = random.randint(1, 5)

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🔥 <b>{attacker['country']}</b> сжёг(сожгла) дотла город <b>{city_name}</b> ({target['country']})."
        await log_action(callback.bot, log_text)
        # ---------------------

        await callback.message.edit_text(f"✅ Город {city_name} сожжён дотла! Его экономика навсегда искалечена.")
        try:
            await callback.bot.send_message(target_id,
                                            f"❗️**ВАШ ГОРОД {city_name} БЫЛ СОЖЖЁН ДОТЛА!**\n"
                                            f"{attacker['country']} наложила на него проклятие руин. Восстановление будет дороже, а бонусы от уровня жизни — вдвое ниже."
                                            )
        except Exception as e:
            print(f"Error notifying target about burn: {e}")

    await callback.answer()

    if all(c.get("level", 0) == 0 for c in target["cities"].values()):
        target["eliminated"] = True

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"☠️ Страна <b>{target['country']}</b> была полностью уничтожена усилиями <b>{attacker['country']}</b>."
        await log_action(callback.bot, log_text)
        # ---------------------

        game_state.round_events.append(
            {'type': 'COUNTRY_ELIMINATED', 'attacker': attacker['country'], 'country': target['country']}
        )
        await callback.bot.send_message(attacker_id,
                                        f"☠️ **ПОЛНОЕ УНИЧТОЖЕНИЕ!** Страна {target['country']} полностью разрушена вашими действиями!")
        try:
            await callback.bot.send_message(target_id, "Все ваши города разрушены. Вы выбыли из игры.",
                                            reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            print(f"Error notifying eliminated player: {e}")


# =====================================================================================
# --- ГАЗЕТА ---
# =====================================================================================

async def generate_newspaper_report():
    if not game_state.round_events:
        return None
    priority_types = ['ATTACK_SUCCESS', 'ATTACK_SHIELDED', 'COUNTRY_ELIMINATED', 'SURRENDERED']
    headlines = []
    priority_events = [e for e in game_state.round_events if e['type'] in priority_types]
    for event in priority_events:
        template_info = TEMPLATES.get(event['type'])
        if template_info:
            template = random.choice(template_info[1])
            headlines.append(f"⚡ {template.format(**event)}")
    regular_events = [e for e in game_state.round_events if e['type'] not in priority_types]
    event_counts = Counter(e['type'] for e in regular_events)
    processed_types = set()
    for event_type, count in event_counts.items():
        if event_type in processed_types: continue
        template_info = TEMPLATES.get(event_type)
        if not template_info: continue
        summary_threshold, specific_templates, summary_templates = template_info
        if summary_threshold and count >= summary_threshold:
            template = random.choice(summary_templates)
            headlines.append(f"📌 {template}")
            processed_types.add(event_type)
        else:
            specific_events_of_type = [e for e in regular_events if e['type'] == event_type]
            for event in specific_events_of_type:
                template = random.choice(specific_templates)
                headlines.append(f"🔹 {template.format(**event)}")
    if not headlines:
        return None
    random.shuffle(headlines)
    newspaper = f"📰 **Le Monde Global - Итоги раунда №{game_state.current_round}** 📰\n"
    newspaper += "================================\n\n"
    newspaper += "\n\n".join(headlines)
    return newspaper


# =====================================================================================
# --- CORE FUNCTIONS (ЛОГИКА) ---
# =====================================================================================

async def show_statistics_logic(message: types.Message):
    p = game_state.players[message.from_user.id]
    display_name = f"{p['country']} ({p.get('nickname')})" if p.get('nickname') else p['country']
    text = (f"📊 Статистика ({display_name}):\n"
            f"💰 Бюджет: ${p['budget']}\n"
            f"🚀 Ракеты (готовы/в производстве): {p['ready_nukes']}/{p['pending_nukes']}\n"
            f"🛡 Щиты: {p['shields']}\n"
            f"⚡ Действий осталось: {p['actions_left']}\n\n"
            "🏙 Города:\n")
    for city, c in p["cities"].items():
        text += f"  • {city}: ур. {c['level']}, доход ${c['income']}, уровень жизни {c['qol']}%\n"
    await message.answer(text, reply_markup=main_menu(message.from_user.id))


async def overview_countries_logic(message: types.Message):
    text = "🌍 Обзор всех стран:\n\n"
    active_players = [p for p in game_state.players.values() if p.get("country") and not p.get('eliminated')]
    if not active_players:
        return await message.answer("Нет активных стран для обзора.", reply_markup=main_menu(message.from_user.id))

    is_espionage_active = game_state.active_global_event and game_state.active_global_event.get(
        'id') == 'GLOBAL_ESPIONAGE'
    if is_espionage_active:
        text = "👁️ **ГЛОБАЛЬНЫЙ ШПИОНАЖ АКТИВЕН!**\nФинансовые данные всех держав утекли в сеть:\n\n"

    for player in active_players:
        display_text = f"<b>{player['country']} ({player.get('nickname', 'N/A')})</b>"
        cities = player.get("cities", {})

        avg_level = 0
        avg_qol = 0
        if cities:
            avg_level = round(sum(c["level"] for c in cities.values()) / len(cities), 2)
            avg_qol = round(sum(c["qol"] for c in cities.values()) / len(cities), 2)

        dev_status = get_development_status(avg_level)
        nation_status = get_nation_status(avg_qol)

        text += f"{display_text}\n"
        if is_espionage_active:
            text += f"💰 <b>Бюджет: ${player.get('budget', 0)}</b>\n"

        text += (f"📈 Уровень развития: {dev_status}\n"
                 f"❤️ Состояние нации: {nation_status}\n"
                 "—————————\n")

    await message.answer(text, parse_mode="HTML", reply_markup=main_menu(message.from_user.id))


async def produce_nuclear_logic(message: types.Message):
    user_id = message.from_user.id
    p = game_state.players[user_id]
    if p["budget"] >= config.NUKE_COST:
        p["budget"] -= config.NUKE_COST
        p["pending_nukes"] += 1
        p["actions_left"] -= 1

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🚀 <b>{p['country']}</b> начал(а) производство ядерной ракеты."
        await log_action(message.bot, log_text)
        # ---------------------

        game_state.round_events.append({'type': 'NUKE_PRODUCED', 'country': p['country']})

        await message.answer(
            f"✅ Ядерная бомба запущена в производство.\n\n"
            f"Осталось действий: {p['actions_left']}",
            reply_markup=main_menu(user_id)
        )
    else:
        await message.answer(f"Недостаточно бюджета ({config.NUKE_COST}).", reply_markup=main_menu(user_id))


async def create_shield_logic(message: types.Message):
    user_id = message.from_user.id
    p = game_state.players[user_id]
    if p.get("shields", 0) >= config.MAX_TOTAL_SHIELDS:
        return await message.answer(
            f"🛡️ Ваша страна уже имеет максимальное количество щитов ({config.MAX_TOTAL_SHIELDS}). Строительство невозможно.",
            reply_markup=main_menu(user_id)
        )
    if p.get("shields_built_this_round", 0) >= config.MAX_SHIELDS_PER_ROUND:
        return await message.answer(
            f"❌ Лимит щитов в этом раунде ({config.MAX_SHIELDS_PER_ROUND}).",
            reply_markup=main_menu(user_id)
        )

    if p["budget"] >= config.SHIELD_COST:
        p["budget"] -= config.SHIELD_COST
        p["shields"] += 1
        p["shields_built_this_round"] = p.get("shields_built_this_round", 0) + 1
        p["actions_left"] -= 1

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🛡️ <b>{p['country']}</b> создал(а) защитный щит. Всего щитов: {p['shields']}."
        await log_action(message.bot, log_text)
        # ---------------------

        game_state.round_events.append({'type': 'SHIELD_BUILT', 'country': p['country']})

        await message.answer(
            f"🛡️ Щит создан! Всего: {p['shields']}/{config.MAX_TOTAL_SHIELDS}.\n\n"
            f"Осталось действий: {p['actions_left']}",
            reply_markup=main_menu(user_id)
        )
    else:
        await message.answer(f"Недостаточно бюджета ({config.SHIELD_COST}).", reply_markup=main_menu(user_id))


async def upgrade_city_logic(message: types.Message):
    user_id, city_name = message.from_user.id, message.text.strip()
    player = game_state.players[user_id]
    city_to_upgrade = player["cities"][city_name]
    cost = calculate_upgrade_cost(city_to_upgrade["level"])

    if player["budget"] < cost:
        return await message.answer(f"Недостаточно бюджета. Нужно ${cost}.", reply_markup=main_menu(user_id))
    if city_to_upgrade["level"] >= config.MAX_CITY_LEVEL:
        return await message.answer(f"{city_name} уже достиг максимального уровня!", reply_markup=main_menu(user_id))

    player["budget"] -= cost
    player["actions_left"] -= 1
    player["upgrades_this_round"] = player.get("upgrades_this_round", 0) + 1

    city_to_upgrade["level"] += 1
    city_to_upgrade["income"] += 500

    old_qol_upgraded = city_to_upgrade['qol']
    if old_qol_upgraded >= 90:
        qol_bonus = random.randint(2, 4)
    elif old_qol_upgraded >= 80:
        qol_bonus = random.randint(3, 5)
    elif old_qol_upgraded >= 70:
        qol_bonus = random.randint(3, 7)
    else:
        qol_bonus = random.randint(7, 15)
    city_to_upgrade['qol'] = min(100, old_qol_upgraded + qol_bonus)

    qol_penalty = random.randint(1, 3)
    penalty_report_lines = []
    for city_name_loop, city_data in player["cities"].items():
        if city_name_loop != city_name:
            old_qol_penalty = city_data['qol']
            city_data['qol'] = max(0, old_qol_penalty - qol_penalty)
            penalty_report_lines.append(f"  • {city_name_loop}: {old_qol_penalty}% ↘️ {city_data['qol']}%")

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"🏙️ <b>{player['country']}</b> улучшил(а) город <b>{city_name}</b> до <b>уровня {city_to_upgrade['level']}</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    game_state.round_events.append({'type': 'CITY_UPGRADED', 'country': player['country']})

    response_text = (
        f"✅ Город **{city_name}** улучшен за **${cost}**!\n\n"
        f"📈 **{city_name}:**\n"
        f"  • Уровень: {city_to_upgrade['level']}\n"
        f"  • Доход: ${city_to_upgrade['income']}\n"
        f"  • Уровень жизни: {old_qol_upgraded}% ↗️ {city_to_upgrade['qol']}% (+{qol_bonus}%)\n\n"
    )
    if penalty_report_lines:
        response_text += (
                f"❗️ Концентрация ресурсов на одном городе вызвала недовольство в других регионах. "
                f"Уровень жизни в остальных городах снизился на {qol_penalty}%:\n"
                + "\n".join(penalty_report_lines) + "\n\n"
        )
    response_text += f"Осталось действий: {player['actions_left']}."

    await message.answer(response_text, parse_mode="Markdown", reply_markup=main_menu(user_id))

    if all(c["qol"] >= 100 for c in player["cities"].values()):
        await message.answer(f"🎉 **ПОЗДРАВЛЯЕМ!** {player['country']} победила в игре, достигнув 100% уровня жизни!")


async def attack_final_step_logic(message: types.Message, target_uid: int, state: FSMContext):
    user_id = message.from_user.id
    city_name_raw = message.text.strip()
    attacker = game_state.players[user_id]
    target_player = game_state.players[target_uid]
    city_name = city_name_raw.replace(" (разрушен)", "").strip()

    if city_name not in target_player["cities"]:
        return await message.answer("Такого города нет у цели.", reply_markup=main_menu(user_id))
    if target_player["cities"][city_name].get("level", 1) == 0:
        return await message.answer("Этот город уже разрушен.", reply_markup=main_menu(user_id))
    if attacker["ready_nukes"] <= 0:
        return await message.answer("Ошибка: нет готовых ракет.", reply_markup=main_menu(user_id))

    attacker["ready_nukes"] -= 1
    attacker["attacked_countries_this_round"].append(target_player['country'])
    attacker["actions_left"] -= 1

    ignore_shields = False
    if game_state.active_global_event and game_state.active_global_event.get('id') == 'SOLAR_FLARE':
        ignore_shields = True

    city_under_attack = target_player["cities"][city_name]
    bunker_level = city_under_attack.get("bunker_level", 0)

    if target_player["shields"] > 0 and not ignore_shields:
        target_player["shields"] -= 1

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🛡️ <b>{attacker['country']}</b> атаковал(а) <b>{target_player['country']}</b>, но удар был отражен щитом."
        await log_action(message.bot, log_text)
        # ---------------------

        qol_penalty_main = random.randint(10, 15)
        qol_penalty_other = random.randint(1, 3)

        if bunker_level > 0:
            bunker_panic_reduction = config.BUNKER_EFFECTS[bunker_level][1]
            qol_penalty_main = int(qol_penalty_main * (1 - bunker_panic_reduction))

        report_lines = []
        for city_loop_name, city_data in target_player["cities"].items():
            old_qol = city_data['qol']
            penalty = qol_penalty_main if city_loop_name == city_name else qol_penalty_other
            city_data['qol'] = max(0, old_qol - penalty)
            report_lines.append(f"  • {city_loop_name}: {old_qol}% ↘️ {city_data['qol']}% (-{penalty}%)")

        game_state.round_events.append(
            {'type': 'ATTACK_SHIELDED', 'attacker': attacker['country'], 'target': target_player['country']})

        await message.answer(f"💥 Атака на {target_player['country']} отражена щитом!", reply_markup=main_menu(user_id))

        defender_message = f"🛡️ **Атака от {attacker['country']} на город {city_name} отражена!**\n\n"
        if bunker_level > 0:
            defender_message += f"✅ Бункер уровня {bunker_level} в городе **значительно снизил панику** среди населения.\n"
        else:
            defender_message += "❗️Новость о приближающейся ракете вызвала панику, снизив уровень жизни.\n"

        defender_message += "Итоговые изменения QoL:\n" + "\n".join(report_lines)
        defender_message += f"\n\nОсталось щитов: {target_player['shields']}."

        try:
            await message.bot.send_message(target_uid, defender_message, parse_mode="Markdown")
        except Exception as e:
            print(f"Error notifying defender about shield: {e}")

    else:
        if ignore_shields and target_player["shields"] > 0:
            await message.answer("💥 **Солнечная вспышка деактивировала щиты! Атака прошла беспрепятственно!**",
                                 parse_mode="Markdown")

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"💥 <b>{attacker['country']}</b> успешно атаковал(а) город <b>{city_name}</b> ({target_player['country']})."
        await log_action(message.bot, log_text)
        # ---------------------

        await message.answer(f"🚀 **Успех! Город {city_name} ({target_player['country']}) беззащитен!**",
                             reply_markup=main_menu(user_id))

        await state.update_data(attacker_id=user_id, target_id=target_uid, city_name=city_name)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Разграбить (Украсть 25% бюджета)", callback_data="corsair_loot")],
            [InlineKeyboardButton(text="🔥 Сжечь дотла (Искалечить экономику)", callback_data="corsair_burn")]
        ])

        await message.bot.send_message(
            user_id,
            f"Какова ваша цель, командир? Город {city_name} в руинах, казна {target_player['country']} открыта.",
            reply_markup=keyboard
        )
        await state.set_state(CorsairChoice.making_choice)


async def negotiation_logic(message: types.Message):
    user_id, text = message.from_user.id, message.text.strip()
    target = next(((uid, p) for uid, p in game_state.players.items() if p.get("country") == text), None)
    if not target:
        return await message.answer("Страна не найдена.", reply_markup=main_menu(user_id))
    target_id, initiator_country = target[0], game_state.players[user_id]["country"]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"neg_accept:{user_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"neg_decline:{user_id}")],
        [InlineKeyboardButton(text="⏳ Отложить", callback_data=f"neg_time:{user_id}")],
    ])
    try:
        await message.bot.send_message(target_id, f"💬 <b>{initiator_country}</b> предлагает переговоры.",
                                       reply_markup=keyboard, parse_mode="HTML")
        await message.answer(f"Предложение отправлено стране {text}.", reply_markup=main_menu(user_id))
    except Exception as e:
        await message.answer(f"Не удалось отправить предложение: {e}", reply_markup=main_menu(user_id))


async def surrender_logic(message: types.Message):
    user_id, text = message.from_user.id, message.text.strip().lower()
    if text == "сбежать":
        player = game_state.players[user_id]
        player["eliminated"] = True
        for city in player["cities"].values(): city["level"], city["income"], city["qol"] = 0, 0, 0

        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🏳️ <b>{player['country']}</b> капитулировал(а) и покинул(а) игру."
        await log_action(message.bot, log_text)
        # ---------------------

        game_state.round_events.append({'type': 'SURRENDERED', 'country': player['country']})
        await message.answer("Вы капитулировали и выбыли из игры.", reply_markup=ReplyKeyboardRemove())
        try:
            await message.bot.send_message(config.ADMIN_ID,
                                           f"🏳️ Игрок {player.get('nickname', 'N/A')} ({player.get('country', 'N/A')}) капитулировал.")
        except Exception as e:
            print(f"Error notifying admin of surrender: {e}")
    else:
        await message.answer("Капитуляция отменена.", reply_markup=main_menu(user_id))


async def toggle_ready_status_logic(message: types.Message):
    user_id = message.from_user.id
    player = game_state.players[user_id]
    player["ready_for_next_round"] = not player.get("ready_for_next_round", False)

    status_text = "Вы подтвердили готовность к следующему раунду." if player[
        "ready_for_next_round"] else "Вы отменили готовность."
    await message.answer(status_text, reply_markup=main_menu(user_id))
    active_players = [p for uid, p in game_state.players.items() if
                      p.get("country") and not p.get("eliminated") and uid != config.ADMIN_ID]
    if active_players and all(p.get("ready_for_next_round") for p in active_players):
        try:
            await message.bot.send_message(config.ADMIN_ID, "✅ Все активные игроки готовы к следующему раунду!")
        except Exception as e:
            print(f"Error notifying admin 'all ready': {e}")


async def call_admin_logic(message: types.Message):
    user_id = message.from_user.id
    ban_until = game_state.call_admin_bans.get(user_id)
    if ban_until and time.time() < ban_until:
        return await message.answer(f"Вы забанены. Осталось {round(ban_until - time.time())} сек.")
    user_info = game_state.players.get(user_id, {})
    text = (f"❗️ <b>Вызов админа!</b>\n"
            f"Игрок: @{message.from_user.username or 'N/A'}\n"
            f"Страна: {user_info.get('country', 'N/A')}\n"
            f"User ID: `{user_id}`")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сейчас зайду", callback_data=f"admin_call_now:{user_id}")],
        [InlineKeyboardButton(text="⏳ Буду через минуту", callback_data=f"admin_call_minute:{user_id}")],
        [InlineKeyboardButton(text="👉 Зайди ко мне", callback_data=f"admin_call_come:{user_id}")],
        [InlineKeyboardButton(text="🚫 Бан на 2 мин", callback_data=f"admin_call_ban:{user_id}")]
    ])
    try:
        await message.bot.send_message(config.ADMIN_ID, text, parse_mode="HTML", reply_markup=keyboard)
        await message.answer("Запрос отправлен администратору.")
    except Exception as e:
        await message.answer("Не удалось отправить запрос.")
        print(f"Error calling admin: {e}")


async def negotiation_response_logic(callback: types.CallbackQuery):
    action, initiator_id_str = callback.data.split(":")
    initiator_id, responder_id = int(initiator_id_str), callback.from_user.id
    if responder_id not in game_state.players or initiator_id not in game_state.players:
        return await callback.answer("Ошибка: один из игроков не найден.", show_alert=True)
    responder_country = game_state.players[responder_id]["country"]
    initiator_country = game_state.players[initiator_id]["country"]
    response_map = {
        "neg_accept": (f"✅ <b>{responder_country}</b> принимает ваше предложение.",
                       f"Вы приняли предложение от <b>{initiator_country}</b>."),
        "neg_time": (f"⏳ <b>{responder_country}</b> отложила переговоры.",
                     f"Вы отложили переговоры с <b>{initiator_country}</b>."),
        "neg_decline": (f"❌ <b>{responder_country}</b> отклонила ваше предложение.",
                        f"Вы отклонили предложение от <b>{initiator_country}</b>.")
    }
    initiator_msg, responder_msg = response_map.get(action, (None, None))
    try:
        await callback.bot.send_message(initiator_id, initiator_msg, parse_mode="HTML")
    except Exception as e:
        print(f"Could not send negotiation response to initiator {initiator_id}: {e}")
    await callback.message.edit_text(responder_msg, parse_mode="HTML", reply_markup=None)
    await callback.answer()