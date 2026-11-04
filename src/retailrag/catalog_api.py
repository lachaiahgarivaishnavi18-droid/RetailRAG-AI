"""Database-backed catalog, customer history, and simulated interaction routes."""

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from retailrag.data_schemas import Channel, InteractionInput, ProductInput, normalize_search_text
from retailrag.ingestion import database_summary
from retailrag.models import Customer, CustomerInteraction, Product, RecommendationItem

router = APIRouter()


def get_session(request: Request):
    with Session(request.app.state.engine) as session:
        yield session


class ProductOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    category: str
    brand: str
    price: Decimal
    currency: str
    rating: float
    stock_quantity: int
    available: bool
    features: list[str]
    attributes: dict[str, str]
    image_url: str | None
    source: str


class CustomerOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    preferred_categories: list[str]
    preferred_brands: list[str]
    budget_min: Decimal
    budget_max: Decimal
    source: str


class InteractionOutput(InteractionInput):
    model_config = ConfigDict(from_attributes=True)
    source: str


@router.get("/database/status", tags=["Database"])
def status(session: Session = Depends(get_session)):
    return database_summary(session)


@router.get("/products/search", tags=["Products"])
@router.get("/products", tags=["Products"])
def products(
    q: str = Query(default="", max_length=200),
    category: str | None = Query(default=None, max_length=100),
    brand: str | None = Query(default=None, max_length=100),
    min_price: Decimal | None = Query(default=None, ge=0, max_digits=12, decimal_places=2),
    max_price: Decimal | None = Query(default=None, ge=0, max_digits=12, decimal_places=2),
    available: bool | None = None,
    sort: Literal["name", "price_asc", "price_desc", "rating"] = "name",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "min_price must be no greater than max_price")
    statement = select(Product)
    # Escape LIKE metacharacters so customer input is treated as literal text.
    for token in normalize_search_text(q).split():
        statement = statement.where(Product.search_text.icontains(token.casefold(), autoescape=True))
    if category is not None:
        statement = statement.where(func.lower(Product.category) == category.lower())
    if brand is not None:
        statement = statement.where(func.lower(Product.brand) == brand.lower())
    if min_price is not None:
        statement = statement.where(Product.price >= min_price)
    if max_price is not None:
        statement = statement.where(Product.price <= max_price)
    if available is not None:
        statement = statement.where(Product.stock_quantity > 0 if available else Product.stock_quantity == 0)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    order = {"name": Product.name, "price_asc": Product.price, "price_desc": Product.price.desc(), "rating": Product.rating.desc()}[sort]
    rows = session.scalars(statement.order_by(order, Product.id).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [ProductOutput.model_validate(row) for row in rows]}


@router.get("/products/{product_id}", response_model=ProductOutput, tags=["Products"])
def product(product_id: str, session: Session = Depends(get_session)):
    row = session.get(Product, product_id)
    if row is None:
        raise HTTPException(404, "Product not found")
    return row


@router.get("/customers", tags=["Customers"])
def customers(
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    rows = session.scalars(select(Customer).order_by(Customer.id).offset(offset).limit(limit)).all()
    return {"total": session.scalar(select(func.count()).select_from(Customer)), "limit": limit, "offset": offset,
            "items": [CustomerOutput.model_validate(row) for row in rows]}


@router.get("/customers/{customer_id}", response_model=CustomerOutput, tags=["Customers"])
def customer(customer_id: str, session: Session = Depends(get_session)):
    row = session.get(Customer, customer_id)
    if row is None:
        raise HTTPException(404, "Customer not found")
    return row


@router.get("/customers/{customer_id}/history", tags=["Customers"])
def history(
    customer_id: str, channel: Channel | None = None,
    limit: int = Query(default=25, ge=1, le=100), offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    if session.get(Customer, customer_id) is None:
        raise HTTPException(404, "Customer not found")
    statement = select(CustomerInteraction).where(CustomerInteraction.customer_id == customer_id)
    if channel:
        statement = statement.where(CustomerInteraction.channel == channel)
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    rows = session.scalars(statement.order_by(CustomerInteraction.occurred_at.desc(), CustomerInteraction.id).offset(offset).limit(limit)).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [InteractionOutput.model_validate(row) for row in rows]}


@router.post("/interactions", response_model=InteractionOutput, status_code=201, tags=["Customers"])
def record_interaction(values: InteractionInput, session: Session = Depends(get_session)):
    if session.get(Customer, values.customer_id) is None or session.get(Product, values.product_id) is None:
        raise HTTPException(404, "Customer or product not found")
    row = CustomerInteraction(**values.model_dump(), source="synthetic_simulation")
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Interaction ID already exists or violates data integrity") from None
    session.refresh(row)
    return row


@router.post("/products", response_model=ProductOutput, status_code=201, tags=["Products"])
def create_product(values: ProductInput, session: Session = Depends(get_session)):
    if session.get(Product, values.id) is not None:
        raise HTTPException(409, "Product ID already exists")
    row = Product(**values.record(), source="user_catalog")
    session.add(row)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Product ID already exists or violates catalog integrity") from None
    session.refresh(row)
    return row


@router.put("/products/{product_id}", response_model=ProductOutput, tags=["Products"])
def update_product(product_id: str, values: ProductInput, session: Session = Depends(get_session)):
    if values.id != product_id:
        raise HTTPException(422, "Product IDs cannot be changed")
    row = session.get(Product, product_id)
    if row is None:
        raise HTTPException(404, "Product not found")
    for key, value in values.record().items():
        setattr(row, key, value)
    row.source = "user_catalog"
    session.commit()
    session.refresh(row)
    return row


@router.delete("/products/{product_id}", status_code=204, tags=["Products"])
def delete_product(product_id: str, session: Session = Depends(get_session)):
    from fastapi import Response
    row = session.get(Product, product_id)
    if row is None:
        raise HTTPException(404, "Product not found")
    history_count = session.scalar(select(func.count()).select_from(CustomerInteraction).where(CustomerInteraction.product_id == product_id))
    recommendation_count = session.scalar(select(func.count()).select_from(RecommendationItem).where(RecommendationItem.product_id == product_id))
    if history_count or recommendation_count:
        raise HTTPException(409, "Product has retained history; set stock_quantity to zero instead of deleting it")
    try:
        session.delete(row)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Product is referenced by retained history") from None
    return Response(status_code=204)
