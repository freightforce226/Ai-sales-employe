'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/use-auth';
import { useTenantStore } from '../../store/tenant-store';
import { api } from '../../lib/api';
import { AppShell } from '../../components/layout/shell';
import { 
  Mail, 
  LogOut, 
  Users, 
  Send, 
  BarChart3, 
  TrendingUp,
  Bot,
  Layers,
  ChevronRight,
  MessageSquarePlus,
  Sparkles,
  Database
} from 'lucide-react';
import { useRouter } from 'next/navigation';

interface Lead {
  id: string;
  company_name: string;
  contact_name: string | null;
  contact_email: string;
  last_contact: string | null;
  created_at: string | null;
}

interface ActivityItem {
  event: string;
  details: string;
  time: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const { isLoading, isTenantInitialized } = useAuth();
  const { branding } = useTenantStore();
  
  // Real Database States
  const [metrics, setMetrics] = useState<{
    total_contacts: number;
    total_campaigns: number;
    total_emails_sent: number;
    response_rate: string;
  } | null>(null);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [engagement, setEngagement] = useState<any>(null);
  const [loadingMetrics, setLoadingMetrics] = useState(true);
  const [seeding, setSeeding] = useState(false);

  // Outlook OAuth status
  const [outlookStatus, setOutlookStatus] = useState<{ connected: boolean; mailbox_email: string | null } | null>(null);
  const [triggerOAuthLoading, setTriggerOAuthLoading] = useState(false);

  const fetchOutlookStatus = async () => {
    try {
      const res = await api.get('/api/v1/oauth/status');
      setOutlookStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch Outlook integration status', err);
    }
  };

  const fetchDashboardMetrics = async () => {
    try {
      setLoadingMetrics(true);
      const res = await api.get('/api/v1/dashboard/metrics');
      setMetrics(res.data.metrics);
      setLeads(res.data.leads);
      setActivities(res.data.activities);
      setEngagement(res.data.engagement);
    } catch (err) {
      console.error('Failed to fetch CRM metrics', err);
    } finally {
      setLoadingMetrics(false);
    }
  };

  const handleSeedDemoData = async () => {
    try {
      setSeeding(true);
      await api.post('/api/v1/dashboard/seed');
      await fetchDashboardMetrics();
    } catch (err) {
      console.error('Failed to seed demo CRM data', err);
    } finally {
      setSeeding(false);
    }
  };

  useEffect(() => {
    if (isTenantInitialized) {
      fetchOutlookStatus();
      fetchDashboardMetrics();
    }
  }, [isTenantInitialized]);

