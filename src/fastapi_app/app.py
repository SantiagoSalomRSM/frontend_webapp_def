import logging
import os
import pathlib
import markdown
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import Depends, FastAPI, Form, Request, status, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2

# Setup logger and Azure Monitor:
logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor()


# Setup FastAPI app:
app = FastAPI()
parent_path = pathlib.Path(__file__).parent.parent
app.mount("/mount", StaticFiles(directory=parent_path / "static"), name="static")
templates = Jinja2Templates(directory=parent_path / "templates")
templates.env.globals["prod"] = os.environ.get("RUNNING_IN_PRODUCTION", False)
# Use relative path for url_for, so that it works behind a proxy like Codespaces
templates.env.globals["url_for"] = app.url_path_for


def get_direct_db_connection():
    try:
        host = os.getenv("POSTGRES_HOST")
        dbname = os.getenv("POSTGRES_DB")
        user = os.getenv("POSTGRES_USER")
        password = os.getenv("POSTGRES_PASSWORD")
        port = int(os.getenv("POSTGRES_PORT", 5432))
    except Exception as e:
        logger.error(f"Missing environment variable: {e}")
        return None

    try:
        conn = psycopg2.connect(
            host=host,
            database=dbname,
            user=user,
            password=password,
            port=port,
            sslmode="require"
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

@app.get("/direct-details", response_class=HTMLResponse)
async def direct_details(request: Request, submission_id: int = Query(...)):
    conn = get_direct_db_connection()
    if not conn:
        logger.error("Failed to connect to the database.")
        return HTMLResponse(content="Database connection error", status_code=500)
    cur = conn.cursor()
    cur.execute("SELECT result_client description FROM form_ai_db WHERE id = %s", (submission_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        logger.warning(f"Submission ID {submission_id} not found in the database.")
        return HTMLResponse(content="submission_id not found", status_code=404)
    markdown_content = row[0]
    html_content = markdown.markdown(markdown_content)
    logger.info(f"Retrieved results for submission ID {submission_id}.")
    return templates.TemplateResponse("direct_details.html", {
        "request": request,
        "results_client": html_content
    })