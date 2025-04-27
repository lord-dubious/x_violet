# x_violet

x_violet is a Twitter bot powered by LLM (Gemini) and customizable persona.

## Installation

```bash
# Linux/macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Run the bot via main.py
python main.py
```

The agent reads configuration from `.env`, initializes the scheduler, and begins action and post loops respecting intervals.

## Configuration

Copy `.env.example` to `.env` and set your Twitter and LLM credentials and intervals.

## Testing

```bash
pytest -q
```
