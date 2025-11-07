# admin_handlers.py

import random
import time
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)

# Импортируем наши модули
import config
import game_state
from keyboards import main_menu
# --- ИЗМЕНЕННЫЕ ИМПОРТЫ ---
from handlers import log_action, generate_newspaper_report, format_admin_message  # Добавлен log_action и другие
# ---------------------------
from filters import PlayerFilter
from states import AdminAttack, AdminModify, AdminBroadcast, AdminTools
from global_events import EVENT_CLASSES

admin_router = Router()


# =====================================================================================
# --- АДМИНСКИЕ FSM ПРОЦЕССЫ ---
# =====================================================================================

# --- FSM ВЫЗОВА СОБЫТИЯ ---
async def admin_choose_event_start(message: types.Message, state: FSMContext):
    """Начинает процесс выбора события для принудительного запуска."""
    if game_state.active_global_event:
        event_name = EVENT_CLASSES.get(game_state.active_global_event['id'],
                                       type('', (object,), {'name': 'Неизвестное событие'})).name
        return await message.answer(f"Тест невозможен: уже активно событие '{event_name}'.")

    kb_rows = [[KeyboardButton(text=f"{event.name}")] for event in EVENT_CLASSES.values()]
    kb_rows.append([KeyboardButton(text="Отмена")])
    keyboard = ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True)

    await message.answer("Выберите событие, которое хотите запустить:", reply_markup=keyboard)
    await state.set_state(AdminTools.choosing_event_to_force)


@admin_router.message(AdminTools.choosing_event_to_force)
async def admin_force_event_logic(message: types.Message, state: FSMContext):
    """Обрабатывает выбор админа и запускает выбранное событие."""
    await state.clear()
    text = message.text.strip()

    if text == "Отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(config.ADMIN_ID))

    chosen_event_class = next((event_class for event_class in EVENT_CLASSES.values() if event_class.name == text), None)

    if not chosen_event_class:
        return await message.answer("Событие не найдено. Попробуйте еще раз.", reply_markup=main_menu(config.ADMIN_ID))

    new_event_data = {
        "id": chosen_event_class.ID,
        "progress": 0,
        "rounds_left": chosen_event_class.duration
    }
    game_state.active_global_event = new_event_data
    game_state.event_cooldowns[chosen_event_class.ID] = 3

    event_object = chosen_event_class(message.bot, new_event_data)
    start_msg = await event_object.get_start_message()

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"⚙️ <b>Администратор</b> вручную запустил событие: <b>{chosen_event_class.name}</b>."
    await log_action(message.bot, log_text)
    await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
# --- FSM АДМИН-АТАКИ ---
async def admin_attack_start(message: types.Message, state: FSMContext):
    targets = [p["country"] for uid, p in game_state.players.items() if uid != config.ADMIN_ID and p.get("country")]
    if not targets:
        return await message.answer("Нет доступных целей.", reply_markup=main_menu(config.ADMIN_ID))
    kb_rows = [[KeyboardButton(text=t)] for t in targets] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выбери страну-цель для админ-удара:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(AdminAttack.choosing_target)


@admin_router.message(AdminAttack.choosing_target)
async def admin_attack_choose_target(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Админ-атака отменена.", reply_markup=main_menu(config.ADMIN_ID))
    target_uid = next((uid for uid, pl in game_state.players.items() if pl.get("country") == text), None)
    if not target_uid:
        return await message.answer("Страна не найдена.")
    await state.update_data(target_uid=target_uid)
    target_player = game_state.players[target_uid]
    kb_rows = [[KeyboardButton(text=c + (" (разрушен)" if d.get("level", 1) == 0 else ""))] for c, d in
               target_player["cities"].items()]
    await message.answer(f"Цель — {text}. Выбери город для удара:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows + [[KeyboardButton(text="Отмена")]],
                                                          resize_keyboard=True))
    await state.set_state(AdminAttack.choosing_city)


