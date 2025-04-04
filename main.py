import logging
import urllib.parse
import requests
import re
import pytz
import os
import telegram
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ConversationHandler, \
    ContextTypes, filters
from telegram import InputMediaPhoto, InputMediaVideo
from datetime import datetime
from config import OPEN_CAGE_API_KEY
from dotenv import load_dotenv
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")
ADMIN_IDS = os.getenv("ADMIN_IDS")
OPEN_CAGE_API_KEY = os.getenv("OPEN_CAGE_API_KEY")

load_dotenv()  # Загружаем переменные окружения

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


# States for ConversationHandler
CHOOSING, SITUATION, ACCIDENT_SITUATION, LOCATION_CHOICE, LOCATION_COORDS, LOCATION_ADDRESS, COMMENT, PHOTO, VIDEO, CONFIRM, EDIT = range(11)


# Dictionary to hold user data
user_data = {}
post_count = 0

def create_yandex_google_links(latitude, longitude):
    """Создает ссылки на Яндекс и Google карты по координатам."""
    yandex = f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=14&l=map"
    google = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
    return yandex, google


def create_map_url(latitude, longitude):
    """Создает ссылку на OpenStreetMap для отображения местоположения."""
    return f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}&zoom=14"


async def send_image_if_needed(context: ContextTypes.DEFAULT_TYPE):
    """Проверка на необходимость отправки изображения в канал"""
    global post_count
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    if post_count > 19 and now.hour >= 20:
        post_count = 0
        with open("picture/S-L-Y.jpg", 'rb') as image:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(image))


