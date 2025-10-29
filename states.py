# states.py

from aiogram.fsm.state import State, StatesGroup

class Registration(StatesGroup):
    choosing_country = State()
    entering_nickname = State()

class Attack(StatesGroup):
    choosing_target = State()
    choosing_city = State()

class AdminAttack(StatesGroup):
    choosing_target = State()
    choosing_city = State()

class AdminModify(StatesGroup):
    choosing_country = State()
    choosing_city = State()
    choosing_action = State()

class AdminBroadcast(StatesGroup):
    choosing_target = State()
    typing_message = State()

class Negotiation(StatesGroup):
    choosing_target = State()

class Surrender(StatesGroup):
    confirming = State()

class Upgrade(StatesGroup):
    choosing_city = State()

class LendLease(StatesGroup):
    choosing_target = State()
    entering_amount = State()
    confirming = State()

class SocialProgram(StatesGroup):
    choosing_city = State()

class GlobalEvent(StatesGroup):
    entering_contribution = State()
    entering_investment = State()
    confirming_black_market = State()

class Bunker(StatesGroup):
    choosing_city = State()

class CorsairChoice(StatesGroup):
    making_choice = State()

class Espionage(StatesGroup):
    choosing_target = State()

class AdminTools(StatesGroup):
    choosing_event_to_force = State()