@admin_router.message(AdminAttack.choosing_city)
async def admin_attack_choose_city(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    target_uid = user_data.get("target_uid")
    target_player = game_state.players[target_uid]
    city_name = message.text.strip().replace(" (разрушен)", "")
    await state.clear()
    if message.text.strip() == "Отмена":
        return await message.answer("Админ-атака отменена.", reply_markup=main_menu(config.ADMIN_ID))
    if city_name not in target_player["cities"]:
        return await message.answer("Такого города нет у цели.")
    if target_player["cities"][city_name].get("level", 1) == 0:
        return await message.answer("Этот город уже разрушен.")
    result_text = ""
    log_text = ""  # Переменная для лога
    if target_player["shields"] > 0:
        target_player["shields"] -= 1
        result_text = f"⚡ Админ-атака на {city_name} отражена щитом! (Осталось: {target_player['shields']})"
        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🛡️ <b>Администратор</b> атаковал город <b>{city_name}</b> ({target_player['country']}), но удар был отражен щитом."
        # ---------------------
    else:
        city = target_player["cities"][city_name]
        city["level"], city["income"], city["qol"] = 0, 0, 0
        result_text = f"💥 Админ разрушил город {city_name} в стране {target_player['country']}."
        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"💥 <b>Администратор</b> разрушил город <b>{city_name}</b> ({target_player['country']})."
        # ---------------------

    await log_action(message.bot, log_text)  # Отправляем лог
    await message.answer(result_text, reply_markup=main_menu(config.ADMIN_ID))
    try:
        await message.bot.send_message(target_uid, f"⚡ Ваша страна подверглась админ-атаке! {result_text}")
    except Exception as e:
        print(f"Error notifying player about admin attack: {e}")


# --- FSM ОТПРАВКИ СООБЩЕНИЯ ---
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    active_countries = [p['country'] for uid, p in game_state.players.items() if
                        p.get('country') and uid != config.ADMIN_ID]
    kb_rows = [[KeyboardButton(text="Всем игрокам")]] + [[KeyboardButton(text=c)] for c in active_countries] + [
        [KeyboardButton(text="Отмена")]]
    await message.answer("Кому отправить сообщение?",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(AdminBroadcast.choosing_target)


@admin_router.message(AdminBroadcast.choosing_target)
async def admin_broadcast_choose_target(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Отправка сообщения отменена.", reply_markup=main_menu(config.ADMIN_ID))
    if text == "Всем игрокам":
        await state.update_data(target='all', target_name='Всем игрокам')
    else:
        target_uid = next((uid for uid, pl in game_state.players.items() if pl.get("country") == text), None)
        if not target_uid:
            return await message.answer("Страна не найдена.")
        await state.update_data(target=target_uid, target_name=text)
    await message.answer("Теперь введите текст сообщения.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AdminBroadcast.typing_message)


@admin_router.message(AdminBroadcast.typing_message)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    target = user_data.get('target')
    target_name = user_data.get('target_name', 'N/A')
    formatted_message = format_admin_message(message.text)
    await state.clear()

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = f"✉️ <b>Администратор</b> отправил сообщение для: <b>{target_name}</b>.\nТекст: <i>{message.text}</i>"
    await log_action(message.bot, log_text)
    # ---------------------

    if target == 'all':
        for uid, p in game_state.players.items():
            if p.get("country") and not p.get("eliminated") and uid != config.ADMIN_ID:
                try:
                    await message.bot.send_message(uid, formatted_message, parse_mode="HTML")
                except Exception as e:
                    print(f"Error in broadcast to {uid}: {e}")
        await message.answer("Сообщение отправлено всем игрокам.", reply_markup=main_menu(config.ADMIN_ID))
    else:
        try:
            await message.bot.send_message(target, formatted_message, parse_mode="HTML")
            await message.answer("Сообщение отправлено игроку.", reply_markup=main_menu(config.ADMIN_ID))
        except Exception as e:
            await message.answer(f"Ошибка отправки: {e}", reply_markup=main_menu(config.ADMIN_ID))


# --- FSM ИЗМЕНЕНИЯ ГОРОДА ---
async def admin_modify_start(message: types.Message, state: FSMContext):
    active_countries = [p['country'] for uid, p in game_state.players.items() if
                        p.get('country') and uid != config.ADMIN_ID]
    if not active_countries:
        return await message.answer("Нет активных стран.", reply_markup=main_menu(config.ADMIN_ID))
    kb_rows = [[KeyboardButton(text=c)] for c in active_countries] + [[KeyboardButton(text="Отмена")]]
    await message.answer("Выберите страну для изменения:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(AdminModify.choosing_country)


@admin_router.message(AdminModify.choosing_country)
async def admin_modify_choose_country(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Действие отменено.", reply_markup=main_menu(config.ADMIN_ID))
    target_uid = next((uid for uid, pl in game_state.players.items() if pl.get("country") == text), None)
    if not target_uid:
        return await message.answer("Страна не найдена.")
    await state.update_data(target_uid=target_uid)
    target_player = game_state.players[target_uid]
    kb_rows = [[KeyboardButton(text=f"{name} (ур. {data.get('level', 0)})")] for name, data in
               target_player['cities'].items()] + [[KeyboardButton(text="Отмена")]]
    await message.answer(f"Выберите город у {target_player['country']}:",
                         reply_markup=ReplyKeyboardMarkup(keyboard=kb_rows, resize_keyboard=True))
    await state.set_state(AdminModify.choosing_city)


@admin_router.message(AdminModify.choosing_city)
async def admin_modify_choose_city(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "Отмена":
        await state.clear()
        return await message.answer("Действие отменено.", reply_markup=main_menu(config.ADMIN_ID))

    city_name = text.split(" (ур.")[0]
    user_data = await state.get_data()
    target_uid = user_data.get('target_uid')
    target_player = game_state.players[target_uid]

    if city_name not in target_player['cities']:
        return await message.answer("Город не найден.")

    await state.update_data(city_name=city_name)
    city = target_player['cities'][city_name]
    actions = []
    if city['level'] < config.MAX_CITY_LEVEL: actions.append([KeyboardButton(text="Улучшить на 1")])
    if city['level'] > 0: actions.append([KeyboardButton(text="Ухудшить на 1")])

    if not actions:
        await state.clear()
        return await message.answer(f"Для города {city_name} нет действий.", reply_markup=main_menu(config.ADMIN_ID))

    await message.answer(f"Что сделать с городом {city_name} (ур: {city['level']})?",
                         reply_markup=ReplyKeyboardMarkup(keyboard=actions + [[KeyboardButton(text="Отмена")]],
                                                          resize_keyboard=True))
    await state.set_state(AdminModify.choosing_action)


@admin_router.message(AdminModify.choosing_action)
async def admin_modify_perform_action(message: types.Message, state: FSMContext):
    text = message.text.strip()
    user_data = await state.get_data()
    target_uid = user_data.get('target_uid')
    target_player = game_state.players[target_uid]
    city_name = user_data.get('city_name')
    city = target_player['cities'][city_name]
    old_level = city['level']
    await state.clear()

    if text == "Отмена":
        return await message.answer("Действие отменено.", reply_markup=main_menu(config.ADMIN_ID))
    if text == "Улучшить на 1" and city['level'] < config.MAX_CITY_LEVEL:
        city['level'] += 1
    elif text == "Ухудшить на 1" and city['level'] > 0:
        city['level'] -= 1
    else:
        return await message.answer("Неверная команда.", reply_markup=main_menu(config.ADMIN_ID))

    city['income'] = city['level'] * 500 if city['level'] > 0 else 0
    if text == "Улучшить на 1":
        city['qol'] = min(100, city['qol'] + random.randint(7, 15))
    else:
        city['qol'] = max(0, city['qol'] - random.randint(7, 15)) if city['level'] > 0 else 0

    # --- ЛОГ ДЕЙСТВИЯ ---
    action_word = "улучшил" if text == "Улучшить на 1" else "ухудшил"
    log_text = f"🛠️ <b>Администратор</b> {action_word} город <b>{city_name}</b> ({target_player['country']}) с {old_level} до {city['level']} уровня."
    await log_action(message.bot, log_text)
    # ---------------------

    await message.answer(f"Город {city_name} изменен. Новый уровень: {city['level']}.",
                         reply_markup=main_menu(config.ADMIN_ID))
    try:
        await message.bot.send_message(target_uid,
                                       f"🛠 Администратор изменил уровень вашего города {city_name} на {city['level']}!")
    except Exception as e:
        print(f"Ошибка уведомления об изменении города: {e}")


# --- ОБРАБОТКА ОТВЕТОВ НА ВЫЗОВ ---
@admin_router.callback_query(F.data.startswith("admin_call_"))
async def handle_admin_call_response(callback: types.CallbackQuery):
    action, player_id_str = callback.data.split(":")
    player_id = int(player_id_str)
    if player_id not in game_state.players:
        return await callback.answer("Игрок не найден.", show_alert=True)
    response_map = {
        "admin_call_now": ("Сейчас зайду.", "Администратор сейчас зайдет."),
        "admin_call_minute": ("Буду через минуту.", "Администратор будет через минуту."),
        "admin_call_come": ("Зайди ко мне.", "Администратор просит вас зайти к нему."),
        "admin_call_ban": ("Игрок забанен.",
                           f"Вы заблокированы от вызова админа на {config.ADMIN_CALL_BAN_DURATION // 60} минуты.")
    }
    admin_response, player_notification = response_map.get(action, (None, None))
    if action == "admin_call_ban":
        game_state.call_admin_bans[player_id] = time.time() + config.ADMIN_CALL_BAN_DURATION
    await callback.message.edit_text(f"{callback.message.text}\n\n✅ <b>Ответ:</b> {admin_response}",
                                     parse_mode="HTML", reply_markup=None)
    try:
        await callback.bot.send_message(player_id, f"🔔 <b>Ответ от админа:</b>\n{player_notification}",
                                        parse_mode="HTML")
    except Exception as e:
        print(f"Не удалось отправить ответ игроку {player_id}: {e}")
    await callback.answer()


# =====================================================================================
# --- ГЛАВНОЕ МЕНЮ И ИНДИВИДУАЛЬНЫЕ ОБРАБОТЧИКИ КНОПОК ---
# =====================================================================================

@admin_router.message(PlayerFilter(is_admin=True), F.text == "Админка")
async def admin_panel_menu(message: types.Message, state: FSMContext):
    """Показывает главное меню админки."""
    await state.clear()
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="Начать игру (1-й раунд)"), KeyboardButton(text="Начать следующий раунд")],
        [KeyboardButton(text="Просмотреть статистику всех"), KeyboardButton(text="Список готовых игроков")],
        [KeyboardButton(text="Изменить уровень города"), KeyboardButton(text="Админ-удар")],
        [KeyboardButton(text="Отправить сообщение"), KeyboardButton(text="Проверить таймер")],
        [KeyboardButton(text="📰 Сводка новостей (для себя)"), KeyboardButton(text="Разослать газету")],
        [KeyboardButton(text="⚙️ Вызвать событие (Тест)"), KeyboardButton(text="Рестарт игры")],
        [KeyboardButton(text="Назад в главное меню")]
    ], resize_keyboard=True)
    await message.answer("Админка:", reply_markup=keyboard)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Начать игру (1-й раунд)")
async def handle_admin_start_game(message: types.Message, state: FSMContext):
    await admin_start_game_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Начать следующий раунд")
async def handle_admin_next_round(message: types.Message, state: FSMContext):
    await admin_next_round_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Просмотреть статистику всех")
async def handle_admin_show_all_stats(message: types.Message, state: FSMContext):
    await admin_show_all_stats_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Список готовых игроков")
async def handle_admin_show_ready_list(message: types.Message, state: FSMContext):
    await admin_show_ready_list_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Изменить уровень города")
async def handle_admin_modify_start(message: types.Message, state: FSMContext):
    await admin_modify_start(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Админ-удар")
async def handle_admin_attack_start(message: types.Message, state: FSMContext):
    await admin_attack_start(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Отправить сообщение")
async def handle_admin_broadcast_start(message: types.Message, state: FSMContext):
    await admin_broadcast_start(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Проверить таймер")
async def handle_admin_check_timer(message: types.Message, state: FSMContext):
    await admin_check_timer_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "📰 Сводка новостей (для себя)")
async def handle_admin_show_newspaper_private(message: types.Message, state: FSMContext):
    await show_newspaper_logic_wrapper(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Разослать газету")
async def handle_admin_broadcast_newspaper(message: types.Message, state: FSMContext):
    newspaper_text = await generate_newspaper_report()
    if not newspaper_text:
        return await message.answer("🗞 Новостей для рассылки нет.")
    sent_count = 0
    for uid, p in game_state.players.items():
        if p.get("country") and not p.get("eliminated") and uid != config.ADMIN_ID:
            try:
                await message.bot.send_message(uid, newspaper_text, parse_mode="Markdown")
                sent_count += 1
            except Exception as e:
                print(f"Error broadcasting newspaper to {uid}: {e}")
    await message.answer(f"✅ Газета успешно разослана {sent_count} игрокам.")


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Рестарт игры")
async def handle_admin_restart_game(message: types.Message, state: FSMContext):
    await admin_restart_game_logic(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "⚙️ Вызвать событие (Тест)")
async def handle_admin_choose_event(message: types.Message, state: FSMContext):
    await admin_choose_event_start(message, state)


@admin_router.message(PlayerFilter(is_admin=True), F.text == "Назад в главное меню")
async def handle_admin_back_to_main(message: types.Message, state: FSMContext):
    await message.answer("Главное меню", reply_markup=main_menu(message.from_user.id))


# =====================================================================================
# --- АДМИНСКИЕ ЛОГИЧЕСКИЕ БЛОКИ ---
# =====================================================================================

def calculate_qol_bonus(city_data):
    qol = city_data.get('qol', 0)
    is_ruined = city_data.get('ruined', False)

    base_multiplier = 1.0
    if qol >= 90:
        base_multiplier = 1.30
    elif qol >= 80:
        base_multiplier = 1.20
    elif qol > 50:
        base_multiplier = 1 + ((qol - 50) / 100 * 0.5)  # Плавный бонус
    elif qol < 50:
        base_multiplier = 1 - ((50 - qol) / 100)  # Плавный штраф

    if is_ruined and base_multiplier > 1.0:
        bonus = base_multiplier - 1.0
        return 1.0 + (bonus / 2)

    return base_multiplier


async def admin_start_game_logic(message: types.Message, state: FSMContext):
    if game_state.round_end_time is not None:
        return await message.answer("Игра уже идет.", reply_markup=main_menu(config.ADMIN_ID))
    game_state.round_end_time = time.time() + config.ROUND_DURATION
    game_state.round_notifications = {'5_min': False, '3_min': False, '1_min': False, 'end': False}

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = "🎉 <b>Игра началась!</b> Администратор запустил <b>Раунд 1</b>."
    await log_action(message.bot, log_text)
    # ---------------------

    msg = "🎉 <b>Игра началась! Раунд 1 запущен.</b>"
    for uid, p in game_state.players.items():
        if p.get("country") and not p.get("eliminated") and uid != config.ADMIN_ID:
            try:
                await message.bot.send_message(uid, msg, parse_mode="HTML")
            except Exception as e:
                print(f"Error broadcasting start game to {uid}: {e}")
    await message.answer("✅ Игра началась!", reply_markup=main_menu(config.ADMIN_ID))


async def admin_next_round_logic(message: types.Message, state: FSMContext):
    if game_state.is_processing_next_round:
        return await message.answer("⏳ Пожалуйста, подождите, идёт обработка предыдущего раунда...")

    game_state.is_processing_next_round = True
    try:
        # --- ЛОГ ДЕЙСТВИЯ ---
        log_text = f"🌐 <b>Администратор</b> запустил <b>Раунд {game_state.current_round + 1}</b>."
        await log_action(message.bot, log_text)
        # ---------------------

        cooldowns_to_remove = []
        for event_id, rounds_left in game_state.event_cooldowns.items():
            game_state.event_cooldowns[event_id] -= 1
            if game_state.event_cooldowns[event_id] <= 0:
                cooldowns_to_remove.append(event_id)
        for event_id in cooldowns_to_remove:
            del game_state.event_cooldowns[event_id]

        if game_state.active_global_event:
            game_state.active_global_event['rounds_left'] -= 1
            if game_state.active_global_event['rounds_left'] <= 0:
                event_id = game_state.active_global_event['id']
                event_class = EVENT_CLASSES[event_id]
                event_object = event_class(message.bot, game_state.active_global_event)
                await event_object.on_fail(game_state.players)
                log_text = f"⌛️ Событие <b>'{event_class.name}'</b> провалилось по истечению времени."
                await log_action(message.bot, log_text)
                await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
                game_state.event_cooldowns[event_id] = 3
                game_state.active_global_event = None


        elif random.random() < 0.33:

            available_events = [eid for eid in EVENT_CLASSES.keys() if eid not in game_state.event_cooldowns]

            if available_events:
                world_state = get_world_state_analysis()
                event_weights = calculate_event_weights(available_events, world_state)
                event_id = random.choices(available_events, weights=event_weights, k=1)[0]

                event_class = EVENT_CLASSES[event_id]
                new_event_data = {
                    "id": event_id,
                    "progress": 0,
                    "rounds_left": event_class.duration

                }
                game_state.active_global_event = new_event_data
                game_state.event_cooldowns[event_id] = 3
                event_object = event_class(message.bot, new_event_data)
                start_msg = await event_object.get_start_message()

                log_text = f"🌍 <b>Началось новое событие: {event_class.name}</b> (Выбрано на основе ситуации в мире)."
                await log_action(message.bot, log_text)
                await message.bot.send_message(config.ADMIN_ID, f"🔔 (Для админа) {log_text}", parse_mode="HTML")
                for uid, p in game_state.players.items():
                    if p.get("country") and not p.get("eliminated"):
                        await message.bot.send_message(uid, start_msg, parse_mode="Markdown")

        game_state.round_events.clear()
        game_state.current_round += 1
        game_state.round_end_time = time.time() + config.ROUND_DURATION
        game_state.round_notifications = {'5_min': False, '3_min': False, '1_min': False, 'end': False}

        for uid, p in game_state.players.items():
            if not p.get('country') or p.get('eliminated'): continue

            p['ready_nukes'] += p.get('pending_nukes', 0)
            p['pending_nukes'] = 0
            p['actions_left'] = 5 if game_state.current_round == 10 else 4
            p['attacked_countries_this_round'] = []
            p['shields_built_this_round'] = 0
            p['upgrades_this_round'] = 0
            p['social_programs_this_round'] = 0
            p['ready_for_next_round'] = False

            effects_to_remove = []
            if 'temp_effects' in p:
                for effect_name, effect_data in p['temp_effects'].items():
                    effect_data['rounds_left'] -= 1
                    if effect_data['rounds_left'] <= 0:
                        effects_to_remove.append(effect_name)
                        try:
                            await message.bot.send_message(uid, f"📈 Эффект '{effect_name}' в вашей стране закончился.")
                        except Exception:
                            pass
                for effect_name in effects_to_remove:
                    del p['temp_effects'][effect_name]

            total_income = 0
            income_details = []

            global_income_modifier = 1.0
            if game_state.active_global_event:
                event_id = game_state.active_global_event['id']
                event_class = EVENT_CLASSES[event_id]
                if hasattr(event_class, 'on_start_effect'):
                    effect = event_class.on_start_effect
                    if effect and effect.get('type') == 'income_modifier':
                        global_income_modifier = 1.0 + effect.get('value', 0)

            temp_income_modifier = 1.0
            if 'recession' in p.get('temp_effects', {}):
                temp_income_modifier = 0.5

            permanent_modifier = p.get('income_modifier', 1.0)

            for city_name, city_data in p.get('cities', {}).items():
                base_income = city_data.get('income', 0)
                qol_multiplier = calculate_qol_bonus(city_data)

                final_income = int(
                    base_income * global_income_modifier * permanent_modifier * temp_income_modifier * qol_multiplier)
                total_income += final_income

                total_multiplier = global_income_modifier * permanent_modifier * temp_income_modifier * qol_multiplier
                bonus_percent = int((total_multiplier - 1) * 100)
                if bonus_percent != 0:
                    sign = "+" if bonus_percent > 0 else ""
                    income_details.append(
                        f"  • {city_name}: ${base_income} ({sign}{bonus_percent}%) -> ${final_income}")
                else:
                    income_details.append(f"  • {city_name}: ${base_income}")

            p['budget'] += total_income

            income_report = f"Доход: **${total_income}**.\n"
            if income_details:
                income_report += "*Детализация дохода:*\n" + "\n".join(income_details) + "\n"

            msg = (f"🌐 **Начался раунд {game_state.current_round}!**\n\n"
                   f"{income_report}\n"
                   f"Ваш бюджет: **${p['budget']}**")
            if game_state.current_round == 10: msg += "\n\n🎉 **Бонус:** Вы получаете +1 дополнительное действие!"

            try:
                await message.bot.send_message(uid, msg, parse_mode="Markdown", reply_markup=main_menu(uid))
            except Exception as e:
                print(f"Error sending next round message to {uid}: {e}")

        await message.answer(f"✅ Раунд {game_state.current_round} начат!", reply_markup=main_menu(config.ADMIN_ID))

    finally:
        game_state.is_processing_next_round = False


def get_world_state_analysis():
    """
    Анализирует game_state и возвращает простую сводку о состоянии мира.
    """
    total_nukes = 0
    total_cities = 0
    total_qol = 0

    # Собираем данные только по живым игрокам
    active_players = [p for p in game_state.players.values() if p.get("country") and not p.get("eliminated")]
    if not active_players:
        # Если игроков нет, возвращаем "мирное" состояние
        return {'total_nukes': 0, 'avg_qol': 70}

    for player in active_players:
        # Считаем общее количество ракет в производстве и готовых
        total_nukes += player.get('ready_nukes', 0) + player.get('pending_nukes', 0)

        # Считаем средний уровень жизни
        player_cities = player.get('cities', {}).values()
        if player_cities:
            for city in player_cities:
                total_qol += city.get('qol', 50)
                total_cities += 1

    # Рассчитываем средние значения
    avg_qol = (total_qol / total_cities) if total_cities > 0 else 70

    return {
        'total_nukes': total_nukes,
        'avg_qol': avg_qol
    }


def calculate_event_weights(available_events, world_state):
    weights = []

    total_nukes = world_state.get('total_nukes', 0)
    avg_qol = world_state.get('avg_qol', 70)

    for event_id in available_events:
        base_weight = 10  # Базовый шанс

        if event_id == "PANDEMIC":
            if avg_qol < 40:
                base_weight += 50
            if avg_qol > 80:
                base_weight = 1

        if event_id == "ENERGY_CRISIS":
            if total_nukes > 5:
                base_weight += 60
            if total_nukes == 0:
                base_weight = 1


        if event_id == "TECH_BREAKTHROUGH":
            if avg_qol > 75:
                base_weight += 40
            if total_nukes > 3:
                base_weight = 1

        if event_id == "BLACK_MARKET":
            if total_nukes > 0:
                base_weight += 20
            if avg_qol < 50:
                base_weight += 20


        if event_id == "SOLAR_FLARE":
            base_weight = 5

        if event_id == "GLOBAL_ESPIONAGE":
            if total_nukes > 2:
                base_weight += 30

        weights.append(max(1, base_weight))

    return weights
async def admin_restart_game_logic(message: types.Message, state: FSMContext):
    admin_data = game_state.players.get(config.ADMIN_ID)
    game_state.players.clear()
    if admin_data: game_state.players[config.ADMIN_ID] = admin_data
    game_state.current_round, game_state.round_end_time = 1, None
    game_state.round_events.clear()
    game_state.active_global_event = None

    # --- ЛОГ ДЕЙСТВИЯ ---
    log_text = "🔥 <b>Администратор</b> полностью перезапустил игру. Все данные сброшены."
    await log_action(message.bot, log_text)
    # ---------------------

    await message.answer("🔥 Игра полностью сброшена!", reply_markup=main_menu(config.ADMIN_ID))


async def admin_show_all_stats_logic(message: types.Message, state: FSMContext):
    active_players = [p for p in game_state.players.values() if p.get('country')]
    if not active_players:
        return await message.answer("Нет зарегистрированных игроков.")
    stats_text = "📊 <b>Статистика всех стран:</b>\n\n"
    for uid, p in game_state.players.items():
        if not p.get('country'): continue
        display_text = f"<b>{p['country']} ({p.get('nickname', 'N/A')})</b>"
        stats_text += (f"{display_text} (ID: <code>{uid}</code>)\n"
                       f"💰 Бюджет: {p.get('budget', 0)}\n"
                       f"🚀 Ракеты: {p.get('ready_nukes', 0)}/{p.get('pending_nukes', 0)}\n"
                       f"🛡 Щиты: {p.get('shields', 0)}\n")
        for city, data in p.get('cities', {}).items():
            stats_text += f"  • {city}: ур. {data['level']}, QoL {data['qol']}%\n"
        stats_text += "—————————\n"
    await message.answer(stats_text, parse_mode="HTML")


async def admin_show_ready_list_logic(message: types.Message, state: FSMContext):
    active_players = [p for uid, p in game_state.players.items() if
                      p.get("country") and not p.get("eliminated") and uid != config.ADMIN_ID]
    if not active_players:
        return await message.answer("Нет активных игроков.")
    ready = [p["country"] for p in active_players if p.get("ready_for_next_round")]
    not_ready = [p["country"] for p in active_players if not p.get("ready_for_next_round")]
    text = "📊 <b>Статус готовности:</b>\n\n"
    if ready: text += f"✅ Готовы ({len(ready)}):\n" + ", ".join(ready) + "\n\n"
    if not_ready: text += f"❌ Не готовы ({len(not_ready)}):\n" + ", ".join(not_ready) + "\n"
    await message.answer(text, parse_mode="HTML")


async def admin_check_timer_logic(message: types.Message, state: FSMContext):
    if game_state.round_end_time is None:
        return await message.answer("Таймер раунда неактивен.")
    time_left = round(game_state.round_end_time - time.time())
    status = f"<b>Статус таймера:</b>\n\n<b>Осталось:</b> {time_left} сек\n\n<b>Уведомления:</b>\n"
    for key, readable in [('5_min', '5 минут'), ('3_min', '3 минуты'), ('1_min', '1 минута'), ('end', 'Конец')]:
        status += f"• {readable}: {'✅' if game_state.round_notifications.get(key) else '❌'}\n"
    await message.answer(status, parse_mode="HTML")


async def show_newspaper_logic_wrapper(message: types.Message, state: FSMContext):
    newspaper_text = await generate_newspaper_report()
    if newspaper_text:
        await message.answer(newspaper_text, parse_mode="Markdown")
    else:
        await message.answer("🗞 В мире пока затишье. Новостей по итогам прошлого раунда нет.")