def get_readable_address(lat, lon):
    """Получает читаемый адрес по координатам через OpenCage API."""
    url = f"https://api.opencagedata.com/geocode/v1/json?q={lat}+{lon}&key={OPEN_CAGE_API_KEY}&language=ru"

    response = requests.get(url)
    if response.status_code != 200:
        logger.error(f"Ошибка запроса к OpenCage API: {response.status_code}, {response.text}")
        return "Ошибка геокодирования"

    json_response = response.json()
    logger.info(f"Ответ OpenCage API: {json_response}")

    if not json_response.get('results'):
        logger.warning("OpenCage не нашел адрес по координатам")
        return "Адрес не найден"

    # Извлекаем отформатированный адрес
    address = json_response['results'][0].get('formatted', "Адрес не найден")

    logger.info(f"Найден адрес: {address}")
    return address


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало выбора типа происшествия"""
    user_id = update.effective_user.id
    user_data[user_id] = {'admin_id': user_id}  # Сохранение ID создателя

    keyboard = [
        [InlineKeyboardButton("ДТП", callback_data='ДТП'), InlineKeyboardButton("Поломка", callback_data='Поломка')],
        [InlineKeyboardButton("Угон", callback_data='Угон'), InlineKeyboardButton("Прочее", callback_data='Прочее')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("Что произошло?", reply_markup=reply_markup)
    else:
        await update.callback_query.message.edit_text("Что произошло?", reply_markup=reply_markup)

    return CHOOSING


async def choosing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор типа происшествия"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':
        return await start(update, context)  # Возвращаемся к выбору типа происшествия

    user_data[user_id]['type'] = query.data  # Сохраняем выбранный тип происшествия

    if query.data == 'ДТП':
        keyboard = [
            [InlineKeyboardButton("мот", callback_data='мот'),
             InlineKeyboardButton("мот/сим", callback_data='мот/сим')],
            [InlineKeyboardButton("мот/мот", callback_data='мот/мот'),
             InlineKeyboardButton("мот/авто", callback_data='мот/авто')],
            [InlineKeyboardButton("мот/пеш", callback_data='мот/пеш'),
             InlineKeyboardButton("Прочее", callback_data='Прочее')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Какая ситуация?", reply_markup=reply_markup)
        return SITUATION
    else:
        user_data[user_id]['situation'] = ''
        user_data[user_id]['accident_situation'] = ''

        keyboard = [
            [InlineKeyboardButton("Координаты", callback_data='coords')],
            [InlineKeyboardButton("Адрес", callback_data='address')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="Как хотите ввести место происшествия?", reply_markup=reply_markup)
        return LOCATION_CHOICE


async def situation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор ситуации в ДТП"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':
        return await choosing(update, context)  # Возвращаемся к выбору типа происшествия

    user_data[user_id]['situation'] = query.data  # Сохраняем выбранную ситуацию

    keyboard = [
        [InlineKeyboardButton("Цел", callback_data='Цел'), InlineKeyboardButton("Ушибся", callback_data='Ушибся')],
        [InlineKeyboardButton("Ранен", callback_data='Ранен'), InlineKeyboardButton("Летально", callback_data='Летально')],
        [InlineKeyboardButton("Прочее", callback_data='Прочее')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text="Какое состояние?", reply_markup=reply_markup)
    return ACCIDENT_SITUATION


async def accident_situation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор состояния пострадавшего после ДТП"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':
        return await situation(update, context)  # Возвращаемся к выбору ситуации

    user_data[user_id]['accident_situation'] = query.data  # Сохраняем выбранное состояние

    keyboard = [
        [InlineKeyboardButton("Ввести координаты", callback_data='coords')],
        [InlineKeyboardButton("Ввести адрес", callback_data='address')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text="Укажите место происшествия", reply_markup=reply_markup)
    return LOCATION_CHOICE


async def location_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выбор способа ввода местоположения"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':
        return await accident_situation(update, context)  # Возвращаемся к выбору состояния

    user_data[user_id]['location_method'] = query.data  # Сохраняем выбранный метод

    if query.data == 'coords':
        await query.edit_message_text(text="Введите координаты (широта, долгота):",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
                                      ]))
        return LOCATION_COORDS

    elif query.data == 'address':
        await query.edit_message_text(text="Введите адрес:",
                                      reply_markup=InlineKeyboardMarkup([
                                          [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
                                      ]))
        return LOCATION_ADDRESS

    return LOCATION_CHOICE


async def location_coords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода координат пользователем"""
    user_id = update.effective_user.id
    location_text = update.message.text

    # Регулярное выражение для проверки корректности ввода координат
    match = re.match(r'^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$', location_text)
    if not match:
        await update.message.reply_text('⚠️ Пожалуйста, отправьте координаты в формате "широта, долгота".',
                                        reply_markup=InlineKeyboardMarkup([
                                            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
                                        ]))
        return LOCATION_COORDS

    # Преобразуем координаты в числа
    end_latitude, end_longitude = float(match.group(1)), float(match.group(2))
    user_data[user_id]['location'] = (end_latitude, end_longitude)

    # Получаем читаемый адрес через OpenCage API
    readable_address = get_readable_address(end_latitude, end_longitude)
    user_data[user_id]['readable_address'] = readable_address

    # Сообщение с подтверждением и кнопкой назад
    await update.message.reply_text(
        f"📍 Местоположение сохранено: {readable_address}\n\n"
        "Добавить комментарий?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data='Да')],
            [InlineKeyboardButton("❌ Нет", callback_data='Нет')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ])
    )
    return COMMENT


def geocode_opencage(address_text):
    url = f"https://api.opencagedata.com/geocode/v1/json?q={requests.utils.quote(address_text)}&key={OPEN_CAGE_API_KEY}&language=ru"

    response = requests.get(url)
    if response.status_code != 200:
        return None

    json_response = response.json()
    if not json_response['results']:
        return None

    lat = json_response['results'][0]['geometry']['lat']
    lon = json_response['results'][0]['geometry']['lng']
    return lat, lon


