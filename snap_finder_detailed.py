#!/usr/bin/env python
# pylint: disable=unused-argument, import-error

import logging
import requests
import textwrap
import datetime, pytz
import pickle
from pathlib import Path

from telegram import Update
from telegram.ext import Application, ConversationHandler, CommandHandler, ContextTypes, MessageHandler, filters
from typing import Dict, List

from keys import *

#Bot data
TOKEN = TEST_BOT

#User data
user_addresses: Dict[int, List[str]] = {}

#conv states
ENTERING_ADDRESS = 0

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

#*** Basic functions ***
def get_dict():
    with open('user_address_file.pkl', "rb") as pickle_file:
        global user_addresses
        user_addresses = pickle.load(pickle_file)

    #for key in user_addresses.copy():
    #    user_addresses[int(key)] = user_addresses.pop(key)
    #
    logger.info("Dict loaded")
    logger.info(user_addresses)

def save_dict():
    with open("user_address_file.pkl", "wb") as pickle_file: 
        pickle.dump(user_addresses, pickle_file)
        pickle_file.close()

    logger.info("Dict saved")
    logger.info(user_addresses)

def get_latest_open_proposals(space_name):
    try:
        # Snapshot API endpoint to retrieve proposals by space
        snapshot_api_url = "https://hub.snapshot.org/graphql"

        # GraphQL query to fetch the latest open proposals for the given space
        query = f'''
        {{
          proposals(where: {{space: "{space_name}", state: "active"}}, first: 5, orderBy: "created", orderDirection: desc) {{
            id
            title
            end
            }}
        }}
        '''

        # Send the GraphQL request to the Snapshot API
        response = requests.post(snapshot_api_url, json={"query": query})
        response_json = response.json()
        logger.info(response_json)

        # Check if the request was successful and extract the proposals
        if "data" in response_json and "proposals" in response_json["data"]:
            return response_json
        else:
            logger.error(f"Error occurred: {e}")
            return "Error retrieving proposals."

    except Exception as e:
        logger.error(f"Error occurred: {e}")
        return f"Error occurred: {e}"

#Update the snapshots
async def update_snaps(context: ContextTypes.DEFAULT_TYPE):
    """Update the snapshots"""
    job = context.job

    for name in user_addresses[job.chat_id]:
        # Call the function to get the latest open proposals for the given space
        response = get_latest_open_proposals(name)

        text = ""

        
        proposals = response["data"]["proposals"]

        if proposals:
            text = f"Proposals in: {name}"
            for proposal in proposals:
                end_stamp = int(proposal["end"])
                end_date = datetime.datetime.fromtimestamp(end_stamp)

                text += textwrap.dedent(f"""
                
                Name: {proposal["title"]}
                End date: {end_date}
                Link: https://snapshot.org/#/{name}/proposal/{proposal["id"]}""")
        else:
            text = f"No proposals in: {name}"

        await context.bot.send_message(job.chat_id, text)

#*** Command handlers ***
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    chat_id = update.effective_message.chat_id

    if chat_id in user_addresses:
        await update.message.reply_text("You already have addresses registered")
        return ConversationHandler.END
    
    else:
        user_addresses[chat_id] = []
        logger.info(f"New user registered {user_addresses}")

        await update.message.reply_text(textwrap.dedent(f"""
        Welcome!             
        Please send a .eth address to save.
        To add additional address use the /reg command"""))

        return ENTERING_ADDRESS
        

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /run is issued."""
    chat_id = update.effective_message.chat_id
    
    await context.bot.send_message(chat_id, "Checking Snaps")
    context.job_queue.run_once(update_snaps, 1, chat_id= chat_id, name= str(chat_id))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text("Functions")

async def reg_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /reg is issued."""
    chat_id = update.effective_message.chat_id

    if chat_id in user_addresses and user_addresses[chat_id]:
        await update.message.reply_text("Send .eth to watch")

        return ENTERING_ADDRESS
    else:
        await update.message.reply_text("You are not registered")

        return ConversationHandler.END

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /list is issued."""
    chat_id = update.effective_message.chat_id
    
    if chat_id in user_addresses and user_addresses[chat_id]:
        await context.bot.send_message(chat_id=chat_id, text=user_addresses[chat_id])
    else:
        await context.bot.send_message(chat_id=chat_id, text="No addresses in your list")

async def run_daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_message.chat_id
    
    context.job_queue.run_daily(update_snaps, datetime.time(hour=9, minute=00, tzinfo=pytz.timezone('UTC')), chat_id= chat_id, name= str(chat_id))

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /stop is issued."""
    chat_id = update.effective_message.chat_id
    
    if chat_id in user_addresses and user_addresses[chat_id]:
        del user_addresses[chat_id]

        current_jobs = context.job_queue.get_jobs_by_name(chat_id)
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()

        await context.bot.send_message(chat_id=chat_id, text="Your addresses and this chat have been removed")
    else:
        await context.bot.send_message(chat_id=chat_id, text="You are not registered")

#*** Non command handlers***
async def address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """address message."""
    global user_addresses

    chat_id = update.effective_message.chat_id

    new_address = update.message.text  # Assuming the address is sent as a text message
    #***TODO ADD ADDRESS SANITATION***

    # Append the new address to the list for this chat_id
    user_addresses[chat_id].append(new_address)

    logger.info(user_addresses)
    save_dict()

    await context.bot.send_message(chat_id=chat_id, text=f"Address '{new_address}' added to your list.")

    return ConversationHandler.END

async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    update.message.reply_text("Registration cancelled")
    
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """unknown message."""
    await update.message.reply_text("Unknown message")


def main():
    #*** Init variables ***
    user_address_file = Path("user_address_file.pkl")
    if user_address_file.is_file():
        get_dict()

    #*** Start the bot ***
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TOKEN).build()

    #Conversation paths
    conv_handler_start = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ENTERING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
        conversation_timeout=60
    )

    conv_handler_reg = ConversationHandler(
        entry_points=[CommandHandler('reg', reg_command)],
        states={
            ENTERING_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, address)],
        },
        fallbacks=[CommandHandler('cancel', cancel_registration)],
        conversation_timeout=60
    )

    application.add_handler(conv_handler_start)
    application.add_handler(conv_handler_reg)

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("run", run))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("rund", run_daily_command))

    # on non command i.e message - unknown message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()