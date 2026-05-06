from aiogram.fsm.state import State, StatesGroup


class UserFlow(StatesGroup):
    waiting_resume = State()
    waiting_vacancy = State()
    updating_resume = State()
