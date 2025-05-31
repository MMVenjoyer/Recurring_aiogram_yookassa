from config import load_config
from aiogram.types import InlineKeyboardButton
from aiogram import F
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio
import uuid
from loader import bot
from yookassa import Payment, Configuration
from tgbot.db import DataBase

db = DataBase("database.db")

config = load_config()

Configuration.account_id = config.tg_bot.yookassa_shop_id  # shop id
Configuration.secret_key = config.tg_bot.yookassa_secret_key  # secret_key


################ СОЗДАЕМ ПЕРВЫЙ ПЛАТЕЖ ################
async def create_first_payment(user_id, amount, description):
    payment = Payment.create({
        "amount": {
            "value": amount,  # цена
            "currency": "RUB"  # валюта
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/"  # куда перекинет юзера при удачной оплате
        },
        "capture": True, # нужно для автоматического списания
        "description": f"{description}", # описание к платежу
        "save_payment_method": True, # ОБЯЗАТЕЛЬНЫЙ ПАРАМЕТР АВТОПЛАТЕЖЕЙ - сохраняй его, чтобы проверить прошла ли оплата
        "metadata": {
            "user_id": str(user_id)
        }
    }, uuid.uuid4())
    db.add_payment_id(user_id, payment.id) # добавляю в базу к юзеру его платежный айди

    kb = InlineKeyboardBuilder()
    kb.add(
        InlineKeyboardButton(text=f"Оплатить {amount}₽",
                             url=payment.confirmation.confirmation_url),
        InlineKeyboardButton(
            text="Я оплатил", callback_data=f"check_payment:{payment.id}")
    )
    await bot.send_message(user_id, "Проведите оплату и нажмите 'Я оплатил(а)':", reply_markup=kb.as_markup()) # отправляю сообщение с кнопками оплаты/проверки оплаты


################ ПРОВЕРЯЕМ УСПЕШЕН ЛИ ПЛАТЕЖ ################
async def check_payment(user_id): # работает по кнопке проверки, не автоматическая история
    payment_id = db.get_payment_id(user_id) # запрашиваю в базе платежный айди
    payment = Payment.find_one(str(payment_id)) # запрашиваю у юкассы по платежному айди, прошла ли оплата

    if payment.status == "succeeded": # если оплата прошла
        if payment.payment_method.saved: # если данные для автоплатежа сохранены
            payment_method_id = payment.payment_method.id # сохраняем payment_method.id - он понадобится нам для автоплатежей
            db.add_payment_method_id(user_id, payment_method_id, 1) # фиксируем в базу payment_method.id
            await bot.send_message(user_id,
                                   f"✅ Оплата прошла успешно!\n"
                                   f"ID платежа: {payment.id}\n"
                                   f"Сумма: {payment.amount.value} {payment.amount.currency}"
                                   ) # говорим юзеру что все круто
            return True, payment.amount.value # это было нужно мне в коде, не обязательно писать

    else: # если оплата не прошла
        await bot.send_message(user_id, "❌ Платеж не завершен или не найден.") # говорим что не получилось
        return False, None

        # await asyncio.sleep(20)


################ АВТОПЛАТЕЖ ################
async def create_recurring_payment(user_id, amount, description):
    payment_method_id = db.get_payment_method_id(user_id) # берем из базы ранее сохраненный способ для автоплатежей

    if not payment_method_id: # если способа сохраненного нет - стопаем. Простая защита от ошибок
        return False

    recurring_payment = Payment.create({
        "amount": {
            "value": amount, # цена
            "currency": "RUB" # валюта
        },
        "payment_method_id": payment_method_id, # тут мы передаем ранее сохраненный способ для автоплатежей
        "capture": True, # автоматического списание
        "description": f"{description}", # описание
    }, uuid.uuid4())

    if recurring_payment.status == "succeeded": # сразу же проверяем прошла ли автооплата. Если да - говорим юзеру
        await bot.send_message(user_id,
                               f"🔁 Автоплатеж прошел успешно!\n"
                               f"ID: <code>{recurring_payment.id}</code>\n"
                               f"Сумма: {recurring_payment.amount.value} {recurring_payment.amount.currency}"
                               )
        return True
    else:
        await bot.send_message(user_id, "❌ Ошибка автоплатежа.") # если оплата не прошла, также оповещаем юзера
        return False
