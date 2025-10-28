# game_state.py

# --- Состояние игры (внутри-игровые данные) ---
players = {}
attack_sessions = {}
admin_attack_session = {}
admin_modify_session = {}
admin_broadcast_session = {}
negotiation_sessions = {}
nickname_sessions = {}
surrender_sessions = {}
call_admin_bans = {}
event_cooldowns = {}

current_round = 1
round_end_time = None
round_notifications = {}

round_events = []
active_global_event = None
is_processing_next_round = False