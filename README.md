# MISChief
> Not another general-purpose bot.

A purist miscellaneous discord bot written in python using interactions.py.
> she/her (in the same sense a middle-aged man calls his truck 'she')

## Important note
This bot is *not even done as of currently. Most things don't even work yet.*
This is ***NOT*** in any way intended to be a serious project, and is purely me learning and practicing how to code. Any ideas or feedback are appreciated, but this is a personal project with no promise or garuantee of support or active development.

## Current features
- `/settimezone`: Register your timezone in the bot.
- `/gotosleep`: Send a message to a user if they're online past a certain time in their timezone, with an attached message.
- `/getusertime`: Get the current time of a user in their timezone.
- `/convertusertime`: Convert a time in own timezone to the equivalent time in someone else's
- Pointing at keywords (I.E. say 'nice' when a message contains 420 or similar)
- `/shutup`: Supress annoyances like pointing at keywords for you specifically
- Text command equivalent to `/shutup` that supresses the most recent poke type. (used by replying to a message from MISChief or mentioning her)
- `/nvm`: Undoes `/shutup`

## Planned features
- Being able to enable or disable features for servers.
- Many major optimizations I haven't thought of yet (I'm still learning good practices ok...)
- Whatever you can think of! Feel free to send ideas to @ureverydaybagelboi on Discord over DMs :)

## Setup

1. Clone the repository:
    For example:
    ```sh
    git clone https://github.com/urEverydayBagelBoi/MISChief.git
    cd MISChief
    ```
    There are more ways to do this though, like through GitHub's desktop app.

2. Create a virtual environment:
    ```sh
    python -m venv venv
    ```

3. Activate the virtual environment:

    - **On Windows**:
        ```sh
        venv\Scripts\activate
        ```
    - **On macOS and Linux**:
        ```sh
        source venv/bin/activate
        ```

4. Install the dependencies:
    ```sh
    pip install -r requirements.txt
    ```

5. Run the bot:
    ```sh
    python bot.py
    ```
    or (on most Linux distros)
   ```sh
   python3 bot.py
   ```

## Dependencies

Dependencies are listed in the `requirements.txt` file.

**The bot also requires a `.env` file that simply contains:** `DISCORD_TOKEN="token_goes_here"` and `USERDBPATH="path_goes_here"` on separate lines. Simply create a text file, enter that with your token and (full or relative) path to where you want your database file (will create one automatically if it doesn't exist), and rename the file **entirely**, ***including*** **the extension**, to just `.env`.
If you don't have a token already, you can create a new bot (and token) in the [Discord Developer Portal](https://discord.com/developers/applications).
