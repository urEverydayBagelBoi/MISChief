# bot.py
# welcome to probably the worst code you've seen in your life (. ❛ ᴗ ❛.)
# please note i am a complete beginner so sorry if some things make zero sense
# from datetime import tzinfo, timedelta
# from types import NoneType
from operator import contains

# TODO:
# per server/guild preferences, like disabling funnies for an entire server
# make respond to 'you know what that means' with 'fish orgy' if the channel its sent in is NSFW
# use discord.utils.format_dt()
# make word prompts use contains_word() instead of 'word in str'

import aiosqlite
import sqlite3
from rich.logging import RichHandler
# from rich.style import Style
import rich.console
# from rich import print
import logging
from dotenv import load_dotenv
# import math
import re
import random
import os
# Note that ZoneInfo requires timezone data (usually from the 'tzdata' package installed separately)
from zoneinfo import ZoneInfo
import zoneinfo
import datetime
# Main (Discord networking lib)
import discord
from discord import app_commands
from discord.ext import tasks
import time

# Discord connection setup and variables
client = discord.Client(intents=discord.Intents.all())
tree = app_commands.CommandTree(client)


def remove_formatting(text):  # Removes Discord/Markdown formatting
    return re.sub(r"[*_`~]", "", text)

# Takes a ZoneInfo timezone (NAME AS STRING) and converts it to a UTC offset, returning it as a pretty string.
def timezone_to_utc(timezone:str):
    if timezone is None:
        logging.warning(f'    timezone_to_utc(): got {timezone} as input. Returning.')
        return
    logging.info(f'    timezone_to_utc(): got {timezone} as input.')
    offset = datetime.datetime.now(ZoneInfo(timezone)).utcoffset()
    logging.info(f'     timezone_to_utc(): converted timezone {timezone} to UTC{offset}')
    if offset.total_seconds() < 0:
        return f"UTC{offset}"
    else:
        return f"UTC+{offset}"

# Finds a word in a string (that isn't part of a word or anything)
def contains_word(s, w):
    return f' {w} ' in f' {s} '


# Loading bot token from environment variables pulled from '.env' file
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
database = os.getenv('USERDBPATH')

# discord.py attaches to this for logging
discord_logger = logging.FileHandler(
    filename='discord.log', encoding='utf-8', mode='w')

# rich formatting
console = rich.console.Console()
_FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=_FORMAT, datefmt="[%X]", handlers=[RichHandler(level=logging.INFO, rich_tracebacks=True)]
)

# These are synchronous (non-async) and are only used for global tasks
# like creating, setting up and verifying the database itself and doing a mass check of users.
syncConn = sqlite3.connect(database)
syncCursor = syncConn.cursor()


def create_tables():
    # If the required tables do not exist, create them.
    syncCursor.execute("PRAGMA foreign_keys = True;")
    syncCursor.execute('''
        CREATE TABLE IF NOT EXISTS "users" (
    	    "id"	INTEGER NOT NULL UNIQUE,
    	    "username"  TEXT NOT NULL,
    	    "timezone"	TEXT,
    	    "timezone_private"	INTEGER DEFAULT 1,
            "recently_bothered" INTEGER,
    	    "recent_message_type"	TEXT,
    	    "bedtime_message"	TEXT,
    	    "bedtime_time"	TEXT,
    	    "bedtime_applicant_username"	TEXT,
    	    PRIMARY KEY("id")
        );
    ''')

    syncCursor.execute('''
        CREATE TABLE IF NOT EXISTS "subscriptions" (
    	    "id"	INTEGER NOT NULL UNIQUE,
    	    "bedtime"	INTEGER NOT NULL DEFAULT 0,
    	    "funnies"	INTEGER NOT NULL DEFAULT 1,
    	    "shutup"    INTEGER NOT NULL DEFAULT 0,
    	    FOREIGN KEY("id") REFERENCES "users"("id") ON DELETE CASCADE,
    	    PRIMARY KEY("id")
        );  
                   
    ''')
    syncConn.commit()


