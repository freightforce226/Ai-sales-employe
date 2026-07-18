'use client';

import React, { useState, useEffect } from 'react';
import { AppShell } from '../../components/layout/shell';
import { useRouter } from 'next/navigation';
import { api } from '../../lib/api';
import { 
  Search, 
  Filter, 
  Trash2, 
  Building, 
  ChevronRight, 
  ChevronLeft,
  X, 
  Edit2, 
  Check, 
  Send,
  Loader2,
  AlertCircle
} from 'lucide-react';

interface Customer {
  id: string;
  company_name: string;
  contact_name: string | null;
  contact_email: string | null;
  industry: string | null;
  country: string | null;
  segment: string | null;
  engagement_readiness: 'READY' | 'EMAIL_MISSING' | 'NOT_ELIGIBLE' | 'MISSING_TEMPLATE' | 'MISSING_ATTACHMENT';
  last_email: string | null;
  imported_on: string;
  status: string;
}

interface TimelineEvent {
  subject: string;
  sent_at: string;
  delivery_status: string;
}

interface CustomerDetail extends Customer {
  import_batch_id: string | null;
  import_batch_name: string | null;
  total_emails_sent: number;
  assigned_template: string | null;
  assigned_attachment: string | null;
  last_subject: string | null;
  last_delivery_status: string | null;
  last_message_id: string | null;
  emails_this_week: number;
  emails_this_month: number;
  timeline: TimelineEvent[];
}

interface FilterValues {
  industries: string[];
  countries: string[];
  segments: string[];
}

interface Stats {
  total_customers: number;
  ready_count: number;
  segment_breakdown: Record<string, number>;
  country_breakdown: Record<string, number>;
}

