import logging
import os
import azure.functions as func
import pymssql
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Securely load Database Connection Details from Environment Variables ---
# This is the standard, secure way for Azure Functions.
# It will use your local.settings.json locally, and Azure Application Settings when deployed.
DB_SERVER = os.environ.get('DB_SERVER')
DB_DATABASE = os.environ.get('DB_DATABASE')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# A check to ensure all environment variables are set
if not all([DB_SERVER, DB_DATABASE, DB_USER, DB_PASSWORD]):
    logging.critical("Database environment variables are not set. Exiting.")
    # In a real scenario, you'd want to handle this more gracefully
    # but for now, it highlights a configuration issue immediately.
    # The function will fail to start if this condition is met.

# Initialize FastAPI app
app = FastAPI()

# --- CORS Middleware ---
# This is critical to allow your SharePoint domain to call the API.
# Update with your specific SharePoint tenant URL.
origins = [
    "https://ganor.sharepoint.com",
    # Add any other origins if needed, e.g., for local testing of your SPFx part
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# --- Pydantic Model for incoming data validation ---
class Registration(BaseModel):
    email: str
    choice: int

# --- API Endpoints ---
@app.post("/register")
async def register_user(registration: Registration):
    """
    Receives registration data and executes the stored procedure using pymssql.
    """
    try:
        with pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE) as conn:
            with conn.cursor() as cursor:
                # IMPORTANT: Stored procedure name from your previous request
                sql_proc_name = 'sp_RegisterUser_EynatForm'
                cursor.callproc(sql_proc_name, (registration.email, registration.choice))
                conn.commit()
        return {"status": "success", "message": f"Registered for option {registration.choice}"}
    except pymssql.Error as db_err:
        logging.error(f"Database error during registration: {db_err}")
        raise HTTPException(status_code=500, detail="Database operation failed.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


@app.get("/registrations/{user_email}")
async def get_user_registrations(user_email: str):
    """
    Fetches all registration numbers for a given user email from EYNATFORM_ALL.
    """
    try:
        with pymssql.connect(server=DB_SERVER, user=DB_USER, password=DB_PASSWORD, database=DB_DATABASE, as_dict=True) as conn:
            with conn.cursor() as cursor:
                # Using the correct table name from your previous request
                sql_query = "SELECT RegNumber FROM EYNATFORM_ALL WHERE email = %s"
                cursor.execute(sql_query, (user_email,))
                rows = cursor.fetchall()
                # When as_dict=True, each row is a dictionary {'RegNumber': 1}
                registrations = [row['RegNumber'] for row in rows]
        return {"email": user_email, "registrations": registrations}
    except pymssql.Error as db_err:
        logging.error(f"Database error fetching registrations: {db_err}")
        raise HTTPException(status_code=500, detail="Could not retrieve registration data.")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail="An unexpected server error occurred.")


# --- Azure Function main entry point ---
async def main(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    """
    This is the adapter that allows our FastAPI app to run in Azure Functions.
    It passes the HTTP request from Azure Functions to the FastAPI application.
    """
    return await func.AsgiMiddleware(app).handle_async(req, context)