# All required columns for user-data tables.
# Used to create and verify columns
# the above code for creating tables should also be updated
# alongside the code below
user_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',  # assumed to exist by creation, primary key
    'username': 'TEXT',  # assumed to exist by creation
    'timezone': 'TEXT',
    # bool that defines whether timezone should be visible to other users
    'timezone_private': 'INTEGER DEFAULT 1',
    'recently_bothered': 'INTEGER',  # datetime stored as unix timestamp
    # for example, if recent message is from a subscription, name of type of the message = name of subscription it's from (see 'subscription_columns'.)
    'recent_message_type': 'TEXT',
    'bedtime_message': 'TEXT',
    'bedtime_time': 'TEXT',  # stored as %H:%M
    # person that used the bedtime command on them
    'bedtime_applicant_username': 'TEXT'
}

subscription_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',  # references 'id' in 'users', primary key
    'bedtime': 'INTEGER NOT NULL DEFAULT 0',  # bedtime reminders
    # responses to funny numbers and other stupid unprompted stuff
    'funnies': 'INTEGER NOT NULL DEFAULT 1',
    'shutup': 'INTEGER NOT NULL DEFAULT 0',
}


async def add_user(user_id):
    async with (aiosqlite.connect(database) as conn):
        try:
            # Insert user
            username = (await client.fetch_user(user_id)).name
            await conn.execute('''INSERT INTO users (id, username) VALUES (?, ?)''', (user_id, username))
            # Insert subscriptions
            await conn.execute('''INSERT INTO subscriptions (id) VALUES (?)''', (user_id,))
            await conn.commit()
        except aiosqlite.Error as e:
            # rollback on error
            await conn.rollback()
            logging.error(f"           [DATABASE USER ADD ERROR]: {e}")
            console.bell()


def verify_columns(table_name, columns):
    if not isinstance(columns, dict):
        raise ValueError(
            'verify_columns(): columns parameter must be a dictionary')

    syncCursor.execute(f'PRAGMA table_info({table_name})')
    existing_columns = syncCursor.fetchall()
    # DEBUG
    logging.info(f"    [existing_columns]: {existing_columns}")
    existing_column_names = ['id'] + [column[1] for column in existing_columns]
    syncConn.execute('BEGIN;')
    try:
        for column_name, column_definition in columns.items():
            if column_name not in existing_column_names:
                # add column if it doesnt exist
                syncConn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition};')
                logging.info(f"Added column '{column_name}' to {table_name}")
            else:
                logging.info(f"Column '{column_name}' already exists in {table_name}")
        syncConn.commit()
    except sqlite3.Error as e:
        syncConn.rollback()
        logging.error(f"           [DATABASE 'verify_columns' ERROR]: {e}")
        console.bell()


async def update_user(user_id, **kwargs):
    if not kwargs:
        logging.error('update_user(): no kwargs were passed.')
        return

    # check if user exists in database, and add them to users table otherwise
    if not await user_exists(user_id):
        await add_user(user_id)
        user = await client.fetch_user(user_id)
        logging.info(f"User {user.name} did not exist in database, attempted to add.")

    # construct the set clause dynamically
    set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
    values = list(kwargs.values())
    values.append(user_id)
    sql = f"UPDATE users SET {set_clause} WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute(sql, values)
            await conn.commit()

    except aiosqlite.Error as e:
        logging.error(f"[DATABASE USER UPDATE ERROR]: {e} | SQL: {sql} | Values: {values}")
        console.bell()

async def update_subscriptions(user_id, **kwargs):
    if not kwargs:
        return

    # construct the set clause dynamically
    set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
    values = list()
    for value in kwargs.values():
        values.append(int(value)) # convert bool to int
    values.append(user_id)
    sql = f"UPDATE subscriptions SET {set_clause} WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute(sql, values)
            await conn.commit()

    except aiosqlite.Error as e:
        logging.error(f"[DATABASE SUBSCRIPTION UPDATE ERROR]: {e} | SQL: {sql} | Values: {values}")
        console.bell()


async def delete_user(user_id):
    if not await user_exists(user_id):
        return

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    except aiosqlite.Error as e:
        logging.error(f'           [DATABASE DELETE USER ERROR]: {e}')
        console.bell()

