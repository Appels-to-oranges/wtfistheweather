# wtfistheweather

Standalone weather dashboard extracted from `PaysonCarpenter.com` for independent deployment.

## Run locally

1. Create a virtual environment and install dependencies:
   - `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add your API keys.
3. Start the app:
   - `python app.py`

The app runs on `http://localhost:5000/`.

## Deploy to Railway

- Create a new Railway project from this repo.
- Set environment variables:
  - `OPENWEATHER_API_KEY`
  - `OPENCAGE_API_KEY`
- Railway will use `Procfile` to launch gunicorn bound to `0.0.0.0:$PORT` with a single worker profile to avoid memory crashes.
