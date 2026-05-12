import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import {
    Receipt, Search, Filter, CreditCard, Banknote, Smartphone, CheckCircle2,
    Activity, ArrowRight, FileText, X, Printer
} from 'lucide-react';
import toast from 'react-hot-toast';
import { printInvoice } from '../utils/printTemplates';
import PageHeader from '../components/PageHeader';

export default function Billing() {
    const [queue, setQueue] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    
    const [activeInvoice, setActiveInvoice] = useState(null);
    const [paymentMethod, setPaymentMethod] = useState('Cash');
    const [mpesaPhone, setMpesaPhone] = useState('');
    const [isProcessing, setIsProcessing] = useState(false);
    const [mpesaStatus, setMpesaStatus] = useState(null); // 'waiting', 'success', 'failed'
    
    // Ledger Modal State
    const [isLedgerOpen, setIsLedgerOpen] = useState(false);
    const [mpesaLogs, setMpesaLogs] = useState([]);

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
                
                if (res.data.checkout_request_id) {
                    pollMpesaStatus(res.data.checkout_request_id);
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

    const fetchMpesaLogs = async () => {
        try {
            const res = await apiClient.get('/billing/mpesa-transactions');
            setMpesaLogs(res.data || []);
        } catch (error) {
            toast.error("Failed to fetch M-Pesa ledger");
        }
    };

    const openLedger = () => {
        setIsLedgerOpen(true);
        fetchMpesaLogs();
    };

    return (
        <div className="space-y-6 pb-8">
            <PageHeader
                eyebrow="Cashier"
                icon={Receipt}
                title="Billing & Finance"
                subtitle="Manage patient invoices, consultation fees, and accept payments."
                actions={
                    <div className="flex gap-2 flex-wrap items-center">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400" size={16} />
                        <input
                            type="text" placeholder="Search invoices…"
                            value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
                            className="input pl-9 w-64"
                        />
                    </div>
                    <button onClick={openLedger} className="btn-success cursor-pointer">
                        <Smartphone size={15} /> M-Pesa Ledger
                    </button>
                    </div>
                }
            />

            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 items-start">
                {/* Billing Queue List */}
                <div className="md:col-span-1 space-y-3">
                    <h3 className="section-eyebrow flex items-center justify-between">
                        Pending invoices <span className="badge-brand">{queue.length}</span>
                    </h3>

                    {isLoading ? (
                        <div className="card text-center py-12 text-ink-400"><Activity className="animate-spin mx-auto mb-2" size={20} /></div>
                    ) : filteredQueue.length === 0 ? (
                        <div className="card p-8 text-center">
                            <Receipt className="mx-auto text-ink-300 mb-3" size={28} />
                            <p className="text-ink-500 text-sm font-medium">No pending invoices.</p>
                        </div>
                    ) : (
                        <div className="space-y-3 max-h-[70vh] overflow-y-auto custom-scrollbar pr-1">
                            {filteredQueue.map(inv => {
                                const active = activeInvoice?.invoice_id === inv.invoice_id;
                                return (
                                    <button key={inv.invoice_id} type="button" onClick={() => setActiveInvoice(inv)}
                                        className={`w-full text-left card p-4 transition-all duration-150 ${active ? 'border-brand-400 ring-2 ring-brand-500/15 shadow-elevated' : 'hover:-translate-y-0.5 hover:shadow-elevated'}`}>
                                        <div className="flex justify-between items-start mb-2">
                                            <span className={inv.status === 'Pending M-Pesa' ? 'badge-success' : 'badge-warn'}>{inv.status}</span>
                                            <span className="text-2xs font-mono text-ink-400">INV-{inv.invoice_id}</span>
                                        </div>
                                        <h4 className="font-semibold text-ink-900 text-sm">{inv.patient_name}</h4>
                                        <p className="text-xs text-ink-500 mb-3">{inv.patient_opd}</p>
                                        <div className="flex justify-between items-center border-t border-ink-100 pt-3">
                                            <span className="text-xs text-ink-500">Balance due</span>
                                            <span className="font-semibold text-brand-700">KES {(inv.total_amount - inv.amount_paid).toFixed(2)}</span>
                                        </div>
                                    </button>
                                );
                            })}
                        </div>
                    )}
                </div>

                {/* Main Cashier Workspace */}
                <div className="md:col-span-3">
                    {activeInvoice ? (
                        <div className="card overflow-hidden flex flex-col min-h-[60vh] md:h-[calc(100vh-160px)]">
                            <div className="p-5 sm:p-6 bg-gradient-to-br from-ink-900 to-ink-950 text-white shrink-0 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                                <div>
                                    <h2 className="text-xl sm:text-2xl font-semibold tracking-tight">{activeInvoice.patient_name}</h2>
                                    <p className="text-ink-400 text-sm mt-1">{activeInvoice.patient_opd} &middot; Invoice #{activeInvoice.invoice_id}</p>
                                </div>
                                <div className="flex items-center gap-3">
                                    <div className="text-right">
                                        <p className="text-2xs font-semibold uppercase tracking-[0.14em] text-ink-400">Balance due</p>
                                        <p className="text-2xl sm:text-3xl font-semibold text-accent-400 tracking-tight">KES {(activeInvoice.total_amount - activeInvoice.amount_paid).toFixed(2)}</p>
                                    </div>
                                    <button onClick={() => printInvoice(activeInvoice)} className="p-2 bg-white/10 hover:bg-white/15 text-white rounded-lg transition-colors ring-1 ring-white/10 no-print flex items-center gap-2 px-3" title="Print invoice / receipt">
                                        <Printer size={16} />
                                        <span className="text-xs font-semibold">Print</span>
                                    </button>
                                </div>
                            </div>

                            <div className="flex-1 overflow-y-auto p-5 sm:p-6 space-y-6 bg-ink-50/40 custom-scrollbar">
                                <div>
                                    <h3 className="section-eyebrow mb-3 border-b border-ink-100 pb-2">Itemized breakdown</h3>
                                    <div className="card-flush overflow-hidden overflow-x-auto">
                                        <table className="table-clean min-w-[500px]">
                                            <thead>
                                                <tr>
                                                    <th>Description</th>
                                                    <th>Category</th>
                                                    <th className="text-right">Amount (KES)</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {activeInvoice.items.map(item => (
                                                    <tr key={item.id}>
                                                        <td className="font-medium text-ink-900">{item.description}</td>
                                                        <td><span className="badge-neutral">{item.item_type}</span></td>
                                                        <td className="text-right font-semibold">{item.amount.toFixed(2)}</td>
                                                    </tr>
                                                ))}
                                                <tr className="bg-ink-50 font-semibold">
                                                    <td colSpan="2" className="text-right text-ink-700">Subtotal</td>
                                                    <td className="text-right text-ink-900">{activeInvoice.total_amount.toFixed(2)}</td>
                                                </tr>
                                                {activeInvoice.amount_paid > 0 && (
                                                    <tr className="bg-accent-50 font-semibold text-accent-700">
                                                        <td colSpan="2" className="text-right">Already paid</td>
                                                        <td className="text-right">&minus;{activeInvoice.amount_paid.toFixed(2)}</td>
                                                    </tr>
                                                )}
                                            </tbody>
                                        </table>
                                    </div>
                                </div>

                                <div>
                                    <h3 className="section-eyebrow mb-3 border-b border-ink-100 pb-2">Receive payment</h3>
                                    <form onSubmit={handleProcessPayment} className="card p-5 sm:p-6">
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-5">
                                            {[
                                                { key: 'Cash',   icon: Banknote,   label: 'Cash',          accent: 'brand'  },
                                                { key: 'M-Pesa', icon: Smartphone, label: 'M-Pesa (STK)',  accent: 'accent' },
                                                { key: 'Card',   icon: CreditCard, label: 'Credit card',   accent: 'purple' },
                                            ].map(({ key, icon: Icon, label, accent }) => {
                                                const isActive = paymentMethod === key;
                                                const accentMap = {
                                                    brand:  isActive ? 'border-brand-500 bg-brand-50 text-brand-700 ring-2 ring-brand-500/15' : '',
                                                    accent: isActive ? 'border-accent-500 bg-accent-50 text-accent-700 ring-2 ring-accent-500/15' : '',
                                                    purple: isActive ? 'border-purple-500 bg-purple-50 text-purple-700 ring-2 ring-purple-500/15' : '',
                                                };
                                                return (
                                                    <button type="button" key={key} onClick={() => setPaymentMethod(key)}
                                                        className={`p-4 rounded-xl border transition-all flex flex-col items-center gap-2 ${isActive ? accentMap[accent] : 'border-ink-200 text-ink-500 hover:border-ink-300 hover:bg-ink-50'}`}>
                                                        <Icon size={22} />
                                                        <span className="font-semibold text-sm">{label}</span>
                                                    </button>
                                                );
                                            })}
                                        </div>

                                        {paymentMethod === 'M-Pesa' && (
                                            <div className="mb-5 animate-fade-in">
                                                <label className="label">Patient phone number for STK push</label>
                                                <input
                                                    type="text"
                                                    required={paymentMethod === 'M-Pesa'}
                                                    value={mpesaPhone}
                                                    onChange={e => setMpesaPhone(e.target.value)}
                                                    placeholder="e.g. 254712345678"
                                                    className="input"
                                                />
                                            </div>
                                        )}

                                        <button
                                            type="submit"
                                            disabled={isProcessing}
                                            className={`w-full py-3.5 rounded-xl font-semibold text-white text-base flex items-center justify-center gap-2 transition-all shadow-soft ${
                                                mpesaStatus === 'waiting' ? 'bg-amber-500 hover:bg-amber-600 animate-pulse-soft' :
                                                paymentMethod === 'M-Pesa' ? 'bg-gradient-to-b from-accent-500 to-accent-600 hover:from-accent-500 hover:to-accent-700' :
                                                paymentMethod === 'Card'   ? 'bg-gradient-to-b from-purple-500 to-purple-600 hover:from-purple-500 hover:to-purple-700' :
                                                                              'bg-gradient-to-b from-brand-500 to-brand-600 hover:from-brand-500 hover:to-brand-700'
                                            } disabled:opacity-80 disabled:cursor-not-allowed`}
                                        >
                                            {mpesaStatus === 'waiting' ? <Smartphone className="animate-pulse" size={20} /> : isProcessing ? <Activity className="animate-spin" size={20} /> : <CheckCircle2 size={20} />}
                                            {mpesaStatus === 'waiting' ? 'Awaiting PIN from patient…' : paymentMethod === 'M-Pesa' ? 'Trigger M-Pesa STK Push' : 'Confirm payment & close bill'}
                                        </button>
                                    </form>
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div className="h-[calc(100vh-160px)] flex flex-col items-center justify-center border-2 border-dashed border-ink-200 rounded-2xl bg-white text-ink-400">
                            <Receipt size={56} className="mb-4 text-ink-300" />
                            <p className="text-base font-semibold text-ink-600">Select an invoice to process payment</p>
                            <p className="text-xs text-ink-400 mt-1">Pick from the queue on the left.</p>
                        </div>
                    )}
                </div>
            </div>

            {/* --- M-PESA LEDGER MODAL --- */}
            {isLedgerOpen && (
                <div className="fixed inset-0 z-50 flex justify-end">
                    <div className="fixed inset-0 bg-ink-900/60 backdrop-blur-sm" onClick={() => setIsLedgerOpen(false)}></div>
                    <div className="relative w-full max-w-4xl bg-white h-full shadow-elevated flex flex-col animate-slide-in-right">
                        <div className="p-6 border-b border-ink-100 bg-gradient-to-br from-ink-900 to-ink-950 text-white shrink-0 flex justify-between items-center">
                            <div>
                                <h2 className="text-lg font-semibold tracking-tight flex items-center gap-2"><Smartphone size={20} className="text-accent-400" /> M-Pesa Receipts Ledger</h2>
                                <p className="text-sm text-ink-400 mt-1">Verify real-time STK push statuses and Daraja receipt codes.</p>
                            </div>
                            <button onClick={() => setIsLedgerOpen(false)} aria-label="Close" className="p-2 rounded-lg text-ink-400 hover:text-white hover:bg-white/10 transition-colors"><X size={20} /></button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-6 bg-ink-50/40 custom-scrollbar">
                            <div className="card overflow-hidden">
                                <table className="table-clean min-w-[800px]">
                                    <thead className="sticky top-0">
                                        <tr>
                                            <th>Timestamp</th>
                                            <th>Phone</th>
                                            <th>Invoice</th>
                                            <th>Amount (KES)</th>
                                            <th>Receipt details</th>
                                            <th className="text-right">Status</th>
                                        </tr>
                                    </thead>
                                    <tbody className="font-mono text-xs">
                                        {mpesaLogs.length === 0 ? (
                                            <tr><td colSpan="6" className="px-6 py-12 text-center text-ink-400 font-sans">No M-Pesa transactions found.</td></tr>
                                        ) : (
                                            mpesaLogs.map((log) => (
                                                <tr key={log.id}>
                                                    <td className="text-ink-500">{new Date(log.created_at).toLocaleString()}</td>
                                                    <td className="font-semibold text-ink-800">{log.phone_number}</td>
                                                    <td className="font-semibold text-brand-700">INV-{log.invoice_id}</td>
                                                    <td className="font-semibold text-ink-900">{log.amount ? log.amount.toFixed(2) : '-'}</td>
                                                    <td className="text-ink-500 max-w-xs truncate">{log.receipt_number || log.result_desc || 'Waiting for callback…'}</td>
                                                    <td className="text-right">
                                                        <span className={log.status === 'Success' ? 'badge-success' : log.status === 'Failed' ? 'badge-danger' : 'badge-warn animate-pulse-soft'}>
                                                            {log.status}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
