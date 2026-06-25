from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import date, timedelta

from app.config.database import get_db
from app.models.inventory import Location, InventoryItem, StockBatch, InventoryUsageLog, StockTransfer
from app.schemas.inventory import LocationCreate, LocationResponse, InventoryItemCreate, InventoryItemResponse, StockBatchCreate, StockBatchResponse, UsageLogResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.core.limiter import limiter
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/inventory", tags=["Central Inventory"])

import uuid

@router.post("/items", response_model=InventoryItemResponse, dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def create_item(item_in: InventoryItemCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    item_data = item_in.model_dump()
    
    # Auto-generate item code if not provided
    if not item_data.get("item_code"):
        prefix = "DRG" if item_data.get("category") == "Drug" else "ITM"
        item_data["item_code"] = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
        
    new_item = InventoryItem(**item_data)
    db.add(new_item)
    db.flush()
    
    log_audit(db, current_user["user_id"], "CREATE", "InventoryItem", new_item.item_id, None, jsonable_encoder(item_data), request.client.host)
    db.commit()
    db.refresh(new_item)
    return new_item

@router.get("/items", response_model=List[InventoryItemResponse], dependencies=[Depends(RequirePermission("pharmacy:read"))])
@limiter.limit("60/minute")
def get_items(request: Request, db: Session = Depends(get_db)):
    """Retrieve all active inventory items."""
    return db.query(InventoryItem).filter(InventoryItem.is_active == True).all()


@router.get("/locations", response_model=List[LocationResponse], dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_locations(db: Session = Depends(get_db)):
    """List the inventory locations (Main Store / Pharmacy / Laboratory / Wards
    by default) so the UI can render them with the right `location_id` from the
    DB rather than guessing.
    """
    return db.query(Location).order_by(Location.location_id).all()


@router.post("/locations", response_model=LocationResponse, dependencies=[Depends(RequirePermission("inventory:manage"))])
def create_location(payload: LocationCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Add a storage location. Names are unique (case-insensitive) so the
    same store can't be created twice with different capitalisation."""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required.")
    if db.query(Location).filter(func.lower(Location.name) == name.lower()).first():
        raise HTTPException(status_code=409, detail=f"A location named '{name}' already exists.")
    loc = Location(name=name, description=(payload.description or None))
    db.add(loc)
    db.flush()
    log_audit(db, current_user["user_id"], "CREATE", "Location", loc.location_id, None, jsonable_encoder(payload), request.client.host)
    db.commit()
    db.refresh(loc)
    return loc


@router.patch("/locations/{location_id}", response_model=LocationResponse, dependencies=[Depends(RequirePermission("inventory:manage"))])
def update_location(location_id: int, payload: LocationCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    loc = db.query(Location).filter(Location.location_id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found.")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Location name is required.")
    clash = db.query(Location).filter(func.lower(Location.name) == name.lower(), Location.location_id != location_id).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"A location named '{name}' already exists.")
    before = {"name": loc.name, "description": loc.description}
    loc.name = name
    loc.description = payload.description or None
    log_audit(db, current_user["user_id"], "UPDATE", "Location", location_id, before, jsonable_encoder(payload), request.client.host)
    db.commit()
    db.refresh(loc)
    return loc


@router.delete("/locations/{location_id}", dependencies=[Depends(RequirePermission("inventory:manage"))])
def delete_location(location_id: int, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Delete an empty storage location. Refused if any stock batch (even
    zero-quantity history) references it — deactivating data integrity isn't
    worth a tidy list."""
    loc = db.query(Location).filter(Location.location_id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found.")
    if db.query(StockBatch).filter(StockBatch.location_id == location_id).first():
        raise HTTPException(status_code=400, detail="This location holds stock batches and cannot be deleted. Transfer or clear its stock first.")
    db.delete(loc)
    log_audit(db, current_user["user_id"], "DELETE", "Location", location_id, {"name": loc.name}, None, request.client.host)
    db.commit()
    return {"message": "Location deleted.", "location_id": location_id}


@router.get("/expired", dependencies=[Depends(RequirePermission("inventory:read"))])
def get_expired_stock(window_days: int = 0, db: Session = Depends(get_db)):
    """Stock batches that are expired (window_days=0) or expiring within
    `window_days`. Joined with item + location so the UI renders a single
    actionable list, soonest-expiry first. Only batches with stock on hand."""
    window_days = max(0, min(window_days, 365))
    cutoff = date.today() + timedelta(days=window_days)
    rows = (
        db.query(
            StockBatch.batch_id, StockBatch.batch_number, StockBatch.quantity,
            StockBatch.expiry_date, StockBatch.supplier_name,
            InventoryItem.name, InventoryItem.item_code, InventoryItem.category,
            InventoryItem.unit_cost,
            Location.name.label("location_name"),
        )
        .join(InventoryItem, StockBatch.item_id == InventoryItem.item_id)
        .join(Location, StockBatch.location_id == Location.location_id)
        .filter(StockBatch.quantity > 0, StockBatch.expiry_date <= cutoff)
        .order_by(StockBatch.expiry_date.asc())
        .all()
    )
    today = date.today()
    out = []
    for r in rows:
        days_left = (r.expiry_date - today).days if r.expiry_date else None
        out.append({
            "batch_id": r.batch_id,
            "batch_number": r.batch_number,
            "quantity": r.quantity,
            "expiry_date": r.expiry_date.isoformat() if r.expiry_date else None,
            "days_to_expiry": days_left,
            "is_expired": days_left is not None and days_left < 0,
            "supplier_name": r.supplier_name,
            "item_name": r.name,
            "item_code": r.item_code,
            "category": r.category,
            "unit_cost": float(r.unit_cost) if r.unit_cost is not None else None,
            "location_name": r.location_name,
            "value_at_cost": float(r.unit_cost) * r.quantity if r.unit_cost is not None else None,
        })
    return out

@router.get("/stock/{location_id}", dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_location_stock(location_id: int, db: Session = Depends(get_db)):
    """Retrieve stock batches for a specific location, joined with item details."""
    stock = db.query(
        StockBatch.batch_id,
        StockBatch.batch_number,
        StockBatch.quantity,
        StockBatch.expiry_date,
        InventoryItem.item_id,
        InventoryItem.name,
        InventoryItem.item_code,
        InventoryItem.category,
        InventoryItem.unit_price,
        InventoryItem.unit_cost
    ).join(InventoryItem, StockBatch.item_id == InventoryItem.item_id).filter(
        StockBatch.location_id == location_id,
        StockBatch.quantity > 0
    ).all()
    
    return [
        {
            "batch_id": s.batch_id,
            "batch_number": s.batch_number,
            "quantity": s.quantity,
            "expiry_date": s.expiry_date,
            "item_id": s.item_id,
            "name": s.name,
            "item_code": s.item_code,
            "category": s.category,
            "unit_price": s.unit_price,
            "unit_cost": s.unit_cost
        }
        for s in stock
    ]

@router.post("/batches", response_model=StockBatchResponse, dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def add_stock_batch(batch_in: StockBatchCreate, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    new_batch = StockBatch(**batch_in.model_dump())
    db.add(new_batch)
    db.flush()

    log_audit(db, current_user["user_id"], "CREATE", "StockBatch", new_batch.batch_id, None, jsonable_encoder(batch_in), request.client.host)
    db.commit()
    db.refresh(new_batch)
    return new_batch

@router.post("/transfer", dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def transfer_stock(from_loc_id: int, to_loc_id: int, batch_id: int, quantity: int, notes: str, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Transfers stock from one department (e.g., Main Store) to another (e.g., Pharmacy)."""
    # 1. Lock the source batch
    source_batch = db.query(StockBatch).with_for_update().filter(StockBatch.batch_id == batch_id, StockBatch.location_id == from_loc_id).first()
    if not source_batch:
        raise HTTPException(status_code=404, detail="Source batch not found at specified location.")
    if source_batch.quantity < quantity:
        raise HTTPException(status_code=400, detail="Insufficient quantity in source batch.")

    # 2. Deduct from source
    source_batch.quantity -= quantity

    # 3. Create or Update destination batch
    dest_batch = db.query(StockBatch).filter(
        StockBatch.item_id == source_batch.item_id,
        StockBatch.location_id == to_loc_id,
        StockBatch.batch_number == source_batch.batch_number
    ).first()

    if dest_batch:
        dest_batch.quantity += quantity
    else:
        dest_batch = StockBatch(
            item_id=source_batch.item_id, location_id=to_loc_id, 
            batch_number=source_batch.batch_number, quantity=quantity, 
            expiry_date=source_batch.expiry_date
        )
        db.add(dest_batch)
    
    db.flush()

    # 4. Create Audit Ledger Entry
    transfer_log = StockTransfer(
        item_id=source_batch.item_id, batch_id=source_batch.batch_id,
        from_location_id=from_loc_id, to_location_id=to_loc_id,
        quantity_transferred=quantity, transferred_by=current_user["user_id"], notes=notes
    )
    db.add(transfer_log)
    
    log_audit(db, current_user["user_id"], "TRANSFER", "StockBatch", source_batch.batch_id, None, {"qty": quantity, "to": to_loc_id}, request.client.host)
    db.commit()
    return {"status": "Transfer Successful"}

@router.get("/alerts", dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def get_inventory_alerts(db: Session = Depends(get_db)):
    """Returns items below reorder threshold and batches expiring within 90 days."""
    ninety_days_from_now = date.today() + timedelta(days=90)
    expiring_batches = db.query(StockBatch).filter(StockBatch.expiry_date <= ninety_days_from_now, StockBatch.quantity > 0).all()

    low_stock_items = []
    items = db.query(InventoryItem).filter(InventoryItem.is_active == True).all()
    # One grouped stock-sum query instead of a SUM per item (N+1). Items with
    # no batches simply won't appear in the map → treated as 0, same as before.
    stock_by_item = dict(
        db.query(StockBatch.item_id, func.sum(StockBatch.quantity))
          .group_by(StockBatch.item_id)
          .all()
    )
    for item in items:
        total_stock = stock_by_item.get(item.item_id) or 0
        if total_stock <= item.reorder_threshold:
            low_stock_items.append({"item_name": item.name, "current_stock": total_stock, "threshold": item.reorder_threshold})

    return {
        "expiring_batches": [{"batch_no": b.batch_number, "qty": b.quantity, "expires": b.expiry_date} for b in expiring_batches],
        "low_stock_alerts": low_stock_items
    }