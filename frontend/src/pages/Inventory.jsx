import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import toast from 'react-hot-toast';
import { 
    Search, Package, AlertTriangle, ArrowRightLeft, 
    Plus, Truck, FileText, Filter, CalendarClock, Store, Microscope, Bed, Activity
} from 'lucide-react';

export default function Inventory() {
    // --- STATE ---
    const [locations, setLocations] = useState([
        { id: 1, name: 'Main Store', icon: Package },
        { id: 2, name: 'Pharmacy', icon: Store },
        { id: 3, name: 'Laboratory', icon: Microscope },
        { id: 4, name: 'Wards', icon: Bed }
    ]);
    const [activeLocation, setActiveLocation] = useState(locations[0]);
    
    const [inventory, setInventory] = useState([]);
    const [alerts, setAlerts] = useState({ low_stock: 0, expiring: 0 });
    const [isLoading, setIsLoading] = useState(true);
    
    const [searchQuery, setSearchQuery] = useState('');
    const [isTransferModalOpen, setIsTransferModalOpen] = useState(false);

    // Transfer Modal State
    const [transferForm, setTransferForm] = useState({
        to_loc_id: '',
        batch_id: '',
        quantity: '',
        notes: ''
    });
    const [isTransferring, setIsTransferring] = useState(false);

    // --- DATA FETCHING ---
    useEffect(() => {
        fetchInventoryData();
    }, [activeLocation]);

    const fetchInventoryData = async () => {
        setIsLoading(true);
        try {
            const response = await apiClient.get(`/inventory/items`); 
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

    // --- RENDER HELPERS ---
    const displayedInventory = inventory.filter(item => 
        item.name?.toLowerCase().includes(searchQuery.toLowerCase()) || 
        item.item_code?.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const totalInventoryValue = inventory.reduce((sum, item) => sum + ((item.quantity || 0) * (item.unit_cost || 0)), 0);

    return (
        <div className="space-y-6 pb-8">
            {/* PAGE HEADER */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Central Logistics Hub</h1>
                    <p className="text-sm text-slate-500 mt-1">Manage global procurement and departmental distribution.</p>
                </div>
                <div className="flex gap-3">
                    <button 
                        onClick={() => setIsTransferModalOpen(true)}
                        className="inline-flex items-center gap-2 bg-white border border-slate-300 text-slate-700 hover:bg-brand-50 hover:text-brand-700 hover:border-brand-300 px-4 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-sm"
                    >
                        <ArrowRightLeft size={18} /> Internal Transfer
                    </button>
                    <button className="inline-flex items-center gap-2 bg-brand-600 hover:bg-brand-700 text-white px-4 py-2.5 rounded-lg text-sm font-bold transition-colors shadow-sm">
                        <Truck size={18} /> External Procurement
                    </button>
                </div>
            </div>

            {/* DEPARTMENT TABS (HUB & SPOKE) */}
            <div className="bg-white border border-slate-200 rounded-xl p-1 shadow-sm flex overflow-x-auto custom-scrollbar">
                {locations.map((loc) => {
                    const Icon = loc.icon;
                    return (
                        <button 
                            key={loc.id}
                            onClick={() => setActiveLocation(loc)}
                            className={`flex items-center gap-2 py-3 px-6 rounded-lg text-sm font-bold whitespace-nowrap transition-all flex-1 justify-center ${
                                activeLocation.id === loc.id 
                                ? 'bg-slate-800 text-white shadow-md' 
                                : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50'
                            }`}
                        >
                            <Icon size={18} /> {loc.name}
                        </button>
                    );
                })}
            </div>

            {/* KPI DASHBOARD */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">{activeLocation.name} Valuation</p>
                        <p className="text-2xl font-black text-slate-900">KES {totalInventoryValue.toLocaleString()}</p>
                    </div>
                    <div className="w-12 h-12 bg-slate-100 text-slate-600 rounded-full flex items-center justify-center"><Package size={24} /></div>
                </div>
                <div className="bg-white p-5 rounded-xl border border-orange-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-orange-600 uppercase tracking-wider mb-1">Global Restock Alerts</p>
                        <p className="text-2xl font-black text-orange-700">{alerts.low_stock} Items</p>
                    </div>
                    <div className="w-12 h-12 bg-orange-100 text-orange-600 rounded-full flex items-center justify-center"><AlertTriangle size={24} /></div>
                </div>
                <div className="bg-white p-5 rounded-xl border border-red-200 shadow-sm flex items-center justify-between">
                    <div>
                        <p className="text-xs font-bold text-red-600 uppercase tracking-wider mb-1">Expiring &lt; 90 Days</p>
                        <p className="text-2xl font-black text-red-700">{alerts.expiring} Batches</p>
                    </div>
                    <div className="w-12 h-12 bg-red-100 text-red-600 rounded-full flex items-center justify-center"><CalendarClock size={24} /></div>
                </div>
            </div>

            {/* INVENTORY DATA TABLE */}
            <div className="bg-white rounded-xl shadow-soft border border-slate-100 overflow-hidden flex flex-col">
                <div className="p-4 border-b border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-4 bg-slate-50">
                    <div className="relative w-full max-w-md">
                        <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                        <input type="text" placeholder={`Search ${activeLocation.name} stock...`} value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm transition-all" />
                    </div>
                    <button className="flex items-center gap-2 px-4 py-2 border border-slate-200 text-slate-600 rounded-lg text-sm font-bold hover:bg-white bg-slate-50"><Filter size={16} /> Filters</button>
                </div>

                <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm text-slate-600">
                        <thead className="bg-white text-slate-500 text-xs uppercase font-bold border-b border-slate-200">
                            <tr>
                                <th className="px-6 py-4">Item Details</th>
                                <th className="px-6 py-4">Category</th>
                                <th className="px-6 py-4">Stock Quantity</th>
                                <th className="px-6 py-4 text-right">Unit Price</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {isLoading ? (
                                <tr><td colSpan="4" className="px-6 py-12 text-center text-slate-400"><Activity className="animate-spin mx-auto mb-2" /> Loading stock...</td></tr>
                            ) : displayedInventory.length === 0 ? (
                                <tr><td colSpan="4" className="px-6 py-12 text-center text-slate-400">No items found in {activeLocation.name}.</td></tr>
                            ) : (
                                displayedInventory.map((item) => (
                                    <tr key={item.item_id} className="hover:bg-slate-50 transition-colors">
                                        <td className="px-6 py-4">
                                            <div className="font-bold text-slate-900">{item.name}</div>
                                            <div className="text-xs text-slate-500 mt-0.5">Code: {item.item_code}</div>
                                        </td>
                                        <td className="px-6 py-4 font-medium text-slate-700">{item.category}</td>
                                        <td className="px-6 py-4 font-black text-slate-900 text-base">{item.quantity || item.stock_level || 0}</td>
                                        <td className="px-6 py-4 text-right font-bold text-slate-700">KES {item.unit_price}</td>
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
                    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm" onClick={() => setIsTransferModalOpen(false)}></div>
                    <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right">
                        <div className="p-6 border-b border-slate-100 bg-slate-800 text-white shrink-0">
                            <h2 className="text-xl font-bold flex items-center gap-2"><ArrowRightLeft size={24} className="text-brand-400" /> Internal Transfer</h2>
                            <p className="text-sm text-slate-300 mt-1">Move stock from {activeLocation.name} to another department.</p>
                        </div>

                        <div className="flex-1 overflow-y-auto p-6 space-y-6 bg-slate-50">
                            <form id="transferForm" onSubmit={handleTransfer} className="space-y-6">
                                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Destination Department</label>
                                        <select required value={transferForm.to_loc_id} onChange={(e) => setTransferForm({...transferForm, to_loc_id: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm font-semibold focus:ring-2 focus:ring-brand-500 outline-none">
                                            <option value="">Select Destination...</option>
                                            {locations.filter(l => l.id !== activeLocation.id).map(loc => (
                                                <option key={loc.id} value={loc.id}>{loc.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>

                                <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm space-y-4">
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Select Item Batch to Transfer</label>
                                        <select required value={transferForm.batch_id} onChange={(e) => setTransferForm({...transferForm, batch_id: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none">
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
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Transfer Quantity</label>
                                        <input required type="number" min="1" value={transferForm.quantity} onChange={(e) => setTransferForm({...transferForm, quantity: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="Enter quantity..." />
                                    </div>
                                    <div>
                                        <label className="block text-xs font-bold text-slate-700 mb-1.5">Authorization Notes</label>
                                        <input type="text" value={transferForm.notes} onChange={(e) => setTransferForm({...transferForm, notes: e.target.value})} className="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none" placeholder="Requisition # or reason..." />
                                    </div>
                                </div>
                            </form>
                        </div>

                        <div className="p-6 border-t border-slate-200 bg-white flex gap-3 shrink-0">
                            <button type="button" onClick={() => setIsTransferModalOpen(false)} className="px-6 py-2.5 border border-slate-300 text-slate-700 rounded-lg font-bold hover:bg-slate-50 w-1/3 transition-colors">Cancel</button>
                            <button type="submit" form="transferForm" disabled={isTransferring} className="flex-1 bg-slate-800 hover:bg-slate-900 disabled:opacity-50 text-white py-2.5 rounded-lg font-bold shadow-sm flex items-center justify-center gap-2 transition-colors">
                                {isTransferring ? 'Processing...' : 'Execute Transfer'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}