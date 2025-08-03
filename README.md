# MISChief
> Not another general-purpose bot.

A purist miscellaneous discord bot written in python using interactions.py.

## Important note
This bot is *not even done as of currently. Most things don't even work yet.*
This is ***NOT*** in any way intended to be a serious project, and is purely me learning and practicing how to code. Any ideas or feedback are appreciated, but this is a personal project with no promise or garuantee of support or active development.

There currently isn't much of anything to this project, but this README will be updated as I flesh out both my skills and the project itself.

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
    or
   ```sh
   python3 bot.py
   ```
   ^^^ On Linux

## Dependencies

Dependencies are listed in the `requirements.txt` file.

**The bot also requires a `.env` file that simply contains:** `DISCORD_TOKEN="token_goes_here"` and `USERDBPATH="path_goes_here"` on separate lines. Simply create a text file, enter that with your token and (full or relative) path to where you want your database file (will create one automatically if it doesn't exist), and rename the file **entirely**, ***including*** **the extension**, to just `.env`
