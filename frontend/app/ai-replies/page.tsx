'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/use-auth';
import { useTenantStore } from '../../store/tenant-store';
import { api } from '../../lib/api';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { Card, MetricCard } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Badge, Skeleton, EmptyState } from '../../components/ui/feedback';
import { 
  Clock, 
  Sparkles, 
  Send, 
  AlertTriangle, 
  Search, 
  RefreshCw, 
  X,
  Calendar,
  Building,
  Mail,
  User,
  Users
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';

interface ReplyDashboardKPIs {
  waiting_for_reply: number;
  ai_preparing_reply: number;
  replies_sent_today: number;
  needs_attention: number;
}

interface ReplyItem {
  reply_id: string;
  delivery_status: string;
  customer_name: string;
  company_name: string | null;
  subject: string;
  received_at: string;
  thread_id: string;
  graph_message_id: string | null;
  reply_time: string | null;
}

interface ReplyDetail {
  reply_id: string;
  customer_name: string;
  company_name: string | null;
  customer_email: string;
  subject: string;
  received_at: string;
  original_body: string;
  final_sent: string | null;
  final_sent_html: string | null;
  recipients: {
    to: string[];
    cc: string[];
    bcc: string[];
  };
  timeline: Array<{ stage: string; timestamp: string }>;
}

export default function AICustomerRepliesPage() {
  const { isLoading, isTenantInitialized } = useAuth();
  const { branding } = useTenantStore();

  const [kpis, setKpis] = useState<ReplyDashboardKPIs | null>(null);
  const [items, setItems] = useState<ReplyItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters and Search
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');

  // Selected Detail
  const [selectedReplyId, setSelectedReplyId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ReplyDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [showHtml, setShowHtml] = useState(false);

  const fetchDashboardData = async () => {
    try {
      setError(null);
      const resKpis = await api.get('/api/v1/ai-reply/dashboard');
      setKpis(resKpis.data);
    } catch (err: any) {
      console.error('Failed to fetch dashboard KPIs', err);
      setError('Could not retrieve statistics.');
    }
  };

  const fetchList = async (search = '', status = 'all') => {
    try {
      setLoading(true);
      setError(null);
      const params: any = {};
      if (search) params.search = search;
      if (status !== 'all') params.status = status;
      
      const resList = await api.get('/api/v1/ai-reply/list', { params });
      setItems(resList.data);
    } catch (err: any) {
      console.error('Failed to fetch reply list', err);
      setError('Could not retrieve replies queue.');
    } finally {
      setLoading(false);
    }
  };

  const fetchDetail = async (id: string) => {
    try {
      setLoadingDetail(true);
      const resDetail = await api.get(`/api/v1/ai-reply/${id}`);
      setDetail(resDetail.data);
    } catch (err) {
      console.error('Failed to fetch reply details', err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleRefreshAll = () => {
    fetchDashboardData();
    fetchList(searchTerm, selectedStatus);
  };

  // Auto-refresh every 30 seconds
  useEffect(() => {
    if (isTenantInitialized) {
      fetchDashboardData();
      fetchList(searchTerm, selectedStatus);

      const interval = setInterval(() => {
        fetchDashboardData();
        // Silent refresh of list in background
        api.get('/api/v1/ai-reply/list', {
          params: {
            ...(searchTerm ? { search: searchTerm } : {}),
            ...(selectedStatus !== 'all' ? { status: selectedStatus } : {})
          }
        }).then(res => setItems(res.data)).catch(err => console.error(err));
      }, 30000);

      return () => clearInterval(interval);
    }
  }, [isTenantInitialized, searchTerm, selectedStatus]);

  // Fetch details when drawer is opened
  useEffect(() => {
    setShowHtml(false);
    if (selectedReplyId) {
      fetchDetail(selectedReplyId);
    } else {
      setDetail(null);
    }
  }, [selectedReplyId]);

  const getStatusBadgeVariant = (statusStr: string) => {
    switch (statusStr) {
      case 'delivered': return 'warning'; // Waiting for Reply
      case 'queued': return 'primary'; // AI Preparing Reply
      case 'sent': return 'success'; // Reply Sent
      case 'failed': return 'danger'; // Needs Attention
      default: return 'neutral';
    }
  };

  const getStatusText = (statusStr: string) => {
    switch (statusStr) {
      case 'delivered': return 'Waiting for Reply';
      case 'queued': return 'AI Preparing Reply';
      case 'sent': return 'Reply Sent';
      case 'failed': return 'Needs Attention';
      default: return statusStr;
    }
  };

  const formatDate = (isoStr: string | null) => {
    if (!isoStr) return '-';
    const date = new Date(isoStr);
    return date.toLocaleDateString(undefined, { 
      month: 'short', 
      day: 'numeric', 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  if (isLoading || !isTenantInitialized) {
    return (
      <AppShell>
        <PageWrapper>
          <div className="p-8 space-y-6">
            <Skeleton variant="text" className="h-8 w-1/4" />
            <Skeleton variant="text" className="h-4 w-1/3" />
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-8">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} variant="rect" className="h-28" />)}
            </div>
            <Skeleton variant="rect" className="h-96 mt-8" />
          </div>
        </PageWrapper>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageWrapper>
        <div className="px-4 py-6 sm:px-6 lg:px-8 space-y-6">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
                AI Customer Replies
              </h1>
              <p className="text-xs sm:text-sm text-text-muted mt-1">
                Monitor AI-prepared customer replies and email delivery.
              </p>
            </div>
            
            <div className="flex items-center gap-2 self-start sm:self-center">
              <span className="text-[10px] text-text-muted hidden md:inline">
                Automatically checks for new customer replies.
              </span>
              <Button 
                variant="secondary" 
                size="sm" 
                leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                onClick={handleRefreshAll}
              >
                Check for New Replies
              </Button>
            </div>
          </div>

          {/* KPI Dashboard Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              title="Waiting for Reply"
              value={kpis ? kpis.waiting_for_reply : '...'}
              icon={<Clock className="w-4 h-4 text-status-warning" />}
            />
            <MetricCard
              title="AI Preparing Reply"
              value={kpis ? kpis.ai_preparing_reply : '...'}
              icon={<Sparkles className="w-4 h-4 text-brand-primary" />}
            />
            <MetricCard
              title="Replies Sent Today"
              value={kpis ? kpis.replies_sent_today : '...'}
              icon={<Send className="w-4 h-4 text-status-success" />}
            />
            <MetricCard
              title="Needs Attention"
              value={kpis ? kpis.needs_attention : '...'}
              icon={<AlertTriangle className="w-4 h-4 text-status-danger" />}
            />
          </div>

          {/* Table Filters & Search */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-bg-surface p-4 rounded-xl border border-border-color shadow-xs">
            <div className="relative flex-1 max-w-md w-full">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-text-muted" />
              <Input
                type="text"
                placeholder="Search customer, company or subject..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 text-xs"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-text-muted whitespace-nowrap">Current Status:</span>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="rounded-lg border border-border-color bg-bg-surface px-3 py-1.5 text-xs font-bold text-text-secondary focus:border-brand-primary focus:outline-none"
              >
                <option value="all">All</option>
                <option value="Waiting for Reply">Waiting for Reply</option>
                <option value="AI Preparing Reply">AI Preparing Reply</option>
                <option value="Reply Sent">Reply Sent</option>
                <option value="Needs Attention">Needs Attention</option>
              </select>
            </div>
          </div>

          {/* Error Message */}
          {error && (
            <Card className="border-status-danger/20 bg-status-danger-bg/50 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-5 h-5 text-status-danger" />
                <span className="text-xs font-semibold text-red-950">{error}</span>
              </div>
              <Button variant="danger" size="sm" onClick={handleRefreshAll}>Try Again</Button>
            </Card>
          )}

          {/* Main Table Queue */}
          <Card padding="none" className="overflow-hidden border border-border-color">
            <div className="overflow-x-auto min-h-[250px]">
              {loading ? (
                <div className="p-6 space-y-4">
                  {[1, 2, 3, 4].map(i => <Skeleton key={i} variant="text" className="h-6" />)}
                </div>
              ) : items.length === 0 ? (
                <div className="py-12">
                  <EmptyState
                    title="No customer replies need attention right now."
                    description="Everything is up to date."
                  />
                </div>
              ) : (
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-bg-secondary text-text-muted uppercase font-bold border-b border-border-color tracking-[0.06em]">
                      <th className="px-6 py-4">Current Status</th>
                      <th className="px-6 py-4">Customer</th>
                      <th className="px-6 py-4">Company</th>
                      <th className="px-6 py-4">Subject</th>
                      <th className="px-6 py-4">Received</th>
                      <th className="px-6 py-4">Reply Time</th>
                      <th className="px-6 py-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-color bg-bg-surface">
                    {items.map((item) => (
                      <tr key={item.reply_id} className="hover:bg-bg-secondary/40 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <Badge variant={getStatusBadgeVariant(item.delivery_status)}>
                            {getStatusText(item.delivery_status)}
                          </Badge>
                        </td>
                        <td className="px-6 py-4 font-semibold text-text-primary whitespace-nowrap">
                          {item.customer_name}
                        </td>
                        <td className="px-6 py-4 text-text-secondary whitespace-nowrap">
                          {item.company_name || '-'}
                        </td>
                        <td className="px-6 py-4 text-text-secondary font-medium max-w-xs truncate">
                          {item.subject}
                        </td>
                        <td className="px-6 py-4 text-text-muted whitespace-nowrap">
                          {formatDate(item.received_at)}
                        </td>
                        <td className="px-6 py-4 text-text-muted whitespace-nowrap">
                          {formatDate(item.reply_time)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-right">
                          <Button 
                            variant="secondary" 
                            size="sm" 
                            onClick={() => setSelectedReplyId(item.reply_id)}
                          >
                            Open
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </Card>
        </div>

        {/* Reply Details Right Drawer Overlay */}
        <AnimatePresence>
          {selectedReplyId && (
            <>
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 0.4 }}
                exit={{ opacity: 0 }}
                onClick={() => setSelectedReplyId(null)}
                className="fixed inset-0 bg-black z-45"
              />
              
              {/* Drawer Container */}
              <motion.div
                initial={{ x: '100%' }}
                animate={{ x: 0 }}
                exit={{ x: '100%' }}
                transition={{ type: 'spring', damping: 25, stiffness: 200 }}
                className="fixed top-0 right-0 bottom-0 w-full sm:w-[40%] bg-bg-surface border-l border-border-color shadow-2xl z-50 flex flex-col h-screen select-none overflow-hidden"
              >
                {/* Drawer Header */}
                <div className="p-5 border-b border-border-color flex items-center justify-between bg-bg-secondary shrink-0">
                  <div>
                    <h3 className="text-sm font-bold text-text-primary">Customer Reply Details</h3>
                    <p className="text-[10px] text-text-muted mt-0.5">Auditing conversation delivery log</p>
                  </div>
                  <button 
                    onClick={() => setSelectedReplyId(null)}
                    className="p-1.5 hover:bg-black/5 rounded-lg text-text-muted hover:text-text-primary transition-colors cursor-pointer"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>

                {/* Drawer Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                  {loadingDetail ? (
                    <div className="space-y-4">
                      <Skeleton variant="text" className="h-4 w-1/3" />
                      <Skeleton variant="rect" className="h-24" />
                      <Skeleton variant="rect" className="h-48" />
                    </div>
                  ) : detail ? (
                    <>
                      {/* Section 1: Customer Information */}
                      <div className="space-y-2.5">
                        <h4 className="text-[10px] uppercase font-bold text-text-muted tracking-wider flex items-center gap-1.5">
                          <User className="w-3.5 h-3.5" /> Customer Information
                        </h4>
                        <Card variant="secondary" padding="sm" className="space-y-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">Name:</span>
                            <span className="font-semibold text-text-primary">{detail.customer_name}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">Company:</span>
                            <span className="font-semibold text-text-primary">{detail.company_name || '-'}</span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">Email:</span>
                            <span className="font-semibold text-text-primary">{detail.customer_email}</span>
                          </div>
                          <div className="border-t border-border-color/30 pt-2 flex justify-between text-xs">
                            <span className="text-text-muted">Subject:</span>
                            <span className="font-semibold text-text-primary text-right max-w-[70%] truncate">{detail.subject}</span>
                          </div>
                        </Card>
                      </div>

                      {/* Section 1.5: Recipients */}
                      <div className="space-y-2.5">
                        <h4 className="text-[10px] uppercase font-bold text-text-muted tracking-wider flex items-center gap-1.5">
                          <Users className="w-3.5 h-3.5" /> Recipients
                        </h4>
                        <Card variant="secondary" padding="sm" className="space-y-2">
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">To:</span>
                            <span className="font-semibold text-text-primary truncate max-w-[80%]">
                              {detail.recipients?.to?.join(', ') || detail.customer_email}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">CC:</span>
                            <span className="font-semibold text-text-primary truncate max-w-[80%]">
                              {detail.recipients?.cc?.join(', ') || '(None)'}
                            </span>
                          </div>
                          <div className="flex justify-between text-xs">
                            <span className="text-text-muted">BCC:</span>
                            <span className="font-semibold text-text-primary truncate max-w-[80%]">
                              {detail.recipients?.bcc?.join(', ') || '(None)'}
                            </span>
                          </div>
                        </Card>
                      </div>

                      {/* Section 2: Customer Message */}
                      <div className="space-y-2">
                        <h4 className="text-[10px] uppercase font-bold text-text-muted tracking-wider flex items-center gap-1.5">
                          <Mail className="w-3.5 h-3.5" /> Customer Message
                        </h4>
                        <div className="border border-border-color rounded-xl p-4 bg-[#F8FAFC] max-h-48 overflow-y-auto text-xs text-text-secondary leading-relaxed font-sans whitespace-pre-wrap">
                          {detail.original_body || '(No content received)'}
                        </div>
                      </div>

                      {/* Section 3: Final Email */}
                      {detail.final_sent && (
                        <div className="space-y-2">
                          <div className="flex items-center justify-between">
                            <h4 className="text-[10px] uppercase font-bold text-text-muted tracking-wider flex items-center gap-1.5">
                              <Send className="w-3.5 h-3.5" /> Final Email
                            </h4>
                            
                            <div className="flex bg-bg-secondary p-0.5 rounded-lg border border-border-color select-none">
                              <button
                                onClick={() => setShowHtml(false)}
                                className={`px-2 py-1 text-[9px] font-bold rounded-md transition-colors ${
                                  !showHtml ? 'bg-bg-surface text-text-primary shadow-xs' : 'text-text-muted hover:text-text-primary'
                                }`}
                              >
                                Plain Text
                              </button>
                              <button
                                onClick={() => setShowHtml(true)}
                                className={`px-2 py-1 text-[9px] font-bold rounded-md transition-colors ${
                                  showHtml ? 'bg-bg-surface text-text-primary shadow-xs' : 'text-text-muted hover:text-text-primary'
                                }`}
                              >
                                Original Layout
                              </button>
                            </div>
                          </div>

                          <div className="border border-border-color rounded-xl p-4 bg-[#F8FAFC] max-h-72 overflow-y-auto text-xs leading-relaxed font-sans overflow-x-hidden">
                            {showHtml && detail.final_sent_html ? (
                              <div 
                                className="prose prose-sm text-text-secondary max-w-none" 
                                dangerouslySetInnerHTML={{ __html: detail.final_sent_html }} 
                              />
                            ) : (
                              <div className="text-text-secondary whitespace-pre-wrap">
                                {detail.final_sent}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Section 4: Activity Timeline */}
                      <div className="space-y-3">
                        <h4 className="text-[10px] uppercase font-bold text-text-muted tracking-wider flex items-center gap-1.5">
                          <Calendar className="w-3.5 h-3.5" /> Activity
                        </h4>
                        <div className="relative pl-6 border-l border-border-color space-y-5 ml-2.5">
                          {detail.timeline.map((step, idx) => (
                            <div key={idx} className="relative">
                              {/* Dot marker */}
                              <div className="absolute -left-[31px] top-1 w-2.5 h-2.5 rounded-full bg-brand-primary border-2 border-bg-surface shadow-xs" />
                              <p className="text-xs font-bold text-text-primary leading-tight">
                                {getStatusText(step.stage) || step.stage}
                              </p>
                              <p className="text-[10px] text-text-muted mt-0.5">
                                {formatDate(step.timestamp)}
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-8 text-xs text-text-muted">
                      Failed to resolve detail parameters.
                    </div>
                  )}
                </div>

                {/* Drawer Footer */}
                <div className="p-4 border-t border-border-color bg-bg-secondary flex justify-end shrink-0">
                  <Button variant="secondary" size="sm" onClick={() => setSelectedReplyId(null)}>
                    Close
                  </Button>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </PageWrapper>
    </AppShell>
  );
}
