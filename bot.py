# bot.py
# welcome to probably the worst code you've seen in your life (. ❛ ᴗ ❛.)

# TO DO:
# 'shut up' command and other essential anti-nuisance stuff
# per server/guild preferences, like disabling funnies for an entire server
# a guided server setup for the above
# make pycodestyle compliant


import aiosqlite
import sqlite3
from rich.logging import RichHandler
from rich.style import Style
import rich.console
from rich import print
import logging
from dotenv import load_dotenv
import math
import re  # Useful for reformatting strings
import random
import os
from zoneinfo import ZoneInfo # Note that this library requires timezone data (usually from the 'tzdata' package installed seperately)
import zoneinfo
import datetime
# Main (Discord networking lib)
import discord
from discord import app_commands
from discord.ext import tasks

# Discord connection setup and variables
client = discord.Client(intents=discord.Intents.all())
tree = app_commands.CommandTree(client)

def remove_formatting(text):  # Removes Discord/Markdown formatting
    return re.sub(r"[*_`~]", "", text)

def timezone_to_utc(timezone=str):
    offset = datetime.datetime.now(ZoneInfo(timezone)).utcoffset(
    ).total_seconds()/60/60  # this is in fractional hours

    hours = math.floor(abs(offset))
    minutes = (abs(offset) - hours) * 60
    if offset < 0:
        return f"UTC-{hours}:{minutes}"
    else:
        return f"UTC+{hours}:{minutes}"


# Loading bot token from environment variables pulled from '.env' files for security reasons
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')


# discord.py attaches to this and creates the log file
discord_logger = logging.FileHandler(
    filename='discord.log', encoding='utf-8', mode='w')


# Rich formatting
danger_style = Style(color="red", blink=True, bold=True)
console = rich.console.Console()
_FORMAT = "%(message)s"
logging.basicConfig(
    level="NOTSET", format=_FORMAT, datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)]
)


# Relative path to .db file that stores user must be entered here
database = 'testing.db'

# These are non-asynchronous and only used for important one off things
# like creating, setting up and verifying the database itself.
conn = sqlite3.connect(database)
cursor = conn.cursor()