async def is_subscribed(user_id, subscription):
    try:
        async with aiosqlite.connect(database) as conn:
            query = f"SELECT {subscription} FROM subscriptions WHERE id = ?"
            async with conn.execute(query, (user_id,)) as cursor:
                value = await cursor.fetchone()
                if value is None:
                    return False
                value = value[0]
                logging.info(f'is_subscribed():  Got subscription [{subscription}] for user [{user_id}]: {value}')
                return bool(value)


    except aiosqlite.Error as e:
        logging.error(f'           [DATABASE SUBSCRIPTION RETRIEVAL ERROR]: {e}')
        console.bell()


async def user_exists(user_id):
    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute('SELECT COUNT(*) FROM users WHERE id = ?', (user_id,)) as cursor:
                data = (await cursor.fetchone())[0]
                return bool(data)
    except aiosqlite.Error as e:
        logging.error(f"           [USER EXISTS VERIFICATION ERROR]: {e}")
        console.bell()


async def get_user_data(user_id, *args):
    if not args:
        return
    # check if user exists in database and add them to users table otherwise
    if not await user_exists(user_id):
        await add_user(user_id)
        user = client.get_user(user_id)
        logging.info(f"User {user.name} did not exist in database, attempted to add.")

    # Construct the Set clause dynamically
    clause = ', '.join(args)
    sql = f"SELECT {clause} FROM users WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute(sql, (user_id,)) as cursor:
                output = await cursor.fetchall()

    except aiosqlite.Error as e:
        logging.error(f"           [DATABASE 'get_user_data' ERROR]: {e}")
        console.bell()
        return None

    # return single value if only one column is requested
    if len(args) == 1:
        return output[0][0] if output else None

    # return as tuple if multiple columns are requested
    return output[0] if output else None


async def bedtime_check(user_id, channel_id=None):
    if await poked_within(user_id, datetime.timedelta(minutes=15)):
        logging.info('bedtime_check(): user was bothered within 15 minutes from now, skipping bedtime check.')
        return

    timezone_str, bedtime_str, username, message, applicant = await get_user_data(user_id, 'timezone', 'bedtime_time',
                                                                                  'username', 'bedtime_message',
                                                                                  'bedtime_applicant_username')
    timezone_obj = ZoneInfo(timezone_str)
    local_time = datetime.datetime.now().astimezone(timezone_obj)
    logging.info(f"bedtime_check: Calculated time for user [{username}] in [{timezone_str}]: {local_time}")

    start = datetime.datetime.strptime(bedtime_str, "%H:%M").time()
    end = datetime.time(5, 30)

    if start < end:
        is_bedtime = start <= datetime.datetime.now().time() <= end
    else:
        now = datetime.datetime.now().time()
        is_bedtime = now >= start or now <= end

    if is_bedtime:
        logging.info(
            f"bedtime_check: Decided bedtime for user {username}. Start time: {start} - End time: {end} - Current time: {local_time}")
        if channel_id:
            channel = await client.fetch_channel(int(channel_id))
            if message:
                await channel.send(f"<@{user_id}>,\n> {message}\n*Bedtime message by {applicant}*")
            else:
                await channel.send(
                    f"<@{user_id}>, it's after {bedtime_str} in your timezone! Go to bed!\n*Bedtime message from {applicant}*")
            await update_user(user_id, recent_message_type='bedtime')
        else:
            user = client.get_user(user_id)
            if message:
                await user.send(f"<@{user_id}>,\n> {message}\n*Bedtime message by {applicant}*")
            else:
                await user.send(
                    f"<@{user_id}>, it's after {bedtime_str} in your timezone! Go to bed!\nBedtime message from {applicant}")
        await reset_poke_time(user_id)

    else:
        logging.info(f"bedtime_check: Decided [underline]NOT[/] bedtime for user {username}.", extra={"markup": True})
        # console.print(f"bedtime_check: Decided [underline]NOT[/] bedtime for user {username}.")
        pass


