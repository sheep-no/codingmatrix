from fastapi import APIRouter, HTTPException, Depends, Query, Path, status, Response
from fastapi.encoders import jsonable_encoder
from typing import List, Optional
from sqlalchemy.orm import Session, sessionmaker  # Added sessionmaker import
from sqlalchemy import create_engine, Column, String
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"  # In real app, use environment variable for config
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define the base class for SQLAlchemy models
Base = declarative_base()

# Define Product SQLAlchemy model (based on typical CRUD needs)
class Product(Base):
    __tablename__ = "products"
    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    
    # For serialization with Pydantic
    class Config:
        orm_mode = True

# Define Pydantic model for input validation (for update operations)
class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

# Create APIRouter instance
router = APIRouter(prefix="/products", tags=["products"])

# Dependency to get database session
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to log errors (optional, can be extended)
def log_error(error: Exception):
    import logging
    logging.basicConfig(level=logging.INFO)
    logging.getLogger().error(f"Error occurred: {str(error)}")

# GET endpoint for listing products with pagination
@router.get("/")
async def get_products(
    page: int = Query(1, ge=1, description="Page number, defaults to 1"),
    per_page: int = Query(10, ge=1, le=100, description="Items per page, defaults to 10"),
    db: Session = Depends(get_db)
):
    try:
        skip = (page - 1) * per_page
        limit = per_page
        products = db.query(Product).offset(skip).limit(limit).all()
        total = db.query(Product).count()
        return {"total": total, "page": page, "per_page": per_page, "data": products}
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching products"
        )

# GET endpoint for retrieving a single product by ID
@router.get("/{product_id}")
async def get_product(
    product_id: str = Path(..., description="The ID of the product to retrieve"),
    db: Session = Depends(get_db)
):
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        return product
    except Exception as e:
        log_error(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the product"
        )

# PUT endpoint for updating a product
@router.put("/{product_id}")
async def update_product(
    product_id: str = Path(..., description="The ID of the product to update"),
    product_data: ProductUpdate = Depends(),  # Using Pydantic for validation
    db: Session = Depends(get_db)
):
    try:
        db_product = db.query(Product).filter(Product.id == product_id).first()
        if not db_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        update_data = product_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_product, key, value)
        
        db.commit()
        db.refresh(db_product)
        return {"message": "Product updated successfully", "data": db_product}
    except Exception as e:
        log_error(e)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An error occurred while updating the product"
        )

# DELETE endpoint for removing a product
@router.delete("/{product_id}")
async def delete_product(
    product_id: str = Path(..., description="The ID of the product to delete"),
    db: Session = Depends(get_db)
):
    try:
        db_product = db.query(Product).filter(Product.id == product_id).first()
        if not db_product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        db.delete(db_product)
        db.commit()
        return {"message": "Product deleted successfully"}
    except Exception as e:
        log_error(e)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while deleting the product"
        )

# Optional: Add a dependency for authentication if needed (not implemented here)
# You can use FastAPI's dependency injection to add auth middleware later.