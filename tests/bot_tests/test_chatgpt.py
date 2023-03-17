import json
import time

from pyrogram.client import Client
from pyrogram.types import Message
from sqlalchemy.orm import Session

from bot.controllers.bot import MenuController
from bot.controllers.chatgpt import ChatGPTController
from bot.models import ConversationRequestsRepository, ConversationsRepository
from bot.models.users import User
from config import config

MAX_WAIT = 10


def wait(fn):
    async def modified_fn(*args, **kwargs):
        start_time = time.time()
        while True:
            try:
                return await fn(*args, **kwargs)
            except AssertionError as exc:
                if time.time() - start_time >= MAX_WAIT:
                    raise exc
                time.sleep(0.5)

    return modified_fn


async def get_last_message(client, chat_name) -> Message:
    async for message in client.get_chat_history(chat_name, limit=1):
        return message


@wait
async def assert_last_messsage_text_in(client, chat_name, text):
    last_message = await get_last_message(client, chat_name)
    if last_message:
        if getattr(last_message, "text"):
            assert text in last_message.text
        elif getattr(last_message, "caption"):
            assert text in last_message.caption
        else:
            raise AssertionError
        return
    raise AssertionError


async def login_conversation_in_direct(
    client: Client, menu_controller: MenuController
):
    data = await client.get_me()
    await menu_controller.register_user(User(id=data.id, username=data.mention))

    await client.send_message(config.bot_name, "/start_conv")
    await assert_last_messsage_text_in(
        client, config.bot_name, "Please enter the password"
    )
    await client.send_message(config.bot_name, config.chatgpt_passwords[0])
    await assert_last_messsage_text_in(client, config.bot_name, "Password accepted")


async def test_chatgpt_login(
    telegram_client: Client, session, menu_controller: MenuController
):
    async with telegram_client as client:
        await login_conversation_in_direct(client, menu_controller)
        await assert_last_messsage_text_in(client, config.bot_name, "Password accepted")

        assert len(ConversationsRepository(session).list()) == 1


async def test_chatgpt_processing(
    aioresponses, telegram_client: Client, menu_controller: MenuController
):
    aioresponses.post(
        "https://api.openai.com/v1/completions",
        payload=json.load(
            open("tests/bot_tests/test-data/test_openai_response_200.json")
        ),
        status=200,
        repeat=True,
    )
    async with telegram_client as client:
        await login_conversation_in_direct(client, menu_controller)
        await client.send_message(config.bot_name, "Hello")
        await assert_last_messsage_text_in(client, config.bot_name, "Hello World")


async def test_chatgpt_history_getting(
    aioresponses,
    telegram_client: Client,
    chatgpt_controller: ChatGPTController,
    menu_controller: MenuController,
):
    aioresponses.post(
        "https://api.openai.com/v1/completions",
        payload=json.load(
            open("tests/bot_tests/test-data/test_openai_response_200.json")
        ),
        status=200,
        repeat=True,
    )

    async with telegram_client as client:
        chat_id = (await client.get_me()).id
        await login_conversation_in_direct(client, menu_controller)
        await chatgpt_controller.process("Hello", chat_id, chat_id)

    _list = await chatgpt_controller.get_conversation_history(chat_id)
    assert len(_list.requests) == 1
    assert (
        "Hello" == _list.requests[0].prompt
        and "Hello World" == _list.requests[0].answer
    )


async def test_chatgpt_logout(
    telegram_client: Client,
    menu_controller,
    session: Session,
):
    async with telegram_client as client:
        await login_conversation_in_direct(client, menu_controller)
        chat_id = (await client.get_me()).id
        await client.send_message(config.bot_name, "/stop")
        await assert_last_messsage_text_in(client, config.bot_name, "Goodbye!")

        repo = ConversationsRepository(session)
        assert (repo.get_by_chat_id(chat_id)).is_stopped is True