async def location_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка ввода адреса пользователем и его преобразование в координаты"""
    user_id = update.effective_user.id
    address_text = update.message.text.strip()

    # Получаем координаты с помощью OpenCage API
    location = geocode_opencage(address_text)

    if not location:
        await update.message.reply_text(
            "⚠️ Адрес не найден. Попробуйте ввести более точное название.\n\n"
            "Например: «Москва, Красная площадь, 1»",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data='retry_address')],
                [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
            ])
        )
        return LOCATION_ADDRESS

    # Сохраняем данные в user_data
    end_latitude, end_longitude = location
    user_data[user_id]['location'] = (end_latitude, end_longitude)
    user_data[user_id]['readable_address'] = address_text

    # Подтверждение с возможностью добавить комментарий
    await update.message.reply_text(
        f"📍 Адрес сохранён: {address_text}\n\n"
        "Добавить комментарий?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data='Да')],
            [InlineKeyboardButton("❌ Нет", callback_data='Нет')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ])
    )
    return COMMENT


async def comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка запроса комментария и кнопки 'Назад'"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':
        return await location_choice(update, context)  # Возвращаем пользователя назад

    if query.data == 'Да':
        await query.edit_message_text(
            text="📝 Введите комментарий:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
            ])
        )
        return COMMENT

    # Если выбрано "Нет", пропускаем ввод комментария
    user_data[user_id]['comment'] = ''
    await query.edit_message_text(
        text="📸 Хотите добавить фото?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data='Да')],
            [InlineKeyboardButton("❌ Нет", callback_data='Нет')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ])
    )
    return PHOTO


async def received_comment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает введённый пользователем комментарий и предлагает добавить фото"""
    user_id = update.effective_user.id
    user_data[user_id]['comment'] = update.message.text  # Сохраняем комментарий

    await update.message.reply_text(
        text="📸 Хотите добавить фото?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Да", callback_data='Да')],
            [InlineKeyboardButton("❌ Нет", callback_data='Нет')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ])
    )
    return PHOTO


async def send_image_if_needed(context: ContextTypes.DEFAULT_TYPE):
    """Проверка на необходимость отправки изображения в канал"""
    global post_count
    tz = pytz.timezone('Europe/Moscow')
    now = datetime.now(tz)
    if post_count > 19 and now.hour >= 20:
        post_count = 0
        with open("picture/S-L-Y.jpg", 'rb') as image:
            await context.bot.send_photo(chat_id=CHANNEL_ID, photo=InputFile(image))


