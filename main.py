import logging

import telegram
from aiogram import Bot, Dispatcher
from aiogram.types import Message

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, \
    ContextTypes, filters
from telegram import InputMediaPhoto, InputMediaVideo
from datetime import datetime
import urllib.parse
import requests
import re
import pytz

import os

YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = os.getenv("ADMIN_IDS")

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States for ConversationHandler
CHOOSING, SITUATION, ACCIDENT_SITUATION, LOCATION_CHOICE, LOCATION_COORDS, LOCATION_ADDRESS, COMMENT, PHOTO, VIDEO, CONFIRM, EDIT = range(11)

# Dictionary to hold user data
user_data = {}
post_count = 0


async def send_image_if_needed(context: ContextTypes.DEFAULT_TYPE):
    """Проверка на необходимость отправки изображения в канал"""
    global post_count
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    if post_count > 19 and now.hour >= 20:
        post_count = 0
        with open("picture/S-L-Y.jpg", 'rb') as image:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(image))

def create_yandex_maps_point_url(latitude, longitude):
    """Создание ссылки на Яндекс.Карты"""
    return f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=14&l=map"


def get_readable_address(lat, lon):
    """Определение читаемого адреса по координатам через Яндекс API"""
    url = f"https://geocode-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&geocode={lon},{lat}&format=json"
    response = requests.get(url)
    response.raise_for_status()
    json_response = response.json()

    if json_response['response']['GeoObjectCollection']['featureMember']:
        address_details = \
        json_response['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']['metaDataProperty'][
            'GeocoderMetaData']['Address']
        components = address_details['Components']
        address_parts = [component['name'] for component in components if
                         component['kind'] in ['house', 'street', 'locality', 'province', 'country']]
        return ", ".join(reversed(address_parts))

    return "Адрес не найден"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начальный экран выбора типа происшествия"""
    user_id = update.effective_user.id
    user_data[user_id] = {'admin_id': user_id}  # Запоминаем, кто создал пост
    keyboard = [
        [InlineKeyboardButton("ДТП", callback_data='ДТП'), InlineKeyboardButton("Поломка", callback_data='Поломка')],
        [InlineKeyboardButton("Угон", callback_data='Угон'), InlineKeyboardButton("Прочее", callback_data='Прочее')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('Что произошло?', reply_markup=reply_markup)
    return CHOOSING

async def choosing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор конкретной ситуации"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    user_data[user_id]['type'] = query.data

    if query.data == 'ДТП':
        keyboard = [
            [InlineKeyboardButton("мот", callback_data='мот'), InlineKeyboardButton("мот/сим", callback_data='мот/сим')],
            [InlineKeyboardButton("мот/мот", callback_data='мот/мот'), InlineKeyboardButton("мот/авто", callback_data='мот/авто')],
            [InlineKeyboardButton("мот/пеш", callback_data='мот/пеш'), InlineKeyboardButton("Прочее", callback_data='Прочее')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Какая ситуация?", reply_markup=reply_markup)
        return SITUATION
    else:
        user_data[user_id]['situation'] = ''
        user_data[user_id]['accident_situation'] = ''
        return await location_choice(update, context)

async def situation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор степени происшествия"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    user_data[user_id]['situation'] = query.data

    keyboard = [
        [InlineKeyboardButton("Цел", callback_data='Цел'), InlineKeyboardButton("Ушибся", callback_data='Ушибся')],
        [InlineKeyboardButton("Ранен", callback_data='Ранен'), InlineKeyboardButton("Летально", callback_data='Летально')],
        [InlineKeyboardButton("Прочее", callback_data='Прочее')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Какое состояние?", reply_markup=reply_markup)
    return ACCIDENT_SITUATION

async def accident_situation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_data['accident_situation'] = query.data
    await query.edit_message_text(text="Укажите место происшествия", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Ввести координаты", callback_data='coords')],
        [InlineKeyboardButton("Ввести адрес", callback_data='address')]
    ]))
    return LOCATION_CHOICE

async def location_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    if query.data == 'coords':
        try:
            await query.edit_message_text(text="Введите координаты (широта, долгота):")
        except telegram.error.Forbidden:
            logger.warning(f"Bot was blocked by the user {user_id}")
        return LOCATION_COORDS
    elif query.data == 'address':
        try:
            await query.edit_message_text(text="Введите адрес:")
        except telegram.error.Forbidden:
            logger.warning(f"Bot was blocked by the user {user_id}")
        return LOCATION_ADDRESS
    return LOCATION_CHOICE

async def location_coords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    location_text = update.message.text
    match = re.match(r'^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$', location_text)
    if not match:
        await update.message.reply_text('Пожалуйста, отправьте координаты в формате "широта, долгота".')
        return LOCATION_COORDS

    end_latitude, end_longitude = float(match.group(1)), float(match.group(2))
    user_data[user_id]['location'] = (end_latitude, end_longitude)

    readable_address = get_readable_address(end_latitude, end_longitude)
    user_data[user_id]['readable_address'] = readable_address

    await update.message.reply_text('Добавить комментарий?', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Да", callback_data='Да'), InlineKeyboardButton("Нет", callback_data='Нет')]
    ]))
    return COMMENT


def geocode_yandex(address_text):
    url = f"https://geocode-maps.yandex.ru/1.x/?apikey={YANDEX_API_KEY}&geocode={urllib.parse.quote(address_text)}&format=json"
    response = requests.get(url)
    response.raise_for_status()
    json_response = response.json()

    if json_response['response']['GeoObjectCollection']['featureMember']:
        geo_object = json_response['response']['GeoObjectCollection']['featureMember'][0]['GeoObject']
        coordinates = geo_object['Point']['pos'].split()
        return float(coordinates[1]), float(coordinates[0])
    return None


async def location_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    address_text = update.message.text

    location = geocode_yandex(address_text)

    if not location:
        await update.message.reply_text('Адрес не найден. Пожалуйста, введите корректный адрес.')
        return LOCATION_ADDRESS

    end_latitude, end_longitude = location
    user_data[user_id]['location'] = (end_latitude, end_longitude)
    user_data[user_id]['readable_address'] = address_text

    await update.message.reply_text('Добавить комментарий?', reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Да", callback_data='Да'), InlineKeyboardButton("Нет", callback_data='Нет')]
    ]))
    return COMMENT


async def comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    if query.data == 'Да':
        try:
            await query.edit_message_text(text="Введите комментарий:")
        except telegram.error.Forbidden:
            logger.warning(f"Bot was blocked by the user {user_id}")
        return COMMENT
    else:
        user_data[user_id]['comment'] = ''
        try:
            await query.edit_message_text(text="Хотите добавить фото?", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data='Да'), InlineKeyboardButton("Нет", callback_data='Нет')]
            ]))
        except telegram.error.Forbidden:
            logger.warning(f"Bot was blocked by the user {user_id}")
        return PHOTO

async def received_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['comment'] = update.message.text
    try:
        await update.message.reply_text("Хотите добавить фото?", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Да", callback_data='Да'), InlineKeyboardButton("Нет", callback_data='Нет')]
        ]))
    except telegram.error.Forbidden:
        logger.warning(f"Bot was blocked by the user {user_id}")
    return PHOTO


async def send_image_if_needed(context: ContextTypes.DEFAULT_TYPE):
    """Проверка на необходимость отправки изображения в канал"""
    global post_count
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    if post_count > 20 and now.hour >= 21:
        post_count = 0
        with open("picture/S-L-Y.jpg", 'rb') as image:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(image))

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос на добавление фото"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    keyboard = [
        [InlineKeyboardButton("Добавить фото", callback_data='add_photo')],
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Пропустить", callback_data='skip_media')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="Хотите добавить медиафайлы?", reply_markup=reply_markup)
    return PHOTO

async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ожидание загрузки фото"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Отправьте фото.")
    return PHOTO

async def received_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка полученного фото"""
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    user_data[user_id].setdefault('photo', []).append(photo_file.file_id)

    keyboard = [
        [InlineKeyboardButton("Добавить еще фото", callback_data='add_photo')],
        [InlineKeyboardButton("Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("Завершить", callback_data='done')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Фото добавлено. Что делаем дальше?", reply_markup=reply_markup)
    return PHOTO

async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос на добавление видео"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Отправьте видео.")
    return VIDEO

async def received_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка полученного видео"""
    user_id = update.effective_user.id
    video_file = await update.message.video.get_file()
    user_data[user_id].setdefault('video', []).append(video_file.file_id)

    keyboard = [
        [InlineKeyboardButton("Добавить еще видео", callback_data='add_video')],
        [InlineKeyboardButton("Добавить фото", callback_data='add_photo')],
        [InlineKeyboardButton("Завершить", callback_data='done')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Видео добавлено. Что делаем дальше?", reply_markup=reply_markup)
    return VIDEO

async def skip_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пропуск добавления медиа"""
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    user_data[user_id]['photo'] = []
    user_data[user_id]['video'] = []
    return await done(update, context)

async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Финальное подтверждение перед отправкой"""
    user_id = update.effective_user.id
    username = update.effective_user.username

    photos = user_data[user_id].get('photo', [])
    videos = user_data[user_id].get('video', [])
    comment_text = user_data[user_id].get('comment', '')
    location = user_data[user_id].get('location', None)
    readable_address = user_data[user_id].get('readable_address', 'Адрес не найден')

    yandex_maps_url = f"https://yandex.ru/maps/?pt={location[1]},{location[0]}&z=14&l=map" if location else "Не указано"

    parts = [
        f"Тип: {user_data[user_id]['type']}",
        f"Ситуация: {user_data[user_id].get('situation', 'Не указано')}",
        f"Состояние: {user_data[user_id].get('accident_situation', 'Не указано')}",
        f"Адрес: {readable_address}",
        f"Позиция: {yandex_maps_url}",
        f"Комментарий: {comment_text}",
        f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Создал: @{username} (ID: {user_id})"
    ]

    parts = [part for part in parts if "Не указано" not in part]
    summary = "\n".join(parts)

    await update.message.reply_text(
        text=summary,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("✏️ Редактировать", callback_data='edit')],
            [InlineKeyboardButton("❌ Отменить", callback_data='cancel')],
            [InlineKeyboardButton("🔙 Назад", callback_data='back')]
        ])
    )

    return CONFIRM


async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    photos = user_data[user_id].get('photo', [])
    videos = user_data[user_id].get('video', [])
    comment_text = user_data[user_id].get('comment', '') or ''
    location = user_data[user_id].get('location', None)
    readable_address = user_data[user_id].get('readable_address', 'Адрес не найден')

    if location:
        end_latitude, end_longitude = location
        yandex_maps_url = f"https://yandex.ru/maps/?pt={end_longitude},{end_latitude}&z=14&l=map"
    else:
        yandex_maps_url = "Не указано"

    parts = [
        user_data[user_id]['type'],
        user_data[user_id].get('situation', '') or '',
        user_data[user_id].get('accident_situation', '') or '',
        readable_address
    ]
    parts = [part for part in parts if part]  # Удаляем пустые части
    summary = ", ".join(parts)
    summary += f"\nПозиция: {yandex_maps_url}\n"
    summary += f"Комментарий: {comment_text}\n"
    summary += f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    summary += f"Пользователь: {update.effective_user.username}"

    try:
        # Если есть фотографии, отправляем их по одному
        if photos:
            for photo in photos:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=summary, parse_mode="Markdown")
                summary = ""  # Убираем подпись, чтобы она не повторялась на всех фото

        # Если есть видео, отправляем их по одному
        if videos:
            for video in videos:
                await context.bot.send_video(chat_id=CHANNEL_ID, video=video, caption=summary, parse_mode="Markdown")
                summary = ""  # Убираем подпись, чтобы она не повторялась на всех видео

        # Если нет медиафайлов, отправляем текстовый пост
        if not photos and not videos:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=summary, parse_mode="Markdown")

        await update.callback_query.message.reply_text(text="Пост отправлен!")
    except Exception as e:
        logger.error("Failed to send media to channel: %s", str(e))
        await update.callback_query.message.reply_text(text="Ошибка при отправке медиа в канал.")

    user_data[user_id].clear()
    post_count += 1
    await send_image_if_needed(context)

    return ConversationHandler.END


async def edit_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("Отправьте отредактированный текст сообщения:")
    return EDIT


async def received_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data[user_id]['edit_message'] = update.message.text
    await update.message.reply_text(
        "Сообщение отредактировано. Подтвердите или отмените отправку.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("Отменить", callback_data='cancel')]
        ])
    )
    return CONFIRM

async def confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    global post_count
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()

    photos = user_data[user_id].get('photo', [])
    videos = user_data[user_id].get('video', [])
    comment_text = user_data[user_id].get('comment', '') or ''
    location = user_data[user_id].get('location', None)
    readable_address = user_data[user_id].get('readable_address', 'Адрес не найден')
    if location:
        end_latitude, end_longitude = location
        yandex_maps_url = f"https://yandex.ru/maps/?pt={end_longitude},{end_latitude}&z=14&l=map"
    else:
        yandex_maps_url = "Не указано"

    summary = user_data[user_id].get('edit_message', None)
    if not summary:
        parts = [
            user_data[user_id]['type'],
            user_data[user_id].get('situation', '') or '',
            user_data[user_id].get('accident_situation', '') or '',
            readable_address
        ]
        parts = [part for part in parts if part]  # Remove empty parts
        summary = ", ".join(parts)
        summary += f"\nПозиция: {yandex_maps_url}\n"
        summary += f"Комментарий: {comment_text}\n"
        summary += f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        summary += f"Пользователь: {update.effective_user.username}"

    media_group = [InputMediaPhoto(photo) for photo in photos]
    media_group.extend([InputMediaVideo(video) for video in videos])

    if media_group:
        media_group[0] = InputMediaPhoto(media_group[0].media, caption=summary, parse_mode="Markdown")

    try:
        await context.bot.send_media_group(
            chat_id=CHANNEL_ID,
            media=media_group
        )
        await query.edit_message_text(text="Пост отправлен!")
    except Exception as e:
        logger.error("Failed to send media group to channel: %s", str(e))
        await query.edit_message_text(text="Ошибка при отправке медиа группы в канал.")

    user_data[user_id].clear()
    post_count += 1
    await send_image_if_needed(context)

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_data[user_id].clear()
    await update.callback_query.edit_message_text('Операция отменена.')
    return ConversationHandler.END

def main() -> None:
    application = Application.builder().token("7415882119:AAEI_ZnQJ6HMeRjQGihU8cluaNKF-sEh5Hc").build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING: [CallbackQueryHandler(choosing)],
            SITUATION: [CallbackQueryHandler(situation)],
            ACCIDENT_SITUATION: [CallbackQueryHandler(accident_situation)],
            LOCATION_CHOICE: [CallbackQueryHandler(location_choice)],
            LOCATION_COORDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, location_coords)],
            LOCATION_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, location_address)],
            COMMENT: [
                CallbackQueryHandler(comment),
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_comment)
            ],
            PHOTO: [
                CallbackQueryHandler(photo, pattern='^Да$'),
                CallbackQueryHandler(add_photo, pattern='add_photo'),
                CallbackQueryHandler(add_video, pattern='add_video'),
                MessageHandler(filters.PHOTO, received_photo),
                MessageHandler(filters.VIDEO, received_video),
                CommandHandler('done', done)
            ],
            VIDEO: [MessageHandler(filters.VIDEO, received_video)],  # Добавьте обработку видео для состояния VIDEO
            CONFIRM: [
                CallbackQueryHandler(confirmed, pattern='confirm'),
                CallbackQueryHandler(edit_post, pattern='edit'),
                CallbackQueryHandler(cancel, pattern='cancel')
            ],
            EDIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, received_edit)
            ]
        },
        fallbacks=[CommandHandler('start', start), CallbackQueryHandler(cancel, pattern='cancel')]
    )

    application.add_handler(conv_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