async def reset_poke_time(user_id):
    # check if user exists in database and add them to users table otherwise
    # this shouldn't ever run because a user shouldn't be bothered if not
    # told to, and said user should be registered if so.
    if not await user_exists(user_id):
        await add_user(user_id)
        logging.critical(
            f"[bold red blink]User {client.get_user(user_id).name} did not exist in database when 'reset_poke_time' was called."
            "This means a user was bothered [underline]UNPROMPTED[/][/]",
            extra={"markup": True}
        )

    try:
        async with aiosqlite.connect(database) as conn:
            unixepoch = time.time()
            await conn.execute("UPDATE users SET recently_bothered = ? WHERE id = ?", (unixepoch, user_id))
            await conn.commit()
    except aiosqlite.Error as e:
        logging.error(f'           [\'reset_poke_time\' UPDATE ERROR]: {e}')
        console.bell()


async def poked_within(user_id, timedelta: datetime.timedelta = None, return_difference: bool = None):
    """
    Returns whether a user was bothered within a certain timeframe passed as datetime.timedelta,
    or how much time has passed since the last time the user was bothered.
    Returned difference may be None if no last bother time is registered for the user
    """
    if not await user_exists(user_id):
        return

    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute("SELECT recently_bothered FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()

                if row is None or row[0] is None:
                    # No data found or never bothered
                    difference = None
                else:
                    then = row[0]
                    now = datetime.datetime.now().timestamp()
                    difference = now - then

                if timedelta:
                    minimum_difference = timedelta.total_seconds()
                    recent = difference is not None and difference < minimum_difference

                if timedelta and return_difference:
                    return recent, difference
                elif timedelta:
                    return recent
                elif return_difference:
                    return difference
                else:
                    raise ValueError(
                        "'poked_within' must be given either a timedelta, True for return_difference, or both.")

    except aiosqlite.Error as e:
        logging.error(f'           [\'poked_within\' ERROR]: {e}')
        console.bell()


@client.event
async def on_ready():
    await tree.sync()
    check_all_bedtimes.start()
    verify_columns(table_name='users', columns=user_columns)
    verify_columns(table_name='subscriptions', columns=subscription_columns)
    logging.info(
        f"[bright_magenta]    || [Ready. Logged in as {client.user}] ||\n",
        extra={"markup": True})
    logging.info(f"Database path: {database}")


@client.event
async def on_close():
    syncConn.close()
    syncCursor.close()

greeting_prompts = ('hello', 'hi', 'salutations', 'helo', 'hai',
                    'greetings', 'hey', 'heey', 'hallo', 'sup', 'hoi', 'howdy')
greeting_responses = ['hiii :3', 'sup!', 'helo!!!',
                      'haiii!!!!', 'hi', 'hello world!!!', 'mrrowdy!!', 'howdy :P',
                      "salutations sir/ma'am/whateverelseyouprefer, how may i help you?"]
shutup_prompts = ['shut up', 'stfu', 'su', 'shut the fuck up', 'stop']
shutup_responses = ['awww okay :<', 'okay :(', 'oh okay :3', 'okay fine', 'ughhh whatever :rolling_eyes:']
fish_prompts = ('you know what that means', 'fish')
fish = '🐟'
two_emoji = '2️⃣'
one_emoji = '1️⃣'
twentyone_prompts = ("whats 9 plus 10", "what's 9 plus 10", "whats 9 + 10", "what's 9 + 10",
                     "whats nine plus ten", "what's nine plus ten", "whats nine + ten", "what's nine + ten")
keywords = ['727', '69', '420', '42', 'auto', 'car', 'audi', 'kip']

shutup_users = {} # if shut up is used they are remembered in this cache for 5 minutes and then deleted if they do not confirm

@client.event
async def on_message(message):
    # Log messages (and return if message is from own client)
    if message.author == client.user:
        logging.info(
            f"\n[black on white]{message.author}[/] [bright_black][{(message.created_at.astimezone()).strftime('%H:%M')}][/]\n{message.content}\n",
            extra={"markup": True})
        return
    logging.info(
        f"[white on blue]{message.author}[/] [bright_black][{message.created_at.strftime('%H:%M')}][/]\n{message.content}\n",
        extra={"markup": True})


    # if the bot is DMed or mentioned, hint to slash commands (unless message is a text prompt response)
    if isinstance(message.channel, discord.DMChannel):
        if (message.content.lower()).startswith(greeting_prompts):
            await message.channel.send(
                f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*")
        else:
            if (any(contains_word(message.content.lower(), prompt)) for prompt in shutup_prompts) or message.content.lower() == 'confirm':
                pass
            else:
                await message.channel.send(f"> *pssst! i work with slash commands, type '/' to continue!*")
    if client.user.mention in message.content and not (any(contains_word(message.content.lower(), prompt)) for prompt in shutup_prompts):
        await message.reply(
            f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*",
            mention_author=True)


    # shut up if the bot is told to
    if message.content.lower() == 'confirm' and message.author.id in shutup_users:
        shutup_users.pop(message.author.id, None)
        await message.reply(f"Got it, I won't bother you with any nonsense.\n You can re-enable funny stuff by using /nvm.")
        if not await user_exists(message.author.id):
            await add_user(message.author.id)
        await update_subscriptions(message.author.id, funnies=False, bedtime=False, shutup=True)
    elif message.author.id in shutup_users and not 'confirm' in message.content.lower():
        shutup_users.pop(message.author.id, None)

    for id, time in shutup_users.items():
        if time > datetime.datetime.utcnow() - datetime.timedelta(minutes=5):
            shutup_users.pop(id, None)    # forget user after 5 minutes

    _messages = [msg async for msg in message.channel.history(limit=2)]
    if len(_messages) < 2:
        second_recent_message = None
    else:
        second_recent_message = _messages[1]

    if ( # check if message directed at MISChief
            isinstance(message.channel, discord.DMChannel) or client.user.mention in message.content
            or (message.reference and client.user.mention in message.reference.resolved.content)
            or (message.reference and message.reference.resolved.author.id == client.user.id)
    ) and any(contains_word(message.content.lower(), prompt) for prompt in shutup_prompts):
        shutup_users[message.author.id] = datetime.datetime.utcnow()
        await message.reply(f"{random.choice(shutup_responses)}\n**Are you sure?**\n-# Type 'confirm' to confirm.")


    # Funnie responses
    if not await user_exists(message.author.id) or await is_subscribed(message.author.id, 'funnies'):
        logging.info('user was subscribed to funnies. commencing the funny')

        if any(contains_word(message.content.lower(), prompt) for prompt in fish_prompts):
            await update_user(message.author.id, recent_message_type='funnies')
            await message.add_reaction(fish)
            await message.reply("**fish!**", mention_author=True)
            logging.info(f"{message.author} got fished")

        if any(contains_word(message.content.lower(), prompt) for prompt in twentyone_prompts):
            await update_user(message.author.id, recent_message_type='funnies')
            await message.add_reaction(two_emoji)
            await message.add_reaction(one_emoji)
            logging.info(f"{message.author} asked what 9 + 10 is")

        # pointing out various keywords, like funnie numbers
        _response = ""
        for keyword in keywords:
            if keyword in message.content:
                if keyword in ['audi', 'auto', 'car']:
                    if not message.author.id == 1037620054721835029:
                        return
                logging.info('FUNNIE DETECTED')
                # split message into sentences
                sentences = re.split(r'(?<=[.!?]) +', message.content)
                # find sentence with keyword
                for sentence in sentences:
                    if keyword in sentence:
                        # Remove other formatting
                        cleaned_sentence = remove_formatting(sentence)
                        # Bold keyword
                        highlighted_sentence = cleaned_sentence.replace(
                            keyword, f" ***{keyword}*** ")
                        _response += f"> {highlighted_sentence}\n"
                        if keyword == '727':
                            _response += 'WYSI\n\n'
                        if keyword == '69' or keyword == '420':
                            _response += 'nice\n\n'
                        if keyword == '42':
                            _response += 'the answer to life, the universe and everything.\n\n'
                        if (keyword == 'auto' or keyword == 'car' or keyword == 'audi') and message.author.id == 1037620054721835029:
                            _response += 'met koelkast? :)\n\n'
                        if keyword == 'kip':
                            _response += 'het meest veelzijdige stukje vleest taar- vis!- **kut**.\n\n'
        if _response != "":
            await message.reply(_response, mention_author=False)
            await update_user(message.author.id, recent_message_type='funnies')

    if await is_subscribed(message.author.id, 'bedtime'):
        await bedtime_check(message.author.id, message.channel.id)


# @tasks.loop(minutes=5)
# async def check_all_bedtimes():
#     try:
#         async with aiosqlite.connect(database) as conn:
#             async with conn.execute("SELECT id FROM subscriptions WHERE bedtime = 1") as cursor:
#                 async for row in cursor:
#                     user_id, = row
#                     await bedtime_check(user_id)
#     except aiosqlite.Error as e:
#         logging.error(f'           [\'check_all_bedtimes()\' ERROR]: {e}')

@tasks.loop(minutes=15)
async def check_all_bedtimes():
    try:
        syncCursor.execute("SELECT id FROM subscriptions WHERE bedtime = 1")
        for row in syncCursor:
            user_id, = row
            await bedtime_check(user_id)
    except sqlite3.Error as e:
        logging.error(f'           [\'check_all_bedtimes()\' ERROR]: {e}')


        # COMMANDS


# Functions for commands


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.channel,
                      discord.channel.DMChannel) or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            "You do not have the required permissions to use this command. (Administrator)", ephemeral=True)
        return False

    return app_commands.check(predicate)


