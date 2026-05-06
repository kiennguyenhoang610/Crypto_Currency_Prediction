# Crypto Currency Prediction

Flask application for cryptocurrency price forecasting with:

- PostgreSQL-backed runtime storage
- role-based login for `admin`, `scientist`, and `user`
- model registry and trained artifacts in `models/`
- admin and scientist dashboards connected to live backend data
- REST endpoints for health, assets, market data, and prediction

## Run With Docker

```bash
docker compose up --build -d
```

Services:

- Flask app: `http://localhost:5050`
- PostgreSQL: `localhost:15432`

To stop the stack:

```bash
docker compose down
```

To remove containers and volumes:

```bash
docker compose down -v
```

To inspect logs:

```bash
docker compose logs -f
```

## Optional Host Run

If you want to run Flask on the host machine while still using PostgreSQL from Docker:

```bash
pip install -r requirements.txt
python app.py
```

## PostgreSQL

Default connection string:

```text
postgresql://postgres:postgres@localhost:15432/crypto_predict
```

PowerShell example:

```powershell
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:15432/crypto_predict"
python app.py
```

The app auto-creates tables from `schema.sql` on startup and seeds:

- `admin` / `Admin@123`
- `scientist` / `Scientist@123`
- `investor` / `User@123`
- BTC and ETH asset rows
- price history from `BTC-USD.csv` and `ETH-USD.csv`

## Seed Accounts

- `admin` / `Admin@123`
- `scientist` / `Scientist@123`
- `investor` / `User@123`
