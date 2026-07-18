'use client';

import React, { useState, useEffect } from 'react';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { api } from '../../lib/api';
import { useAuth } from '../../hooks/use-auth';
import {
  Send, Save, Activity, CheckCircle, XCircle, Clock, AlertCircle, RefreshCw, ChevronRight, Play
} from 'lucide-react';

interface Execution {
  id: string;
  status: string;
  trigger_type: string;
  total_customers: number;
  processed: number;
  sent: number;
  failed: number;
  skipped: number;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  error_message?: string;
}

interface LogEntry {
  id: string;
  status: string;
  message: string;
  created_at: string;
}

export default function EngagementPage() {
  const { isLoading: authLoading, isTenantInitialized } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Settings Fields
  const [autoEngagement, setAutoEngagement] = useState(false);
  const [schedule, setSchedule] = useState('daily');
  const [preferredSendTime, setPreferredSendTime] = useState('09:00');
  const [timezone, setTimezone] = useState('UTC');
  const [emailsPerWeek, setEmailsPerWeek] = useState(3);
  const [minGapDays, setMinGapDays] = useState(2);
  const [allowedWeekdays, setAllowedWeekdays] = useState<number[]>([1, 2, 3, 4, 5]);
  const [batchSize, setBatchSize] = useState(50);
  const [delaySeconds, setDelaySeconds] = useState(5);

  // Execution Progress / History
  const [activeExecution, setActiveExecution] = useState<Execution | null>(null);
  const [activeLogs, setActiveLogs] = useState<LogEntry[]>([]);
  const [history, setHistory] = useState<Execution[]>([]);

  // Confirmation Modal
  const [confirmModalOpen, setConfirmModalOpen] = useState(false);
  const [triggeringRun, setTriggeringRun] = useState(false);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const handleCancelRun = async () => {
    if (!activeExecution) return;
    try {
      setCancelling(true);
      await api.post(`/api/v1/engagement/cancel/${activeExecution.id}`);
      setActiveExecution(null);
      setActiveLogs([]);
      fetchHistory();
    } catch (err) {
      console.error('Failed to cancel run', err);
    } finally {
      setCancelling(false);
    }
  };

  // Stats for Modal
  const [stats, setStats] = useState<{ ready_count: number } | null>(null);

  useEffect(() => {
    if (isTenantInitialized) {
      fetchData();
    }
  }, [isTenantInitialized]);

  // Poll active execution progress if running
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (activeExecution && (activeExecution.status === 'started' || activeExecution.status === 'running')) {
      interval = setInterval(async () => {
        try {
          const res = await api.get(`/api/v1/engagement/status/${activeExecution.id}`);
          setActiveExecution(res.data.execution);
          setActiveLogs(res.data.logs);

          if (res.data.execution.status === 'completed' || res.data.execution.status === 'failed') {
            // Reload history if completed
            fetchHistory();
          }
        } catch (err) {
          console.error('Failed to poll status', err);
        }
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [activeExecution]);

  const fetchData = async () => {
    try {
      setLoading(true);
      await Promise.all([
        fetchSettings(),
        fetchHistory(),
        fetchStats()
      ]);
    } catch (err) {
      console.error('Failed to load data', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchSettings = async () => {
    try {
      const res = await api.get('/api/v1/engagement/settings');
      const data = res.data;
      setAutoEngagement(data.auto_engagement);
      setSchedule(data.schedule);
      setPreferredSendTime(data.preferred_send_time);
      setTimezone(data.timezone);
      setEmailsPerWeek(data.emails_per_week);
      setMinGapDays(data.min_gap_days);
      setAllowedWeekdays(data.allowed_weekdays || [1, 2, 3, 4, 5]);
      setBatchSize(data.batch_size);
      setDelaySeconds(data.delay_seconds);
    } catch (err) {
      console.error('Failed to fetch settings', err);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await api.get('/api/v1/engagement/history?limit=10');
      setHistory(res.data);

      // Detect if there's a currently active execution
      const active = res.data.find((run: Execution) => run.status === 'started' || run.status === 'running');
      if (active) {
        setActiveExecution(active);
        const statusRes = await api.get(`/api/v1/engagement/status/${active.id}`);
        setActiveLogs(statusRes.data.logs);
      } else {
        setActiveExecution(null);
        setActiveLogs([]);
      }
    } catch (err) {
      console.error('Failed to fetch history', err);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await api.get('/api/v1/customers/stats');
      setStats(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  const handleToggleWeekday = (day: number) => {
    if (allowedWeekdays.includes(day)) {
      setAllowedWeekdays(allowedWeekdays.filter(d => d !== day));
    } else {
      setAllowedWeekdays([...allowedWeekdays, day].sort());
    }
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setSaving(true);
      setError(null);
      setSuccess(false);
      await api.put('/api/v1/engagement/settings', {
        auto_engagement: autoEngagement,
        schedule,
        preferred_send_time: preferredSendTime,
        timezone,
        emails_per_week: emailsPerWeek,
        min_gap_days: minGapDays,
        allowed_weekdays: allowedWeekdays,
        batch_size: batchSize,
        delay_seconds: delaySeconds
      });
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError('Failed to update settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleTriggerRun = async () => {
    try {
      setTriggeringRun(true);
      setTriggerError(null);
      const res = await api.post('/api/v1/engagement/run');
      setConfirmModalOpen(false);

      // Start polling progress immediately
      const newExec: Execution = {
        id: res.data.execution_id,
        status: 'started',
        trigger_type: 'manual',
        total_customers: stats?.ready_count || 0,
        processed: 0,
        sent: 0,
        failed: 0,
        skipped: 0,
        started_at: new Date().toISOString()
      };
      setActiveExecution(newExec);
      setActiveLogs([]);
      fetchHistory();
    } catch (err: any) {
      if (err.response?.status === 409) {
        setTriggerError('An engagement run is already active. Parallel runs are locked.');
      } else {
        setTriggerError('Failed to trigger run. Check mailbox integrations.');
      }
    } finally {
      setTriggeringRun(false);
    }
  };

  const weekdays = [
    { value: 1, label: 'Mon' },
    { value: 2, label: 'Tue' },
    { value: 3, label: 'Wed' },
    { value: 4, label: 'Thu' },
    { value: 5, label: 'Fri' },
    { value: 6, label: 'Sat' },
    { value: 0, label: 'Sun' }
  ];

  return (
    <AppShell>
      <PageWrapper>
        <PageHeader
          title="Engagement Dashboard"
          description="Manage scheduling, delivery parameters, and manual campaign executions"
          actions={
            <button
              onClick={() => setConfirmModalOpen(true)}
              className="h-10 px-5 bg-indigo-650 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer border-0"
            >
              <Play className="w-4 h-4" />
              <span>Send Engagement</span>
            </button>
          }
        />
        {authLoading || !isTenantInitialized || loading ? (
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin"></div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Left & Middle Column: Settings and Progress */}
            <div className="lg:col-span-2 space-y-6">

              {/* Real-time Progress Widget (Only when running) */}
              {activeExecution && (
                <div className="bg-bg-surface border-2 border-indigo-500 rounded-2xl p-6 space-y-4">
                  <div className="flex items-center justify-between border-b border-border-color pb-3 select-none">
                    <div>
                      <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                        <Activity className="w-4 h-4 text-indigo-600 animate-pulse" />
                        <span>Execution in Progress</span>
                      </h3>
                      <p className="text-[10px] text-text-muted mt-0.5">ID: {activeExecution.id}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={handleCancelRun}
                        disabled={cancelling}
                        className="px-3 py-1 bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 rounded-lg text-xs font-bold transition-all cursor-pointer"
                      >
                        {cancelling ? 'Cancelling...' : 'Cancel Campaign'}
                      </button>
                      <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200 animate-pulse capitalize animate-pulse">
                        {activeExecution.status}
                      </span>
                    </div>
                  </div>

                  {/* Progress bar */}
                  <div className="space-y-2">
                    <div className="w-full h-3 bg-bg-secondary rounded-full overflow-hidden border border-border-color">
                      <div
                        className="h-full bg-indigo-600 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, Math.round((activeExecution.processed / (activeExecution.total_customers || 1)) * 100))}%` }}
                      ></div>
                    </div>
                    <div className="flex justify-between text-xs text-text-muted">
                      <span>{activeExecution.processed} of {activeExecution.total_customers} processed</span>
                      <span className="font-bold text-indigo-650">
                        {Math.min(100, Math.round((activeExecution.processed / (activeExecution.total_customers || 1)) * 100))}%
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div className="bg-emerald-50/15 border border-emerald-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider block">Sent</span>
                      <span className="text-lg font-bold text-emerald-700">{activeExecution.sent}</span>
                    </div>
                    <div className="bg-rose-50/15 border border-rose-105 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-rose-800 uppercase tracking-wider block">Failed</span>
                      <span className="text-lg font-bold text-rose-700">{activeExecution.failed}</span>
                    </div>
                    <div className="bg-slate-50/15 border border-slate-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-slate-800 uppercase tracking-wider block">Skipped</span>
                      <span className="text-lg font-bold text-slate-600">{activeExecution.skipped}</span>
                    </div>
                  </div>

                  {/* Live Mini Log Console */}
                  <div className="space-y-2">
                    <span className="text-[10px] font-bold text-text-secondary uppercase">Live Feed</span>
                    <div className="space-y-1.5 max-h-[140px] overflow-y-auto border border-border-color rounded-xl p-3 bg-bg-secondary/40 font-mono text-[10px] leading-normal">
                      {activeLogs.slice(-5).map((log) => (
                        <div key={log.id} className="flex gap-2">
                          <span className="text-text-muted shrink-0">[{new Date(log.created_at).toLocaleTimeString()}]</span>
                          <span className="text-text-primary break-all">{log.message}</span>
                        </div>
                      ))}
                      {activeLogs.length === 0 && <p className="text-text-muted italic">Polling active updates...</p>}
                    </div>
                  </div>
                </div>
              )}

              {/* Settings Form */}
              <form onSubmit={handleSaveSettings} className="bg-bg-surface border border-border-color rounded-2xl p-6 space-y-6">
                <div className="flex items-center justify-between border-b border-border-color pb-3">
                  <h3 className="text-sm font-bold text-text-primary">Automation Settings</h3>
                  {success && <span className="text-xs font-semibold text-emerald-600 flex items-center gap-1"><CheckCircle className="w-3.5 h-3.5" /> Saved!</span>}
                  {error && <span className="text-xs font-semibold text-rose-600 flex items-center gap-1"><AlertCircle className="w-3.5 h-3.5" /> {error}</span>}
                </div>

                <div className="flex items-center justify-between p-4 bg-bg-secondary rounded-xl">
                  <div>
                    <h4 className="text-sm font-bold text-text-primary">Auto Engagement Scheduling</h4>
                    <p className="text-xs text-text-muted mt-0.5">Let n8n run campaign delivery automatically based on the schedule below</p>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={autoEngagement}
                      onChange={(e) => setAutoEngagement(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-350 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-650"></div>
                  </label>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Cadence */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-text-secondary">Run Cadence</label>
                    <select
                      value={schedule}
                      onChange={(e) => setSchedule(e.target.value)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-sm focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                    </select>
                  </div>

                  {/* Send time */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-text-secondary">Preferred Time</label>
                    <input
                      type="time"
                      value={preferredSendTime}
                      onChange={(e) => setPreferredSendTime(e.target.value)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-sm focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  {/* Timezone */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-text-secondary">Timezone</label>
                    <select
                      value={timezone}
                      onChange={(e) => setTimezone(e.target.value)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-sm focus:border-indigo-500 focus:outline-none"
                    >
                      <option value="UTC">UTC</option>
                      <option value="America/New_York">New York (EST)</option>
                      <option value="Europe/London">London (GMT)</option>
                      <option value="Asia/Kolkata">Kolkata (IST)</option>
                    </select>
                  </div>
                </div>

                {/* Weekdays */}
                <div className="space-y-2">
                  <label className="text-xs font-bold text-text-secondary block">Allowed Weekdays</label>
                  <div className="flex flex-wrap gap-2">
                    {weekdays.map((day) => {
                      const active = allowedWeekdays.includes(day.value);
                      return (
                        <button
                          key={day.value}
                          type="button"
                          onClick={() => handleToggleWeekday(day.value)}
                          className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-all cursor-pointer ${active
                              ? 'bg-indigo-50 border-indigo-300 text-indigo-700 font-bold'
                              : 'bg-bg-surface border-border-color text-text-secondary hover:bg-bg-secondary'
                            }`}
                        >
                          {day.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-border-color/60">
                  {/* Limits */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-text-secondary">Emails per week per customer</label>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={emailsPerWeek}
                      onChange={(e) => setEmailsPerWeek(parseInt(e.target.value) || 3)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-sm focus:border-indigo-500 focus:outline-none"
                    />
                  </div>

                  {/* Delay */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-bold text-text-secondary">Delay between emails (Seconds)</label>
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={delaySeconds}
                      onChange={(e) => setDelaySeconds(parseInt(e.target.value) || 5)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-sm focus:border-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-2">
                  <button
                    type="submit"
                    disabled={saving}
                    className="h-10 px-6 bg-indigo-650 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg shadow-sm hover:shadow transition-all disabled:opacity-50 flex items-center gap-2 cursor-pointer border-0"
                  >
                    <Save className="w-4 h-4" />
                    <span>{saving ? 'Saving...' : 'Save Settings'}</span>
                  </button>
                </div>
              </form>
            </div>

            {/* Right Column: Execution History List */}
            <div className="space-y-6">
              <div className="bg-bg-surface border border-border-color rounded-2xl p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-border-color pb-3">
                  <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
                    <Clock className="w-4 h-4 text-slate-400" />
                    <span>Recent Executions</span>
                  </h3>
                </div>

                {history.length === 0 ? (
                  <p className="text-xs text-text-muted italic text-center py-6">No campaign history recorded.</p>
                ) : (
                  <div className="divide-y divide-border-color/60 max-h-[480px] overflow-y-auto pr-1">
                    {history.map((run) => {
                      let statusText = 'Completed';
                      let statusColor = 'text-emerald-650';
                      if (run.status === 'failed') {
                        statusText = 'Failed';
                        statusColor = 'text-rose-600';
                      } else if (run.status === 'running' || run.status === 'started') {
                        statusText = 'Running';
                        statusColor = 'text-blue-600 font-semibold';
                      }

                      return (
                        <div key={run.id} className="py-3 text-xs space-y-1 hover:bg-bg-secondary/20 px-1 rounded transition-colors">
                          <div className="flex justify-between font-bold">
                            <span className="text-text-primary capitalize">{run.trigger_type} Run</span>
                            <span className={statusColor}>{statusText}</span>
                          </div>
                          <div className="flex justify-between text-text-muted">
                            <span>{new Date(run.started_at).toLocaleDateString()}</span>
                            <span>{run.sent} sent ({run.failed} failed)</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Send Engagement Confirmation Modal */}
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
                  onClick={handleTriggerRun}
                  disabled={triggeringRun}
                  className="px-5 py-2 bg-indigo-650 hover:bg-indigo-700 text-white rounded-lg text-sm font-bold shadow-sm transition-all flex items-center gap-2 cursor-pointer border-0"
                >
                  {triggeringRun ? 'Starting...' : 'Start Run'}
                </button>
              </div>
            </div>
          </div>
        )}
      </PageWrapper>
    </AppShell>
  );
}