export default function CustomersPage() {
  const router = useRouter();
  
  // State variables
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [triggeringRun, setTriggeringRun] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);

  const handleTriggerEngagement = async () => {
    try {
      setTriggeringRun(true);
      setTriggerError(null);
      const res = await api.post('/api/v1/engagement/run');
      setConfirmModalOpen(false);
      router.push('/engagement');
    } catch (err: any) {
      console.error('Failed to trigger run', err);
      if (err.response?.status === 409) {
        setTriggerError('An engagement run is already active. Parallel executions are locked to prevent duplicates.');
      } else {
        setTriggerError(err.response?.data?.detail || 'Failed to start execution. Please verify your MS Graph/mailbox settings.');
      }
    } finally {
      setTriggeringRun(false);
    }
  };
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [limit] = useState(10);
  const [search, setSearch] = useState('');
  const [industry, setIndustry] = useState('');
  const [country, setCountry] = useState('');
  const [segment, setSegment] = useState('');
  
  // Lists for dropdown options
  const [filtersOptions, setFiltersOptions] = useState<FilterValues>({
    industries: [],
    countries: [],
    segments: []
  });

  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  
  // Drawer states
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedCustomer, setSelectedCustomer] = useState<CustomerDetail | null>(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    company_name: '',
    contact_name: '',
    contact_email: '',
    industry: '',
    country: ''
  });
  const [savingEdit, setSavingEdit] = useState(false);

  // Load resources
  const fetchFilters = async () => {
    try {
      const res = await api.get('/api/v1/customers/filters');
      setFiltersOptions(res.data);
    } catch (err) {
      console.error('Failed to fetch filters options', err);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await api.get('/api/v1/customers/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to fetch stats', err);
    }
  };

  const fetchCustomers = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/v1/customers', {
        params: {
          page,
          limit,
          q: search || undefined,
          industry: industry || undefined,
          country: country || undefined,
          segment: segment || undefined
        }
      });
      setCustomers(res.data.customers);
      setTotal(res.data.total);
    } catch (err) {
      console.error('Failed to fetch customers list', err);
    } finally {
      setLoading(false);
    }
  };

  // Triggers
  useEffect(() => {
    fetchFilters();
    fetchStats();
  }, []);

  useEffect(() => {
    fetchCustomers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, industry, country, segment]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchCustomers();
  };

  const handleClearFilters = () => {
    setSearch('');
    setIndustry('');
    setCountry('');
    setSegment('');
    setPage(1);
  };

  // Row Selection
  const handleSelectRow = (id: string) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    if (selectedIds.length === customers.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(customers.map(c => c.id));
    }
  };

  // Actions: Delete Single
  const handleDeleteSingle = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete "${name}"?`)) return;
    try {
      await api.delete(`/api/v1/customers/${id}`);
      fetchCustomers();
      fetchStats();
      fetchFilters();
      if (selectedCustomer?.id === id) {
        setDrawerOpen(false);
      }
    } catch {
      alert('Failed to delete customer.');
    }
  };

  // Actions: Bulk Delete
  const handleBulkDelete = async () => {
    if (!confirm(`Are you sure you want to delete ${selectedIds.length} customers?`)) return;
    try {
      await api.post('/api/v1/customers/bulk-delete', { ids: selectedIds });
      setSelectedIds([]);
      fetchCustomers();
      fetchStats();
      fetchFilters();
    } catch {
      alert('Failed to execute bulk deletion.');
    }
  };

  // Actions: Details Drawer
  const handleOpenDrawer = async (customer: Customer) => {
    setDrawerOpen(true);
    setLoadingDetails(true);
    setIsEditing(false);
    setSelectedCustomer(null);
    try {
      const res = await api.get(`/api/v1/customers/${customer.id}`);
      const detail: CustomerDetail = res.data;
      setSelectedCustomer(detail);
      setEditForm({
        company_name: detail.company_name,
        contact_name: detail.contact_name || '',
        contact_email: detail.contact_email || '',
        industry: detail.industry || '',
        country: detail.country || ''
      });
    } catch {
      console.error('Failed to fetch customer detail details');
    } finally {
      setLoadingDetails(false);
    }
  };

  // Actions: Edit Form Save
  const handleSaveEdit = async () => {
    if (!selectedCustomer) return;
    if (!editForm.company_name.trim()) {
      alert('Company Name is required.');
      return;
    }
    setSavingEdit(true);
    try {
      const res = await api.put(`/api/v1/customers/${selectedCustomer.id}`, editForm);
      setSelectedCustomer(prev => prev ? { ...prev, ...res.data } : null);
      setIsEditing(false);
      fetchCustomers();
      fetchStats();
    } catch {
      alert('Failed to save changes.');
    } finally {
      setSavingEdit(false);
    }
  };

  // Helpers: Badges styling
  const getReadinessBadge = (code: string) => {
    switch (code) {
      case 'READY':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">Ready</span>;
      case 'EMAIL_MISSING':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800">Email Missing</span>;
      case 'NOT_ELIGIBLE':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-100 text-rose-800">Not Eligible</span>;
      case 'MISSING_TEMPLATE':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800">Missing Template</span>;
      case 'MISSING_ATTACHMENT':
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-800">Missing Attachment</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-800">{code}</span>;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'ACTIVE':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">ACTIVE</span>;
      case 'PAUSED':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-amber-500/10 text-amber-600 border border-amber-500/20">PAUSED</span>;
      case 'COMPLETED':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-blue-500/10 text-blue-600 border border-blue-500/20">COMPLETED</span>;
      case 'EXITED_REPLIED':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-indigo-500/10 text-indigo-600 border border-indigo-500/20">REPLIED</span>;
      case 'EXITED_UNSUBSCRIBED':
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/10 text-rose-600 border border-rose-500/20">UNSUBSCRIBED</span>;
      default:
        return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-slate-100 text-slate-500 border border-slate-200">NOT CONTACTED</span>;
    }
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <AppShell>
      <div className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6 sm:space-y-8">
        
        {/* Header section */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-border-color gap-4">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
              Customers Directory
            </h1>
            <p className="text-xs sm:text-sm text-text-secondary font-medium">
              View, filter, and manage customer records integrated with CSV Import and Campaigns.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setConfirmModalOpen(true)}
              className="h-10 px-5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold flex items-center gap-2 shadow-sm transition-all cursor-pointer border-0"
            >
              <Send className="w-4 h-4" />
              <span>Send Engagement</span>
            </button>
          </div>
        </div>

        {/* Stats Grid */}
        {stats && (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 sm:gap-6">
            <div className="bg-bg-surface p-5 rounded-xl border border-border-color border-t-2 border-t-brand-primary flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div>
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Total Customers</span>
                <p className="text-2xl font-bold text-text-primary mt-1 font-mono">{stats.total_customers}</p>
              </div>
              <span className="text-[10px] text-text-muted mt-2 font-medium">Synced database profile records</span>
            </div>

            <div className="bg-bg-surface p-5 rounded-xl border border-border-color border-t-2 border-t-emerald-500 flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div>
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Engagement Ready</span>
                <p className="text-2xl font-bold text-emerald-600 mt-1 font-mono">
                  {stats.ready_count} <span className="text-xs text-text-secondary font-medium">({stats.total_customers ? Math.round((stats.ready_count / stats.total_customers) * 100) : 0}%)</span>
                </p>
              </div>
              <span className="text-[10px] text-text-muted mt-2 font-medium">Emails and assets completely validated</span>
            </div>

            <div className="bg-bg-surface p-5 rounded-xl border border-border-color border-t-2 border-t-brand-accent flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div>
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Active Segments</span>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {Object.entries(stats.segment_breakdown).length === 0 ? (
                    <span className="text-xs text-text-muted">No segments active</span>
                  ) : (
                    Object.entries(stats.segment_breakdown).map(([seg, count]) => (
                      <span key={seg} className="text-[10px] font-semibold bg-bg-secondary border border-border-color px-2 py-0.5 rounded-md text-text-secondary uppercase">
                        {seg}: {count}
                      </span>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Filters and Search toolbar */}
        <div className="bg-bg-surface p-4 rounded-xl border border-border-color space-y-4">
          <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by company name, contact person, or email..."
                className="w-full pl-9 pr-4 py-2 border border-border-color rounded-xl text-xs sm:text-sm bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary"
              />
            </div>
            <button
              type="submit"
              className="bg-brand-primary text-white hover:bg-brand-primary-hover text-xs font-bold px-4 py-2 rounded-xl transition-all shadow-xs cursor-pointer"
            >
              Search
            </button>
            {(search || industry || country || segment) && (
              <button
                type="button"
                onClick={handleClearFilters}
                className="border border-border-color text-text-secondary hover:bg-bg-secondary text-xs font-semibold px-4 py-2 rounded-xl transition-all cursor-pointer bg-transparent"
              >
                Clear Filters
              </button>
            )}
          </form>

          <div className="flex flex-wrap items-center gap-3 border-t border-border-color/60 pt-3 text-xs">
            <div className="flex items-center space-x-2">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-bold text-text-secondary">Filters:</span>
            </div>

            {/* Industry Filter */}
            <select
              value={industry}
              onChange={(e) => { setIndustry(e.target.value); setPage(1); }}
              className="border border-border-color rounded-lg bg-bg-secondary px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="">All Industries</option>
              {filtersOptions.industries.filter(Boolean).map(ind => (
                <option key={ind} value={ind}>{ind}</option>
              ))}
            </select>

            {/* Country Filter */}
            <select
              value={country}
              onChange={(e) => { setCountry(e.target.value); setPage(1); }}
              className="border border-border-color rounded-lg bg-bg-secondary px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="">All Countries</option>
              {filtersOptions.countries.filter(Boolean).map(cntry => (
                <option key={cntry} value={cntry}>{cntry}</option>
              ))}
            </select>

            {/* Segment Filter */}
            <select
              value={segment}
              onChange={(e) => { setSegment(e.target.value); setPage(1); }}
              className="border border-border-color rounded-lg bg-bg-secondary px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-brand-primary"
            >
              <option value="">All Segments</option>
              {filtersOptions.segments.filter(Boolean).map(seg => (
                <option key={seg} value={seg}>{seg.toUpperCase()}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Selected row bulk action header */}
        {selectedIds.length > 0 && (
          <div className="flex items-center justify-between p-4 bg-red-50 border border-red-200 rounded-xl">
            <span className="text-xs font-bold text-red-800">
              {selectedIds.length} customer records selected
            </span>
            <button
              onClick={handleBulkDelete}
              className="flex items-center gap-1 bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Bulk Delete</span>
            </button>
          </div>
        )}

        {/* Customers Table */}
        <div className="bg-bg-surface rounded-xl border border-border-color overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-bg-secondary border-b border-border-color">
                  <th className="p-4 w-10">
                    <input 
                      type="checkbox"
                      checked={customers.length > 0 && selectedIds.length === customers.length}
                      onChange={handleSelectAll}
                      className="rounded border-border-color text-brand-primary focus:ring-brand-primary cursor-pointer w-4 h-4"
                    />
                  </th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Company</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Contact</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Email</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Industry</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Country</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Segment</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Engagement Readiness</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Last Email</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Imported On</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em]">Status</th>
                  <th className="p-4 text-[10px] font-bold text-text-muted uppercase tracking-[0.08em] text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-color/60">
                {loading ? (
                  <tr>
                    <td colSpan={12} className="p-12 text-center text-xs text-text-muted font-semibold">
                      <div className="flex items-center justify-center space-x-2">
                        <Loader2 className="w-4.5 h-4.5 animate-spin text-brand-primary" />
                        <span>Loading customer records...</span>
                      </div>
                    </td>
                  </tr>
                ) : customers.length === 0 ? (
                  <tr>
                    <td colSpan={12} className="p-12 text-center text-xs text-text-muted font-medium">
                      No customer records found matching your filters.
                    </td>
                  </tr>
                ) : (
                  customers.map((c) => (
                    <tr key={c.id} className="hover:bg-bg-secondary/40 transition-colors">
                      <td className="p-4">
                        <input 
                          type="checkbox"
                          checked={selectedIds.includes(c.id)}
                          onChange={() => handleSelectRow(c.id)}
                          className="rounded border-border-color text-brand-primary focus:ring-brand-primary cursor-pointer w-4 h-4"
                        />
                      </td>
                      <td className="p-4 text-xs font-bold text-text-primary">
                        <button 
                          onClick={() => handleOpenDrawer(c)}
                          className="hover:underline text-left cursor-pointer bg-transparent border-0 font-bold p-0"
                        >
                          {c.company_name}
                        </button>
                      </td>
                      <td className="p-4 text-xs font-semibold text-text-secondary">{c.contact_name || '—'}</td>
                      <td className="p-4 text-xs text-text-muted font-medium font-mono">{c.contact_email || '—'}</td>
                      <td className="p-4 text-xs font-medium text-text-secondary">{c.industry || '—'}</td>
                      <td className="p-4 text-xs font-medium text-text-secondary">{c.country || '—'}</td>
                      <td className="p-4 text-xs font-semibold text-text-secondary uppercase">{c.segment || '—'}</td>
                      <td className="p-4">{getReadinessBadge(c.engagement_readiness)}</td>
                      <td className="p-4 text-xs text-text-muted font-mono">{c.last_email || '—'}</td>
                      <td className="p-4 text-xs text-text-muted font-mono">{c.imported_on}</td>
                      <td className="p-4">{getStatusBadge(c.status)}</td>
                      <td className="p-4 text-right">
                        <div className="flex items-center justify-end space-x-1.5">
                          <button
                            onClick={() => handleOpenDrawer(c)}
                            className="text-xs font-bold text-brand-primary hover:text-brand-primary-hover px-2.5 py-1.5 rounded-lg hover:bg-brand-primary/5 transition-all cursor-pointer"
                          >
                            Details
                          </button>
                          <div className="relative group inline-block">
                            <button
                              disabled
                              className="text-xs font-bold text-slate-400 bg-slate-100 cursor-not-allowed px-2.5 py-1.5 rounded-lg flex items-center gap-1"
                            >
                              <Send className="w-3 h-3" />
                              <span>Campaign</span>
                            </button>
                            <div className="absolute bottom-full right-0 mb-1 hidden group-hover:block bg-slate-950 text-white font-bold text-[9px] px-2 py-1 rounded shadow-md whitespace-nowrap z-50">
                              Campaign Module Coming Soon
                            </div>
                          </div>
                          <button
                            onClick={() => handleDeleteSingle(c.id, c.company_name)}
                            className="text-slate-400 hover:text-red-500 p-1.5 rounded-lg hover:bg-red-50 transition-all cursor-pointer"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="p-4 border-t border-border-color flex items-center justify-between text-xs font-medium text-text-secondary">
              <span>Showing {customers.length} of {total} records</span>
              <div className="flex items-center space-x-2">
                <button
                  disabled={page === 1}
                  onClick={() => setPage(p => Math.max(1, p - 1))}
                  className="p-1.5 rounded-lg border border-border-color hover:bg-bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ChevronLeft className="w-4.5 h-4.5" />
                </button>
                <span className="font-bold">Page {page} of {totalPages}</span>
                <button
                  disabled={page === totalPages}
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                  className="p-1.5 rounded-lg border border-border-color hover:bg-bg-secondary disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <ChevronRight className="w-4.5 h-4.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Customer Drawer Overlay */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* Backdrop */}
          <div 
            onClick={() => setDrawerOpen(false)}
            className="absolute inset-0 bg-black/35 backdrop-blur-xs transition-opacity duration-200" 
          />

          {/* Panel */}
          <div className="relative w-full max-w-md bg-white h-full shadow-2xl flex flex-col z-50 border-l border-border-color animate-slide-in">
            {/* Header */}
            <div className="p-5 border-b border-border-color flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
                <div className="w-8 h-8 rounded-lg bg-brand-primary/10 text-brand-primary flex items-center justify-center font-bold">
                  <Building className="w-4.5 h-4.5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-text-primary">Customer Profile</h3>
                  <p className="text-[10px] text-text-muted font-medium">BFF Workflow Workspace</p>
                </div>
              </div>
              <button 
                onClick={() => setDrawerOpen(false)}
                className="p-1.5 hover:bg-bg-secondary rounded-lg text-slate-400 hover:text-slate-600 transition-colors cursor-pointer"
              >
                <X className="w-4.5 h-4.5" />
              </button>
            </div>

            {/* Content Body */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {loadingDetails ? (
                <div className="flex flex-col items-center justify-center py-20 space-y-3">
                  <Loader2 className="w-8 h-8 animate-spin text-brand-primary" />
                  <span className="text-xs font-semibold text-text-muted">Loading details...</span>
                </div>
              ) : selectedCustomer ? (
                <>
                  {/* Status / Readiness Row */}
                  <div className="flex items-center justify-between p-3.5 bg-bg-secondary rounded-xl border border-border-color">
                    <div className="space-y-1">
                      <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Workflow Status</span>
                      {getStatusBadge(selectedCustomer.status)}
                    </div>
                    <div className="space-y-1 text-right">
                      <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Readiness Code</span>
                      {getReadinessBadge(selectedCustomer.engagement_readiness)}
                    </div>
                  </div>

                  {/* Fields Form or View */}
                  <div className="space-y-4">
                    <div className="flex justify-between items-center pb-2 border-b border-border-color/60">
                      <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Properties</h4>
                      {!isEditing ? (
                        <button
                          onClick={() => setIsEditing(true)}
                          className="text-[10px] font-bold text-brand-primary hover:text-brand-primary-hover flex items-center gap-1 cursor-pointer bg-transparent border-0"
                        >
                          <Edit2 className="w-3 h-3" />
                          <span>Edit</span>
                        </button>
                      ) : (
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={handleSaveEdit}
                            disabled={savingEdit}
                            className="text-[10px] font-bold text-emerald-600 hover:text-emerald-700 flex items-center gap-1 cursor-pointer bg-transparent border-0"
                          >
                            {savingEdit ? '...' : <Check className="w-3.5 h-3.5" />}
                            <span>Save</span>
                          </button>
                          <button
                            onClick={() => setIsEditing(false)}
                            className="text-[10px] font-bold text-rose-500 hover:text-rose-600 cursor-pointer bg-transparent border-0"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                    </div>

                    <div className="space-y-4">
                      {/* Company Name */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Company</label>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editForm.company_name}
                            onChange={(e) => setEditForm(prev => ({ ...prev, company_name: e.target.value }))}
                            className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold"
                          />
                        ) : (
                          <p className="text-xs font-bold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                            {selectedCustomer.company_name}
                          </p>
                        )}
                      </div>

                      {/* Contact Name */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Contact Person</label>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editForm.contact_name}
                            onChange={(e) => setEditForm(prev => ({ ...prev, contact_name: e.target.value }))}
                            className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold"
                          />
                        ) : (
                          <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                            {selectedCustomer.contact_name || '—'}
                          </p>
                        )}
                      </div>

                      {/* Contact Email */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Contact Email</label>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editForm.contact_email}
                            onChange={(e) => setEditForm(prev => ({ ...prev, contact_email: e.target.value }))}
                            className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold font-mono"
                          />
                        ) : (
                          <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 font-mono">
                            {selectedCustomer.contact_email || '—'}
                          </p>
                        )}
                      </div>

                      {/* Industry */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Industry</label>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editForm.industry}
                            onChange={(e) => setEditForm(prev => ({ ...prev, industry: e.target.value }))}
                            className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold"
                          />
                        ) : (
                          <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                            {selectedCustomer.industry || '—'}
                          </p>
                        )}
                      </div>

                      {/* Country */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Country</label>
                        {isEditing ? (
                          <input
                            type="text"
                            value={editForm.country}
                            onChange={(e) => setEditForm(prev => ({ ...prev, country: e.target.value }))}
                            className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold"
                          />
                        ) : (
                          <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                            {selectedCustomer.country || '—'}
                          </p>
                        )}
                      </div>

                      {/* Segment */}
                      <div className="space-y-1">
                        <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Segment</label>
                        <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 uppercase">
                          {selectedCustomer.segment || '—'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Workflow Integration fields */}
                  <div className="space-y-4 pt-4 border-t border-border-color/60">
                    <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Workflow Diagnostics</h4>
                    
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider">Last Email Date</span>
                        <p className="text-xs font-semibold text-text-secondary font-mono">{selectedCustomer.last_email || 'Never'}</p>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider">Total Emails Sent</span>
                        <p className="text-xs font-bold text-text-secondary font-mono">{selectedCustomer.total_emails_sent}</p>
                      </div>
                    </div>

                    <div className="space-y-1.5 bg-blue-50/50 border border-blue-200/50 p-3 rounded-xl">
                      <span className="text-[9px] font-bold text-brand-primary uppercase tracking-wider">Import Reference</span>
                      <div className="space-y-1">
                        <p className="text-xs font-bold text-text-primary truncate">
                          File: {selectedCustomer.import_batch_name || 'Manual Import'}
                        </p>
                        <p className="text-[10px] text-text-muted font-medium">
                          Imported: {selectedCustomer.imported_on}
                        </p>
                      </div>
                    </div>

                    {/* Engagement Timeline Details */}
                    <div className="space-y-4 pt-4 border-t border-border-color/60">
                      <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Engagement Details</h4>
                      
                      <div className="grid grid-cols-2 gap-3 text-xs bg-bg-secondary p-3.5 rounded-xl border border-border-color/50">
                        <div>
                          <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Sent This Week</span>
                          <span className="font-bold text-text-primary">{selectedCustomer.emails_this_week}</span>
                        </div>
                        <div>
                          <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Sent This Month</span>
                          <span className="font-bold text-text-primary">{selectedCustomer.emails_this_month}</span>
                        </div>
                        <div className="col-span-2 pt-2 border-t border-border-color/30">
                          <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Last Contact Date</span>
                          <span className="font-semibold text-text-secondary">{selectedCustomer.last_email || 'Never contacted'}</span>
                        </div>
                      </div>

                      {selectedCustomer.last_subject && (
                        <div className="space-y-2 bg-bg-secondary p-3.5 rounded-xl border border-border-color/50 text-xs">
                          <div>
                            <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Last Subject</span>
                            <span className="font-bold text-text-primary block truncate">{selectedCustomer.last_subject}</span>
                          </div>
                          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border-color/30">
                            <div>
                              <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Delivery Status</span>
                              <span className="font-bold text-emerald-650 uppercase">{selectedCustomer.last_delivery_status || 'Delivered'}</span>
                            </div>
                            <div>
                              <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Message ID</span>
                              <span className="font-semibold text-text-muted truncate block max-w-[120px] font-mono">{selectedCustomer.last_message_id}</span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Timeline Events list */}
                      <div className="space-y-2">
                        <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block">Engagement Timeline</span>
                        {selectedCustomer.timeline && selectedCustomer.timeline.length > 0 ? (
                          <div className="space-y-2 max-h-[160px] overflow-y-auto border border-border-color rounded-xl p-3 bg-bg-secondary/40 font-mono text-[10px]">
                            {selectedCustomer.timeline.map((evt, idx) => (
                              <div key={idx} className="flex flex-col border-b border-border-color/30 pb-2 last:border-0 last:pb-0">
                                <div className="flex justify-between font-bold text-text-muted">
                                  <span>[{new Date(evt.sent_at).toLocaleDateString()}]</span>
                                  <span className="text-emerald-650 uppercase">{evt.delivery_status}</span>
                                </div>
                                <span className="text-text-primary mt-1 font-sans">{evt.subject}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-xs text-text-muted italic text-center py-2 bg-bg-secondary/20 rounded-lg">No engagement history timeline found.</p>
                        )}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex flex-col items-center justify-center py-20 text-center space-y-2">
                  <AlertCircle className="w-8 h-8 text-rose-500" />
                  <span className="text-xs font-semibold text-text-muted">Error loading customer details.</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal */}
      {confirmModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs select-none">
          <div className="bg-white rounded-2xl border border-border-color max-w-md w-full p-6 shadow-2xl space-y-5 animate-scale-up">
            <h3 className="text-lg font-bold text-text-primary">Confirm Campaign Run</h3>
            
            <div className="space-y-3.5 text-sm text-text-secondary">
              <p>You are initiating a manual campaign run for this organization.</p>
              
              <div className="bg-bg-secondary rounded-xl p-4 border border-border-color/50 space-y-2">
                <div className="flex justify-between">
                  <span className="font-semibold text-text-muted">Eligible Customers</span>
                  <span className="font-bold text-text-primary">{stats?.ready_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-semibold text-text-muted">Estimated Emails</span>
                  <span className="font-bold text-emerald-600">{stats?.ready_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-semibold text-text-muted">Estimated Duration</span>
                  <span className="font-bold text-text-primary">~{((stats?.ready_count || 0) * 5) >= 60 ? `${Math.round(((stats?.ready_count || 0) * 5) / 60)} min` : `${(stats?.ready_count || 0) * 5} sec`}</span>
                </div>
              </div>

              {triggerError && (
                <p className="text-xs font-semibold text-rose-600 bg-rose-50 border border-rose-100 p-3 rounded-lg leading-relaxed">{triggerError}</p>
              )}
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setConfirmModalOpen(false)}
                disabled={triggeringRun}
                className="px-4 py-2 border border-border-color text-text-secondary hover:bg-bg-secondary rounded-lg text-sm font-semibold transition-all cursor-pointer bg-transparent"
              >
                Cancel
              </button>
              <button
                onClick={handleTriggerEngagement}
                disabled={triggeringRun}
                className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer border-0"
              >
                {triggeringRun ? 'Starting...' : 'Start Button'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