def is_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        developer_ids = {582583719546847234}  # edited from here
        if interaction.user.id in developer_ids:
            return True
        await interaction.response.send_message("you're not a dev!! go away, shoo.")
        return False

    return app_commands.check(predicate)


async def timezone_autocomplete(interaction: discord.Interaction, current: str):
    return [
               app_commands.Choice(name=timezone, value=timezone)
               for timezone in zoneinfo.available_timezones() if current.lower() in timezone.lower()][:25]


# Commands (the actual commands)
@tree.command(
    name="gotosleep",
    description="\"Subtly\" remind someone to go to bed when they are online after bedtime."
)
@app_commands.describe(user="The user to bother", time="Bedtime. Format: [HOUR]:[MINUTE] (24-hour, devided by a ':')",
                       message="The message to send with each reminder",
                       timezone="Timezone to account for (if target user has not yet set it themselves)")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def gotosleep(interaction:discord.Interaction,user:discord.User,time:str,timezone:str=None,
                    message: str = None):
    # check if user exists in database and add them to users table otherwise
    if not await user_exists(user.id):
        await add_user(user.id)
        logging.info(
            f"User {user.name} did not exist in database, attempted to add.")
    if await is_subscribed(user.id, 'shutup'):
        await interaction.response.send_message(f"{user.name} told me to shut up sooo uhhhh... no can do. :3")
        return

    # check if given time valid
    try:
        _ = datetime.datetime.strptime(time, "%H:%M").time()
        logging.info(f"gotosleep: Time {time} was considered valid.")
    except ValueError:
        await interaction.response.send_message(f"Time `{time}` isn't formatted correctly.")
        return
    except TypeError:
        logging.info(f"gotosleep: User had no bedtime registered")
        return

    if timezone is not None:
        if timezone not in zoneinfo.available_timezones():
            await interaction.response.send_message(f"Invalid timezone: {timezone}")
            return
        await update_user(user.id, timezone=timezone, timezone_private=1)
        logging.info("gotosleep: Attempted to update user timezone")

    user_data = await get_user_data(user.id, 'timezone', 'timezone_private')
    if user_data is not None:
        registered_timezone, timezone_private = user_data
        if timezone_private:
            public_timezone = timezone_to_utc(registered_timezone)
        else:
            public_timezone = registered_timezone
    else:
        registered_timezone = None
        timezone_private = None
        public_timezone = None

    if registered_timezone is None and timezone is None:
        await interaction.response.send_message(f"User does not have a timezone registered (nor was one specified).")
        return

    response = ""
    if registered_timezone not in zoneinfo.available_timezones():
        response += (f'\n'
                     f'User had an invalid timezone registered somehow. Setting timezone to `{timezone_to_utc(timezone)}`\n'
                     f'-# (timezone converted to UTC offset for privacy reasons)\n'
                     f'> uh-oh,,, that really shouldn\'t have happened.... please report this to my developer :,3\n\n')
    else:
        response += f"User already has timezone `{public_timezone}` registered. Setting bedtime to `{time}` in that timezone.\n"

    await update_user(user.id, bedtime_time=time, bedtime_message=message,
                      bedtime_applicant_username=interaction.user.name)
    await update_subscriptions(user.id, bedtime=True)

    user_data = await get_user_data(
        user.id,
        'username',
        'bedtime_time',
        'bedtime_message',
        'bedtime_applicant_username'
    )
    if user_data is not None:
        username, time, message, applicant_username = user_data
    else:
        username = None
        time = None; message = None
        applicant_username = None

    response += (
        f"Registered bedtime for user ***{username}***:\n"
        f"Bedtime: **`{time}`**\n"
        f"Bedtime message: **{message}**\n"
        f"Bedtime applicant (will be credited on sending the message): **{applicant_username}**"
    )
    await interaction.response.send_message(response)


