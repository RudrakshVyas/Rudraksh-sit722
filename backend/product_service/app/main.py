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
from .models import Product
from .schemas import ProductCreate, ProductResponse, ProductUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Product Service API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "product-service"}

@app.on_event("startup")
async def startup_event():
    if os.getenv("DISABLE_DB", "false").lower() == "true":
        logger.warning("Product Service: Skipping DB initialization (DISABLE_DB=true).")
        return
    for i in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Product Service: DB initialized successfully.")
            break
        except OperationalError as e:
            logger.warning(f"Product Service DB failed: {e}")
            time.sleep(5)

@app.get("/")
def root():
    return {"message": "Welcome to the Product Service!"}

@app.post("/products/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
def create_product(product: ProductCreate, db: Session = Depends(get_db)):
    db_product = Product(**product.model_dump())
    try:
        db.add(db_product)
        db.commit()
        db.refresh(db_product)
        return db_product
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Product already exists")
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create product")

@app.get("/products/", response_model=List[ProductResponse])
def list_products(db: Session = Depends(get_db), skip: int = 0, limit: int = 100):
    return db.query(Product).offset(skip).limit(limit).all()

@app.get("/products/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.put("/products/{product_id}", response_model=ProductResponse)
def update_product(product_id: int, product_data: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    update_data = product_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    try:
        db.commit()
        db.refresh(product)
        return product
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not update product")

@app.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.product_id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        db.delete(product)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not delete product")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
