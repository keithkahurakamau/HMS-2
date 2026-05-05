import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { 
    Receipt, Search, Filter, CreditCard, Banknote, Smartphone, CheckCircle2,
    Activity, ArrowRight, FileText, X
} from 'lucide-react';
import toast from 'react-hot-toast';

export default function Billing() {
    const [queue, setQueue] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    
    const [activeInvoice, setActiveInvoice] = useState(null);
    const [paymentMethod, setPaymentMethod] = useState('Cash');
    const [mpesaPhone, setMpesaPhone] = useState('');
    const [isProcessing, setIsProcessing] = useState(false);
    const [mpesaStatus, setMpesaStatus] = useState(null); // 'waiting', 'success', 'failed'

    const fetchQueue = async () => {
        setIsLoading(true);
        try {
            const res = await apiClient.get('/billing/queue');
            setQueue(res.data || []);
        } catch (error) {
            toast.error("Failed to fetch billing queue");
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchQueue();
    }, []);

    const filteredQueue = queue.filter(inv => 
        inv.patient_name.toLowerCase().includes(searchQuery.toLowerCase()) || 
        inv.patient_opd.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const pollMpesaStatus = async (checkoutRequestId) => {
        let attempts = 0;
        const interval = setInterval(async () => {
            attempts++;
            if (attempts > 20) { // 60 seconds timeout
                clearInterval(interval);
                setMpesaStatus(null);
                setIsProcessing(false);
                toast.error("M-Pesa request timed out. Patient did not enter PIN.");
                return;
            }
            try {
                const res = await apiClient.get(`/payments/mpesa/status/${checkoutRequestId}`);
                if (res.data.status === 'Success') {
                    clearInterval(interval);
                    setMpesaStatus('success');
                    toast.success("M-Pesa payment received successfully!");
                    setIsProcessing(false);
                    setMpesaStatus(null);
                    setActiveInvoice(null);
                    fetchQueue();
                } else if (res.data.status === 'Failed') {
                    clearInterval(interval);
                    setMpesaStatus('failed');
                    toast.error(`M-Pesa payment failed: ${res.data.result_desc || 'Cancelled by user'}`);
                    setIsProcessing(false);
                    setMpesaStatus(null);
                }
                // If status is still Pending, continue polling
            } catch (error) {
                // Ignore errors during polling and keep trying
            }
        }, 3000);
    };

    const handleProcessPayment = async (e) => {
        e.preventDefault();
        setIsProcessing(true);
        
        try {
            const idempotencyKey = crypto.randomUUID();
            const amountDue = activeInvoice.total_amount - activeInvoice.amount_paid;

            if (paymentMethod === 'M-Pesa') {
                if (!mpesaPhone) {
                    setIsProcessing(false);
                    return toast.error("Phone number required for M-Pesa");
                }
                const res = await apiClient.post('/payments/mpesa/stk-push', {
                    phone_number: mpesaPhone,
                    amount: amountDue,
                    invoice_id: activeInvoice.invoice_id,
                    callback_url: 'https://placeholder.ngrok.app/callback' // Overridden by backend dynamically
                });
                
                toast.success("STK Push sent to patient's phone. Waiting for PIN...");
                setMpesaStatus('waiting');
                
                if (res.data.CheckoutRequestID) {
                    pollMpesaStatus(res.data.CheckoutRequestID);
                } else {
                    toast.error("Invalid response from Safaricom.");
                    setIsProcessing(false);
                    setMpesaStatus(null);
                }
            } else {
                await apiClient.post('/billing/process-payment', {
                    idempotency_key: idempotencyKey,
                    invoice_id: activeInvoice.invoice_id,
                    amount: amountDue,
                    payment_method: paymentMethod
                });
                toast.success(`Payment of KES ${amountDue.toFixed(2)} processed via ${paymentMethod}.`);
                setActiveInvoice(null);
                fetchQueue();
                setIsProcessing(false);
            }
        } catch (error) {
            toast.error(error.response?.data?.detail || "Payment processing failed");
            setIsProcessing(false);
            setMpesaStatus(null);
        }
    };

    return (
        <div className="space-y-6 pb-8">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Billing & Finance</h1>
                    <p className="text-sm text-slate-500 mt-1">Manage patient invoices, consultation fees, and accept payments.</p>
                </div>
                <div className="flex gap-3">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                        <input 
                            type="text" placeholder="Search invoices..." 
                            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                            className="pl-9 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none w-64 shadow-sm"
                        />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-start">
                {/* Billing Queue List */}
                <div className="md:col-span-1 space-y-4">
                    <h3 className="font-bold text-slate-800 uppercase tracking-wider text-xs flex items-center justify-between">
                        Pending Invoices <span className="bg-brand-100 text-brand-700 py-0.5 px-2 rounded-full">{queue.length}</span>
                    </h3>
                    
                    {isLoading ? (
                        <div className="text-center py-12 text-slate-400"><Activity className="animate-spin mx-auto mb-2" /></div>
                    ) : filteredQueue.length === 0 ? (
                        <div className="bg-white border border-slate-200 rounded-xl p-8 text-center shadow-sm">
                            <Receipt className="mx-auto text-slate-300 mb-3" size={32} />
                            <p className="text-slate-500 text-sm font-medium">No pending invoices.</p>
                        </div>
                    ) : (
                        <div className="space-y-3 max-h-[70vh] overflow-y-auto custom-scrollbar pr-2">
                            {filteredQueue.map(inv => (
                                <div 
                                    key={inv.invoice_id}
                                    onClick={() => setActiveInvoice(inv)}
                                    className={`bg-white border p-4 rounded-xl cursor-pointer transition-all ${activeInvoice?.invoice_id === inv.invoice_id ? 'border-brand-500 ring-2 ring-brand-500/20 shadow-md' : 'border-slate-200 hover:border-brand-300 shadow-sm'}`}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                                            inv.status === 'Pending M-Pesa' ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'
                                        }`}>{inv.status}</span>
                                        <span className="text-xs font-bold text-slate-400">INV-{inv.invoice_id}</span>
                                    </div>
                                    <h4 className="font-bold text-slate-900 text-sm mb-1">{inv.patient_name}</h4>
                                    <p className="text-xs text-slate-500 mb-3">{inv.patient_opd}</p>
                                    <div className="flex justify-between items-center border-t border-slate-100 pt-3">
                                        <span className="text-xs text-slate-500">Balance Due</span>
                                        <span className="font-black text-brand-600">KES {(inv.total_amount - inv.amount_paid).toFixed(2)}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Main Cashier Workspace */}
                <div className="md:col-span-3">
                    {activeInvoice ? (
                        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col min-h-[60vh] md:h-[calc(100vh-140px)]">
                            <div className="p-6 bg-slate-900 text-white shrink-0 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                                <div>
                                    <h2 className="text-2xl font-black mb-1">{activeInvoice.patient_name}</h2>
                                    <p className="text-slate-400 font-medium">{activeInvoice.patient_opd} • Invoice #{activeInvoice.invoice_id}</p>
                                </div>
                                <div className="text-right">
                                    <p className="text-slate-400 text-xs font-bold uppercase mb-1">Total Balance Due</p>
                                    <p className="text-3xl font-black text-green-400">KES {(activeInvoice.total_amount - activeInvoice.amount_paid).toFixed(2)}</p>
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-6 space-y-8 bg-slate-50/50">
                                {/* Bill Breakdown */}
                                <div>
                                    <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 border-b border-slate-200 pb-2">Itemized Breakdown</h3>
                                    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden overflow-x-auto shadow-sm">
                                        <table className="w-full text-left text-sm text-slate-600 min-w-[500px]">
                                            <thead className="bg-slate-50 border-b border-slate-200 text-xs uppercase font-bold text-slate-500">
                                                <tr>
                                                    <th className="px-4 py-3">Description</th>
                                                    <th className="px-4 py-3">Category</th>
                                                    <th className="px-4 py-3 text-right">Amount (KES)</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-slate-100">
                                                {activeInvoice.items.map(item => (
                                                    <tr key={item.id}>
                                                        <td className="px-4 py-3 font-medium text-slate-900">{item.description}</td>
                                                        <td className="px-4 py-3"><span className="px-2 py-1 bg-slate-100 rounded text-xs">{item.item_type}</span></td>
                                                        <td className="px-4 py-3 text-right font-bold">{item.amount.toFixed(2)}</td>
                                                    </tr>
                                                ))}
                                                <tr className="bg-slate-50 font-bold">
                                                    <td colSpan="2" className="px-4 py-3 text-right text-slate-700">Subtotal</td>
                                                    <td className="px-4 py-3 text-right text-slate-900">{activeInvoice.total_amount.toFixed(2)}</td>
                                                </tr>
                                                {activeInvoice.amount_paid > 0 && (
                                                    <tr className="bg-green-50 font-bold text-green-700">
                                                        <td colSpan="2" className="px-4 py-3 text-right">Already Paid</td>
                                                        <td className="px-4 py-3 text-right">-{activeInvoice.amount_paid.toFixed(2)}</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                {/* Payment Processing */}
                                <div>
                                    <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-4 border-b border-slate-200 pb-2">Receive Payment</h3>
                                    <form onSubmit={handleProcessPayment} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                                            {/* Payment Methods */}
                                            <div 
                                                onClick={() => setPaymentMethod('Cash')}
                                                className={`p-4 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center gap-2 ${paymentMethod === 'Cash' ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 text-slate-500 hover:border-brand-300'}`}
                                            >
                                                <Banknote size={24} />
                                                <span className="font-bold text-sm">Cash</span>
                                            </div>
                                            <div 
                                                onClick={() => setPaymentMethod('M-Pesa')}
                                                className={`p-4 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center gap-2 ${paymentMethod === 'M-Pesa' ? 'border-green-500 bg-green-50 text-green-700' : 'border-slate-200 text-slate-500 hover:border-green-300'}`}
                                            >
                                                <Smartphone size={24} />
                                                <span className="font-bold text-sm">M-Pesa (STK)</span>
                                            </div>
                                            <div 
                                                onClick={() => setPaymentMethod('Card')}
                                                className={`p-4 rounded-xl border-2 cursor-pointer transition-all flex flex-col items-center gap-2 ${paymentMethod === 'Card' ? 'border-purple-500 bg-purple-50 text-purple-700' : 'border-slate-200 text-slate-500 hover:border-purple-300'}`}
                                            >
                                                <CreditCard size={24} />
                                                <span className="font-bold text-sm">Credit Card</span>
                                            </div>
                                        </div>

                                        {paymentMethod === 'M-Pesa' && (
                                            <div className="mb-6">
                                                <label className="block text-xs font-bold text-slate-700 mb-1.5">Patient Phone Number for STK Push</label>
                                                <input 
                                                    type="text" 
                                                    required={paymentMethod === 'M-Pesa'}
                                                    value={mpesaPhone} 
                                                    onChange={e => setMpesaPhone(e.target.value)}
                                                    placeholder="e.g. 254712345678" 
                                                    className="w-full px-4 py-3 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-green-500 outline-none" 
                                                />
                                            </div>
                                        )}

                                            <button 
                                                type="submit" 
                                                disabled={isProcessing}
                                                className={`w-full py-4 rounded-xl font-black text-white text-lg flex items-center justify-center gap-2 transition-colors shadow-md ${
                                                    mpesaStatus === 'waiting' ? 'bg-orange-500 hover:bg-orange-600 animate-pulse' :
                                                    paymentMethod === 'M-Pesa' ? 'bg-green-600 hover:bg-green-700' :
                                                    paymentMethod === 'Card' ? 'bg-purple-600 hover:bg-purple-700' :
                                                    'bg-brand-600 hover:bg-brand-700'
                                                } disabled:opacity-80 cursor-pointer disabled:cursor-not-allowed`}
                                            >
                                                {mpesaStatus === 'waiting' ? <Smartphone className="animate-bounce" size={24}/> : isProcessing ? <Activity className="animate-spin" size={24}/> : <CheckCircle2 size={24} />}
                                                {mpesaStatus === 'waiting' ? 'Awaiting PIN from Patient...' : paymentMethod === 'M-Pesa' ? 'Trigger M-Pesa STK Push' : 'Confirm Payment & Close Bill'}
                                            </button>
                                    </form>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="h-[calc(100vh-140px)] flex flex-col items-center justify-center border-2 border-dashed border-slate-200 rounded-xl bg-slate-50 text-slate-400">
                            <Receipt size={64} className="mb-4 text-slate-300" />
                            <p className="text-lg font-bold text-slate-500">Select an invoice to process payment</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
