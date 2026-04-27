# Strydom Travel Hub

A small Flask web app to plan weekends, long weekends, and extended trips with dates, accommodation, transport, activities, planner text, and notes.

## Run locally (terminal)

1. **Install Python 3** from [python.org](https://www.python.org/downloads/) if you do not have it. On Windows, tick **“Add python.exe to PATH”** during setup.

2. **Open a terminal** (PowerShell or Command Prompt) and go to this folder:

   ```text
   cd "c:\Cursor Files\Robot Arm\Trip Planner"
   ```

3. **Create a virtual environment** (recommended):

   ```text
   python -m venv .venv
   .venv\Scripts\activate
   ```

4. **Install dependencies**:

   ```text
   pip install -r requirements.txt
   ```

5. **Start the app**:

   ```text
   python app.py
   ```

6. **Open a browser** to [http://127.0.0.1:5000](http://127.0.0.1:5000).

Press `Ctrl+C` in the terminal to stop the server.

Plans are stored in the **session** (browser cookie) until you click **Clear saved plans** or close the browser session.
