import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import {
    Search, Package, AlertTriangle, ArrowRightLeft,
    Plus, Truck, FileText, Filter, CalendarClock, Store, Microscope, Bed, Activity
} from 'lucide-react';
import PageHeader from '../components/PageHeader';

// Each tenant defines its own location set in the DB. The API gives us
// {location_id, name, description}; we map the well-known names to icons here
// and fall back to a generic Package icon for anything else.
const LOCATION_ICON = {
    'Main Store': Package,
    Pharmacy: Store,
    Laboratory: Microscope,
    Wards: Bed,
};

const decorateLocation = (loc) => ({
    id: loc.location_id,
    name: loc.name,
    icon: LOCATION_ICON[loc.name] || Package,
});

export default function Inventory() {
    // --- STATE ---
    const [locations, setLocations] = useState([]);
    const [activeLocation, setActiveLocation] = useState(null);
    
    const [inventory, setInventory] = useState([]);
    const [catalogItems, setCatalogItems] = useState([]);
    const [alerts, setAlerts] = useState({ low_stock: 0, expiring: 0 });
    const [isLoading, setIsLoading] = useState(true);
    
    const [searchQuery, setSearchQuery] = useState('');
    const [categoryFilter, setCategoryFilter] = useState('All');
    const [isTransferModalOpen, setIsTransferModalOpen] = useState(false);
    const [isProcurementModalOpen, setIsProcurementModalOpen] = useState(false);

    // Transfer Modal State
    const [transferForm, setTransferForm] = useState({
        to_loc_id: '',
        batch_id: '',
        quantity: '',
        notes: ''
    });
    const [isTransferring, setIsTransferring] = useState(false);

    // Procurement Modal State
    const [procurementForm, setProcurementForm] = useState({
        isNewItem: false,
        item_id: '',
        new_item_code: '',
        new_item_name: '',
        new_item_category: 'Consumable',
        new_item_unit_cost: '',
        new_item_unit_price: '',
        batch_number: '',
        quantity: '',
        expiry_date: '',
        supplier_name: ''
    });
    const [isProcuring, setIsProcuring] = useState(false);

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchCatalogData();
        fetchLocations();
    }, []);

    useEffect(() => {
        if (activeLocation) fetchInventoryData();
    }, [activeLocation]);

    const fetchLocations = async () => {
        try {
            const response = await apiClient.get('/inventory/locations');
            const decorated = (response.data || []).map(decorateLocation);
            setLocations(decorated);
            // Pick the first location as the active one — usually Main Store.
            setActiveLocation((prev) => prev || decorated[0] || null);
        } catch (error) {
            console.error('Failed to fetch locations', error);
            toast.error('Could not load inventory locations.');
        }
    };

    const fetchCatalogData = async () => {
        try {
            const response = await apiClient.get(`/inventory/items`);
            setCatalogItems(response.data || []);
        } catch (error) {
            console.error("Failed to fetch catalog", error);
        }
    };

    const fetchInventoryData = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get(`/inventory/stock/${activeLocation.id}`); 
            setInventory(response.data || []);
            
            const alertRes = await apiClient.get('/inventory/alerts');
            setAlerts({
                low_stock: alertRes.data.low_stock_alerts.length,
                expiring: alertRes.data.expiring_batches.length
            });
        } catch (error) {
            console.error("Failed to fetch inventory", error);
        } finally {
            setIsLoading(false);
        }
    };

    // --- ACTION HANDLERS ---
    const handleTransfer = async (e) => {
        e.preventDefault();
        setIsTransferring(true);
        try {
            await apiClient.post(`/inventory/transfer?from_loc_id=${activeLocation.id}&to_loc_id=${transferForm.to_loc_id}&batch_id=${transferForm.batch_id}&quantity=${transferForm.quantity}&notes=${transferForm.notes}`);
            
            toast.success("Stock transferred successfully!");
            setIsTransferModalOpen(false);
            setTransferForm({ to_loc_id: '', batch_id: '', quantity: '', notes: '' });
            fetchInventoryData(); 
        } catch (error) {
            toast.error(error.response?.data?.detail || "Transfer failed. Check stock levels.");
        } finally {
            setIsTransferring(false);
        }
    };

    const handleProcurement = async (e) => {
        e.preventDefault();
        setIsProcuring(true);
        try {
            let finalItemId = parseInt(procurementForm.item_id);

            // Create new item if toggled
            if (procurementForm.isNewItem) {
                const itemRes = await apiClient.post('/inventory/items', {
                    name: procurementForm.new_item_name,
                    category: procurementForm.new_item_category,
                    unit_cost: parseFloat(procurementForm.new_item_unit_cost) || 0,
                    unit_price: parseFloat(procurementForm.new_item_unit_price) || 0,
                    reorder_threshold: 10,
                    is_active: true
                });
                finalItemId = itemRes.data.item_id;
            }

            await apiClient.post(`/inventory/batches`, {
                item_id: finalItemId,
                location_id: activeLocation.id,
                batch_number: procurementForm.batch_number,
                quantity: parseInt(procurementForm.quantity),
                expiry_date: procurementForm.expiry_date,
                supplier_name: procurementForm.supplier_name || null
            });
            
            toast.success(`Stock successfully received into ${activeLocation.name}!`);
            setIsProcurementModalOpen(false);
            setProcurementForm({ 
                isNewItem: false, item_id: '', new_item_code: '', new_item_name: '', new_item_category: 'Consumable',
                new_item_unit_cost: '', new_item_unit_price: '', batch_number: '', quantity: '', expiry_date: '', supplier_name: '' 
            });
            fetchCatalogData();
            fetchInventoryData();
        } catch (error) {
            toast.error(error.response?.data?.detail || "Procurement failed.");
        } finally {
            setIsProcuring(false);
        }
    };

    // --- RENDER HELPERS ---
    const availableCategories = Array.from(
        new Set(inventory.flatMap(i => i.category ? [i.category] : []))
    ).sort();

    const displayedInventory = inventory.filter(item => {
        const matchesSearch =
            item.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
            item.item_code?.toLowerCase().includes(searchQuery.toLowerCase());
        const matchesCategory = categoryFilter === 'All' || item.category === categoryFilter;
        return matchesSearch && matchesCategory;
    });

    const totalInventoryValue = inventory.reduce((sum, item) => sum + ((item.quantity || 0) * (item.unit_cost || 0)), 0);

    // Locations come from the API now, so render a brief shim while the list
    // is in flight. Without this guard, every `activeLocation.id` access below
    // would crash the page on first paint.
    if (!activeLocation) {
        return (
            <div className="flex items-center justify-center py-16 text-ink-400">
                <Activity className="animate-spin mr-2" /> Loading inventory locations…
            </div>
        );
    }

    return (
        <div className="space-y-6 pb-8">
            <PageHeader
                eyebrow="Logistics"
                icon={Package}
                title="Central Logistics Hub"
                subtitle="Manage global procurement and departmental distribution."
                actions={
                    <>
                        <button type="button" data-tour="inv-transfer" onClick={() => setIsTransferModalOpen(true)} className="btn-secondary cursor-pointer">
                            <ArrowRightLeft size={15} /> Internal transfer
                        </button>
                        <button type="button" data-tour="inv-procurement" onClick={() => setIsProcurementModalOpen(true)} className="btn-primary cursor-pointer">
                            <Truck size={15} /> External procurement
                        </button>
                    </>
                }
            />

            {/* DEPARTMENT TABS (HUB & SPOKE) */}
            <div data-tour="inv-locations" className="card p-1.5 flex overflow-x-auto custom-scrollbar gap-1">
                {locations.map((loc) => {
                    const Icon = loc.icon;
                    const isActive = activeLocation.id === loc.id;
                    return (
                        <button type="button" key={loc.id} onClick={() => setActiveLocation(loc)}
                            className={`flex items-center gap-2 py-2.5 px-5 rounded-lg text-sm font-medium whitespace-nowrap transition-all flex-1 justify-center ${
                                isActive ? 'bg-ink-900 dark:bg-ink-700 text-white shadow-soft' : 'text-ink-600 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white hover:bg-ink-50 dark:hover:bg-ink-800/50'
                            }`}>
                            <Icon size={16} className={isActive ? 'text-brand-300' : 'text-ink-400'} /> {loc.name}
                        </button>
                    );
                })}
            </div>

            {/* KPI DASHBOARD */}
            <div data-tour="inv-kpis" className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="stat-tile">
                    <div className="flex justify-between items-start"><div className="stat-icon bg-ink-100 ring-ink-200 text-ink-700 dark:bg-ink-800/40 dark:ring-ink-800 dark:text-ink-200"><Package size={20} /></div></div>
                    <div>
                        <h3 className="stat-label">{activeLocation.name} valuation</h3>
                        <p className="stat-value mt-1">KES {totalInventoryValue.toLocaleString()}</p>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="flex justify-between items-start"><div className="stat-icon bg-amber-50 ring-amber-100 text-amber-600 dark:bg-amber-500/10 dark:ring-amber-500/20 dark:text-amber-300"><AlertTriangle size={20} /></div></div>
                    <div>
                        <h3 className="stat-label">Global restock alerts</h3>
                        <p className="stat-value mt-1 text-amber-700 dark:text-amber-300">{alerts.low_stock} Items</p>
                    </div>
                </div>
                <div className="stat-tile">
                    <div className="flex justify-between items-start"><div className="stat-icon bg-rose-50 ring-rose-100 text-rose-600 dark:bg-rose-500/10 dark:ring-rose-500/20 dark:text-rose-300"><CalendarClock size={20} /></div></div>
                    <div>
                        <h3 className="stat-label">Expiring &lt; 90 days</h3>
                        <p className="stat-value mt-1 text-rose-700 dark:text-rose-300">{alerts.expiring} Batches</p>
                    </div>
                </div>
            </div>

            {/* INVENTORY DATA TABLE */}
            <div data-tour="inv-table" className="card overflow-hidden flex flex-col">
                <div data-tour="inv-search" className="p-4 border-b border-ink-100 dark:border-ink-800 flex flex-col sm:flex-row items-center justify-between gap-3 bg-ink-50/40 dark:bg-ink-800/40">
                    <div className="relative w-full max-w-md">
                        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" />
                        <input type="text" aria-label="Search stock" placeholder={`Search ${activeLocation.name} stock…`} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="input pl-10" />
                    </div>
                    <div className="flex items-center gap-2">
                        <Filter size={14} className="text-ink-400" aria-hidden="true" />
                        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label="Filter by category" className="input">
                            <option value="All">All categories</option>
                            {availableCategories.map(cat => (
                                <option key={cat} value={cat}>{cat}</option>
                            ))}
                        </select>
                        {categoryFilter !== 'All' && (
                            <button type="button" onClick={() => setCategoryFilter('All')} className="text-xs font-semibold text-ink-500 dark:text-ink-400 hover:text-ink-900 dark:hover:text-white">Clear</button>
                        )}
                    </div>
                </div>

                <div className="overflow-x-auto">
                    <table className="table-clean min-w-[600px]">
                        <thead>
                            <tr>
                                <th>Item details</th>
                                <th>Category</th>
                                <th>Stock quantity</th>
                                <th className="text-right">Unit price</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isLoading ? (
                                <tr><td colSpan="4" className="px-6 py-12 text-center text-ink-400"><Activity className="animate-spin mx-auto mb-2" size={20} /> Loading stock…</td></tr>
                            ) : displayedInventory.length === 0 ? (
                                <tr><td colSpan="4" className="px-6 py-12 text-center text-ink-400">No items found in {activeLocation.name}.</td></tr>
                            ) : (
                                displayedInventory.map((item) => (
                                    <tr key={item.item_id}>
                                        <td>
                                            <div className="font-semibold text-ink-900 dark:text-white">{item.name}</div>
                                            <div className="text-xs font-mono text-ink-500 dark:text-ink-400 mt-0.5">{item.item_code}</div>
                                        </td>
                                        <td><span className="badge-neutral">{item.category}</span></td>
                                        <td className="font-semibold text-ink-900 dark:text-white text-base">{item.quantity || item.stock_level || 0}</td>
                                        <td className="text-right font-semibold text-ink-700 dark:text-ink-200">KES {item.unit_price}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* INTERNAL STOCK TRANSFER MODAL */}
            {isTransferModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsTransferModalOpen(false)} />
                    <div className="relative w-full max-w-md bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="p-6 border-b border-ink-100 dark:border-ink-800 bg-gradient-to-br from-ink-800 to-ink-900 text-white shrink-0">
                            <h2 className="text-xl font-bold flex items-center gap-2"><ArrowRightLeft size={24} className="text-brand-400" /> Internal Transfer</h2>
                            <p className="text-sm text-slate-300 mt-1">Move stock from {activeLocation.name} to another department.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-5 space-y-5 bg-ink-50/40 dark:bg-ink-800/40 custom-scrollbar">
                            <form id="transferForm" onSubmit={handleTransfer} className="space-y-5">
                                <div className="card p-5 space-y-4">
                                    <div>
                                        <label htmlFor="invent-destination-department" className="label">Destination Department</label>
                                        <select id="invent-destination-department" required value={transferForm.to_loc_id} onChange={(e) => setTransferForm({...transferForm, to_loc_id: e.target.value})} className="input">
                                            <option value="">Select Destination...</option>
                                            {locations.flatMap(loc => loc.id !== activeLocation.id ? [
                                                <option key={loc.id} value={loc.id}>{loc.name}</option>
                                            ] : [])}
                                        </select>
                                    </div>
                                </div>

                                <div className="card p-5 space-y-4">
                                    <div>
                                        <label htmlFor="invent-select-item-batch-to-transfer" className="label">Select Item Batch to Transfer</label>
                                        <select id="invent-select-item-batch-to-transfer" required value={transferForm.batch_id} onChange={(e) => setTransferForm({...transferForm, batch_id: e.target.value})} className="input">
                                            <option value="">Select Item from {activeLocation.name}...</option>
                                            
                                            {/* DYNAMIC INVENTORY MAPPING */}
                                            {inventory.map(item => (
                                                <option key={item.batch_id} value={item.batch_id}>
                                                    {item.name} (Batch: {item.batch_number}) - {item.quantity || item.stock_level} available
                                                </option>
                                            ))}

                                        </select>
                                    </div>
                                    <div>
                                        <label htmlFor="invent-transfer-quantity" className="label">Transfer Quantity</label>
                                        <input id="invent-transfer-quantity" required type="number" min="1" value={transferForm.quantity} onChange={(e) => setTransferForm({...transferForm, quantity: e.target.value})} className="input" placeholder="Enter quantity..." />
                                    </div>
                                    <div>
                                        <label htmlFor="invent-authorization-notes" className="label">Authorization Notes</label>
                                        <input id="invent-authorization-notes" type="text" value={transferForm.notes} onChange={(e) => setTransferForm({...transferForm, notes: e.target.value})} className="input" placeholder="Requisition # or reason..." />
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsTransferModalOpen(false)} className="btn-secondary">Cancel</button>
                            <button type="submit" form="transferForm" disabled={isTransferring} className="btn flex-1 bg-ink-800 text-white hover:bg-ink-900 dark:bg-ink-700 dark:hover:bg-ink-600 shadow-soft">
                                {isTransferring ? 'Processing...' : 'Execute Transfer'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* EXTERNAL PROCUREMENT MODAL */}
            {isProcurementModalOpen && (
                <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
                    <button type="button" aria-label="Close" className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsProcurementModalOpen(false)} />
                    <div className="relative w-full max-w-md bg-white dark:bg-ink-900 h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="p-6 border-b border-ink-100 dark:border-ink-800 bg-gradient-to-br from-brand-600 to-brand-700 text-white shrink-0">
                            <span className="text-2xs font-semibold uppercase tracking-[0.16em] text-brand-200">Receive stock</span>
                            <h2 className="text-lg font-semibold mt-1 flex items-center gap-2"><Truck size={20} className="text-brand-200" /> External procurement</h2>
                            <p className="text-sm text-brand-100/90 mt-1">Receive new stock batches from suppliers into {activeLocation.name}.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50 dark:bg-ink-800/40">
                            <form id="procurementForm" onSubmit={handleProcurement} className="space-y-6">
                                <div className="card p-5 space-y-4">
                                    <div className="flex items-center justify-between pb-3 border-b border-ink-100 dark:border-ink-800">
                                        <h3 className="text-sm font-semibold text-ink-800 dark:text-ink-200">Item details</h3>
                                        <label className="flex items-center gap-2 text-xs font-semibold text-brand-700 dark:text-brand-400 cursor-pointer">
                                            <input type="checkbox" checked={procurementForm.isNewItem} onChange={e => setProcurementForm({...procurementForm, isNewItem: e.target.checked})} className="rounded border-ink-300 dark:border-ink-700 text-brand-600 focus:ring-brand-500" />
                                            Add as new catalog item
                                        </label>
                                    </div>

                                    {!procurementForm.isNewItem ? (
                                        <div>
                                            <label htmlFor="invent-catalog-item" className="label">Catalog Item</label>
                                            <select id="invent-catalog-item" required value={procurementForm.item_id} onChange={(e) => setProcurementForm({...procurementForm, item_id: e.target.value})} className="input">
                                                <option value="">Select Item from Catalog...</option>
                                                {catalogItems.map(item => (
                                                    <option key={item.item_id} value={item.item_id}>
                                                        {item.name} ({item.category})
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    ) : (
                                        <div className="grid grid-cols-2 gap-4 bg-brand-50/50 dark:bg-brand-500/10 p-4 rounded-lg border border-brand-100 dark:border-brand-500/20">
                                            <div className="col-span-2">
                                                <label htmlFor="invent-item-name" className="label">Item Name</label>
                                                <input id="invent-item-name" required type="text" value={procurementForm.new_item_name} onChange={e => setProcurementForm({...procurementForm, new_item_name: e.target.value})} className="input" placeholder="e.g. Paracetamol 500mg" />
                                            </div>
                                            <div>
                                                <label htmlFor="invent-category" className="label">Category</label>
                                                <select id="invent-category" required value={procurementForm.new_item_category} onChange={e => setProcurementForm({...procurementForm, new_item_category: e.target.value})} className="input">
                                                    <option>Drug</option>
                                                    <option>Consumable</option>
                                                    <option>Reagent</option>
                                                    <option>Equipment</option>
                                                </select>
                                            </div>
                                            <div>
                                                <label htmlFor="invent-unit-cost-kes" className="label">Unit Cost (KES)</label>
                                                <input id="invent-unit-cost-kes" required type="number" min="0" value={procurementForm.new_item_unit_cost} onChange={e => setProcurementForm({...procurementForm, new_item_unit_cost: e.target.value})} className="input" placeholder="e.g. 30" />
                                            </div>
                                            <div>
                                                <label htmlFor="invent-unit-selling-price-kes" className="label">Unit Selling Price (KES)</label>
                                                <input id="invent-unit-selling-price-kes" required type="number" min="0" value={procurementForm.new_item_unit_price} onChange={e => setProcurementForm({...procurementForm, new_item_unit_price: e.target.value})} className="input" placeholder="e.g. 50" />
                                            </div>
                                        </div>
                                    )}

                                    <div className="grid grid-cols-2 gap-4 pt-2">
                                        <div>
                                            <label htmlFor="invent-supplier-name" className="label">Supplier Name</label>
                                            <input id="invent-supplier-name" required type="text" value={procurementForm.supplier_name} onChange={(e) => setProcurementForm({...procurementForm, supplier_name: e.target.value})} className="input" placeholder="e.g. MedKEM Logistics" />
                                        </div>
                                        <div>
                                            <label htmlFor="invent-supplier-batch-number" className="label">Supplier Batch Number</label>
                                            <input id="invent-supplier-batch-number" required type="text" value={procurementForm.batch_number} onChange={(e) => setProcurementForm({...procurementForm, batch_number: e.target.value})} className="input" placeholder="e.g. BATCH-2024-X1" />
                                        </div>
                                        <div>
                                            <label htmlFor="invent-quantity-received" className="label">Quantity Received</label>
                                            <input id="invent-quantity-received" required type="number" min="1" value={procurementForm.quantity} onChange={(e) => setProcurementForm({...procurementForm, quantity: e.target.value})} className="input" placeholder="Qty" />
                                        </div>
                                        <div>
                                            <label htmlFor="invent-expiry-date" className="label">Expiry Date</label>
                                            <input id="invent-expiry-date" required type="date" value={procurementForm.expiry_date} onChange={(e) => setProcurementForm({...procurementForm, expiry_date: e.target.value})} className="input" />
                                        </div>
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-5 border-t border-ink-100 dark:border-ink-800 bg-white dark:bg-ink-900 flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsProcurementModalOpen(false)} className="btn-secondary">Cancel</button>
                            <button type="submit" form="procurementForm" disabled={isProcuring} className="btn-primary flex-1">
                                {isProcuring ? 'Processing…' : 'Confirm delivery'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}