async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает фото или видео у пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == 'back':  # Если нажата кнопка "Назад", возвращаемся к комментарию
        return await comment(update, context)

    if query.data == 'Да':
        keyboard = [
            [InlineKeyboardButton("📷 Добавить фото", callback_data='add_photo')],
            [InlineKeyboardButton("🎥 Добавить видео", callback_data='add_video')],
            [InlineKeyboardButton("✅ Завершить", callback_data='done')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text="📎 Загрузите медиафайлы:", reply_markup=reply_markup)
        return PHOTO

    elif query.data == 'Нет':
        user_data[user_id]['photo'] = []
        user_data[user_id]['video'] = []
        return await done(update, context)


async def add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ожидание загрузки фото пользователем"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="📷 Отправьте фото.")
    return PHOTO


async def received_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает загруженное пользователем фото"""
    user_id = update.effective_user.id
    photo_file = await update.message.photo[-1].get_file()
    user_data[user_id].setdefault('photo', []).append(photo_file.file_id)

    keyboard = [
        [InlineKeyboardButton("📷 Добавить ещё фото", callback_data='add_photo')],
        [InlineKeyboardButton("🎥 Добавить видео", callback_data='add_video')],
        [InlineKeyboardButton("✅ Завершить", callback_data='done')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📸 Фото добавлено. Что делаем дальше?", reply_markup=reply_markup)
    return PHOTO


async def add_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у пользователя видео"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="🎥 Отправьте видео.")
    return VIDEO

async def received_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает загруженное пользователем видео и логирует возможные ошибки"""
    user_id = update.effective_user.id

    try:
        video_file = await update.message.video.get_file()
        user_data[user_id].setdefault('video', []).append(video_file.file_id)
        logger.info(f"✅ Видео успешно добавлено пользователем {user_id}: {video_file.file_id}")

        keyboard = [
            [InlineKeyboardButton("📷 Добавить фото", callback_data='add_photo')],
            [InlineKeyboardButton("🎥 Добавить ещё видео", callback_data='add_video')],
            [InlineKeyboardButton("✅ Завершить", callback_data='done')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='back')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("🎥 Видео добавлено. Что делаем дальше?", reply_markup=reply_markup)

        return VIDEO

    except Exception as e:
        logger.error(f"❌ Ошибка при загрузке видео пользователем {user_id}: {str(e)}")
        await update.message.reply_text("🚨 Произошла ошибка при загрузке видео. Попробуйте снова.")
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
    user_id = update.effective_user.id
    username = update.effective_user.username
    user_data[user_id]['admin_id'] = user_id  # Запоминаем ID создателя поста

    # Достаем данные из user_data
    photos = user_data[user_id].get('photo', [])
    videos = user_data[user_id].get('video', [])
    comment_text = user_data[user_id].get('comment', '') or ''
    location = user_data[user_id].get('location', None)
    readable_address = user_data[user_id].get('readable_address', 'Адрес не найден')

    parts = [
        f"Тип: {user_data[user_id]['type']}",
        f"Ситуация: {user_data[user_id].get('situation', 'Не указано')}",
        f"Состояние: {user_data[user_id].get('accident_situation', 'Не указано')}",
        f"Адрес: {readable_address}",
    ]

    if location:
        latitude, longitude = location
        yandex_link = f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=14&l=map"
        google_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        parts.append(f"Яндекс карты: {yandex_link}")
        parts.append(f"Google карты: {google_link}")
    else:
        parts.append("Координаты: Не указаны")

    parts.append(f"Комментарий: {comment_text}")
    parts.append(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"Создал: @{username} (ID: {user_id})")

    summary = "\n".join(parts)

    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
        [InlineKeyboardButton("✏️ Редактировать", callback_data='edit')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_photo')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text=summary, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text=summary, reply_markup=reply_markup)

    return CONFIRM


async def confirm_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    photos = user_data[user_id].get('photo', [])
    videos = user_data[user_id].get('video', [])
    comment_text = user_data[user_id].get('comment', '') or ''
    location = user_data[user_id].get('location', None)
    readable_address = user_data[user_id].get('readable_address', 'Адрес не найден')

    parts = [
        user_data[user_id]['type'],
        user_data[user_id].get('situation', '') or '',
        user_data[user_id].get('accident_situation', '') or '',
        readable_address
    ]

    if location:
        latitude, longitude = location
        yandex_link = f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=14&l=map"
        google_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
        parts.append(f"Яндекс карты: {yandex_link}")
        parts.append(f"Google карты: {google_link}")
    else:
        parts.append("Координаты: Не указаны")

    parts.append(f"Комментарий: {comment_text}")
    parts.append(f"Дата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"Пользователь: {update.effective_user.username}")

    summary = "\n".join(part for part in parts if part)

    try:
        if photos:
            for photo in photos:
                await context.bot.send_photo(chat_id=CHANNEL_ID, photo=photo, caption=summary, parse_mode="Markdown")
                summary = ""  # Только для первого медиафайла
        if videos:
            for video in videos:
                await context.bot.send_video(chat_id=CHANNEL_ID, video=video, caption=summary, parse_mode="Markdown")
                summary = ""
        if not photos and not videos:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=summary, parse_mode="Markdown")

        await update.callback_query.message.reply_text(text="Пост отправлен!")
    except Exception as e:
        logger.error(f"Ошибка отправки медиа: {str(e)}")
        await update.callback_query.message.reply_text(text="Ошибка при отправке медиа в канал.")

    user_data[user_id].clear()
    global post_count
    post_count += 1
    await send_image_if_needed(context)

    return ConversationHandler.END


async def edit_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос на редактирование поста"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    # Проверяем, есть ли у пользователя данные поста
    if user_id not in user_data or not user_data[user_id]:
        await query.message.reply_text("❌ Нет данных для редактирования. Начните заново с /start")
        return ConversationHandler.END

    # Предлагаем выбрать параметр для редактирования
    keyboard = [
        [InlineKeyboardButton("Тип", callback_data='edit_type')],
        [InlineKeyboardButton("Ситуация", callback_data='edit_situation')],
        [InlineKeyboardButton("Состояние", callback_data='edit_accident_situation')],
        [InlineKeyboardButton("Адрес", callback_data='edit_location')],
        [InlineKeyboardButton("Комментарий", callback_data='edit_comment')],
        [InlineKeyboardButton("Фото", callback_data='edit_photo')],
        [InlineKeyboardButton("Видео", callback_data='edit_video')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_done')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text("✏️ Выберите, что хотите изменить:", reply_markup=reply_markup)
    return EDIT


async def received_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение изменений в посте после редактирования"""
    user_id = update.effective_user.id
    new_text = update.message.text

    # Проверяем, есть ли у пользователя данные поста
    if user_id not in user_data or not user_data[user_id]:
        await update.message.reply_text("❌ Нет данных для редактирования. Начните заново с /start")
        return ConversationHandler.END

    # Сохраняем отредактированный текст
    user_data[user_id]['edit_message'] = new_text

    # Предлагаем подтвердить изменения
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
        [InlineKeyboardButton("✏️ Изменить снова", callback_data='edit')],
        [InlineKeyboardButton("❌ Отменить", callback_data='cancel')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_edit')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📝 Ваш отредактированный текст:\n\n" + new_text +
        "\n\nВыберите действие:", reply_markup=reply_markup
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
    edited_message = user_data[user_id].get('edit_message', None)

    if edited_message:
        summary = edited_message
    else:
        parts = [
            user_data[user_id]['type'],
            user_data[user_id].get('situation', ''),
            user_data[user_id].get('accident_situation', ''),
            readable_address
        ]
        parts = [part for part in parts if part]

        summary = ", ".join(parts)

        if location:
            latitude, longitude = location
            yandex_link = f"https://yandex.ru/maps/?pt={longitude},{latitude}&z=14&l=map"
            google_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
            summary += f"\nЯндекс карты: {yandex_link}"
            summary += f"\nGoogle карты: {google_link}"

        if comment_text:
            summary += f"\nКомментарий: {comment_text}"

        summary += f"\nДата и время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        summary += f"\nПользователь: @{update.effective_user.username}"

    try:
        media_group = []
        if photos:
            for idx, photo in enumerate(photos):
                if idx == 0:
                    media_group.append(InputMediaPhoto(photo, caption=summary, parse_mode="Markdown"))
                else:
                    media_group.append(InputMediaPhoto(photo))
        if videos:
            for idx, video in enumerate(videos):
                if idx == 0 and not media_group:
                    media_group.append(InputMediaVideo(video, caption=summary, parse_mode="Markdown"))
                else:
                    media_group.append(InputMediaVideo(video))

        if media_group:
            await context.bot.send_media_group(chat_id=CHANNEL_ID, media=media_group)
        else:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=summary, parse_mode="Markdown")

        await query.edit_message_text(text="Пост отправлен!")
    except Exception as e:
        logger.error(f"Ошибка отправки медиа группы в канал: {str(e)}")
        await query.edit_message_text(text="Ошибка при отправке медиа группы в канал.")

    user_data[user_id].clear()
    post_count += 1
    await send_image_if_needed(context)

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик отмены создания поста"""
    user_id = update.effective_user.id
    query = update.callback_query

    # Логируем отмену
    logger.info(f"🚫 Пользователь {user_id} отменил создание поста.")

    # Проверяем, есть ли у пользователя сохраненные данные, и очищаем их
    if user_id in user_data:
        user_data[user_id].clear()

    # Отправляем уведомление пользователю
    if query:
        await query.answer()
        await query.edit_message_text("❌ Создание поста отменено.")
    else:
        await update.message.reply_text("❌ Создание поста отменено.")

    return ConversationHandler.END


def main() -> None:
    """Основная функция запуска бота"""
    # Создаем объект приложения Telegram
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    # Определяем обработчик диалогов
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
                CallbackQueryHandler(done, pattern='^done$'),
                MessageHandler(filters.PHOTO, received_photo),
                MessageHandler(filters.VIDEO, received_video),
                CallbackQueryHandler(skip_media, pattern='Нет'),
                CommandHandler('done', done)
            ],
            VIDEO: [MessageHandler(filters.VIDEO, received_video)],
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

    # Добавляем обработчик диалогов
    application.add_handler(conv_handler)

    # Запускаем бота
    logger.info("🤖 Бот запущен и ожидает команды...")
    application.run_polling()

if __name__ == '__main__':
    main()
