'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '../../hooks/use-auth';
import { useTenantStore } from '../../store/tenant-store';
import { api } from '../../lib/api';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper } from '../../components/layout/page-wrapper';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Alert, Skeleton, Badge } from '../../components/ui/feedback';
import { 
  Settings,
  Building,
  Mail,
  Sparkles,
  Calendar,
  Bell,
  RefreshCw,
  Info,
  ChevronDown,
  ChevronUp,
  X,
  CheckCircle,
  HelpCircle,
  Plus
} from 'lucide-react';

import { SignatureTab } from '../../components/signature-tab';

interface ProfileData {
  display_name: string;
  phone_number: string;
  website: string;
  timezone: string;
  country: string;
}

interface SettingsData {
  cc_emails: string[];
  bcc_emails: string[];
  ai_enabled: boolean;
  reply_style: string;
  reply_length: string;
  scheduler_enabled: boolean;
  scheduler_interval_minutes: number;
  business_hours_enabled: boolean;
  working_days: string[];
  start_time: string;
  end_time: string;
  last_scheduler_run: string | null;
}

interface OutlookData {
  connected: boolean;
  connected_account: string | null;
  last_sync: string | null;
}

interface SystemData {
  organization_id: string;
  created_date: string;
  current_plan: string;
  ai_sales_employee_version: string;
}

