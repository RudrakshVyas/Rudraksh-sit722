import logging
import os
import sys
import time
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Customer
from .schemas import CustomerCreate, CustomerResponse, CustomerUpdate

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8000")
logger.info(f"Customer Service configured to talk to Product Service at {PRODUCT_SERVICE_URL}")

# --- FastAPI App ---
app = FastAPI(
    title="Customer Service API",
    description="Manages customers for mini-ecommerce app.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Health ---
@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "ok", "service": "customer-service"}

# --- Startup: Conditional DB init ---
@app.on_event("startup")
async def startup_event():
    if os.getenv("DISABLE_DB", "false").lower() == "true":
        logger.warning("Customer Service: Skipping DB initialization (DISABLE_DB=true).")
        return

    max_retries = 10
    for i in range(max_retries):
        try:
            logger.info(f"Customer Service: Attempting DB init (attempt {i+1}/{max_retries})")
            Base.metadata.create_all(bind=engine)
            logger.info("Customer Service: DB initialized successfully.")
            break
        except OperationalError as e:
            logger.warning(f"Customer Service: DB connection failed: {e}")
            time.sleep(5)
        except Exception as e:
            logger.critical(f"Unexpected DB startup error: {e}", exc_info=True)
            sys.exit(1)

# --- Root ---
@app.get("/", status_code=status.HTTP_200_OK)
async def read_root():
    return {"message": "Welcome to the Customer Service!"}

# --- CRUD Endpoints (unchanged) ---
@app.post("/customers/", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    db_customer = Customer(
        email=customer.email,
        password_hash=customer.password,
        first_name=customer.first_name,
        last_name=customer.last_name,
        phone_number=customer.phone_number,
        shipping_address=customer.shipping_address,
    )
    try:
        db.add(db_customer)
        db.commit()
        db.refresh(db_customer)
        return db_customer
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered.")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create customer.")

@app.get("/customers/", response_model=List[CustomerResponse])
def list_customers(db: Session = Depends(get_db), skip: int = 0, limit: int = 100, search: Optional[str] = None):
    query = db.query(Customer)
    if search:
        query = query.filter(
            (Customer.first_name.ilike(f"%{search}%")) |
            (Customer.last_name.ilike(f"%{search}%")) |
            (Customer.email.ilike(f"%{search}%"))
        )
    return query.offset(skip).limit(limit).all()

@app.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer

@app.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(customer_id: int, customer_data: CustomerUpdate, db: Session = Depends(get_db)):
    db_customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    update_data = customer_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_customer, key, value)
    try:
        db.commit()
        db.refresh(db_customer)
        return db_customer
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Updated email already exists")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not update customer")

@app.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.customer_id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    try:
        db.delete(customer)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete customer")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