  const handleLogout = async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch (err) {
      console.error('Failed to log out cleanly', err);
    }
    router.push('/login');
  };

  const handleConnectOutlook = async () => {
    setTriggerOAuthLoading(true);
    try {
      const res = await api.get('/api/v1/oauth/connect');
      window.location.href = res.data.authorization_url;
    } catch (err) {
      console.error('Failed to start Outlook connection', err);
      setTriggerOAuthLoading(false);
    }
  };

  if (isLoading || !isTenantInitialized) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary">
        <div className="flex flex-col items-center space-y-4">
          <div className="w-10 h-10 border-4 border-brand-primary border-t-transparent rounded-full animate-spin"></div>
          <div className="text-sm font-semibold text-text-secondary">Loading your workspace...</div>
        </div>
      </div>
    );
  }

  return (
    <AppShell>
      <div className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6 sm:space-y-8">
          
          {/* Header section */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-border-color gap-4">
            <div className="flex items-center space-x-4">
              {branding?.logo_url ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={branding.logo_url}
                  alt={`${branding.company_name} logo`}
                  className="w-12 h-12 rounded-xl object-contain bg-bg-surface border border-border-color p-1.5 shadow-xs"
                />
              ) : (
                <div 
                  style={{ backgroundColor: 'var(--brand-primary)' }}
                  className="w-12 h-12 rounded-xl flex items-center justify-center font-bold text-white text-xl shadow-md"
                >
                  {branding?.company_name.charAt(0) || 'F'}
                </div>
              )}
              <div>
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
                  {branding?.company_name || 'FreightForce'} AI Sales Employee Workspace
                </h1>
                <p className="text-xs sm:text-sm text-text-secondary font-medium flex items-center gap-1.5 mt-0.5">
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  Active Tenant Account
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3 self-end sm:self-center">
              <button
                onClick={handleLogout}
                className="flex items-center space-x-2 text-xs font-semibold text-text-secondary hover:text-red-500 bg-bg-surface border border-border-color hover:border-red-200 px-3.5 py-2.5 rounded-xl transition-all cursor-pointer shadow-xs"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </div>
          </div>

          {/* ZONE 1 — System Health Bar (Outlook/AI status, light gray background, 56px height, high visibility) */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 min-h-[56px] rounded-xl bg-bg-secondary border border-border-color text-text-secondary text-xs font-medium">
            <div className="flex flex-wrap items-center gap-4 md:gap-6">
              <div className="flex items-center space-x-2">
                <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">Outlook Connection:</span>
                {outlookStatus?.connected ? (
                  <span className="flex items-center space-x-1.5 text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span>Connected as {outlookStatus.mailbox_email}</span>
                  </span>
                ) : (
                  <span className="flex items-center space-x-1.5 text-rose-600 bg-rose-50 border border-rose-200 px-2 py-0.5 rounded-md font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                    <span>Reconnection Required</span>
                  </span>
                )}
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">AI Engine:</span>
                <span className="flex items-center space-x-1.5 text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  <span>AI Active</span>
                </span>
              </div>
            </div>
            {!outlookStatus?.connected && (
              <button
                onClick={handleConnectOutlook}
                disabled={triggerOAuthLoading}
                className="bg-brand-primary text-white hover:bg-brand-primary-hover text-[11px] font-bold px-3 py-1.5 rounded-lg transition-all active:scale-[0.99] flex items-center gap-1.5"
              >
                {triggerOAuthLoading ? 'Connecting...' : 'Connect Outlook'}
              </button>
            )}
          </div>

          {/* ZONE 2 — Quick Start Onboarding Prompt (Replaces Empty State banner) */}
          {!loadingMetrics && metrics?.total_contacts === 0 && (
            <div className="relative overflow-hidden rounded-xl bg-blue-50/50 border border-blue-200 p-5 sm:p-6 text-text-primary shadow-xs">
              <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                <div className="space-y-1.5 max-w-2xl">
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold tracking-widest uppercase text-brand-primary">
                    <Sparkles className="w-3 h-3 animate-pulse" />
                    Quick Start
                  </span>
                  <h3 className="text-lg font-bold text-text-primary">Your AI sales agent is ready — let’s get started</h3>
                  <p className="text-xs sm:text-sm text-text-secondary leading-relaxed">
                    Populate your pipeline with realistic cargo forwarding leads, target segments, outbound campaigns, and email activities to see the outreach workflow in action.
                  </p>
                </div>
                <button
                  onClick={handleSeedDemoData}
                  disabled={seeding}
                  className="bg-brand-primary hover:bg-brand-primary-hover text-white text-xs font-bold px-5 py-3 rounded-xl transition-all shadow-md active:scale-99 disabled:opacity-50 cursor-pointer self-start md:self-center flex items-center space-x-2 shrink-0 border border-transparent"
                >
                  {seeding ? (
                    <>
                      <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>Seeding...</span>
                    </>
                  ) : (
                    <>
                      <Database className="w-4 h-4" />
                      <span>Seed AI Demo Leads</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* ZONE 3 — Operational Metrics Grid (4 Columns) */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
            <div className="bg-bg-surface p-5 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] border-t-2 border-t-brand-primary flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Active Customers</span>
                <div className="p-2.5 rounded-xl bg-blue-500/5 text-blue-500">
                  <Users className="w-4.5 h-4.5" />
                </div>
              </div>
              <div className="mt-4 flex items-baseline justify-between">
                <span className="text-xl sm:text-2xl font-bold text-text-primary font-mono">
                  {loadingMetrics ? '...' : metrics?.total_contacts}
                </span>
                <span className="text-[10px] sm:text-xs font-bold text-emerald-600 flex items-center gap-0.5">
                  Live DB
                </span>
              </div>
            </div>

            <div className="bg-bg-surface p-5 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] border-t-2 border-t-brand-primary flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Campaigns Live</span>
                <div className="p-2.5 rounded-xl bg-indigo-500/5 text-indigo-500">
                  <Send className="w-4.5 h-4.5" />
                </div>
              </div>
              <div className="mt-4 flex items-baseline justify-between">
                <span className="text-xl sm:text-2xl font-bold text-text-primary font-mono">
                  {loadingMetrics ? '...' : metrics?.total_campaigns}
                </span>
                <span className="text-[10px] sm:text-xs font-bold text-indigo-600 flex items-center gap-0.5">
                  Pipeline
                </span>
              </div>
            </div>

            <div className="bg-bg-surface p-5 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] border-t-2 border-t-brand-primary flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Emails This Week</span>
                <div className="p-2.5 rounded-xl bg-violet-500/5 text-violet-500">
                  <Mail className="w-4.5 h-4.5" />
                </div>
              </div>
              <div className="mt-4 flex items-baseline justify-between">
                <span className="text-xl sm:text-2xl font-bold text-text-primary font-mono">
                  {loadingMetrics ? '...' : metrics?.total_emails_sent}
                </span>
                <span className="text-[10px] sm:text-xs font-bold text-violet-600 flex items-center gap-0.5">
                  Outbound
                </span>
              </div>
            </div>

            <div className="bg-bg-surface p-5 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] border-t-2 border-t-brand-primary flex flex-col justify-between hover:border-slate-300 transition-all duration-200">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Reply Rate (7-day)</span>
                <div className="p-2.5 rounded-xl bg-emerald-500/5 text-emerald-500">
                  <BarChart3 className="w-4.5 h-4.5" />
                </div>
              </div>
              <div className="mt-4 flex items-baseline justify-between">
                <span className="text-xl sm:text-2xl font-bold text-text-primary font-mono">
                  {loadingMetrics ? '...' : metrics?.response_rate}
                </span>
                <span className="text-[10px] sm:text-xs font-bold text-emerald-600 flex items-center gap-0.5">
                  <TrendingUp className="w-3 h-3" />
                  Conversion
                </span>
              </div>
            </div>
          </div>

          {/* ZONE 4 — Two-Column Content Area */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* LEFT (2/3): Agent Activity Timeline */}
            <div className="bg-bg-surface p-5 sm:p-6 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] flex flex-col h-full lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-border-color">
                <h2 className="text-base font-bold text-text-primary flex items-center space-x-2">
                  <Layers className="w-5 h-5 text-brand-primary" />
                  <span>Agent Activity Timeline</span>
                </h2>
                <span className="text-[10px] font-bold text-brand-primary bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-md">
                  Live Stream
                </span>
              </div>

              <div className="flex-1 divide-y divide-border-color/60 overflow-y-auto max-h-[320px] pr-2">
                {loadingMetrics ? (
                  <div className="py-8 text-center text-xs text-text-muted font-semibold">Loading logs...</div>
                ) : activities.length === 0 ? (
                  <div className="py-8 text-center text-xs text-text-muted font-medium">No campaign activity recorded yet.</div>
                ) : (
                  activities.map((act, index) => (
                    <div key={index} className="py-3.5 flex justify-between items-start gap-4">
                      <div className="space-y-1">
                        <p className="text-xs font-bold text-text-primary flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-brand-primary animate-pulse"></span>
                          {act.event}
                        </p>
                        <p className="text-xs text-text-secondary font-medium pl-3">{act.details}</p>
                      </div>
                      <span className="text-[10px] text-text-muted font-semibold shrink-0 font-mono">{act.time}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* RIGHT (1/3): Compact Engagement Widget */}
            <div className="bg-bg-surface p-5 sm:p-6 rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] flex flex-col justify-between h-full space-y-6">
              <div>
                <div className="flex items-center justify-between pb-4 border-b border-border-color">
                  <h2 className="text-base font-bold text-text-primary flex items-center space-x-2">
                    <Send className="w-5 h-5 text-brand-primary" />
                    <span>Engagement Summary</span>
                  </h2>
                  <span className="flex items-center space-x-1 text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-md text-[10px] font-bold border border-indigo-200">
                    <span>LIVE</span>
                  </span>
                </div>
                
                <div className="py-4 space-y-4 text-xs font-semibold text-text-secondary">
                  <div className="flex justify-between items-center p-2.5 bg-bg-secondary rounded-xl border border-border-color">
                    <span className="text-text-muted">Sent Today</span>
                    <span className="font-bold text-emerald-600 text-sm">{loadingMetrics ? '...' : (engagement?.sent_today || 0)}</span>
                  </div>

                  <div className="flex justify-between items-center p-2.5 bg-bg-secondary rounded-xl border border-border-color">
                    <span className="text-text-muted">Failed Today</span>
                    <span className="font-bold text-rose-600 text-sm">{loadingMetrics ? '...' : (engagement?.failed || 0)}</span>
                  </div>

                  <div className="flex justify-between items-center p-2.5 bg-bg-secondary rounded-xl border border-border-color">
                    <span className="text-text-muted">Pending Targets</span>
                    <span className="font-bold text-text-primary text-sm">{loadingMetrics ? '...' : (engagement?.pending || 0)}</span>
                  </div>

                  <div className="space-y-1">
                    <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block">Next Auto Run</span>
                    <p className="text-xs text-text-primary font-bold bg-bg-secondary px-3 py-2 rounded-xl border border-border-color font-mono truncate">
                      {loadingMetrics ? '...' : (engagement?.next_auto_run || 'Not Scheduled')}
                    </p>
                  </div>
                </div>
              </div>

              <div>
                <button
                  onClick={() => router.push('/engagement')}
                  className="w-full text-xs font-bold text-white bg-indigo-650 hover:bg-indigo-700 py-3 px-4 rounded-xl cursor-pointer transition-all shadow-md active:scale-98 flex items-center justify-center space-x-2 border border-transparent"
                >
                  <span>Go to Engagement Panel</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>

          </div>

          {/* ZONE 5 — Active Outreach Pipeline Table */}
          <div className="bg-bg-surface rounded-xl border border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)] overflow-hidden">
            <div className="p-5 sm:p-6 border-b border-border-color flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="space-y-0.5">
                <h2 className="text-base font-bold text-text-primary">Active Outreach Pipeline</h2>
                <p className="text-xs text-text-secondary">Leads generated and monitored by AI Agents</p>
              </div>
              <button 
                className="border border-[#BFDBFE] hover:bg-[#EFF6FF] text-brand-primary text-xs font-bold px-4 py-2 rounded-xl transition-all cursor-pointer flex items-center gap-1.5 self-start sm:self-center shadow-xs bg-transparent"
              >
                <MessageSquarePlus className="w-4 h-4" />
                <span>Add Custom Lead</span>
              </button>
            </div>

            {/* Responsive Table Container with Sticky Header */}
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-bg-secondary/80 border-b-2 border-border-color sticky top-0 backdrop-blur-xs">
                    <th className="p-4 text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Contact</th>
                    <th className="p-4 text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Company</th>
                    <th className="p-4 text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Email</th>
                    <th className="p-4 text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">Last Activity</th>
                    <th className="p-4 text-[11px] font-bold text-text-muted uppercase tracking-[0.06em] text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-color/60">
                  {loadingMetrics ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-xs text-text-muted font-semibold">Loading leads...</td>
                    </tr>
                  ) : leads.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="p-8 text-center text-xs text-text-muted font-medium">No leads currently loaded. Seed sample data above.</td>
                    </tr>
                  ) : (
                    leads.map((lead) => (
                      <tr key={lead.id} className="hover:bg-bg-secondary/40 transition-colors">
                        <td className="p-4">
                          <div className="flex items-center space-x-3">
                            <div className="w-8 h-8 rounded-full bg-bg-secondary flex items-center justify-center font-bold text-xs text-text-secondary border border-border-color">
                              {lead.contact_name ? lead.contact_name.split(' ').map((n: string) => n[0]).join('') : 'L'}
                            </div>
                            <span className="text-xs font-semibold text-text-primary">{lead.contact_name || 'N/A'}</span>
                          </div>
                        </td>
                        <td className="p-4 text-xs font-semibold text-text-primary">{lead.company_name}</td>
                        <td className="p-4 text-xs font-medium text-text-muted font-mono">{lead.contact_email}</td>
                        <td className="p-4 text-xs font-medium text-text-muted font-mono">
                          {lead.last_contact ? new Date(lead.last_contact).toLocaleDateString() : 'Pending outreach'}
                        </td>
                        <td className="p-4 text-right">
                          <button className="text-text-secondary hover:text-text-primary p-1.5 rounded-lg hover:bg-bg-secondary transition-all cursor-pointer">
                            <ChevronRight className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
          
      </div>
    </AppShell>
  );
}