export default function SettingsPage() {
  const { isLoading, isTenantInitialized } = useAuth();
  const { branding } = useTenantStore();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Loaded Settings state
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [settings, setSettings] = useState<SettingsData | null>(null);
  const [outlook, setOutlook] = useState<OutlookData | null>(null);
  const [system, setSystem] = useState<SystemData | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  // Original state backup for change detection
  const [originalData, setOriginalData] = useState<string | null>(null);

  // Accordions expanded state
  const [expandedSections, setExpandedSections] = useState({
    profile: true,
    email: true,
    signature: true,
    ai: true,
    scheduler: true,
    outlook: true,
    system: true,
  });

  // Local inputs for chip lists
  const [ccInput, setCcInput] = useState('');
  const [bccInput, setBccInput] = useState('');

  // Provider states
  const [selectedProvider, setSelectedProvider] = useState<'microsoft_graph' | 'smtp'>('microsoft_graph');
  const [presets, setPresets] = useState<any>({});
  const [selectedPreset, setSelectedPreset] = useState('custom');
  
  // SMTP Config states
  const [mailboxEmail, setMailboxEmail] = useState('');
  const [authUsername, setAuthUsername] = useState('');
  const [password, setPassword] = useState('');
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState('');
  const [smtpSecurity, setSmtpSecurity] = useState('ssl_tls');
  const [imapHost, setImapHost] = useState('');
  const [imapPort, setImapPort] = useState('');
  const [imapSecurity, setImapSecurity] = useState('ssl_tls');
  
  // SMTP helper/status states
  const [testSuccess, setTestSuccess] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);
  const [savingSmtp, setSavingSmtp] = useState(false);
  const [smtpError, setSmtpError] = useState<string | null>(null);
  const [smtpSuccess, setSmtpSuccess] = useState<string | null>(null);

  const fetchPresets = async () => {
    try {
      const res = await api.get('/api/v1/smtp/presets');
      setPresets(res.data);
    } catch (err) {
      console.error('Failed to fetch presets', err);
    }
  };

  useEffect(() => {
    if (isTenantInitialized) {
      fetchPresets();
    }
  }, [isTenantInitialized]);

  const handlePresetChange = (presetKey: string) => {
    setSelectedPreset(presetKey);
    setTestSuccess(false);
    if (presetKey === 'custom') return;
    const preset = presets[presetKey];
    if (preset) {
      setSmtpHost(preset.smtp_host || '');
      setSmtpPort(preset.smtp_port ? String(preset.smtp_port) : '');
      setSmtpSecurity(preset.smtp_security || 'ssl_tls');
      setImapHost(preset.imap_host || '');
      setImapPort(preset.imap_port ? String(preset.imap_port) : '');
      setImapSecurity(preset.imap_security || 'ssl_tls');
    }
  };

  const onFieldChange = (setter: (val: string) => void, val: string) => {
    setter(val);
    setTestSuccess(false);
  };

  const handleTestSmtp = async () => {
    try {
      setTestingConnection(true);
      setSmtpError(null);
      setSmtpSuccess(null);
      await api.post('/api/v1/smtp/test', {
        mailbox_email: mailboxEmail,
        auth_username: authUsername || null,
        password: password,
        smtp_host: smtpHost,
        smtp_port: parseInt(smtpPort),
        smtp_security: smtpSecurity,
        imap_host: imapHost,
        imap_port: parseInt(imapPort),
        imap_security: imapSecurity,
        send_test_email: false
      });
      setTestSuccess(true);
      setSmtpSuccess('Connection tested and validated successfully!');
    } catch (err: any) {
      console.error('SMTP test failed', err);
      setSmtpError(err?.response?.data?.detail || 'SMTP/IMAP validation failed. Please check settings.');
      setTestSuccess(false);
    } finally {
      setTestingConnection(false);
    }
  };

  const handleConnectSmtp = async () => {
    if (!testSuccess) return;
    try {
      setSavingSmtp(true);
      setSmtpError(null);
      setSmtpSuccess(null);
      await api.post('/api/v1/smtp/connect', {
        mailbox_email: mailboxEmail,
        auth_username: authUsername || null,
        password: password,
        smtp_host: smtpHost,
        smtp_port: parseInt(smtpPort),
        smtp_security: smtpSecurity,
        imap_host: imapHost,
        imap_port: parseInt(imapPort),
        imap_security: imapSecurity
      });
      setSmtpSuccess('SMTP/IMAP integrated and saved successfully!');
      setTestSuccess(false);
      await fetchSettings();
    } catch (err: any) {
      console.error('SMTP connect failed', err);
      setSmtpError(err?.response?.data?.detail || 'Failed to save SMTP integration.');
    } finally {
      setSavingSmtp(false);
    }
  };

  const handleDisconnectSmtp = async () => {
    if (!confirm('Are you sure you want to disconnect SMTP/IMAP integration?')) return;
    try {
      await api.delete('/api/v1/smtp/disconnect');
      await fetchSettings();
    } catch (err) {
      console.error('Failed to disconnect SMTP', err);
      alert('Could not disconnect SMTP integration.');
    }
  };

  const fetchSettings = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.get('/api/v1/settings');
      
      setProfile(res.data.profile);
      setSettings(res.data.settings);
      setOutlook(res.data.outlook);
      setSystem(res.data.system);
      setIsAdmin(res.data.is_admin);

      const outlookData = res.data.outlook;
      if (outlookData) {
        setSelectedProvider(outlookData.provider || 'microsoft_graph');
        if (outlookData.provider === 'smtp') {
          setMailboxEmail(outlookData.connected_account || '');
          setSmtpHost(outlookData.smtp_host || '');
          setSmtpPort(outlookData.smtp_port ? String(outlookData.smtp_port) : '');
          setSmtpSecurity(outlookData.smtp_security || 'ssl_tls');
          setImapHost(outlookData.imap_host || '');
          setImapPort(outlookData.imap_port ? String(outlookData.imap_port) : '');
          setImapSecurity(outlookData.imap_security || 'ssl_tls');
          setPassword('__UNCHANGED__');
        }
      }

      const serialized = JSON.stringify({
        profile: res.data.profile,
        settings: res.data.settings
      });
      setOriginalData(serialized);
      setIsDirty(false);
    } catch (err: any) {
      console.error('Failed to load settings', err);
      setError('Could not retrieve settings configuration.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isTenantInitialized) {
      fetchSettings();
    }
  }, [isTenantInitialized]);

  // Track modification changes
  useEffect(() => {
    if (profile && settings && originalData) {
      const currentSerialized = JSON.stringify({ profile, settings });
      setIsDirty(currentSerialized !== originalData);
    }
  }, [profile, settings, originalData]);

  // Alert user before leaving page with unsaved modifications
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  // Profile change handlers
  const handleProfileChange = (field: keyof ProfileData, value: string) => {
    if (!profile) return;
    setProfile({
      ...profile,
      [field]: value
    });
  };

  // Settings change handlers
  const handleSettingsChange = (field: keyof SettingsData, value: any) => {
    if (!settings) return;
    setSettings({
      ...settings,
      [field]: value
    });
  };

  // Chip List additions
  const addCcEmail = () => {
    if (!settings || !ccInput.trim()) return;
    const clean = ccInput.trim();
    if (settings.cc_emails.includes(clean)) return;
    handleSettingsChange('cc_emails', [...settings.cc_emails, clean]);
    setCcInput('');
  };

  const removeCcEmail = (index: number) => {
    if (!settings) return;
    const updated = settings.cc_emails.filter((_, idx) => idx !== index);
    handleSettingsChange('cc_emails', updated);
  };

  const addBccEmail = () => {
    if (!settings || !bccInput.trim()) return;
    const clean = bccInput.trim();
    if (settings.bcc_emails.includes(clean)) return;
    handleSettingsChange('bcc_emails', [...settings.bcc_emails, clean]);
    setBccInput('');
  };

  const removeBccEmail = (index: number) => {
    if (!settings) return;
    const updated = settings.bcc_emails.filter((_, idx) => idx !== index);
    handleSettingsChange('bcc_emails', updated);
  };

  // Day toggle for scheduler
  const toggleWorkingDay = (day: string) => {
    if (!settings) return;
    const current = settings.working_days;
    const updated = current.includes(day)
      ? current.filter(d => d !== day)
      : [...current, day];
    handleSettingsChange('working_days', updated);
  };

  // Save Settings
  const handleSaveAll = async () => {
    if (!isAdmin || !isDirty) return;
    try {
      setSaving(true);
      setError(null);
      setSaveSuccess(false);

      await api.put('/api/v1/settings', {
        profile,
        settings
      });

      // Update original backup state
      const serialized = JSON.stringify({ profile, settings });
      setOriginalData(serialized);
      setIsDirty(false);
      setSaveSuccess(true);
      
      // Auto fade success message
      setTimeout(() => setSaveSuccess(false), 5000);
    } catch (err: any) {
      console.error('Failed to save settings', err);
      setError(err?.response?.data?.detail || 'Failed to save configuration settings.');
    } finally {
      setSaving(false);
    }
  };

  // Outlook OAuth Actions
  const handleReconnectOutlook = () => {
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/oauth/login`;
  };

  const handleDisconnectOutlook = async () => {
    if (!confirm('Are you sure you want to disconnect Outlook integration?')) return;
    try {
      await api.post('/api/v1/oauth/disconnect');
      if (outlook) {
        setOutlook({
          ...outlook,
          connected: false,
          connected_account: null,
          last_sync: null
        });
      }
    } catch (err) {
      console.error('Failed to disconnect outlook', err);
      alert('Could not disconnect Outlook integrations.');
    }
  };

  const formatDate = (isoStr: string | null) => {
    if (!isoStr) return 'Never';
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
            <div className="space-y-4 mt-8">
              {[1, 2, 3, 4, 5].map(i => <Skeleton key={i} variant="rect" className="h-16" />)}
            </div>
          </div>
        </PageWrapper>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageWrapper>
        <div className="px-4 py-6 sm:px-6 lg:px-8 max-w-4xl mx-auto space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-border-color pb-5">
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
                Settings
              </h1>
              <p className="text-xs sm:text-sm text-text-muted mt-1">
                Configure your multi-tenant AI Sales Employee preferences and workspace defaults.
              </p>
            </div>
            
            {isAdmin && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleSaveAll}
                disabled={!isDirty || saving}
                isLoading={saving}
              >
                Save Settings
              </Button>
            )}
          </div>

          {/* Inline Feedback Alerts */}
          {saveSuccess && (
            <Alert 
              variant="success" 
              title="Settings Saved Successfully" 
              description="Your organization configurations have been updated." 
              onClose={() => setSaveSuccess(false)}
            />
          )}

          {error && (
            <Alert 
              variant="danger" 
              title="Unable to Save Settings" 
              description={error} 
              onClose={() => setError(null)}
            />
          )}

          {!isAdmin && !loading && (
            <div className="bg-[#EFF6FF] border border-blue-200/50 rounded-xl p-3.5 flex items-center gap-3 text-xs text-blue-900 font-medium">
              <Info className="w-4.5 h-4.5 text-brand-primary shrink-0" />
              <span>You are viewing settings in Read-Only mode. Only Organization Admins can save changes.</span>
            </div>
          )}

          {loading ? (
            <div className="space-y-4">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} variant="rect" className="h-16" />)}
            </div>
          ) : (
            <div className="space-y-4">
              {/* SECTION 1: Organization Profile Info */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('profile')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Building className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">Organization Profile</span>
                  </div>
                  {expandedSections.profile ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.profile && profile && (
                  <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                    <div className="space-y-1.5 col-span-1 sm:col-span-2">
                      <label className="font-bold text-text-secondary">Display Name</label>
                      <Input
                        type="text"
                        value={profile.display_name}
                        onChange={(e) => handleProfileChange('display_name', e.target.value)}
                        disabled={!isAdmin}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="font-bold text-text-secondary">Phone Number</label>
                      <Input
                        type="text"
                        value={profile.phone_number || ''}
                        onChange={(e) => handleProfileChange('phone_number', e.target.value)}
                        disabled={!isAdmin}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="font-bold text-text-secondary">Website</label>
                      <Input
                        type="text"
                        value={profile.website || ''}
                        onChange={(e) => handleProfileChange('website', e.target.value)}
                        disabled={!isAdmin}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <label className="font-bold text-text-secondary">Timezone</label>
                      <select
                        value={profile.timezone}
                        onChange={(e) => handleProfileChange('timezone', e.target.value)}
                        disabled={!isAdmin}
                        className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none"
                      >
                        <option value="UTC">UTC</option>
                        <option value="America/New_York">Eastern Time (EST/EDT)</option>
                        <option value="America/Chicago">Central Time (CST/CDT)</option>
                        <option value="America/Denver">Mountain Time (MST/MDT)</option>
                        <option value="America/Los_Angeles">Pacific Time (PST/PDT)</option>
                        <option value="Asia/Kolkata">India Standard Time (IST)</option>
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <label className="font-bold text-text-secondary">Country</label>
                      <Input
                        type="text"
                        value={profile.country || ''}
                        onChange={(e) => handleProfileChange('country', e.target.value)}
                        disabled={!isAdmin}
                      />
                    </div>
                  </div>
                )}
              </Card>

              {/* SECTION 2: Email Settings */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('email')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Mail className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">Email Settings</span>
                  </div>
                  {expandedSections.email ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.email && settings && (
                  <div className="p-6 space-y-4 text-xs">
                    {/* CC / BCC Chip Inputs */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <label className="font-bold text-text-secondary">CC Recipients</label>
                        {isAdmin && (
                          <div className="flex gap-2">
                            <Input
                              type="email"
                              value={ccInput}
                              onChange={(e) => setCcInput(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addCcEmail())}
                              placeholder="Add email address..."
                              className="text-xs"
                            />
                            <Button variant="secondary" size="sm" onClick={addCcEmail} className="px-3">
                              <Plus className="w-4 h-4" />
                            </Button>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-1.5 mt-2 min-h-8 p-2 border border-border-color rounded-lg bg-bg-primary/50">
                          {settings.cc_emails.length === 0 ? (
                            <span className="text-[10px] text-text-muted self-center pl-1">No default CC recipients</span>
                          ) : (
                            settings.cc_emails.map((email, idx) => (
                              <Badge key={idx} variant="primary" className="gap-1 px-2.5 py-0.5 text-[10px] font-bold">
                                <span>{email}</span>
                                {isAdmin && (
                                  <X 
                                    className="w-3 h-3 text-brand-primary hover:text-brand-primary-hover cursor-pointer" 
                                    onClick={() => removeCcEmail(idx)} 
                                  />
                                )}
                              </Badge>
                            ))
                          )}
                        </div>
                      </div>

                      <div className="space-y-2">
                        <label className="font-bold text-text-secondary">BCC Recipients</label>
                        {isAdmin && (
                          <div className="flex gap-2">
                            <Input
                              type="email"
                              value={bccInput}
                              onChange={(e) => setBccInput(e.target.value)}
                              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addBccEmail())}
                              placeholder="Add email address..."
                              className="text-xs"
                            />
                            <Button variant="secondary" size="sm" onClick={addBccEmail} className="px-3">
                              <Plus className="w-4 h-4" />
                            </Button>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-1.5 mt-2 min-h-8 p-2 border border-border-color rounded-lg bg-bg-primary/50">
                          {settings.bcc_emails.length === 0 ? (
                            <span className="text-[10px] text-text-muted self-center pl-1">No default BCC recipients</span>
                          ) : (
                            settings.bcc_emails.map((email, idx) => (
                              <Badge key={idx} variant="primary" className="gap-1 px-2.5 py-0.5 text-[10px] font-bold">
                                <span>{email}</span>
                                {isAdmin && (
                                  <X 
                                    className="w-3 h-3 text-brand-primary hover:text-brand-primary-hover cursor-pointer" 
                                    onClick={() => removeBccEmail(idx)} 
                                  />
                                )}
                              </Badge>
                            ))
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </Card>

              {/* SECTION 2.5: Email Signature Settings */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('signature')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Mail className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">Email Signature</span>
                  </div>
                  {expandedSections.signature ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.signature && (
                  <div className="p-6">
                    <SignatureTab />
                  </div>
                )}
              </Card>

              {/* SECTION 3: AI Reply Settings */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('ai')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Sparkles className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">AI Reply Settings</span>
                  </div>
                  {expandedSections.ai ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.ai && settings && (
                  <div className="p-6 space-y-4 text-xs">
                    <div className="flex items-center justify-between p-3.5 bg-bg-secondary/40 border border-border-color/50 rounded-xl">
                      <div className="space-y-0.5 col-span-2">
                        <p className="font-bold text-text-primary">AI Auto Reply</p>
                        <p className="text-[10px] text-text-muted">Allow AI Sales Employee to automatically prepare customer replies.</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={settings.ai_enabled}
                        onChange={(e) => handleSettingsChange('ai_enabled', e.target.checked)}
                        disabled={!isAdmin}
                        className="w-4 h-4 accent-brand-primary cursor-pointer"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="font-bold text-text-secondary">Reply Style</label>
                        <select
                          value={settings.reply_style}
                          onChange={(e) => handleSettingsChange('reply_style', e.target.value)}
                          disabled={!isAdmin}
                          className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                        >
                          <option value="Professional">Professional</option>
                          <option value="Friendly">Friendly</option>
                          <option value="Formal">Formal</option>
                        </select>
                      </div>
                      <div className="space-y-1.5">
                        <label className="font-bold text-text-secondary">Reply Length</label>
                        <select
                          value={settings.reply_length}
                          onChange={(e) => handleSettingsChange('reply_length', e.target.value)}
                          disabled={!isAdmin}
                          className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                        >
                          <option value="Short">Short (20-40 words)</option>
                          <option value="Medium">Medium (40-60 words)</option>
                          <option value="Detailed">Detailed (60+ words)</option>
                        </select>
                      </div>
                    </div>
                  </div>
                )}
              </Card>

              {/* SECTION 4: Scheduler Settings */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('scheduler')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Calendar className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">Scheduler Settings</span>
                  </div>
                  {expandedSections.scheduler ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.scheduler && settings && (
                  <div className="p-6 space-y-4 text-xs">
                    <div className="flex items-center justify-between p-3.5 bg-bg-secondary/40 border border-border-color/50 rounded-xl">
                      <div className="space-y-0.5">
                        <p className="font-bold text-text-primary">Automatic Email Checking</p>
                        <p className="text-[10px] text-text-muted">Automatically checks Outlook for new customer emails.</p>
                      </div>
                      <input
                        type="checkbox"
                        checked={settings.scheduler_enabled}
                        onChange={(e) => handleSettingsChange('scheduler_enabled', e.target.checked)}
                        disabled={!isAdmin}
                        className="w-4 h-4 accent-brand-primary cursor-pointer"
                      />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="font-bold text-text-secondary">Check Frequency</label>
                        <select
                          value={settings.scheduler_interval_minutes}
                          onChange={(e) => handleSettingsChange('scheduler_interval_minutes', parseInt(e.target.value))}
                          disabled={!isAdmin}
                          className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                        >
                          <option value="5">Every 5 Minutes</option>
                          <option value="10">Every 10 Minutes</option>
                          <option value="15">Every 15 Minutes</option>
                          <option value="30">Every 30 Minutes</option>
                          <option value="45">Every 45 Minutes</option>
                          <option value="60">Every 60 Minutes</option>
                          <option value="90">Every 90 Minutes</option>
                          <option value="120">Every 120 Minutes</option>
                        </select>
                      </div>

                      <div className="space-y-1.5">
                        <label className="font-bold text-text-secondary">Last Checked</label>
                        <Input
                          type="text"
                          value={formatDate(settings.last_scheduler_run)}
                          disabled={true}
                          className="bg-bg-secondary text-text-muted"
                        />
                      </div>
                    </div>

                    {/* Business Hours Settings */}
                    <div className="border-t border-border-color/50 pt-4 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="space-y-0.5">
                          <p className="font-bold text-text-secondary">Business Hours Only</p>
                          <p className="text-[10px] text-text-muted">Only check customer emails during business hours.</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={settings.business_hours_enabled}
                          onChange={(e) => handleSettingsChange('business_hours_enabled', e.target.checked)}
                          disabled={!isAdmin}
                          className="w-4 h-4 accent-brand-primary cursor-pointer"
                        />
                      </div>

                      {settings.business_hours_enabled && (
                        <div className="space-y-3 p-4 bg-bg-secondary/40 border border-border-color/40 rounded-xl">
                          <div className="space-y-1.5">
                            <label className="font-bold text-text-secondary">Working Days</label>
                            <div className="flex flex-wrap gap-2">
                              {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map(day => {
                                const selected = settings.working_days.includes(day);
                                return (
                                  <button
                                    key={day}
                                    type="button"
                                    onClick={() => toggleWorkingDay(day)}
                                    disabled={!isAdmin}
                                    className={`px-3 py-1 rounded-md text-[10px] font-bold border transition-colors ${
                                      selected 
                                        ? 'bg-brand-primary text-white border-transparent' 
                                        : 'bg-bg-surface text-text-secondary border-border-color hover:bg-bg-secondary'
                                    }`}
                                  >
                                    {day}
                                  </button>
                                );
                              })}
                            </div>
                          </div>

                          <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                              <label className="font-bold text-text-secondary">Working Hours Start</label>
                              <Input
                                type="time"
                                value={settings.start_time}
                                onChange={(e) => handleSettingsChange('start_time', e.target.value)}
                                disabled={!isAdmin}
                              />
                            </div>
                            <div className="space-y-1.5">
                              <label className="font-bold text-text-secondary">Working Hours End</label>
                              <Input
                                type="time"
                                value={settings.end_time}
                                onChange={(e) => handleSettingsChange('end_time', e.target.value)}
                                disabled={!isAdmin}
                              />
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </Card>

              {/* SECTION 6: Email Integration Settings */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('outlook')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <RefreshCw className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">Email Integration Settings</span>
                  </div>
                  {expandedSections.outlook ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.outlook && outlook && (
                  <div className="p-6 space-y-6 text-xs">
                    {/* Active Integration Status */}
                    <div className="p-4 bg-bg-secondary/20 border border-border-color/40 rounded-xl space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-text-secondary">Current Active Integration:</span>
                        <Badge variant={outlook.connected ? 'success' : 'danger'}>
                          {outlook.connected ? (outlook.provider === 'smtp' ? 'SMTP/IMAP' : 'Microsoft 365') : 'No Active Integration'}
                        </Badge>
                      </div>
                      {outlook.connected && (
                        <>
                          <p className="text-text-secondary">
                            Account: <span className="font-semibold text-text-primary">{outlook.connected_account}</span>
                          </p>
                          <p className="text-[10px] text-text-muted">
                            Last Sync/Activity: {formatDate(outlook.last_sync)}
                          </p>
                        </>
                      )}
                    </div>

                    {/* Provider Selector */}
                    {isAdmin && (
                      <div className="flex gap-4 border-b border-border-color/50 pb-4">
                        <button
                          type="button"
                          onClick={() => setSelectedProvider('microsoft_graph')}
                          className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors ${
                            selectedProvider === 'microsoft_graph'
                              ? 'bg-brand-primary text-white'
                              : 'bg-bg-secondary text-text-secondary hover:bg-bg-secondary/80'
                          }`}
                        >
                          Microsoft 365 (OAuth)
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedProvider('smtp')}
                          className={`px-4 py-2 text-xs font-bold rounded-lg transition-colors ${
                            selectedProvider === 'smtp'
                              ? 'bg-brand-primary text-white'
                              : 'bg-bg-secondary text-text-secondary hover:bg-bg-secondary/80'
                          }`}
                        >
                          SMTP / IMAP
                        </button>
                      </div>
                    )}

                    {/* Microsoft 365 Integration Block */}
                    {selectedProvider === 'microsoft_graph' && (
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
                        <div className="space-y-1">
                          <p className="font-bold text-text-secondary">Microsoft 365 (via Outlook REST API)</p>
                          <p className="text-[10px] text-text-muted">Connect your corporate email mailbox securely via OAuth authorization.</p>
                        </div>
                        {isAdmin && (
                          <div className="flex gap-2">
                            <Button 
                              variant={outlook.connected && outlook.provider === 'microsoft_graph' ? 'secondary' : 'primary'} 
                              size="sm" 
                              onClick={handleReconnectOutlook}
                            >
                              {outlook.connected && outlook.provider === 'microsoft_graph' ? 'Reconnect' : 'Connect Account'}
                            </Button>
                            {outlook.connected && outlook.provider === 'microsoft_graph' && (
                              <Button 
                                variant="danger" 
                                size="sm" 
                                onClick={handleDisconnectOutlook}
                              >
                                Disconnect
                              </Button>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* SMTP/IMAP Manual Form Block */}
                    {selectedProvider === 'smtp' && (
                      <div className="space-y-4 pt-2">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border-color/30 pb-4">
                          <div className="space-y-1">
                            <p className="font-bold text-text-secondary">SMTP & IMAP Mail Server</p>
                            <p className="text-[10px] text-text-muted">Configure outbound and inbound mail server settings manually or use a provider preset.</p>
                          </div>
                          {outlook.connected && outlook.provider === 'smtp' && isAdmin && (
                            <Button 
                              variant="danger" 
                              size="sm" 
                              onClick={handleDisconnectSmtp}
                            >
                              Disconnect SMTP/IMAP
                            </Button>
                          )}
                        </div>

                        {isAdmin && (
                          <div className="space-y-4">
                            {/* Preset Selector */}
                            <div className="space-y-1.5">
                              <label className="font-bold text-text-secondary">Choose Provider Preset</label>
                              <select
                                value={selectedPreset}
                                onChange={(e) => handlePresetChange(e.target.value)}
                                className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                              >
                                <option value="custom">Custom (SMTP/IMAP)</option>
                                {Object.keys(presets).map((key) => (
                                  <option key={key} value={key}>
                                    {presets[key].name}
                                  </option>
                                ))}
                              </select>
                            </div>

                            {/* Credentials */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="space-y-1.5">
                                <label className="font-bold text-text-secondary">Mailbox Email</label>
                                <Input
                                  type="email"
                                  placeholder="sales@company.com"
                                  value={mailboxEmail}
                                  onChange={(e) => onFieldChange(setMailboxEmail, e.target.value)}
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="font-bold text-text-secondary">Auth Username (Optional)</label>
                                <Input
                                  type="text"
                                  placeholder="Defaults to mailbox email"
                                  value={authUsername}
                                  onChange={(e) => onFieldChange(setAuthUsername, e.target.value)}
                                />
                              </div>
                            </div>

                            <div className="space-y-1.5">
                              <label className="font-bold text-text-secondary">Password</label>
                              <Input
                                type="password"
                                placeholder={password === '__UNCHANGED__' ? '•••••••• (Password Saved)' : 'Enter password'}
                                value={password === '__UNCHANGED__' ? '' : password}
                                onChange={(e) => onFieldChange(setPassword, e.target.value)}
                              />
                            </div>

                            {/* Server Configurations */}
                            <div className="border-t border-border-color/30 pt-4 space-y-4">
                              <p className="font-bold text-text-secondary">Outgoing Server (SMTP)</p>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">SMTP Host</label>
                                  <Input
                                    type="text"
                                    placeholder="smtp.domain.com"
                                    value={smtpHost}
                                    onChange={(e) => onFieldChange(setSmtpHost, e.target.value)}
                                  />
                                </div>
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">SMTP Port</label>
                                  <Input
                                    type="text"
                                    placeholder="465"
                                    value={smtpPort}
                                    onChange={(e) => onFieldChange(setSmtpPort, e.target.value)}
                                  />
                                </div>
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">SMTP Security</label>
                                  <select
                                    value={smtpSecurity}
                                    onChange={(e) => onFieldChange(setSmtpSecurity, e.target.value)}
                                    className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                                  >
                                    <option value="ssl_tls">SSL / TLS</option>
                                    <option value="starttls">STARTTLS</option>
                                    <option value="none">None (Plaintext)</option>
                                  </select>
                                </div>
                              </div>
                            </div>

                            <div className="border-t border-border-color/30 pt-4 space-y-4">
                              <p className="font-bold text-text-secondary">Incoming Server (IMAP)</p>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">IMAP Host</label>
                                  <Input
                                    type="text"
                                    placeholder="imap.domain.com"
                                    value={imapHost}
                                    onChange={(e) => onFieldChange(setImapHost, e.target.value)}
                                  />
                                </div>
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">IMAP Port</label>
                                  <Input
                                    type="text"
                                    placeholder="993"
                                    value={imapPort}
                                    onChange={(e) => onFieldChange(setImapPort, e.target.value)}
                                  />
                                </div>
                                <div className="space-y-1.5">
                                  <label className="font-bold text-text-secondary">IMAP Security</label>
                                  <select
                                    value={imapSecurity}
                                    onChange={(e) => onFieldChange(setImapSecurity, e.target.value)}
                                    className="w-full rounded-lg border border-border-color bg-bg-surface px-3 py-2 text-xs text-text-primary focus:border-brand-primary focus:outline-none font-bold text-text-secondary"
                                  >
                                    <option value="ssl_tls">SSL / TLS</option>
                                    <option value="starttls">STARTTLS</option>
                                    <option value="none">None (Plaintext)</option>
                                  </select>
                                </div>
                              </div>
                            </div>

                            {/* Notifications */}
                            {smtpError && (
                              <Alert variant="danger" title="Integration Error" description={smtpError} />
                            )}
                            {smtpSuccess && (
                              <Alert variant="success" title="Success" description={smtpSuccess} />
                            )}

                            {/* SMTP Action Buttons */}
                            <div className="flex gap-3 pt-2 border-t border-border-color/30">
                              <Button
                                type="button"
                                variant="secondary"
                                size="sm"
                                disabled={testingConnection || !mailboxEmail || !smtpHost || !smtpPort || !imapHost || !imapPort || !password}
                                onClick={handleTestSmtp}
                              >
                                {testingConnection ? 'Testing Connection...' : 'Test Connection'}
                              </Button>

                              <Button
                                type="button"
                                variant="primary"
                                size="sm"
                                disabled={savingSmtp || !testSuccess}
                                onClick={handleConnectSmtp}
                              >
                                {savingSmtp ? 'Saving Integration...' : 'Save Configuration'}
                              </Button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </Card>

              {/* SECTION 7: System Info */}
              <Card padding="none" className="overflow-hidden border border-border-color">
                <div 
                  onClick={() => toggleSection('system')}
                  className="flex items-center justify-between p-5 bg-bg-secondary/40 border-b border-border-color cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <Info className="w-4.5 h-4.5 text-text-secondary" />
                    <span className="text-sm font-bold text-text-primary">System Information</span>
                  </div>
                  {expandedSections.system ? <ChevronUp className="w-4 h-4 text-text-muted" /> : <ChevronDown className="w-4 h-4 text-text-muted" />}
                </div>

                {expandedSections.system && system && (
                  <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                    <div className="space-y-1">
                      <span className="font-bold text-text-muted">Organization ID</span>
                      <p className="font-mono text-text-secondary tracking-tight select-all">{system.organization_id}</p>
                    </div>
                    <div className="space-y-1">
                      <span className="font-bold text-text-muted">Current Plan</span>
                      <p className="font-semibold text-text-primary uppercase tracking-wider">{system.current_plan}</p>
                    </div>
                    <div className="space-y-1">
                      <span className="font-bold text-text-muted">Created Date</span>
                      <p className="text-text-secondary">{formatDate(system.created_date)}</p>
                    </div>
                    <div className="space-y-1">
                      <span className="font-bold text-text-muted">AI Sales Employee Version</span>
                      <p className="text-text-secondary font-mono">{system.ai_sales_employee_version}</p>
                    </div>
                  </div>
                )}
              </Card>
            </div>
          )}
        </div>
      </PageWrapper>
    </AppShell>
  );
}
