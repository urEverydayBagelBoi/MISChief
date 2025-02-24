# bot.py
# welcome to probably the worst code you've seen in your life (. ❛ ᴗ ❛.)
# please note i am a complete beginner so sorry if some things make zero sense

# TODO:
# '*' == Done
# * IMPORTANT: Store bedtime applicant as an account ID instead of a username; people can use the command and then change username without it being updated.
# * Also why even store username??? (can change at any point and no way to detect that other than regularly checking anyway)
# * check if message directed at MISChief before responding to 'hi'
# MAJOR REVELATION: database connections are objects that can probably be passed to functions.
# Instead of creating one in the function or copying code from it, a connection can be passed to the function
# and multiple functions can easily be executed in succession reusing that single connection
# im so smart ong
# * message create event doesn't use a 'try:' when it uses database functions
# * verify requested columns in all database functions that dynamically construct SQL queries (done i think?)
# update_subscriptions() isn't working properly for some reason...?

# Main Discord API's
import interactions # main module
from interactions import User, Member, Intents # fundamental
from interactions import Task, IntervalTrigger # Tasks
from interactions import slash_command, SlashContext, slash_option, OptionType, SlashCommandChoice, AutocompleteContext # Slash Commands
from interactions.api.events import MessageCreate # Events

# Utilities
import datetime
import zoneinfo # exposes zoneinfo.available_timezones() as thats not under 'ZoneInfo' (capital letters) for some reason
from zoneinfo import ZoneInfo
import random
import re
from fuzzywuzzy import process as fuzzywuzzy_process # Narrow selection for autocomplete/many choice
import logging
import rich
from rich.logging import RichHandler
logging.basicConfig(
    level="INFO", format="%(message)s", datefmt="[%X]", handlers=[RichHandler(rich_tracebacks=True)]
)
# discord api related logging goes here
discord_logger = logging.Logger(
    level=logging.WARN,
    name='interactions-py'
)

def remove_formatting(str):
    '''Removes markdown'''
    return re.sub(r"[*_`~]", "", str)

def timezone_to_utc(timezone:str):
    '''Takes a ZoneInfo timezone (NAME AS STRING) and converts it to a UTC offset, returning it as a pretty, user-facing string.'''
    if timezone is None or timezone not in zoneinfo.available_timezones():
        logging.warning(f'    timezone_to_utc(): got invalid timezone {timezone} as input. returning.')
        return
    logging.info(f'timezone_to_utc(): got {timezone} as input.')
    offset = datetime.datetime.now(tz=ZoneInfo(timezone)).utcoffset()
    logging.info(f'timezone_to_utc(): converted timezone {timezone} to UTC{offset}')
    if offset.total_seconds() < 0:
        return f"UTC{offset}"
    else:
        return f"UTC+{offset}"

def contains_word(s, w):
    '''Returns whether a word exists in a string, seperated by spaces.'''
    return f' {w} ' in f' {s} '

# Environment variables
from py_dotenv import read_dotenv
import os
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
read_dotenv(dotenv_path)
database = os.getenv('DBPATH')


#   \\\ SETUP DATABASES
# Databases and (persistent) data
import sqlite3
import aiosqlite

# These are synchronous (non-async) and are only used for global tasks
# like creating, setting up and verifying the database itself and when indiscriminately checking all users
syncConn = sqlite3.connect(database)
syncCursor = syncConn.cursor()

# All required columns for user-data tables.
# Used to create and verify columns
# the code for creating tables should also be updated
# alongside the code below
user_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',  # assumed to exist by creation, primary key
    'timezone': 'TEXT',
    'recently_bothered': 'INTEGER',  # datetime stored as unix timestamp
    'bedtime_message': 'TEXT',
    'bedtime_time': 'TEXT',  # stored as %H:%M 24-hour
    # id of person that used the bedtime command on them
    'bedtime_applicant': 'INTEGER UNIQUE'
}
subscription_columns = {
    'id': 'INTEGER NOT NULL UNIQUE',  # references 'id' in 'users' table, primary key
    'bedtime': 'INTEGER NOT NULL DEFAULT 0',  # bedtime reminders
    'funnies': 'INTEGER NOT NULL DEFAULT 1', # responses to funny numbers and other stupid unprompted stuff
    'shutup': 'INTEGER NOT NULL DEFAULT 0', # whether the user should *ever* be poked in any unnecessary way
}
subscription_defaults = {
    'bedtime': 0,
    'funnies': 1,
    'shutup': 0
}

