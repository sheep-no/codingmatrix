# src/app/routers/products.py
from typing import List, Optional, Annotated, Depends
from fastapi import APIRouter, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from ..core import get_db
from ..models import Product
from ..schemas import ProductCreate, ProductUpdate, ProductRead, ProductReadWithPagination

router = APIRouter(prefix="/products", tags=["products"])

# 分页参数
Page = Annotated[int, Query(title="Page number", ge=1, default=1)]
PerPage = Annotated[int, Query(title="Items per page", ge=1, le=100, default=10)]

@router.get("/", response_model=ProductReadWithPagination)
def get_products(
    page: Page,
    per_page: PerPage,
    db: Session = Depends(get_db)
):
    """List products with pagination"""
    skip = (page - 1) * per_page
    total = db.query(Product).count()
    
    products = db.query(Product).offset(skip).limit(per_page).all()
    
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "data": products
    }

@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: Annotated[str, Path(title="Product ID", example="prod_1234567890")],
    db: Session = Depends(get_db)
):
    """Get product details"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    return product

@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: Annotated[str, Path(title="Product ID", example="prod_1234567890")],
    product: ProductUpdate,
    db: Session = Depends(get_db)
):
    """Update product"""
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if not db_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    # Update fields
    if product.name:
        db_product.name = product.name
    if product.description:
        db_product.description = product.description
    if product.price:
        db_product.price = product.price
    if product.category:
        db_product.category = product.category
    
    db.commit()
    db.refresh(db_product)
    return db_product

@router.delete("/{product_id}", response_model=None)
def delete_product(
    product_id: Annotated[str, Path(title="Product ID", example="prod_1234567890")],
    db: Session = Depends(get_db)
):
    """Delete product"""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )
    
    db.delete(product)
    db.commit()
    return None