def create_tables():
    # If the required tables do not exist, create them.
    cursor.execute("PRAGMA foreign_keys = True;")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "users" (
    	    "id"	INTEGER NOT NULL UNIQUE,
    	    "timezone"	TEXT,
    	    "timezone_private"	INTEGER DEFAULT 1,
            "recently_bothered"	INT,
    	    "recent_message_type"	TEXT,
    	    "bedtime_message"	TEXT,
    	    "bedtime_time"	TEXT,
    	    "bedtime_applicant_username"	TEXT,
    	    PRIMARY KEY("id")
        );
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS "subscriptions" (
    	    "id"	INTEGER NOT NULL UNIQUE,
    	    "bedtime"	INTEGER NOT NULL DEFAULT 0,
    	    "funnies"	INTEGER NOT NULL DEFAULT 1,
    	    FOREIGN KEY("id") REFERENCES "users"("id") ON DELETE CASCADE,
    	    PRIMARY KEY("id")
        );  
                   
    ''')
    conn.commit()


# All required columns in the 'users' table.
# This dictionary is used directly for
# verifying columns in their respective tables
# and to note which should exist.
# the above code for creating tables should also be updated.
user_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',    # assumed to exist by creation, primary key
    'username': 'TEXT',  # assumed to exist by creation
    'timezone': 'TEXT',
    # bool that defines wether timezone should be visible to other users
    'timezone_private': 'INTEGER DEFAULT 1',
    'recently_bothered': 'INT',  # datetime stored as unix timestamp
    # for example, if recent message is from a subscription, name of type of the message = name of subscription it's from (see 'subscription_columns'.)
    'recent_message_type': 'TEXT',
    'bedtime_message': 'TEXT',
    'bedtime_time': 'TEXT',  # stored as %H:%M
    # person that used the bedtime command on them
    'bedtime_applicant_username': 'TEXT'
}

subscription_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',    # references 'id' in 'users', primary key
    'bedtime':  'INTEGER NOT NULL DEFAULT 0',   # bedtime reminders
    # responses to funny numbers and other stupid unprompted stuff
    'funnies': 'INTEGER NOT NULL DEFAULT 1',
}


async def verify_columns(table_name, columns):
    if not isinstance(columns, dict):
        raise ValueError(
            "columns parameter for verify_columns must be a dictionary")

    async with aiosqlite.connect(database) as conn:
        cursor = conn.cursor()

        # get column info
        cursor.execute("PRAGMA table_info(?);", (table_name,))
        existing_columns = cursor.fetchall()

        existing_column_names = [column[1] for column in existing_columns]

        conn.execute('BEGIN;')
        try:
            for column_name, column_definition in columns.items():
                if column_name not in existing_column_names:
                    # Add the column if it does not exist
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {
                                   column_name} {column_definition};")
                    logging.debug(f"Added column '{
                                  column_name}' to {table_name}")
                else:
                    logging.debug(
                        f"Column '{column_name}' already exists in {table_name}")
            conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            # console.print("           [DATABASE 'verify_columns' ERROR]: {e}", style=danger_style)
            logging.error(f"           [DATABASE 'verify_columns' ERROR]: {e}")
            console.bell()


async def add_user(user_id, username: str = None):
    try:
        if not username:
            username = client.fetch_user(user_id).name

        async with aiosqlite.connect(database) as conn:
            # Insert user
            await conn.execute('''INSERT INTO users (id, username) VALUES (?, ?)''', (user_id, username))
            # Insert subscriptions
            await conn.execute('''INSERT INTO subscriptions (id) VALUES (?)''', (user_id,))

    except aiosqlite.Error as e:
        # rollback on error
        conn.rollback()
        # console.print(f"           [DATABASE USER ADD ERROR]: {e}", style=danger_style)
        logging.error(f"           [DATABASE USER ADD ERROR]: {e}")
        console.bell()


async def update_user(user_id, **kwargs):
    if not kwargs:
        return

    # Check if user exists in database, and add them to users table otherwise
    if not await user_exists(user_id):
        await add_user(user_id)
        logging.debug(f"User {client.get_user(
            user_id).name} did not exist in database, attempted to add.")

    # Construct the Set clause dynamically
    set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
    values = list(kwargs.values())
    values.append(user_id)
    sql = f"UPDATE users SET {set_clause} WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute(sql, values)
            await conn.commit()

    except aiosqlite.Error as e:
        conn.rollback()
        # console.print(f"           [DATABASE USER UPDATE ERROR]: {e}", style=danger_style)
        logging.error(f"           [DATABASE USER UPDATE ERROR]: {e}")
        console.bell()


async def update_subscriptions(user_id, **kwargs):
    if not kwargs:
        return

    # check if user exists in database and add them to users table otherwise
    if not await user_exists(user_id):
        await add_user(user_id)
        logging.debug(f"User {client.get_user(
            user_id).name} did not exist in database, attempted to add.")

    # construct the Set clause dynamically
    set_clause = ', '.join(f"{key} = ?" for key in kwargs.keys())
    values = list(kwargs.values())
    values.append(user_id)

    sql = f"UPDATE subscriptions SET {set_clause} WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute(sql, values)
    except aiosqlite.Error as e:
        conn.rollback()
        # console.print(f"           [DATABASE USER SUBSCRIPTION UPDATE ERROR]: {e}", style=danger_style)
        logging.error(
            f"           [DATABASE USER SUBSCRIPTION UPDATE ERROR]: {e}")
        console.bell()


async def delete_user(user_id):
    if not await user_exists(user_id):
        return

    try:
        async with aiosqlite.connect(database) as db:
            await cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
    except aiosqlite.Error as e:
        conn.rollback()
        # console.print(f"           [DATABASE DELETE USER ERROR]: {e}", style=danger_style)
        logging.error(f"           [DATABASE DELETE USER ERROR]: {e}")
        console.bell()


async def is_subscribed(user_id, subscription):
    if not await user_exists(user_id):
        return

    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute("SELECT ? FROM subscriptions WHERE id = ?", (subscription, user_id)) as cursor:
                return not not (await cursor.fetchone())

    # except sqlite3.Error as e:
    except aiosqlite.Error as e:
        logging.error(
            f"           [DATABASE SUBSCRIPTION RETRIEVAL ERROR]: {e}")
        # console.print(f"           [DATABASE SUBSCRIPTION RETRIEVAL ERROR]: {e}", style=danger_style)
        console.bell()


async def user_exists(user_id):
    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute('''SELECT COUNT(*) FROM users WHERE id = ?''', (user_id,)) as cursor:
                data = (await cursor.fetchone())[0]
                return not not data  # transforms to bool

    except aiosqlite.Error as e:
        conn.rollback()
        # console.print("           [USER EXISTS VERIFICATION ERROR]: {e}", style=danger_style)
        logging.error(f"           [USER EXISTS VERIFICATION ERROR]: {e}")
        console.bell()


async def get_user_data(user_id, *args):
    if not args:
        return

    # check if user exists in database and add them to users table otherwise
    if not await user_exists(user_id):
        await add_user(user_id)
        logging.debug(f"User {client.get_user(
            user_id).name} did not exist in database, attempted to add.")

    # Construct the Set clause dynamically
    # clause = ', '.join(f"{arg} = ?" for arg in len(args))
    clause = ', '.join(args)
    sql = f"SELECT {clause} FROM users WHERE id = ?"

    try:
        async with aiosqlite.connect(database) as conn:
            async with conn.execute(sql, (user_id,)) as cursor:
                output = await cursor.fetchall()

    except aiosqlite.Error as e:
        conn.rollback()
        logging.error(f"           [DATABASE 'get_user_data' ERROR]: {e}")
        # console.print(f"           [DATABASE 'get_user_data' ERROR]: {e}", style=danger_style)
        console.bell()
        return None

    # return single value directly if only one column is requested
    if len(args) == 1:
        return output[0][0] if output else None

    # return as tuple if multiple columns are requested
    return output[0] if output else None


async def bedtime_check(user_id, channel_id=None):
    if not await user_exists(user_id):
        logging.warn(f"bedtime_check attempted for user [{
                     user_id}], but id not present in users table.")
        # console.print(f"bedtime_check attempted for user [{user_id}], but id not present in users table.", style=danger_style)
        return

    timezone_str, bedtime_str, username, message, applicant = await get_user_data(user_id, 'timezone', 'bedtime_time', 'username', 'bedtime_message', 'bedtime_applicant_username')
    timezone_obj = ZoneInfo(timezone_str)
    local_time = datetime.datetime.now().astimezone(timezone_obj)
    logging.debug(f"bedtime_check: Calculated time for user [{
                  username}] in [{timezone_str}]: {local_time}")

    start = datetime.datetime.strptime(bedtime_str, "%H:%M").time()
    end = datetime.time(5, 30)

    if start < end:
        is_bedtime = start <= datetime.datetime.now().time() <= end
    else:
        now = datetime.datetime.now().time()
        is_bedtime = now >= start or now <= end

    if is_bedtime:
        if not await poked_within(user_id, datetime.timedelta(minutes=30)):
            logging.debug(f"bedtime_check: Decided bedtime for user {username}.
                          Start time: {start} - End time: {end} - Current time: {local_time}")

            if channel_id:
                channel = await client.fetch_channel(int(channel_id))
                if message:
                    await channel.send(f"<@{user_id}>,\n> {message}\n*Bedtime message by {applicant}*")
                else:
                    await channel.send(f"<@{user_id}>, it's after {bedtime_str} in your timezone! Go to bed!
                                       \n*Bedtime message from {applicant}*")
                await update_user(user_id, recent_message_type='bedtime')

            else:
                user = client.get_user(user_id)
                if message:
                    await user.send(f"<@{user_id}>,\n> {message}\n*Bedtime message by {applicant}*")
                else:
                    await user.send(f"<@{user_id}>, it's after {bedtime_str} in your timezone! Go to bed!
                                    \nBedtime message from {applicant}")

            await reset_poke_time(user_id)

        else:
            logging.debug(
                f"bedtime_check: Decided bedtime, but user was already bothered less than 30 minutes ago")

    else:
        logging.debug(f"bedtime_check: Decided [underline]NOT[/] bedtime 
                      for user {username}.", extra={"markup": True})
        # console.print(f"bedtime_check: Decided [underline]NOT[/] bedtime for user {username}.")
        pass


async def reset_poke_time(user_id):
    """
    Resets the poke time for a user in the database.
    If the user does not exist, they are added to the database.
    """
    # check if user exists in database and add them to users table otherwise
    # this shouldn't ever run because a user shouldn't be bothered if not
    # told to, and said user should be registered if so.
    if not await user_exists(user_id):
        await add_user(user_id)
        logging.critical(f"[bold red blink]User
                         {client.get_user(user_id).name} did not exist in database when 'reset_poke_time' was called.
                         This means a user was bothered [underline]UNPROMPTED[/][/]", extra={"markup": True})

    try:
        async with aiosqlite.connect(database) as conn:
            await conn.execute("UPDATE users SET recently_bothered = unixepoch() WHERE id = ?", (user_id,))
            await conn.commit()
    except aiosqlite.Error as e:
        conn.rollback()
        # console.print("           ['reset_poke_time' UPDATE ERROR]: {e}", style=danger_style)
        logging.error("           ['reset_poke_time' UPDATE ERROR]: {e}")
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
        # console.print("           ['poked_within' ERROR]: {e}", style=danger_style)
        logging.error("           ['poked_within' ERROR]: {e}")
        console.bell()


@client.event
async def on_ready():
    await tree.sync()
    check_all_bedtimes.start()
    logging.info(
        f"[bright_magenta bold]    || [Ready. Logged in as {client.user}] ||\n")

greeting_prompts = ('hello', 'hi', 'salutations', 'helo', 'hai',
                    'greetings', 'hey', 'heey', 'hallo', 'sup', 'hoi', 'howdy')
greeting_responses = ['hiii :3', 'sup!', 'helo!!!',
                      'haiii!!!!', 'hi', 'hello world!!!', 'mrrowdy!!']
fish_prompts = ('you know what that means', 'fish')
fish = '🐟'
two_emoji = '2️⃣'
one_emoji = '1️⃣'
twentyone_prompts = ("whats 9 plus 10", "what's 9 plus 10", "whats 9 + 10", "what's 9 + 10",
                     "whats nine plus ten", "what's nine plus ten", "whats nine + ten", "what's nine + ten")
keywords = ["727", "69", "420"]


@client.event
async def on_message(message):
    # Log messages
    if message.author == client.user:
        # console.print(_)  <-- Not really needed since it prints logs to console anyway
        logging.info(f"\n[black on white]{message.author}[/] [bright_black]
                     [{(message.created_at.astimezone()).strftime("%H:%M")}][/]
                     \n{message.content}\n", extra={"markup": True})
        return
    
    # console.print(_)  <-- Not really needed since it prints logs to console anyway
    logging.info(f"[white on blue]{message.author}[/] [bright_black]
                 [{message.created_at.strftime("%H:%M")}][/]\n{message.content}\n", extra={"markup": True})

    # if the bot is DMed or mentioned, hint to slash commands
    if isinstance(message.channel, discord.DMChannel):
        if (message.content.lower()).startswith(greeting_prompts):
            await message.channel.send(f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*")
        else:
            await message.channel.send(f"> *pssst! i work with slash commands, type '/' to continue!*")
    if client.user.mention in message.content and not 'shut up' in message.content.lower():
        await message.reply(f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*", mention_author=True)

    # Funnie responses
    if await is_subscribed(message.author.id, 'funnies') or not await user_exists(message.author.id):
        for prompt in fish_prompts:
            if prompt in message.content.lower():
                await update_user(message.author.id, recent_message_type='funnies')
                await message.add_reaction(fish)
                await message.reply("**fish!**", mention_author=True)

        for prompt in twentyone_prompts:
            if prompt in message.content.lower():
                await update_user(message.author.id, recent_message_type='funnies')
                await message.add_reaction(two_emoji)
                await message.add_reaction(one_emoji)

        # pointing out various keywords, like funnie numbers
        _response = ""
        for keyword in keywords:
            if keyword in message.content:
                # Split message into sentences
                sentences = re.split(r'(?<=[.!?]) +', message.content)
                # Find sentence containing keyword
                for sentence in sentences:
                    if keyword in sentence:
                        # Remove other formatting
                        cleaned_sentence = remove_formatting(sentence)
                        # Bold keyword
                        highlighted_sentence = cleaned_sentence.replace(
                            keyword, f" ***{keyword}*** ")
                        _response += f"> {highlighted_sentence}\n"
                        if keyword == '727':
                            _response += 'WYSI\n'
                        if keyword == '69' or keyword == '420':
                            _response += '\nnice\n'
        if _response != "":
            await message.reply(_response, mention_author=False)
            await update_user(message.author.id, recent_message_type='funnies')

    if await is_subscribed(message.author.id, 'bedtime'):
        await bedtime_check(message.author.id, message.channel.id)

    if client.user in message.mentions and ('shut up' in message.content.lower() or 'su' in message.content.lower()):
        # console.print("[magenta] Was told to shut up.")
        logging.info("[magenta] Was told to shut up.")
        recent_message_type = await get_user_data(message.author.id, 'recent_message_type')
        # for false
        await update_subscriptions(message.author.id, recently_bothered=0)
        await message.reply(f"ok :,3\n*(I will no longer bother you with messages of type ``{recent_message_type}``)*")


@tasks.loop(minutes=5)
async def check_all_bedtimes():
    async with aiosqlite.connect(database) as conn:
        async with conn.execute("SELECT id FROM subscriptions WHERE bedtime = 1") as cursor:
            async for row in cursor:
                user_id, = row
                await bedtime_check(user_id)

        # COMMANDS

# Functions for commands


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.channel, discord.channel.DMChannel) or interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("You do not have the required permissions to use this command. (Administrator)", ephemeral=True)
        return False
    return app_commands.check(predicate)


def is_dev():
    async def predicate(interaction: discord.Interaction) -> bool:
        developer_ids = {582583719546847234, }  # edited from here
        if interaction.user.id in developer_ids:
            return True
        await interaction.response.send_message("You are not a developer.")
        return False
    return app_commands.check(predicate)


async def timezone_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=timezone, value=timezone)
        for timezone in zoneinfo.available_timezones() if current.lower() in timezone.lower()][:25]


# Commands (the actual commands)
@tree.command(
    name="gotosleep",
    description="Remind someone to go to bed when they are online after bedtime."
)
@app_commands.describe(user="The user to bother", time="Bedtime. Format: [HOUR]:[MINUTE] (24-hour, devided by a ':')", message="The message to send with each reminder", timezone="Timezone to account for (if target user has not yet set it themselves)")
@app_commands.autocomplete(timezone=timezone_autocomplete)
async def gotosleep(interaction: discord.Interaction, user: discord.User, time: str, timezone: str = None, message: str = None):
    # check if user exists in database and add them to users table otherwise
    if not await user_exists(user.id):
        await add_user(user.id, user.name)
        logging.debug(
            f"User {user.name} did not exist in database, attempted to add.")

    response = ""

    if timezone != None:
        if timezone not in zoneinfo.available_timezones():
            interaction.response.send_message(f"Invalid timezone: {timezone}")
            return

        elif await get_user_data(user.id, 'timezone') != None:
            response += f"User already has timezone {await get_user_data(user.id, 'timezone')} registered. Setting bedtime to {time} in that timezone.\n\n"
        else:
            # 1 for bool as registered in database
            await update_user(user.id, timezone=timezone, timezone_private=1)
            logging.debug("gotosleep: Attempted to update user timezone")

    if await get_user_data(user.id, 'timezone') not in zoneinfo.available_timezones():
        await interaction.response.send_message(f"User does not have a timezone registered (nor was one specified)")
        return

    if datetime.datetime.strptime(time, "%H:%M").time():
        pass
        logging.debug(f"gotosleep: Time {time} was considered valid.")
    else:
        await interaction.response.send_message(f"Time ``{time}`` isn't formatted correctly.")
        return

    await update_user(user.id, bedtime_time=time, bedtime_message=message, bedtime_applicant_username=interaction.user.name)
    # 1 for true as stored in database
    await update_subscriptions(user.id, bedtime=1)
    response += f"Set bedtime for user ***{await get_user_data(user.id, 'username')}***:\nBedtime: **{await get_user_data(user.id, 'bedtime_time')}**\nBedtime message: **{await get_user_data(user.id, 'bedtime_message')}**\nBedtime applicant (will be credited on sending the message): **{await get_user_data(user.id, 'bedtime_applicant_username')}**"
    # DEBUG
    response += f"\n> DEBUG:\n> Inputs:\ntime: {time}\nmessage: {message}
    \nbedtime_applicant_username: {interaction.user.name}\n\nUser: [{user.id}]"
    await interaction.response.send_message(response)


@tree.command(
    name="bedtimecheck",
    description="Dev command for manually checking if a user is up after bedtime"
)
@app_commands.describe(user="The user to bother")
@is_dev()
async def bedtimecheck(interaction: discord.Interaction, user: discord.User):
    if await user_exists(user.id):
        if await is_subscribed(user_id=user.id, subscription='bedtime'):
            logging.info(f"User {user.name} got bedtimed")
            await bedtime_check(user.id, interaction.channel_id)
            await interaction.response.send_message('User was subscribed to bedtime, attempted bedtime check.', ephemeral=True)
        else:
            await interaction.response.send_message('User not subscribed to bedtime', ephemeral=True)
    else:
        await interaction.response.send_message('User has no user data registered/does not exist.', ephemeral=True)


@tree.command(
    name="getrecentbother",
    description="Dev command for manually getting when a user was most recently bothered by the bot."
)
@app_commands.describe(user="Target user")
@is_dev()
async def getrecentbother(interaction: discord.Interaction, user: discord.User):
    if await user_exists(user.id):
        await interaction.response.send_message(str(await poked_within(user_id=user.id, return_difference=True)))


# Can optionally be substituted for running the bot manually
client.run(TOKEN, log_handler=discord_logger,
           log_level=logging.NOTSET, root_logger=False)
