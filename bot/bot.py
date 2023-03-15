import logging

from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy_utils import create_database, database_exists

from bot.controllers import ChatGPTController, MenuController
from bot.handlers import register_chatgpt_handlers, register_menu
from bot.middlewares import ObjectsTransferMiddleware
from bot.models import UsersRepository
from bot.models.orm.base import Base
from config import config

logger = logging.getLogger("telegram_bot")


def init_repository(session):
    return {
        "users": UsersRepository(session).dict(),
    }


def init_db(bot: Bot):
    logger.debug("Initing database, session and repository")
    login_data = (
        f"{config.db.login}:{config.db.password}@{config.db.host}:{config.db.port}"
    )
    url = f"postgresql://{login_data}/{config.db.database}"
    engine = create_engine(url)
    if not database_exists(url):
        create_database(url)

    Base.metadata.create_all(engine)
    Base.metadata.bind = engine
    session = Session(engine)
    bot["session"] = session
    bot["db_repository"] = init_repository(session)


def register_controllers(bot: Bot):
    logger.debug("Registering controllers.")
    bot["chatgpt_controller"] = ChatGPTController()
    bot["menu_controller"] = MenuController(bot["session"], bot["db_repository"])


def register_handlers(dp: Dispatcher):
    logger.debug("Registering handlers.")
    register_chatgpt_handlers(dp, dp.bot["chatgpt_controller"])
    register_menu(dp)


def register_middlewares(dp: Dispatcher):
    logger.debug("Registering middlewares.")
    dp.setup_middleware(ObjectsTransferMiddleware())


async def start_bot():
    logger.debug("Telegram bot setup has started.")

    bot = Bot(token=config.bot_token, parse_mode="HTML")
    dp = Dispatcher(bot, storage=MemoryStorage())

    bot["dp"] = dp

    init_db(bot)

    register_controllers(bot)
    register_handlers(dp)
    register_middlewares(dp)

    logger.debug("Telegram bot setup was completed successfully.")

    # start
    try:
        await dp.start_polling()
    finally:
        await dp.storage.close()
        await dp.storage.wait_closed()
