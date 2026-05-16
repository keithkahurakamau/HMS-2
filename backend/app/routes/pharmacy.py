from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
import json

from app.config.database import get_db
# ADDED Location to the imports here
from app.models.inventory import InventoryItem, StockBatch, DispenseLog, Location
from app.models.billing import Invoice, InvoiceItem
from app.models.idempotency import IdempotencyKey
from app.schemas.pharmacy import DispenseRequest, DispenseResponse
from app.core.dependencies import get_current_user, RequirePermission
from app.services.accounting_posting import post_dispense_pair
from app.utils.audit import log_audit

router = APIRouter(prefix="/api/pharmacy", tags=["Pharmacy"])

@router.get("/inventory", dependencies=[Depends(RequirePermission("pharmacy:read"))])
def get_pharmacy_inventory(db: Session = Depends(get_db)):
    """Fetches all stock currently physically located in the Pharmacy."""
    # Find the Pharmacy location
    pharmacy_location = db.query(Location).filter(Location.name == "Pharmacy").first()
    if not pharmacy_location:
        return []

    # Join StockBatch with Master Inventory to get names, prices, and batches
    inventory = db.query(
        InventoryItem.item_id,
        InventoryItem.name,
        InventoryItem.category,
        InventoryItem.unit_price,
        StockBatch.batch_id,
        StockBatch.batch_number,
        StockBatch.quantity,
        StockBatch.expiry_date
    ).join(
        StockBatch, InventoryItem.item_id == StockBatch.item_id
    ).filter(
        StockBatch.location_id == pharmacy_location.location_id,
        StockBatch.quantity > 0
    ).order_by(StockBatch.expiry_date.asc()).all()

    return [dict(item._mapping) for item in inventory]

@router.post("/dispense", response_model=DispenseResponse, dependencies=[Depends(RequirePermission("pharmacy:manage"))])
def dispense_drug(req: DispenseRequest, request: Request, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    try:
        # 1. Idempotency Check (Prevent accidental double-clicks from charging twice)
        idem_key = db.query(IdempotencyKey).filter(IdempotencyKey.key == req.idempotency_key).first()
        if idem_key:
            return json.loads(idem_key.response_body) # Return the exact same response as the first time

        # 2. Inventory Check & Deduction (Using Specific StockBatch for FEFO)
        batch = db.query(StockBatch).with_for_update().filter(StockBatch.batch_id == req.batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Stock batch not found in Pharmacy.")
        if batch.quantity < req.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock. Only {batch.quantity} remaining in batch {batch.batch_number}.")
            
        # Fetch the master catalog item to get pricing
        item = db.query(InventoryItem).filter(InventoryItem.item_id == batch.item_id).first()
        
        # Deduct Physical Stock
        batch.quantity -= req.quantity
        total_cost = float(item.unit_price) * req.quantity

        # 3. Create Dispense Log
        log_entry = DispenseLog(
            item_id=item.item_id, batch_id=batch.batch_id, patient_id=req.patient_id, record_id=req.record_id,
            quantity_dispensed=req.quantity, total_cost=total_cost,
            dispensed_by=current_user["user_id"], notes=req.notes
        )
        db.add(log_entry)
        db.flush()

        # 4. Billing Integration (If patient is known, route to their bill)
        if req.patient_id:
            # Find an active pending invoice or create one
            invoice = db.query(Invoice).filter(Invoice.patient_id == req.patient_id, Invoice.status == "Pending").first()
            if not invoice:
                invoice = Invoice(patient_id=req.patient_id, total_amount=0, created_by=current_user["user_id"])
                db.add(invoice)
                db.flush()
            
            invoice.total_amount += total_cost
            
            # Add line item detailing the exact drug dispensed
            line_item = InvoiceItem(
                invoice_id=invoice.invoice_id,
                description=f"Pharmacy: {item.name} x{req.quantity}",
                amount=total_cost, item_type="Pharmacy", reference_id=log_entry.dispense_id
            )
            db.add(line_item)

        # 4b. Auto-post the dispensation to the ledger.
        # Revenue side uses unit_price (what we charged), COGS side uses
        # unit_cost (what we paid). Both post in the same transaction.
        cogs_amount = float(item.unit_cost or 0) * req.quantity
        post_dispense_pair(
            db,
            dispense_id=log_entry.dispense_id,
            revenue_amount=total_cost,
            cogs_amount=cogs_amount,
            memo=f"Pharmacy: {item.name} x{req.quantity}",
            user_id=current_user["user_id"],
        )

        # 5. Audit & Idempotency Save
        resp_data = {"dispense_id": log_entry.dispense_id, "item_id": item.item_id, "quantity_dispensed": req.quantity, "total_cost": total_cost, "dispensed_at": str(log_entry.dispensed_at)}
        
        db.add(IdempotencyKey(key=req.idempotency_key, response_body=json.dumps(resp_data)))
        log_audit(db, current_user["user_id"], "CREATE", "DispenseLog", log_entry.dispense_id, None, {"item": item.name, "qty": req.quantity}, request.client.host)
        
        db.commit()
        return log_entry

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))