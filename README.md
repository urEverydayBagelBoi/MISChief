# MISChief
A purist miscellaneous discord bot written in python using discord.py.


## Important note
This is ***NOT*** in any way intended to be a serious project, and is purely me learning and practicing how to code. Any ideas, feedback or even contributions are still appreciated, but this is a **personal project** with no promise or garuantee of support or active development from me if ever or until stated otherwise. The only thing I ask for is as much feedback as you feel like giving.

There currently isn't much of anything to this project, but this README will be updated as I flesh out both my skills and the project itself.

## Setup

1. Clone the repository:
    For example:
    ```sh
    git clone https://github.com/yourusername/your-repo.git
    cd your-repo
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
    python your_bot_file.py
    ```

## Dependencies

Dependencies are listed in the `requirements.txt` file.

**The bot also requires a `.env` file that simply contains:** `DISCORD_TOKEN="TOKEN_GOES_HERE"`. Simply create a text file, enter that with your token, and rename the file **entirely**, ***including*** **the extension**, to just `.env`