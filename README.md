# Group Travel Planner

A Flask-based travel dashboard website with:
- Trip planning form
- AI-style itinerary panel
- Recommended hotels panel
- Expense splitter
- Route map section
- AI travel assistant chat box

## 1. Prerequisites

- Python 3.10+ (recommended: Python 3.12 or 3.13)
- `pip` available in terminal

Check:

```powershell
python --version
pip --version
```

## 2. Project Structure

```text
Group/
  .vscode/
    extensions.json
    launch.json
    settings.json
    tasks.json
  app.py
  requirements.txt
  README.md
  templates/
    index.html
  static/
    style.css
    script.js
```

## 3. Setup (Windows PowerShell)

From project folder:

```powershell
cd "c:\Users\VIKAS PRAJAPATI\OneDrive\Desktop\Group"
```

Create virtual environment:

```powershell
python -m venv .venv
```

Activate virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## 4. Run the App

```powershell
python app.py
```

Open in browser:

```text
http://127.0.0.1:5000
```

You will first see the login page at `/login`.

## 5. Stop the App

Press `Ctrl + C` in terminal.

## 6. Deactivate Virtual Environment

```powershell
deactivate
```

## 7. Common Issues

- `flask not found`:
  - Virtual environment not activated, run:
  - `.\.venv\Scripts\Activate.ps1`

- PowerShell script execution blocked:
  - Run once in PowerShell:
  - `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

- Port already in use:
  - Change port in `app.py`:
  - `app.run(debug=True, port=5001)`

## 8. Optional Production Run (Waitress)

Install Waitress:

```powershell
pip install waitress
```

Run:

```powershell
waitress-serve --listen=127.0.0.1:8000 app:app
```

Open:

```text
http://127.0.0.1:8000
```

## 9. Full Setup in VS Code

1. Open VS Code.
2. Click `File` > `Open Folder...`.
3. Select:
   - `c:\Users\VIKAS PRAJAPATI\OneDrive\Desktop\Group`
4. Install recommended extensions when prompted:
   - Python
   - Pylance
5. Open terminal in VS Code:
   - `Terminal` > `New Terminal`
6. Run this once:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

7. Run with Task:
   - `Terminal` > `Run Task...` > `Run app`
8. Or run with Debug:
   - Open `Run and Debug` panel (`Ctrl+Shift+D`)
   - Select `Run Group Travel Planner`
   - Click `Start Debugging` (F5)
9. Open browser:
   - `http://127.0.0.1:5000`

## 10. Login and Feature Notes

- Login fields required: username/email and password
- Validation rules:
  - Username: 3-30 chars, letters/numbers/underscore
  - Email: valid email format
  - Password: 8+ chars with uppercase, lowercase, number, special char
- Forgot password section is available on login page
- Dashboard menu options are functional and jump to active sections
- Advanced chatbot supports itinerary, hotels, expenses, budget optimization, food, packing, safety, transport, summary, and general questions
- Route map shows starting point name, destination name, and distance value
- AI Generated Itinerary includes must-visit famous spots for the selected destination
- Chatbot also returns famous spots for destination-specific queries
- Chatbot now supports nearby famous spots, food, activity pricing, and destination hotel recommendations with exact names and prices
- Chatbot supports advanced visited-place mode (history/culture, revisit plan, shopping, local transport, activities, and hotels with exact prices)
- New hotel details page opens from "Select Hotel" with contact details, reviews, and nearby hotel price comparison

## 11. Optional: Broader Q&A with OpenAI

For broader general-question answering, set an API key before running:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

Optional model override:

```powershell
$env:OPENAI_MODEL="gpt-4.1-mini"
```

## 12. Live Nearby Hotels (Google Places)

Nearby hotel data and famous destination spots can be fetched from Google Places API (New) for itinerary and map sections.

Requirements:
- Enable `Places API (New)` in your Google Cloud project.
- Use the same `GOOGLE_MAPS_API_KEY` configured for this app.