@tree.command(
    name="bedtimecheck",
    description="Dev command for manually checking if a user is up after bedtime"
)
@app_commands.describe(user="The user to bother")
@is_dev()
async def bedtimecheck(interaction: discord.Interaction, user: discord.User):
    if await user_exists(user.id):
        if await is_subscribed(user.id, subscription='bedtime'):
            poked, difference = poked_within(user.id, datetime.timedelta(minutes=15), return_difference=True)
            if not poked:
                await bedtime_check(user.id, interaction.channel_id)
                await interaction.response.send_message('User was subscribed to bedtime, attempted bedtime check.', ephemeral=True)
            else:
                await interaction.response.send_message(f"User was subscribed to bedtime but was bothered less than {difference} ago. Try again later.")
        else:
            await interaction.response.send_message('User not subscribed to bedtime', ephemeral=True)
    else:
        await interaction.response.send_message('User does not exist in database.', ephemeral=True)


@tree.command(
    name="getrecentbother",
    description="Dev command for manually getting when a user was most recently bothered by the bot."
)
@app_commands.describe(user="Target user")
@is_dev()
async def getrecentbother(interaction: discord.Interaction, user: discord.User):
    if await user_exists(user.id):
        await interaction.response.send_message(str(await poked_within(user_id=user.id, return_difference=True)) + " minutes")


