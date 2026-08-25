# OYO Performance Hub

Run:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

Admin: `http://127.0.0.1:5000/admin/login`
Default login: `admin` / `admin123`

For production set `SECRET_KEY`, `ADMIN_USER`, `ADMIN_PASS`, and `PORT` environment variables.

The importer accepts XLSX/XLS/CSV and tries to map common column names for CZ ID, Name, TL, QA, AM, Shift, Status, SOB fields, and KPI fields.
