from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Date, Numeric, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.config.database import Base

class Location(Base):
    __tablename__ = "locations"
    # Examples: "Main Store", "Pharmacy", "Laboratory", "Wards"
    location_id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

class InventoryItem(Base):
    """The Master Catalog for all physical goods in the hospital."""
    __tablename__ = "inventory_items"
    
    item_id = Column(Integer, primary_key=True)
    item_code = Column(String(100), unique=True, index=True, nullable=False)
    name = Column(String(255), index=True, nullable=False) # Brand name or item name
    category = Column(String(100), index=True, nullable=False) # Drug/Consumable/Reagent/Equipment
    
    # Pharmacy-specific fields (Nullable for non-drug items like Syringes)
    generic_name = Column(String(255), index=True, nullable=True)
    dosage_form = Column(String(50), nullable=True) # tablet/syrup/vial
    strength = Column(String(50), nullable=True)
    requires_prescription = Column(Boolean, default=False)
    
    # Financials & Thresholds
    unit_cost = Column(Numeric(10, 2), nullable=False) # Procurement cost (Valuation)
    unit_price = Column(Numeric(10, 2), nullable=False) # Selling/Dispensing price
    reorder_threshold = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)

    # Reusable items (microscope slides, beakers, glassware) are logged on use
    # but never decrement the stock count — they go back into circulation after
    # cleaning. Setting this to True makes the lab UI skip the quantity prompt
    # and the inventory usage logger skip the deduction step.
    is_reusable = Column(Boolean, default=False, nullable=False)

class StockBatch(Base):
    """Tracks physical quantities at specific locations with Expiry Dates (FEFO)."""
    __tablename__ = "stock_batches"
    
    batch_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id"), index=True, nullable=False)
    location_id = Column(Integer, ForeignKey("locations.location_id"), index=True, nullable=False)
    
    batch_number = Column(String(100), index=True, nullable=False)
    quantity = Column(Integer, nullable=False)
    expiry_date = Column(Date, index=True, nullable=False) # Crucial for First-Expire-First-Out sorting
    supplier_name = Column(String(255), nullable=True)
    
    added_at = Column(DateTime(timezone=True), server_default=func.now())

class StockTransfer(Base):
    """Audit ledger for moving items between the Hub (Main Store) and Spokes (Pharmacy/Labs)."""
    __tablename__ = "stock_transfers"
    
    transfer_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id"), index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("stock_batches.batch_id"), nullable=False)
    
    from_location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=False)
    to_location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=False)
    
    quantity_transferred = Column(Integer, nullable=False)
    transferred_by = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    transfer_date = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(String, nullable=True)

class DispenseLog(Base):
    """Logs items leaving the hospital ecosystem entirely (Prescriptions or OTC Sales)."""
    __tablename__ = "dispense_logs"
    
    dispense_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id"), index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("stock_batches.batch_id"), nullable=False) # Tracks exact batch sold
    
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), index=True, nullable=True) # Null for OTC walk-ins
    record_id = Column(Integer, ForeignKey("medical_records.record_id"), index=True, nullable=True) # Link to clinical encounter
    
    quantity_dispensed = Column(Integer, nullable=False)
    total_cost = Column(Numeric(10, 2), nullable=False)
    
    dispensed_by = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)
    dispensed_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    notes = Column(String, nullable=True)

class InventoryUsageLog(Base):
    """Logs items consumed internally (e.g., Lab reagents, Ward consumables)."""
    __tablename__ = "inventory_usage_logs"
    
    log_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("inventory_items.item_id"), index=True, nullable=False)
    batch_id = Column(Integer, ForeignKey("stock_batches.batch_id"), nullable=False)
    location_id = Column(Integer, ForeignKey("locations.location_id"), nullable=False)
    
    quantity_used = Column(Integer, nullable=False)
    used_by_user_id = Column(Integer, ForeignKey("users.user_id"), index=True, nullable=False)

    reference_type = Column(String(50), nullable=False) # e.g., 'LabTest', 'WardProcedure'
    reference_id = Column(Integer, nullable=False)
    # When True, this usage record is informational only: the corresponding
    # StockBatch.quantity was NOT decremented because the item is reusable.
    is_reusable_use = Column(Boolean, default=False, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