@tree.command(
    name="getusertime",
    description="Gets a user's local time if they have a timezone set."
)
async def getusertime(interaction: discord.Interaction, user: discord.User):
    if await user_exists(user.id):
        timezone_str = await get_user_data(user.id, 'timezone')
        if timezone_str:
            timezone = ZoneInfo(timezone_str)
            if datetime.datetime.now().astimezone(timezone).time() >= datetime.time(hour=12):
                await interaction.response.send_message(f"It's {(datetime.datetime.now().astimezone(timezone)).strftime('`%H:%M`/`%I:%M %p` (%d %b)')} for {user.display_name}")
            else:
                await interaction.response.send_message(f"It's {datetime.datetime.now().astimezone(timezone).strftime('%H:%M(%p) (%d %b)')} for {user.display_name}")
        else:
            await interaction.response.send_message("User does not have a timezone registered.")
    else:
        await interaction.response.send_message("User doesn't exist in database.")


@tree.command(
    name="convertusertime",
    description="Converts a time in your timezone to the equivalent time in theirs, if they've set one."
)
@app_commands.describe(time="Format: `[HOUR]`:`[MINUTE]` (24-hour, devided by a ':')", timezone="Own/source timezone (this isn't registered)")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def convertusertime(interaction: discord.Interaction, user: discord.User, time: str, timezone: str=None):
    if timezone and timezone not in zoneinfo.available_timezones():
        await interaction.response.send_message(f"Invalid timezone: {timezone}")
    if await user_exists(user.id):
        target_timezone_str = await get_user_data(user.id, 'timezone')
        if target_timezone_str:
            if target_timezone_str not in zoneinfo.available_timezones():
                await interaction.response.send_message("Target user timezone invalid! (report this to my dev)")
                return
            if not timezone:
                source_timezone_str = await get_user_data(interaction.user.id, 'timezone')
                if not source_timezone_str:
                    await interaction.response.send_message("You don't have a timezone registered, nor was a source timezone specified.")
                    return
            else:
                source_timezone_str = timezone

            target_timezone = ZoneInfo(target_timezone_str)
            source_timezone = ZoneInfo(source_timezone_str)
            if time:
                conversion_time = datetime.datetime.strptime(time, "%H:%M").replace(tzinfo=source_timezone)
            else:
                conversion_time = datetime.datetime.strptime(datetime.datetime.now(tzinfo=source_timezone))
            converted_time = conversion_time.astimezone(target_timezone).time()
            await interaction.response.send_message(
                f"{conversion_time.strftime('`%H:%M`/`%I:%M %p`')} for {interaction.user.name} -> {converted_time.strftime('`%H:%M`/`%I:%M %p`')} for {user.display_name}")
        else:
            await interaction.response.send_message("Target user does not have a timezone registered.")
    else:
        await interaction.response.send_message("Target user doesn't exist in database.")


