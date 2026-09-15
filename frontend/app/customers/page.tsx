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
  AlertCircle,
  Mail,
  Calendar,
  CheckCircle,
  FileText,
  Sparkles,
  Clock,
  ChevronDown,
  ChevronUp,
  Users,
  Layers
} from 'lucide-react';
import { Alert } from '../../components/ui/feedback';
import { ConfirmationModal } from '../../components/ui/confirmation-modal';

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
  is_suppressed?: boolean;
  suppression_reason?: string | null;
  bounce_reason?: string | null;
  suppressed_at?: string | null;
  designation?: string | null;
  phone?: string | null;
  website?: string | null;
  linkedin?: string | null;
  address?: string | null;
  city?: string | null;
  state?: string | null;
  shipment_mode?: string | null;
  trade_direction?: string | null;
  customer_type?: string | null;
  trade_region?: string | null;
  goods_description?: string | null;
  raw_company_name?: string | null;
  raw_contact_name?: string | null;
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

const isValidWebsite = (url: string | null | undefined): boolean => {
  if (!url) return false;
  const cleaned = url.trim().toLowerCase();
  return cleaned !== '' && cleaned !== 'null' && cleaned !== 'n/a' && cleaned !== 'na' && cleaned !== '-';
};

const isValidLinkedin = (url: string | null | undefined): boolean => {
  if (!url) return false;
  const cleaned = url.trim().toLowerCase();
  return (
    cleaned !== '' &&
    cleaned !== 'null' &&
    cleaned !== 'n/a' &&
    cleaned !== 'na' &&
    cleaned !== '-' &&
    (cleaned.includes('linkedin.com') || cleaned.startsWith('http'))
  );
};

const cleanDisplayValue = (val: string | null | undefined): string => {
  if (!val) return '—';
  const cleaned = val.trim();
  const lower = cleaned.toLowerCase();
  if (lower === '' || lower === 'null' || lower === 'n/a' || lower === 'na' || cleaned === '-') {
    return '—';
  }
  return cleaned;
};

const getEventIcon = (type: string) => {
  switch (type) {
    case 'csv_imported': return <Building className="w-3.5 h-3.5" />;
    case 'email_sent':
    case 'followup_sent': return <Send className="w-3.5 h-3.5" />;
    case 'email_failed': return <AlertCircle className="w-3.5 h-3.5" />;
    case 'followup_scheduled': return <Calendar className="w-3.5 h-3.5" />;
    case 'reply_received': return <Mail className="w-3.5 h-3.5" />;
    case 'sequence_stopped': return <X className="w-3.5 h-3.5" />;
    default: return <Clock className="w-3.5 h-3.5" />;
  }
};

const getEventColorClasses = (color: string) => {
  switch (color) {
    case 'blue': return 'text-blue-600 bg-blue-50 border-blue-200';
    case 'emerald': return 'text-emerald-600 bg-emerald-50 border-emerald-200';
    case 'red': return 'text-rose-600 bg-rose-50 border-rose-200';
    case 'indigo': return 'text-indigo-600 bg-indigo-50 border-indigo-200';
    case 'violet': return 'text-violet-600 bg-violet-50 border-violet-200';
    default: return 'text-slate-600 bg-slate-50 border-slate-200';
  }
};

