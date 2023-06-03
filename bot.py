import logging
import os
import dotenv
import uuid
import traceback
import html
import json

import easyocr
import cv2

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.constants import ParseMode

DEVELOPER_CHAT_ID = os.environ.get("DEVELOPER_CHAT_ID")
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO, filename='logs.txt')

logger = logging.getLogger(__name__)

PHOTO, CENSOR = range(2)

base_dir = os.getcwd()
images_dir = os.path.join(base_dir, 'images')

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks the user about their gender."""
    await update.message.reply_text(
        "Hi! I'm censor Bot. I will censor words on the provided photo."
        "Send /censor to proceed."
    )


async def censor(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    
    await update.message.reply_text(
        "Please send me an image to censor\n"
        "Send /cancel to stop current censoring.\n\n"
    )

    return PHOTO

async def photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the photo and asks for a location."""
    user = update.message.from_user
    image_file = await update.message.photo[-1].get_file()
    image_uuid = uuid.uuid4()
    user_original_images_dir = os.path.join(images_dir, f"{user.username}_{user.id}", 'original')
    exists = os.path.exists(user_original_images_dir)
    if not exists:
       os.makedirs(user_original_images_dir)
       print(f"The new directory {user_original_images_dir} is created!")

    original_image_path = os.path.join(user_original_images_dir, f"{image_uuid}.jpg")
    await image_file.download_to_drive(original_image_path)
    context.user_data["original_image_path"] = original_image_path 
    logger.info(f"Photo from {user.username} saved to {original_image_path}")
    await update.message.reply_text(
        "Now, please send me text that needs to be censored on the image."
    )

    return CENSOR

async def censor_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the photo and asks for a location."""
    user = update.message.from_user
    chat_id = update.effective_chat.id
    censor_text = update.message.text

    await context.bot.send_message(
        chat_id=chat_id,
        text="Thank you for using this bot.\n"
            "My broke ass creator couldn't afford a GPU server to process images faster.\n"
            "I'll be right back with the results!")
    await context.bot.send_animation(
        chat_id=chat_id,
        animation="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNDc2ZmFjMTZiN2YyNzRjOWY5NWE2YmI2NTM4NDFkOWZkNTY0MTliNyZlcD12MV9pbnRlcm5hbF9naWZzX2dpZklkJmN0PWc/l2SpZkQ0XT1XtKus0/giphy.gif")
    
    user_processed_images_dir = os.path.join(images_dir, f"{user.username}_{user.id}", 'processed')
    exists = os.path.exists(user_processed_images_dir)
    if not exists:
       # Create a new directory because it does not exist
       os.makedirs(user_processed_images_dir)
       print(f"The new directory {user_processed_images_dir} is created!")
    original_image_path = context.user_data["original_image_path"]
    original_image = cv2.imread(original_image_path)
    reader = easyocr.Reader(['en', 'ru'], gpu=False)

    result = reader.readtext(original_image_path, width_ths=0)
    processed_image_file_name = uuid.uuid4()
    full_processed_image_file_name = os.path.join(user_processed_images_dir, f"{processed_image_file_name}.jpg")
    for detection in result:
        if detection[1].casefold() in censor_text.casefold():
            top_left = tuple([int(val) for val in detection[0][0]])
            bottom_right = tuple([int(val) for val in detection[0][2]])
            processed_image = cv2.rectangle(original_image, top_left, bottom_right, (0,255,0),-1)
            cv2.imwrite(full_processed_image_file_name, processed_image)
    
    if os.path.exists(full_processed_image_file_name):
        await context.bot.send_document(chat_id=chat_id, document=full_processed_image_file_name)
        os.remove(full_processed_image_file_name)

    else:
        result_list = [f"{detection[1]}\n" for detection in result]
        result_list = '\n'.join(result_list)
        await update.message.reply_text(
            "Sorry, your text wasn't found on the image.\n"
            "Here's the list of what I found:\n"
            f"{result_list}"
        )

    os.remove(original_image_path)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels and ends the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text(
        "Bye! I hope we can talk again some day.", reply_markup=ReplyKeyboardRemove()
    )

    return ConversationHandler.END

def main() -> None:
    """Run the bot."""
    dotenv.load_dotenv()
    bot_token = os.environ.get("TOKEN")
    application = Application.builder().token(bot_token).build()

    start_handler = CommandHandler("start", start)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("censor", censor)],
        states={
            PHOTO: [MessageHandler(filters.PHOTO, photo)],
            CENSOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, censor_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(start_handler)

    application.run_polling()


if __name__ == "__main__":
    main()