@tree.command(
    name="settimezone",
    description="Registers your timezone in the bot's database."
)
@app_commands.describe(timezone="Timezone list: https://zones.arilyn.cc/",private="Whether full timezone or only UTC offset is public")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def settimezone(interaction: discord.Interaction, timezone: str, private: bool):
    # check if user exists in database and add them to users table otherwise
    if not await user_exists(interaction.user.id):
        await add_user(interaction.user.id)
        logging.info(
            f"User {interaction.user.name} did not exist in database, attempted to add.")

    if timezone not in zoneinfo.available_timezones():
        await interaction.response.send_message(f"Invalid timezone: {timezone}")
        return

    try:
        await update_user(interaction.user.id, timezone=timezone, timezone_private=private)
        logging.info("settimezone: Attempted to update user timezone")
        if not private:
            await interaction.response.send_message(f"Set timezone to `{timezone}`.")
        else:
            await interaction.response.send_message(f"Set timezone to `{timezone_to_utc(timezone)}`")

    except aiosqlite.Error as e:
        await interaction.response.send_message(f"Setting timezone failed! :( (report this to my dev)\n`{e}`")


@tree.command(
    name="funnies",
    description="Toggles annoying unprompted funny replies for you"
)
async def togglefunnies(interaction: discord.Interaction):
    if await user_exists(interaction.user.id):
        if not await is_subscribed(interaction.user.id, 'funnies'):
            await update_subscriptions(interaction.user.id, funnies=True)
            await interaction.response.send_message('funnies re-enabled.')
            return
        else:
            await update_subscriptions(interaction.user.id, funnies=False)
            await interaction.response.send_message('ok no more funnies :thumbsup:')
            return
    else:
        await add_user(interaction.user.id)
        await update_subscriptions(interaction.user.id, funnies=False)
        await interaction.response.send_message('ok no more funnies :thumbsup:')

@tree.command(
    name="nvm",
    description="Reverts 'shutup' and allows funny stuff again"
)
@app_commands.describe(enablefunnies="whether to re-enable annoying unprompted funny replies")
async def nvm(interaction: discord.Interaction, enablefunnies: bool):
    if await user_exists(interaction.user.id):
        await update_subscriptions(interaction.user.id, shutup=False)
        await interaction.response.send_message("we can now annoy you again :thumbsup:\n-# if you want funnies to be enabled too use /funnies")
    else:
        await interaction.response.send_message("i don't know you... :face_with_raised_eyebrow:\n-# (you don't exist in my database")


# Start the bot
create_tables()
client.run(
    token=TOKEN,
    log_handler=discord_logger,
    log_level=logging.NOTSET,
    root_logger=False
)