const stripHtmlToPlainText = (html: string) => {
  if (!html) return '';
  if (!html.includes('<') && !html.includes('>')) return html;
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    let txt = doc.body.textContent || doc.body.innerText || '';
    txt = txt.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    txt = txt.replace(/\n{3,}/g, '\n\n');
    return txt.trim();
  } catch (e) {
    let cleaned = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    cleaned = cleaned.replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '');
    cleaned = cleaned.replace(/<[^>]+>/g, '\n');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
    return cleaned.trim();
  }
};

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
  
  // Customer Journey States
  const [activeTab, setActiveTab] = useState<'overview' | 'journey'>('overview');
  const [journeyTimeline, setJourneyTimeline] = useState<any[]>([]);
  const [loadingJourney, setLoadingJourney] = useState(false);
  const [expandedEvents, setExpandedEvents] = useState<Record<string, boolean>>({});

  // Modal states
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingCustomerId, setDeletingCustomerId] = useState<string | null>(null);
  const [deletingCustomerName, setDeletingCustomerName] = useState<string>('');
  const [isDeletingLoading, setIsDeletingLoading] = useState(false);

  const [bulkDeleteModalOpen, setBulkDeleteModalOpen] = useState(false);
  const [isBulkDeletingLoading, setIsBulkDeletingLoading] = useState(false);

  const [alertInfo, setAlertInfo] = useState<{ variant: 'success' | 'danger'; title: string; message: string } | null>(null);

  const showToast = (variant: 'success' | 'danger', title: string, message: string) => {
    setAlertInfo({ variant, title, message });
    setTimeout(() => {
      setAlertInfo(null);
    }, 4000);
  };
  const [isCreatingCustomer, setIsCreatingCustomer] = useState(false);
  const [createForm, setCreateForm] = useState({
    company_name: '',
    contact_name: '',
    contact_email: '',
    industry: '',
    country: '',
    designation: '',
    phone: '',
    website: '',
    linkedin: '',
    address: '',
    city: '',
    state: '',
    shipment_mode: '',
    trade_direction: '',
    customer_type: '',
    trade_region: '',
    goods_description: ''
  });
  const [creatingLoading, setCreatingLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [activeFormTab, setActiveFormTab] = useState<'basic' | 'professional' | 'logistics'>('basic');

  const resetCreateForm = () => {
    setCreateForm({
      company_name: '',
      contact_name: '',
      contact_email: '',
      industry: '',
      country: '',
      designation: '',
      phone: '',
      website: '',
      linkedin: '',
      address: '',
      city: '',
      state: '',
      shipment_mode: '',
      trade_direction: '',
      customer_type: '',
      trade_region: '',
      goods_description: ''
    });
    setCreateError(null);
    setActiveFormTab('basic');
  };

  const handleCreateCustomer = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!createForm.company_name.trim()) {
      setCreateError('Company Name is required.');
      return;
    }
    try {
      setCreatingLoading(true);
      setCreateError(null);
      
      const payload: Record<string, any> = {};
      Object.entries(createForm).forEach(([key, val]) => {
        if (val && val.trim() !== '') {
          payload[key] = val.trim();
        }
      });

      const res = await api.post('/api/v1/customers', payload);
      showToast('success', 'Customer Added', `Customer ${res.data.company_name} was created successfully.`);
      setIsCreatingCustomer(false);
      resetCreateForm();
      fetchStats();
      fetchCustomers();
    } catch (err: any) {
      console.error('Failed to create customer', err);
      setCreateError(err.response?.data?.detail || 'Failed to add customer. Please verify input data.');
    } finally {
      setCreatingLoading(false);
    }
  };

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
  const confirmDeleteSingle = async () => {
    if (!deletingCustomerId) return;
    try {
      setIsDeletingLoading(true);
      await api.delete(`/api/v1/customers/${deletingCustomerId}`);
      showToast('success', 'Customer Deleted', `Successfully deleted ${deletingCustomerName}.`);
      fetchCustomers();
      fetchStats();
      fetchFilters();
      if (selectedCustomer?.id === deletingCustomerId) {
        setDrawerOpen(false);
      }
    } catch {
      showToast('danger', 'Deletion Failed', 'Could not delete the customer record.');
    } finally {
      setIsDeletingLoading(false);
      setDeleteModalOpen(false);
      setDeletingCustomerId(null);
    }
  };

  // Actions: Bulk Delete
  const confirmBulkDelete = async () => {
    if (selectedIds.length === 0) return;
    try {
      setIsBulkDeletingLoading(true);
      await api.post('/api/v1/customers/bulk-delete', { ids: selectedIds });
      showToast('success', 'Customers Deleted', `Successfully deleted ${selectedIds.length} customer records.`);
      setSelectedIds([]);
      fetchCustomers();
      fetchStats();
      fetchFilters();
    } catch {
      showToast('danger', 'Bulk Deletion Failed', 'Could not delete the selected customer records.');
    } finally {
      setIsBulkDeletingLoading(false);
      setBulkDeleteModalOpen(false);
    }
  };

  // Actions: Details Drawer
  const handleOpenDrawer = async (customer: Customer) => {
    setDrawerOpen(true);
    setLoadingDetails(true);
    setIsEditing(false);
    setSelectedCustomer(null);
    setActiveTab('overview');
    setJourneyTimeline([]);
    setExpandedEvents({});
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
      
      // Fetch Journey
      setLoadingJourney(true);
      const journeyRes = await api.get(`/api/v1/customers/${customer.id}/journey`);
      setJourneyTimeline(journeyRes.data.timeline || []);
    } catch {
      console.error('Failed to fetch customer detail details or journey');
    } finally {
      setLoadingDetails(false);
      setLoadingJourney(false);
    }
  };

  // Actions: Edit Form Save
  const handleSaveEdit = async () => {
    if (!selectedCustomer) return;
    if (!editForm.company_name.trim()) {
      showToast('danger', 'Validation Error', 'Company Name is required.');
      return;
    }
    setSavingEdit(true);
    try {
      const res = await api.put(`/api/v1/customers/${selectedCustomer.id}`, editForm);
      setSelectedCustomer(prev => prev ? { ...prev, ...res.data } : null);
      setIsEditing(false);
      showToast('success', 'Changes Saved', 'Customer details updated successfully.');
      fetchCustomers();
      fetchStats();
    } catch {
      showToast('danger', 'Save Failed', 'Failed to save modifications.');
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

  const getStatusBadge = (status: string, isSuppressed?: boolean) => {
    if (isSuppressed || status === 'hard_bounce' || status === 'HARD_BOUNCE') {
      return <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-[10px] font-bold bg-rose-500/10 text-rose-600 border border-rose-500/20 font-mono">🔴 HARD BOUNCE</span>;
    }
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
      {alertInfo && (
        <div className="fixed top-4 right-4 z-[60] w-full max-w-md animate-in fade-in slide-in-from-top-4 duration-200">
          <Alert 
            variant={alertInfo.variant} 
            title={alertInfo.title} 
            description={alertInfo.message} 
            onClose={() => setAlertInfo(null)} 
          />
        </div>
      )}
      {!drawerOpen ? (
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
          <div className="flex items-center gap-3 select-none">
            <button
              onClick={() => { resetCreateForm(); setIsCreatingCustomer(true); }}
              className="h-10 px-5 bg-bg-surface border border-border-color hover:bg-bg-secondary text-text-primary rounded-lg text-sm font-semibold flex items-center gap-2 shadow-xs transition-all cursor-pointer"
            >
              <Users className="w-4 h-4 text-brand-primary" />
              <span>Add Customer</span>
            </button>
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
              onClick={() => setBulkDeleteModalOpen(true)}
              className="flex items-center gap-1 bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition-all"
            >
              <Trash2 className="w-3.5 h-3.5" />
              <span>Delete Selected ({selectedIds.length})</span>
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
                      <td className="p-4">{getStatusBadge(c.status, c.is_suppressed)}</td>
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
                            onClick={() => {
                              setDeletingCustomerId(c.id);
                              setDeletingCustomerName(c.company_name);
                              setDeleteModalOpen(true);
                            }}
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
      ) : (
        <div className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6 sm:space-y-8 select-text">
          {/* Breadcrumb */}
          <div className="flex items-center space-x-2 text-xs font-semibold text-text-secondary select-none">
            <button 
              onClick={() => setDrawerOpen(false)} 
              className="hover:text-brand-primary cursor-pointer bg-transparent border-0 font-bold"
            >
              Customers
            </button>
            <span className="text-text-muted">/</span>
            <span className="text-text-primary font-bold">
              {selectedCustomer?.company_name || 'Loading Profile...'}
            </span>
          </div>

          {loadingDetails ? (
            <div className="flex flex-col items-center justify-center py-20 space-y-3">
              <Loader2 className="w-8 h-8 animate-spin text-brand-primary" />
              <span className="text-xs font-semibold text-text-muted">Loading workspace details...</span>
            </div>
          ) : selectedCustomer ? (
            <>
              {/* Customer Header */}
              <div className="bg-bg-surface p-5 sm:p-6 rounded-xl border border-border-color shadow-sm space-y-4">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block">Customer Workspace</span>
                    <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
                      {selectedCustomer.company_name}
                    </h1>
                    <p className="text-xs sm:text-sm text-text-secondary font-medium font-mono">
                      {selectedCustomer.contact_email} • {selectedCustomer.contact_name}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-xs font-semibold text-text-secondary">
                      <span className="text-text-muted mr-1.5 font-bold uppercase tracking-wider text-[10px]">Sequence:</span>
                      {getStatusBadge(selectedCustomer.status)}
                    </div>
                    <div className="text-xs font-semibold text-text-secondary">
                      <span className="text-text-muted mr-1.5 font-bold uppercase tracking-wider text-[10px]">Readiness:</span>
                      {getReadinessBadge(selectedCustomer.engagement_readiness)}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-border-color/60 text-xs font-semibold text-text-secondary">
                  <div>
                    <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Industry</span>
                    <span className="text-text-primary">{selectedCustomer.industry || '—'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Country</span>
                    <span className="text-text-primary">{selectedCustomer.country || '—'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Last Activity</span>
                    <span className="text-text-primary font-mono">{selectedCustomer.last_email || 'Never contacted'}</span>
                  </div>
                  <div>
                    <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider block">Import Reference</span>
                    <span className="text-text-primary truncate block max-w-[200px]" title={selectedCustomer.import_batch_name || 'Manual Import'}>
                      {selectedCustomer.import_batch_name || 'Manual Import'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Workspace Content Tabs */}
              <div className="space-y-6">
                {/* Tabs */}
                <div className="flex border-b border-border-color pb-1 gap-6 text-sm font-bold text-text-muted select-none">
                  <button 
                    onClick={() => setActiveTab('overview')}
                    className={`pb-2 border-b-2 px-1 transition-all cursor-pointer bg-transparent border-0 ${activeTab === 'overview' ? 'border-brand-primary text-brand-primary font-bold' : 'border-transparent hover:text-text-primary'}`}
                  >
                    Overview
                  </button>
                  <button 
                    onClick={() => setActiveTab('journey')}
                    className={`pb-2 border-b-2 px-1 transition-all cursor-pointer bg-transparent border-0 ${activeTab === 'journey' ? 'border-brand-primary text-brand-primary font-bold' : 'border-transparent hover:text-text-primary'}`}
                  >
                    AI Journey
                  </button>
                </div>

                {/* Tab content view */}
                {activeTab === 'overview' && (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Left details pane (2/3 width) */}
                    <div className="lg:col-span-2 space-y-6">
                      <div className="bg-bg-surface p-5 sm:p-6 rounded-xl border border-border-color shadow-sm space-y-4">
                        <div className="flex justify-between items-center pb-2 border-b border-border-color/60">
                          <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Properties</h4>
                          {!isEditing ? (
                            <button
                              onClick={() => setIsEditing(true)}
                              className="text-[10px] font-bold text-brand-primary hover:text-brand-primary-hover flex items-center gap-1 cursor-pointer bg-transparent border-0"
                            >
                              <Edit2 className="w-3.5 h-3.5" />
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

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                          {selectedCustomer.is_suppressed && (
                            <div className="col-span-1 sm:col-span-2 p-4 bg-rose-50 border border-rose-200 rounded-xl space-y-1.5">
                              <div className="flex items-center space-x-2 text-rose-700 font-bold text-xs">
                                <AlertCircle className="w-4 h-4 text-rose-600" />
                                <span>🔴 Hard Bounce / Suppressed</span>
                              </div>
                              {selectedCustomer.bounce_reason && (
                                <p className="text-xs text-rose-900 font-mono">
                                  <span className="font-bold">Reason:</span> {selectedCustomer.bounce_reason}
                                </p>
                              )}
                              {selectedCustomer.suppressed_at && (
                                <p className="text-[11px] text-rose-700 font-mono">
                                  <span className="font-bold">Suppressed:</span> {new Date(selectedCustomer.suppressed_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
                                </p>
                              )}
                            </div>
                          )}
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
                              {cleanDisplayValue(selectedCustomer.segment)}
                            </p>
                          </div>

                          {/* Designation */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Designation</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                              {cleanDisplayValue(selectedCustomer.designation)}
                            </p>
                          </div>

                          {/* Phone */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Phone</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                              {cleanDisplayValue(selectedCustomer.phone)}
                            </p>
                          </div>

                          {/* Website */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Website</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                              {isValidWebsite(selectedCustomer.website) ? (
                                <a 
                                  href={selectedCustomer.website!.trim().startsWith('http') ? selectedCustomer.website!.trim() : `https://${selectedCustomer.website!.trim()}`} 
                                  target="_blank" 
                                  rel="noreferrer" 
                                  className="text-brand-primary hover:underline"
                                >
                                  {selectedCustomer.website!.trim()}
                                </a>
                              ) : '—'}
                            </p>
                          </div>

                          {/* LinkedIn */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">LinkedIn</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                              {isValidLinkedin(selectedCustomer.linkedin) ? (
                                <a 
                                  href={selectedCustomer.linkedin!.trim().startsWith('http') ? selectedCustomer.linkedin!.trim() : `https://${selectedCustomer.linkedin!.trim()}`} 
                                  target="_blank" 
                                  rel="noreferrer" 
                                  className="text-brand-primary hover:underline"
                                >
                                  LinkedIn Profile
                                </a>
                              ) : '—'}
                            </p>
                          </div>

                          {/* Address */}
                          <div className="space-y-1 sm:col-span-2">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Full Address</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40">
                              {cleanDisplayValue(selectedCustomer.address) === '—' ? '—' : (
                                <>
                                  {selectedCustomer.address}
                                  {(isValidWebsite(selectedCustomer.city) || isValidWebsite(selectedCustomer.state)) && (
                                    <span className="block text-text-secondary mt-1 font-medium">
                                      {isValidWebsite(selectedCustomer.city) && `${selectedCustomer.city}, `}
                                      {isValidWebsite(selectedCustomer.state) && `${selectedCustomer.state}`}
                                    </span>
                                  )}
                                </>
                              )}
                            </p>
                          </div>

                          {/* Trade Region & Customer Type */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Trade Region / Market</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 uppercase">
                              {cleanDisplayValue(selectedCustomer.trade_region)}
                            </p>
                          </div>

                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Customer Type</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 uppercase">
                              {cleanDisplayValue(selectedCustomer.customer_type)}
                            </p>
                          </div>

                          {/* Logistics Segment Details */}
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Shipment Mode</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 uppercase">
                              {cleanDisplayValue(selectedCustomer.shipment_mode)}
                            </p>
                          </div>

                          <div className="space-y-1">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Trade Direction</label>
                            <p className="text-xs font-semibold text-text-primary bg-bg-secondary p-2.5 rounded-lg border border-border-color/40 uppercase">
                              {cleanDisplayValue(selectedCustomer.trade_direction)}
                            </p>
                          </div>

                          {/* Raw Fields & Audit Logs */}
                          <div className="space-y-1 sm:col-span-2">
                            <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Original Information</label>
                            <div className="text-xs font-medium text-text-secondary bg-bg-secondary p-3 rounded-lg border border-border-color/40 space-y-1.5 font-mono">
                              <div><span className="font-bold text-text-muted text-[10px] uppercase mr-2">Original Company Name:</span> {cleanDisplayValue(selectedCustomer.raw_company_name)}</div>
                              <div><span className="font-bold text-text-muted text-[10px] uppercase mr-2">Original Contact Details:</span> {cleanDisplayValue(selectedCustomer.raw_contact_name)}</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right widgets (1/3 width) */}
                    <div className="space-y-6">
                      <div className="bg-bg-surface p-5 rounded-xl border border-border-color shadow-sm space-y-4">
                        <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider border-b border-border-color pb-2">Workflow diagnostics</h4>
                        <div className="grid grid-cols-2 gap-4 text-xs">
                          <div>
                            <span className="text-[9px] font-bold text-text-muted uppercase block">Last Contact</span>
                            <span className="font-semibold text-text-primary font-mono">{selectedCustomer.last_email || 'Never'}</span>
                          </div>
                          <div>
                            <span className="text-[9px] font-bold text-text-muted uppercase block">Total Emails</span>
                            <span className="font-bold text-brand-primary font-mono">{selectedCustomer.total_emails_sent}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {activeTab === 'journey' && (
                  <div className="max-w-5xl bg-bg-surface p-6 sm:p-8 rounded-xl border border-border-color shadow-sm">
                    {loadingJourney ? (
                      <div className="space-y-4">
                        {[1, 2, 3].map((n) => (
                          <div key={n} className="animate-pulse flex space-x-3 items-start py-2">
                            <div className="rounded-full bg-slate-200 h-8 w-8" />
                            <div className="flex-1 space-y-2 py-1">
                              <div className="h-2.5 bg-slate-200 rounded w-1/4" />
                              <div className="h-2 bg-slate-200 rounded w-3/4" />
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : journeyTimeline.length === 0 ? (
                      <div className="text-center py-10 bg-bg-secondary/20 border border-border-color rounded-xl">
                        <p className="text-xs text-text-muted italic">Customer imported. No engagement started yet.</p>
                      </div>
                    ) : (
                      <div className="relative border-l border-border-color/80 ml-3.5 pl-6 space-y-6">
                        {journeyTimeline.map((evt, idx) => {
                          const isExpanded = expandedEvents[evt.id] || false;
                          
                          // Determine wait days
                          const nextEvt = journeyTimeline[idx + 1];
                          let waitDays = 0;
                          if (nextEvt) {
                            const diffTime = Math.abs(new Date(nextEvt.timestamp).getTime() - new Date(evt.timestamp).getTime());
                            waitDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                          }

                          return (
                            <div key={evt.id} className="relative">
                              {/* Bullet node */}
                              <span className={`absolute -left-[30px] top-1.5 flex items-center justify-center w-6 h-6 rounded-full border shadow-xs ${getEventColorClasses(evt.color || 'slate')}`}>
                                {getEventIcon(evt.event_type)}
                              </span>

                              {/* Card */}
                              <div 
                                onClick={() => evt.expandable && setExpandedEvents(prev => ({ ...prev, [evt.id]: !isExpanded }))}
                                className={`rounded-xl p-5 space-y-3 shadow-2xs border transition-all ${
                                  evt.expandable ? 'cursor-pointer hover:border-border-color/80' : ''
                                } ${
                                  evt.event_type === 'reply_received' 
                                    ? 'bg-emerald-500/5 border-emerald-500/30 ring-1 ring-emerald-500/20' 
                                    : 'bg-bg-surface border-border-color'
                                }`}
                              >
                                <div className="flex items-start justify-between gap-4">
                                  <div className="space-y-1">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="text-[9px] font-bold text-text-muted uppercase tracking-wider bg-bg-secondary px-2 py-0.5 rounded border border-border-color">
                                        {evt.module}
                                      </span>
                                      <span className="text-sm font-bold text-text-primary">
                                        {evt.title}
                                      </span>
                                    </div>
                                    {evt.subtitle && (
                                      <p className="text-2xs text-text-secondary font-semibold max-w-lg">
                                        {evt.subtitle}
                                      </p>
                                    )}
                                  </div>
                                  <span className="text-[10px] font-bold text-text-muted font-mono shrink-0">
                                    {new Date(evt.timestamp).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })}
                                  </span>
                                </div>

                                <p className="text-xs text-text-secondary leading-relaxed font-medium">
                                  {evt.description}
                                </p>

                                {evt.expandable && (
                                  <>
                                    <button
                                      onClick={(e) => { e.stopPropagation(); setExpandedEvents(prev => ({ ...prev, [evt.id]: !isExpanded })) }}
                                      className="text-[10px] font-bold text-brand-primary hover:text-brand-primary-hover flex items-center gap-1 bg-transparent border-0 cursor-pointer p-0"
                                    >
                                      <span>{isExpanded ? 'Collapse Details' : 'Inspect Details'}</span>
                                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                                    </button>

                                    {isExpanded && evt.mail && (
                                      <div 
                                        onClick={(e) => e.stopPropagation()}
                                        className="mt-3 p-4 bg-bg-secondary/40 border border-border-color rounded-xl space-y-3 text-[11px] select-text cursor-default"
                                      >
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-2xs border-b border-border-color/40 pb-2 mb-2">
                                          <div><span className="text-text-muted">Sender Name:</span> <strong className="text-text-primary">{evt.mail.sender}</strong></div>
                                          <div><span className="text-text-muted">Recipient:</span> <strong className="text-text-primary">{evt.mail.recipient}</strong></div>
                                          <div><span className="text-text-muted">Subject:</span> <strong className="text-text-primary">{evt.mail.subject}</strong></div>
                                          <div><span className="text-text-muted">Communication Type:</span> <strong className="text-text-primary">{evt.mail.email_type || evt.event_type}</strong></div>
                                          {evt.step_number && <div><span className="text-text-muted">Sequence Step:</span> <strong className="text-text-primary">Step {evt.step_number}</strong></div>}
                                          <div><span className="text-text-muted">Sent Time:</span> <strong className="text-text-primary">{new Date(evt.timestamp).toLocaleString()}</strong></div>
                                          <div><span className="text-text-muted">Email Status:</span> <strong className="text-text-primary uppercase">{evt.mail.delivery_status || 'completed'}</strong></div>
                                        </div>
                                        <div className="whitespace-pre-wrap text-text-secondary leading-relaxed font-sans max-h-[300px] overflow-y-auto pr-1 text-2xs">
                                          {stripHtmlToPlainText(evt.mail.body)}
                                        </div>
                                        
                                        {evt.attachments && evt.attachments.length > 0 && (
                                          <div className="pt-2 border-t border-border-color/30 flex items-center gap-1.5 flex-wrap">
                                            {evt.attachments.map((attName: string, aIdx: number) => (
                                              <div 
                                                key={aIdx} 
                                                onClick={(e) => e.stopPropagation()}
                                                className="flex items-center space-x-1.5 text-text-muted bg-white border border-border-color px-2.5 py-1 rounded-lg shadow-2xs cursor-default"
                                              >
                                                <FileText className="w-3.5 h-3.5 text-slate-400" />
                                                <span className="font-semibold">{attName}</span>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>

                              {/* WAIT Connector Line */}
                              {waitDays > 0 && (
                                <div className="py-3 my-2 text-center select-none relative">
                                  <div className="absolute inset-0 flex items-center" aria-hidden="true">
                                    <div className="w-full border-t border-dashed border-border-color/85" />
                                  </div>
                                  <span className="relative inline-flex items-center px-4 py-1.5 bg-white border border-border-color rounded-full text-[9px] font-bold text-brand-primary tracking-widest uppercase shadow-2xs">
                                    WAIT {waitDays} {waitDays === 1 ? 'DAY' : 'DAYS'}
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-20 text-center space-y-2">
              <AlertCircle className="w-8 h-8 text-rose-500" />
              <span className="text-xs font-semibold text-text-muted">Error loading customer details.</span>
            </div>
          )}
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

      {/* Destructive Confirmations */}
      <ConfirmationModal
        isOpen={deleteModalOpen}
        onClose={() => setDeleteModalOpen(false)}
        onConfirm={confirmDeleteSingle}
        title="Delete Customer"
        message={`This action cannot be undone. Are you sure you want to delete ${deletingCustomerName}?`}
        confirmText="Delete Customer"
        isLoading={isDeletingLoading}
        variant="destructive"
      />

      <ConfirmationModal
        isOpen={bulkDeleteModalOpen}
        onClose={() => setBulkDeleteModalOpen(false)}
        onConfirm={confirmBulkDelete}
        title={`Delete ${selectedIds.length} Customers`}
        message={`This action cannot be undone. Are you sure you want to delete ${selectedIds.length} selected customer records?`}
        confirmText={`Delete ${selectedIds.length} Customers`}
        isLoading={isBulkDeletingLoading}
        variant="destructive"
      />

      {/* Add Customer Modal */}
      {isCreatingCustomer && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/45 backdrop-blur-xs select-none">
          <div className="bg-bg-surface border border-border-color rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col animate-scale-up">
            {/* Header */}
            <div className="p-5 border-b border-border-color flex justify-between items-center bg-bg-surface">
              <div>
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Add New Customer</h3>
                <p className="text-[10px] text-text-muted mt-0.5">Manually create a new customer or lead profile record.</p>
              </div>
              <button
                onClick={() => { setIsCreatingCustomer(false); resetCreateForm(); }}
                disabled={creatingLoading}
                className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Error Message */}
            {createError && (
              <div className="px-5 pt-4">
                <div className="flex gap-2.5 p-3 rounded-lg border border-rose-100 bg-rose-50 text-xs font-semibold text-rose-600 leading-relaxed">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{createError}</span>
                </div>
              </div>
            )}

            {/* Tabs */}
            <div className="px-5 pt-3 flex gap-2 border-b border-border-color/60 bg-bg-surface select-none">
              <button
                onClick={() => setActiveFormTab('basic')}
                className={`pb-2 px-1 text-xs font-bold border-b-2 transition-all cursor-pointer ${
                  activeFormTab === 'basic' 
                    ? 'border-brand-primary text-brand-primary' 
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                Basic Information
              </button>
              <button
                onClick={() => setActiveFormTab('professional')}
                className={`pb-2 px-1 text-xs font-bold border-b-2 transition-all cursor-pointer ${
                  activeFormTab === 'professional' 
                    ? 'border-brand-primary text-brand-primary' 
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                Professional Info
              </button>
              <button
                onClick={() => setActiveFormTab('logistics')}
                className={`pb-2 px-1 text-xs font-bold border-b-2 transition-all cursor-pointer ${
                  activeFormTab === 'logistics' 
                    ? 'border-brand-primary text-brand-primary' 
                    : 'border-transparent text-text-muted hover:text-text-primary'
                }`}
              >
                Logistics Parameters
              </button>
            </div>

            {/* Form Fields Body */}
            <form onSubmit={handleCreateCustomer} className="flex-1 overflow-y-auto max-h-[50vh] p-5 space-y-4">
              {activeFormTab === 'basic' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1 sm:col-span-2">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Company Name <span className="text-rose-500 font-bold">*</span></label>
                    <input
                      type="text"
                      required
                      placeholder="E.g., Apex Logistics Ltd"
                      value={createForm.company_name}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, company_name: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Contact Name</label>
                    <input
                      type="text"
                      placeholder="E.g., John Doe"
                      value={createForm.contact_name}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, contact_name: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Contact Email</label>
                    <input
                      type="email"
                      placeholder="E.g., john@apexlogistics.com"
                      value={createForm.contact_email}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, contact_email: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Industry</label>
                    <input
                      type="text"
                      placeholder="E.g., Electronics, Textiles"
                      value={createForm.industry}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, industry: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Country</label>
                    <input
                      type="text"
                      placeholder="E.g., China, Germany"
                      value={createForm.country}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, country: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>
                </div>
              )}

              {activeFormTab === 'professional' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Designation</label>
                    <input
                      type="text"
                      placeholder="E.g., Procurement Manager"
                      value={createForm.designation}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, designation: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Phone</label>
                    <input
                      type="text"
                      placeholder="E.g., +919818299901"
                      value={createForm.phone}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, phone: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Website</label>
                    <input
                      type="text"
                      placeholder="E.g., www.apexlogistics.com"
                      value={createForm.website}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, website: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">LinkedIn URL</label>
                    <input
                      type="text"
                      placeholder="E.g., linkedin.com/company/apex"
                      value={createForm.linkedin}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, linkedin: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>
                </div>
              )}

              {activeFormTab === 'logistics' && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1 sm:col-span-2">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Street Address</label>
                    <input
                      type="text"
                      placeholder="E.g., 42 Business Hub Marg"
                      value={createForm.address}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, address: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">City</label>
                    <input
                      type="text"
                      placeholder="E.g., New Delhi"
                      value={createForm.city}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, city: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">State</label>
                    <input
                      type="text"
                      placeholder="E.g., Delhi"
                      value={createForm.state}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, state: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Shipment Mode</label>
                    <select
                      value={createForm.shipment_mode}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, shipment_mode: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    >
                      <option value="">Select Mode...</option>
                      <option value="air">Air</option>
                      <option value="sea">Sea</option>
                      <option value="road">Road</option>
                      <option value="rail">Rail</option>
                      <option value="multi">Multi</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Trade Direction</label>
                    <select
                      value={createForm.trade_direction}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, trade_direction: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    >
                      <option value="">Select Direction...</option>
                      <option value="import">Import</option>
                      <option value="export">Export</option>
                      <option value="both">Both</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Customer Type</label>
                    <input
                      type="text"
                      placeholder="E.g., Manufacturer, Trader"
                      value={createForm.customer_type}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, customer_type: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">Goods Description</label>
                    <input
                      type="text"
                      placeholder="E.g., Machinery, Auto Parts"
                      value={createForm.goods_description}
                      onChange={(e) => setCreateForm(prev => ({ ...prev, goods_description: e.target.value }))}
                      className="w-full p-2 border border-border-color rounded-lg text-xs bg-bg-secondary focus:outline-none focus:ring-1 focus:ring-brand-primary font-semibold text-text-primary"
                    />
                  </div>
                </div>
              )}

              {/* Action Buttons Footer */}
              <div className="pt-4 border-t border-border-color flex justify-end gap-3 select-none">
                <button
                  type="button"
                  onClick={() => { setIsCreatingCustomer(false); resetCreateForm(); }}
                  disabled={creatingLoading}
                  className="px-4 py-2 border border-border-color bg-bg-surface text-text-secondary hover:bg-bg-secondary text-xs font-semibold rounded-xl transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingLoading}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-xl transition-all shadow-xs flex items-center justify-center gap-1.5 cursor-pointer border-0"
                >
                  {creatingLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Add Lead</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </AppShell>
  );
}