def create_tables():
    # create tables if they don't exist
    syncCursor.execute("PRAGMA foreign_keys = True;")
    syncCursor.execute('''
        CREATE TABLE IF NOT EXISTS "users" (
    	    "id"	INTEGER NOT NULL UNIQUE,
    	    "timezone"	TEXT,
            "recently_bothered" INTEGER,
    	    "bedtime_message"	    TEXT,
    	    "bedtime_time"	        TEXT,
    	    "bedtime_applicant" INTEGER UNIQUE,
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

def verify_columns(table_name, columns):
    if not isinstance(columns, dict):
        raise ValueError(
            'verify_columns(): columns parameter must be a dictionary')

    syncCursor.execute(f'PRAGMA table_info({table_name})')
    existing_columns = syncCursor.fetchall()
    # logging.info(f"    [existing_columns]: {existing_columns}")
    existing_column_names = ['id'] + [column[1] for column in existing_columns]
    logging.info(f"Verifying table [{table_name}]")
    syncConn.execute('BEGIN;')
    try:
        for column_name, column_definition in columns.items():
            if column_name not in existing_column_names:
                syncConn.execute(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition};')
                logging.info(f"Added column '{column_name}' to {table_name}")
            else:
                logging.info(f"Column '{column_name}' already exists in {table_name}")
        syncConn.commit()
    except sqlite3.Error as e:
        syncConn.rollback()
        logging.error(f"           [DATABASE 'verify_columns' ERROR]: {e}")

async def add_user(conn, user_id):
    '''Adds a user to the database if they don't exist'''
    try:
        if await user_exists(conn, user_id):
            return
        await conn.execute('''INSERT INTO users (id) VALUES (?)''', (user_id,))
        await conn.execute('''INSERT INTO subscriptions (id) VALUES (?)''', (user_id,))
        await conn.commit()
    except aiosqlite.Error as e:
        await conn.rollback()
        logging.error(f"           [DATABASE USER ADD ERROR]: {e}")

async def delete_user(conn, user_id):
    if not await user_exists(conn, user_id):
        return
    try:
        await conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    except aiosqlite.Error as e:
        conn.rollback()

        # CONTACT USER (delete data manually)
        user = await client.fetch_user(user_id)
        logging.ERROR(f'    !!!!!!!!!!FAILED TO DELETE DATA FOR USER {user}!!!!!!!!!!!')
        try:
            await user.send('I somehow failed to delete your data, contact @ureverydaybagelboi so it may be deleted manually!!')
        except:
            logging.ERROR(f'    !!!!!!!!!FAILED TO NOTIFY USER OF FAILING TO DELETE DATA!!!!')
        await client.fetch_user(582583719546847234).send(f'Failed to delete data for user {user}!!! {client.get_user(582583719546847234).mention}')
        
            

async def user_exists(conn, user_id):
    try:
        async with conn.execute('SELECT COUNT(*) FROM users WHERE id = ?', (user_id,)) as cursor:
            data = (await cursor.fetchone())[0]
            return bool(data)
    except aiosqlite.Error as e:
        logging.error(f"           [USER EXISTS VERIFICATION ERROR]: {e}")

async def update_user(conn, user_id, **kwargs):
    '''Updates user data. Adds to database if they do not exist.'''
    if not kwargs:
        logging.error('update_user(): no kwargs were passed.')
        return

    # construct the set clause dynamically
    valid_columns = user_columns.keys()
    valid_kwargs = {key: value for key, value in kwargs.items() if key in valid_columns}
    set_clause = ', '.join(f"{key} = ?" for key in valid_kwargs.keys())
    values = list(valid_kwargs.values())
    values.append(user_id)
    sql = f"UPDATE users SET {set_clause} WHERE id = ?"

    try:
        if not await user_exists(conn, user_id):
            await add_user(conn, user_id)
            conn.commit()
            user = await client.fetch_user(user_id)
            logging.info(f"User {user.username} did not exist in database, attempted to add.")
        await conn.execute(sql, values)
        await conn.commit()

    except aiosqlite.Error as e:
        conn.rollback()
        logging.error(f"[DATABASE USER UPDATE ERROR]: {e} | SQL: {sql} | Values: {values}")

async def get_user_data(conn, user_id, *args):
    '''
    Returns user data as a single value or a tuple
    if multiple columns are requested. Doesn't
    account for defaults since there are none
    for user data right now.
    '''
    if not args:
        logging.error(f"get_user_data(): no args were passed.")
        return
    # construct clause dynamically
    valid_columns =  user_columns.keys()
    filtered_args = [arg for arg in args if arg in valid_columns]
    if not filtered_args:
        logging.error("get_user_data(): no valid columns were passed.")
        return None
    clause = ', '.join(filtered_args)
    sql = f"SELECT {clause} FROM users WHERE id = ?"
    try:
        if not await user_exists(conn, user_id):
            return None
        async with conn.execute(sql, (user_id,)) as cursor:
            output = await cursor.fetchone()
    except aiosqlite.Error as e:
        logging.error(f"           [DATABASE 'get_user_data' ERROR]: {e}")

    # return single value if only one column is requested
    if len(args) == 1:
        return output[0] if output else None
    # return as tuple if multiple columns requested
    return output if output else None

async def update_subscriptions(conn, user_id, **kwargs):
    if not kwargs:
        logging.error(f"update_subscriptions(): no kwargs were passed.")
        return
    # construct set clause dynamically
    valid_columns = set(subscription_columns.keys())
    valid_kwargs = {key: value for key, value in kwargs.items() if key in valid_columns}
    if not valid_kwargs:
        logging.error("update_subscriptions(): no valid kwargs were passed.")
        return
    set_clause = ', '.join(f"{key} = ?" for key in valid_kwargs.keys())
    values = list()
    for value in valid_kwargs.values():
        values.append(int(bool(value))) # convert bool to int
    values.append(user_id)
    sql = f"UPDATE subscriptions SET {set_clause} WHERE id = ?"

    try:
        if not await user_exists(conn, user_id):
            await add_user(conn, user_id)
            await conn.commit()
            user = await client.fetch_user(user_id)
            logging.info(f"User {user.username} did not exist in database, attempted to add.")
        await conn.execute(sql, values)
        await conn.commit()
    except aiosqlite.Error as e:
        conn.rollback()
        logging.error(f"[DATABASE SUBSCRIPTIONS UPDATE ERROR]: {e} | SQL: {sql} | Values: {values}")

async def is_subscribed(conn, user_id, *args):
    '''
    Returns whether user is subscribed to single subscription
    or a tuple of booleans for each requested subscription in order of *args.
    If no data is found, just assumes default values and returns those.
    '''
    defaults = subscription_defaults[args[0]] if len(args) == 1 else tuple(subscription_defaults[arg] for arg in args)
    if not args:
        logging.error(f"is_subscribed(): no args were passed")
        return defaults
    
    valid_columns = subscription_columns.keys()
    filtered_args = [arg for arg in args if arg in valid_columns]
    if not filtered_args:
        logging.error("is_subscribed(): no valid columns were passed.")
        return defaults
    # construct clause dynamically
    clause = ', '.join(filtered_args)
    sql = f"SELECT {clause} FROM subscriptions WHERE id = ?"

    try:
        async with conn.execute(sql, (user_id,)) as cursor:
            output = await cursor.fetchone()
    except aiosqlite.Error as e:
        logging.error(f"        [DATABASE 'is_subscribed' ERROR]: {e} | SQL: {sql}")
    
    if not output: # if user doesn't exist
        return defaults

    # return single value if only one column is requested
    if len(args) == 1:
        return output[0] if output else defaults
    #return as tuple if multiple columns requested
    return output if output else defaults

async def poked_within(conn, user_id, timedelta: datetime.timedelta = None, return_difference: bool = None):
    '''
    Returns whether a user was bothered within a 'datetime.timedelta' timeframe,
    or optionally how much time passed since last poke.
    Returned difference == None if no poke time is registered.
    '''
    if not await user_exists(conn, user_id):
        return

    try:
        async with conn.execute("SELECT recently_bothered FROM users WHERE id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None or row[0] is None:
                # No data found or was never poked
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
                    "'poked_within' must be given either a timedelta, True for return_difference or both."
                    )
    except aiosqlite.Error as e:
        logging.error(f"           ['poked_within' ERROR]: {e}")

async def reset_poke_time(conn, user_id):
    '''
    Sets the last time the user was poked to now
    '''
    
    # check if user exists in database and add them to users table otherwise.
    # this shouldn't ever run because a user shouldn't be bothered if not told to
    # (excluding funnies) and said user should be registered if so.
    if not await user_exists(user_id):
        await add_user(user_id)
        conn.commit()
        logging.WARNING(
            f"[bold red blink]User {client.fetch_user(user_id).username} did not exist in database when 'reset_poke_time' was called."
            "This means a user was bothered [underline]UNPROMPTED[/][/]",
            extra={"markup": True}
        )
    try:
        unixepoch = datetime.datetime.now().timestamp()
        await conn.execute("UPDATE users SET recently_bothered = ? WHERE id = ?", (unixepoch, user_id))
        await conn.commit()
    except aiosqlite.Error as e:
        conn.rollback()
        logging.error(f"           ['reset_poke_time' UPDATE ERROR]: {e}")

async def bedtime_check(conn, user_id: int, channel_id: int = None):
    '''
    Assumes that the user is subscribed to 'bedtime'
    Handles checking if their local time is past bedtime and sending messages to the user's DM and the specified 'channel_id', if any.
    Cooldown is not handled by this function.
    '''
    try:
        timezone_str, bedtime_str, message, applicant_id = await get_user_data(conn, user_id, 'timezone', 'bedtime_time', 'bedtime_message', 'bedtime_applicant')
        timezone = ZoneInfo(timezone_str)
        local_time = datetime.datetime.now().astimezone(timezone)
        logging.info(f"bedtime_check: Calculated time for user [{user_id}] in [{timezone_str}]: {local_time}")

        start = datetime.datetime.strptime(bedtime_str, "%H:%M").time()
        end = datetime.time(5, 30, tzinfo=timezone)

        if start < end:
            is_bedtime = start <= datetime.datetime.now().time() <= end
        else:
            now = datetime.datetime.now().time()
            is_bedtime = now >= start or now <= end

        if is_bedtime:
            logging.info(f"bedtime_check: Decided bedtime for user [{user_id}]. Start time: {start} - End time: {end} - Current time: {local_time}")
            if channel_id:
                channel = await fetch_channel(channel_id)
                applicant = await fetch_user(applicant_id)
                if message:
                    await channel.send(f"<@{user_id}>,\n> {message}\n*Bedtime message from {applicant.username}*")
                else:
                    await channel.send(
                        f"<@{user_id}>, it's after {bedtime_str} in your timezone! Go to bed!\n*Bedtime message from {applicant.global_name}*"
                    )
            else:
                user = client.fetch_user(user_id)
                if message:
                    await user.send(f"<@{user_id}>,\n> {message}\n*Bedtime message from {applicant.global_name}*")
                else:
                    await user.send(
                        f"<@{user_id}>, it's after {bedtime_str} in your timezone! go to bed!\n*Bedtime message from {applicant.global_name}*"
                    )
            await reset_poke_time(conn, user_id)

        else:
            logging.info(f"bedtime_check: Decided [underline]NOT[/] bedtime for user [{user_id}].", extra={"markup": True})
            pass
    except aiosqlite.Error as e:
        logging.error(f"            [bedtime_check() ERROR]: {e}")



#   \\\ DISCORD API
# define bot client
client = interactions.Client(logger=discord_logger, intents=Intents.GUILDS | Intents.GUILD_PRESENCES | Intents.MESSAGE_CONTENT | Intents.GUILD_MESSAGES | Intents.DIRECT_MESSAGES | Intents.GUILD_MESSAGE_REACTIONS | Intents.DIRECT_MESSAGE_REACTIONS | Intents.GUILD_MEMBERS)

@interactions.Task.create(interactions.TimeTrigger(minute=5))
async def check_all_bedtimes():
    conn = await aiosqlite.connect(database)
    try:
        cursor = await conn.execute("SELECT id FROM subscriptions WHERE bedtime = 1")
        for row in cursor:
            user_id, = row
            if await poked_within(conn, user_id, timedelta=datetime.timedelta(minutes=30)):
                return
            bedtime_check(conn, user_id)
    except sqlite3.Error as e:
        conn.rollback()
        logging.error(f"           ['check_all_bedtimes()' ERROR]: {e}")

# On bot start
@interactions.listen()
async def on_startup():
    verify_columns(table_name='users', columns=user_columns)
    verify_columns(table_name='subscriptions', columns=subscription_columns)
    logging.info(
        f"[bright_magenta]    || [Ready. Logged in as {client.user}] ||\n",
        extra={"markup": True}
    )
    logging.info(f"Database path: {database}")

@interactions.listen()
async def on_close():
    syncConn.close()
    syncCursor.close()

greeting_prompts = ('hello', 'hi', 'salutations', 'helo', 'hai',
                    'greetings', 'hey', 'heey', 'hallo', 'sup', 'hoi', 'howdy')
greeting_responses = ['hiii :3', 'sup!', 'helo!!!',
                      'haiii!!!!', 'hi', 'hello world!!!', 'mrrowdy!!', 'howdy :P',
                      "salutations my good sir/ma'am/whateveryouprefer, how may i help you?"]
shutup_prompts = ['shut up', 'stfu', 'su', 'shut the fuck up', 'stop']
shutup_responses = ['awww okay :<', 'okay :(', 'oh okay :3', 'okay fine', 'ughhh whatever :rolling_eyes:']
fish_prompts = ('you know what that means', 'fish')
fish_emoji = '🐟'
two_emoji = '2️⃣'
one_emoji = '1️⃣'
twentyone_prompts = ("whats 9 plus 10", "what's 9 plus 10", "whats 9 + 10", "what's 9 + 10",
                     "whats nine plus ten", "what's nine plus ten", "whats nine + ten", "what's nine + ten")
keywords = ['727', '69', '420', 'auto', 'car', 'audi', 'kip']
shutup_users = {} # if shut up is used they are remembered in this cache for 5 minutes and then deleted if they do not confirm or send a message not equal to 'confirm'

@interactions.listen(MessageCreate, delay_until_ready=True)
async def on_message_create(event):
    message = event.message
    conn = await aiosqlite.connect(database) # connection used for this message

    subscribed_funnies, subscribed_bedtime = await is_subscribed(conn, message.author.id, 'funnies', 'bedtime')

    # users that have been mentioned in message
    mentioned_users = []
    for id in message._mention_ids:
        mentioned_users.append(await message._client.cache.fetch_user(id))
    # if bot was mentioned in the message
    bot_mentioned = client.user in mentioned_users
    
    # Log messages (and return if message is from own client)
    # THIS IS TEMPORARY AND FOR DEBUG PURPOSES ONLY, AND SHOULD BE COMMENTED OUT/REMOVED FOR SECURITY/PRIVACY REASONS IN REAL USE
    if message.author == client.user:
        logging.info(
            f"\n[black on white]{message.author}[/] [bright_black][{(message.created_at.astimezone()).strftime('%H:%M')}][/]\n{message.content}\n",
            extra={"markup": True})
        return
    logging.info(
        f"[white on blue]{message.author}[/] [bright_black][{message.created_at.strftime('%H:%M')}][/]\n{message.content}\n",
        extra={"markup": True})

    command = False # Whether this message is a text prompt command
    # shut up if the bot is told to
    if message.content.lower() == 'confirm' and message.author.id in shutup_users:
        command = True
        shutup_users.pop(message.author.id, None)
        await message.reply(f"Got it, I won't bother you with any more nonsense.\n You can re-enable funny stuff by using /nvm.")
        try:
            await update_subscriptions(conn, message.author.id, funnies=False, bedtime=False, shutup=True)
        except aiosqlite.Error as e:
            await message.reply(f'Failed to register your request!! Please contact my dev so this may be resolved manually!! (@ureverydaybagelboi)\nERROR: `{e}`')
    elif message.author.id in shutup_users and not 'confirm' in message.content.lower():
        shutup_users.pop(message.author.id, None) # forget if user says something other than confirm
    
    # forget user after 5 minutes
    for id, time in shutup_users.items():
        if time > datetime.datetime.utcnow() - datetime.timedelta(minutes=5):
            shutup_users.pop(id, None)

    # check if message directed at MISCHief
    referenced_message = await event.message.fetch_referenced_message()
    if (
        (message.channel.type == interactions.ChannelType.DM) or bot_mentioned
        or referenced_message is not None and referenced_message.author == client.user
    ) and any(contains_word(message.content.lower(), prompt) for prompt in shutup_prompts):
        shutup_users[message.author.id] = datetime.datetime.utcnow()
        await message.reply(f"{random.choice(shutup_responses)}\n**Are you sure?**\n-# Type 'confirm' to confirm.")
        command = True

        # if the bot is DMed or mentioned, hint to slash commands (unless message is a text prompt command)
    if event.message.channel.type == interactions.ChannelType.DM and not command:
        if any(prompt in message.content.lower() for prompt in greeting_prompts):
            await message.channel.send(
                f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*"
                )
        else:
           await message.channel.send(f"> *pssst! i work with slash commands, type '/' to continue!*")
    if bot_mentioned and not command:
        if any(prompt in message.content.lower() for prompt in greeting_prompts):
            await message.reply(
                f"{random.choice(greeting_responses)}\n> *pssst! i work with slash commands, type '/' to continue!*"
            )
        else:
            await message.reply("> *pssst! i work with slash commands, type '/' to continue!*")

    # Bedtime
    if subscribed_bedtime:
        logging.info(f"Message author {message.author.username} was subscribed to bedtime")
        if not await poked_within(conn, message.author.id, timedelta=datetime.timedelta(minutes=15)):
            logging.info(f"Message author wasn't poked in the last 15 minutes. Running bedtime check.")
            await bedtime_check(conn, message.author.id, message.channel_id)
    else:
        logging.info(f"Message author {message.author.username} seemingly wasn't subscribed to bedtime.")

    # Funny Stuff :tm:
    if subscribed_funnies:
        logging.info('user was subscribed to funnies, initiating the funny')
    
        if any(contains_word(message.content.lower(), prompt) for prompt in fish_prompts):
            await message.add_reaction(fish_emoji)
            await message.reply("**fish!**", mention_author=True)
            logging.info(f"{message.author} got fished")
        if any(contains_word(message.content.lower(), prompt) for prompt in twentyone_prompts):
            await message.add_reaction(two_emoji)
            await message.add_reaction(one_emoji)
            logging.info(f"{message.author} asked what 9 + 10 is")
        
        # pointing at keywords
        response = ""
        for keyword in keywords:
            if keyword in message.content.lower():
                logging.info('FUNNY WORD DETECTED')
                if keyword in ('auto', 'car', 'audi') and not message.author.id == 1037620054721835029:
                    continue
                # split message into lowercase sentences
                sentences = re.split(r'(?<=[.!?]) +', message.content.lower())
                # find sentences with keyword
                for sentence in sentences:
                    if keyword in sentence:
                        # remove formatting
                        cleaned_sentence = remove_formatting(sentence)
                        # bold keyword
                        highlighted_sentence = cleaned_sentence.replace(keyword, f" ***{keyword}*** ")
                        
                        response += f"> {highlighted_sentence}\n"
                        if keyword == '727':
                            response += 'WYSI\n\n'
                            continue
                        if keyword == '69' or keyword == '420':
                            response += 'nice\n\n'
                            continue
                        if (keyword in ('auto', 'car', 'audi')):
                            response += 'met koelkast? :)\n\n'
                            continue
                        if keyword == 'kip':
                            response += 'het meest veelzijdige stukje vleest- taar- vis!- **kut.**\n\n'
                            continue
        if response != "":
            await message.reply(response, mention_author=False)
    else:
        logging.info('user was not subscribed to funnies :(')


#       //// SLASH-COMMANDS
@slash_command(
    name='gotosleep',
    description="'subtly' remind someone to go to bed when they are online after bedtime."
    )
@slash_option(
    name='user',
    description='the user to bother',
    required=True,
    opt_type=OptionType.USER
)
@slash_option(
    name='time',
    description="Bedtime. Format: '[HOUR]:[MINUTE]' (24-hour, divided by a ':')",
    required=True,
    opt_type=OptionType.STRING
)
@slash_option(
    name='message',
    description="Message to attach with each reminder",
    required=False,
    opt_type=OptionType.STRING
)
@slash_option(
    name='timezone',
    description="Timezone to account for (if none registered)",
    required=False,
    opt_type=OptionType.STRING,
    autocomplete=True
)
async def gotosleep_func(ctx: SlashContext, user: User | Member, time: str, message: str = None, timezone: str = None):
    conn = await aiosqlite.connect(database)
    response = ""
    try:
        if await is_subscribed(conn, user.id, 'shutup'):
            await ctx.send(f"{user.username} told me to shut so uhh... no can do. :3")
            return

        try:
            _ = datetime.datetime.strptime(time, '%H:%M')
            logging.info(f'gotosleep_func(): Time {time} was considered valid.')
        except ValueError:
            await ctx.send(f"Time `{time}` isn't formatted correctly.\n-# The format is a 24-hour time divided by a semicolon (':'), like this: `[HOUR]:[MINUTE]`")
            return

        # timetzone register logic
        try:
            registered_timezone = await get_user_data(conn, user.id, 'timezone')
            if timezone is not None: # if timezone specified
                if registered_timezone is None: # and no timezone registered: consider timezone input
                    if timezone not in zoneinfo.available_timezones(): # timezone not valid
                        await ctx.send(f"Invalid timezone: {timezone}")
                        return
                    await update_user(conn, user.id, timezone=timezone) # update timezone
                    logging.info(f"gotosleep: Attempted to update timezone to {timezone} for user {user}")
                else: # timezone already registered
                    if registered_timezone not in zoneinfo.available_timezones(): # existing timezone invalid
                        response += (f'\n'
                                     f'{user.username} had invalid timezone {registered_timezone} registered somehow...?\n'
                                     f'> uh-oh,,, that really shouldn\'t have happened.... please report this to my developer :,3\n\n')
                        logging.error(f"gotosleep_func(): user apparently had invalid timezone registered: {registered_timezone}")
                        if timezone in zoneinfo.available_timezones(): # provided timezone is valid
                            response += f"Attempting to set timezone to {timezone}\n"
                            await update_user(conn, user.id, timezone=timezone)
                        else:
                            response += (f"Specified timezone isn't valid either dumdum!!")
                            await ctx.send(response)
                    else:
                        response += (f"User already had timezone {registered_timezone} registered. Using that instead.")
            elif registered_timezone is None:
                await ctx.send(f"User does not have a timezone registered, nor was one specified.")
                return
        except aiosqlite.Error as e:
            conn.rollback()
            logging.error(f"gotosleep_func() failed to set timezone: {e}")

        public_timezone = timezone_to_utc(registered_timezone) if registered_timezone else "Unknown"
        try:
            await update_user(conn, user.id, bedtime_time=time, bedtime_message=message, bedtime_applicant=ctx.user.id)
            await update_subscriptions(conn, user.id, bedtime=True)
        except aiosqlite.Error as e:
            conn.rollback()
            logging.error(f"gotosleep_func() failed to set bedtime data and subscription: {e}")

        response += (
            f"Registered bedtime for user **{user.username}**:\n"
            f"Bedtime: **`{time}`**\n"
            f"Bedtime message: ***'{message}'***\n"
            f"Bedtime applicant (credited on each reminder sent): **{ctx.user.username}**"
        )
        await ctx.send(response)
        
    except aiosqlite.Error as e:
        conn.rollback()
        logging.error(f"           ['gotosleep_func()' ERROR]: {e}")

@gotosleep_func.autocomplete('timezone')
async def tz_autocomplete(ctx: AutocompleteContext):
    user_input = ctx.input_text  # can be empty/None
    if user_input is None or user_input == '':
        await ctx.send(list(zoneinfo.available_timezones())[0:8])
    else:
        narrowed = fuzzywuzzy_process.extract(user_input, zoneinfo.available_timezones(), limit=8)
        choices = []
        for item in narrowed:
            choices.append(item[0])
        await ctx.send(choices=choices)



create_tables()
client.start(token=(os.getenv('DISCORD_TOKEN')))