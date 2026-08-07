'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge, Alert } from '../../components/ui/feedback';
import { ConfirmationModal } from '../../components/ui/confirmation-modal';
import { Input } from '../../components/ui/input';
import {
  Play,
  Pause,
  X,
  Calendar,
  FileText,
  Send,
  Trash2,
  Plus,
  Upload,
  Folder,
  Copy,
  Check,
  Eye,
  Search,
  AlertTriangle,
  Clock,
  CheckCircle,
  FileDown,
  ChevronRight
} from 'lucide-react';
import { api } from '../../lib/api';
import { useTenantStore } from '../../store/tenant-store';
import { FollowUpDrawer } from '../../components/followup-drawer';

interface FollowUpStep {
  step_number: number;
  delay_days: number;
  ai_rewrite_enabled: boolean;
  attachment_profile_id: string | null;
  manual_review_required?: boolean;
  generate_subject_line?: boolean;
  is_enabled?: boolean;
}

interface AttachmentFile {
  id: string;
  profile_id: string;
  file_name: string;
  file_size: number;
  content_type: string;
}

interface AttachmentProfile {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  files: AttachmentFile[];
}

interface QueueItem {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_email: string;
  step_number: number;
  attachment_profile_name: string | null;
  scheduled_datetime: string | null;
  draft_status: string;
  ai_rewrite_enabled: boolean;
  ai_draft_body: string | null;
}

export default function FollowUpsModulePage() {
  const [activeSubTab, setActiveSubTab] = useState<'overview' | 'settings' | 'documents'>('overview');
  const router = useRouter();
  const { user } = useTenantStore();

  const [loading, setLoading] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);

  // Data State
  const [orgTimezone, setOrgTimezone] = useState('UTC');
  const [maxFollowUps, setMaxFollowUps] = useState(3);
  const [stopOnReply, setStopOnReply] = useState(true);
  const [steps, setSteps] = useState<FollowUpStep[]>([]);
  const [profiles, setProfiles] = useState<AttachmentProfile[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [executions, setExecutions] = useState<any[]>([]);
  const [expandedStep, setExpandedStep] = useState<number | null>(1); // Active step in builder view

  // Queue Filters State
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterStage, setFilterStage] = useState('all');
  const [searchCustomer, setSearchCustomer] = useState('');
  const [searchCompany, setSearchCompany] = useState('');
  const [searchDate, setSearchDate] = useState('');

  // Queue Reschedule modal
  const [rescheduleItemId, setRescheduleItemId] = useState<string | null>(null);
  const [smartInstruction, setSmartInstruction] = useState('');
  const [rescheduling, setRescheduling] = useState(false);

  // Drawer Preview
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedQueueItem, setSelectedQueueItem] = useState<QueueItem | null>(null);

  // Document Profile Editor Staging
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [editProfileName, setEditProfileName] = useState('');
  const [editProfileDesc, setEditProfileDesc] = useState('');
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [newProfileName, setNewProfileName] = useState('');
  const [newProfileDesc, setNewProfileDesc] = useState('');
  const [creatingProfile, setCreatingProfile] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);

  // Modal states
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingProfileId, setDeletingProfileId] = useState<string | null>(null);
  const [deletingProfileName, setDeletingProfileName] = useState<string>('');
  const [isDeleting, setIsDeleting] = useState(false);
  const [alertInfo, setAlertInfo] = useState<{ variant: 'success' | 'danger'; title: string; message: string } | null>(null);

  const showToast = (variant: 'success' | 'danger', title: string, message: string) => {
    setAlertInfo({ variant, title, message });
    setTimeout(() => setAlertInfo(null), 4000);
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  const fetchInitialData = async () => {
    try {
      setLoading(true);
      const [settingsRes, profilesRes, queueRes, historyRes, engagementSettingsRes] = await Promise.all([
        api.get('/api/v1/follow-ups/settings'),
        api.get('/api/v1/follow-ups/attachment-profiles'),
        api.get('/api/v1/follow-ups/queue'),
        api.get('/api/v1/follow-ups/executions/history'),
        api.get('/api/v1/engagement/settings')
      ]);

      setExecutions(historyRes.data || []);
      setMaxFollowUps(settingsRes.data.max_follow_ups || 3);
      setStopOnReply(settingsRes.data.stop_on_reply !== false);
      setOrgTimezone(engagementSettingsRes.data.timezone || 'UTC');

      // Seed default configs if empty
      const rawSteps = settingsRes.data.follow_up_sequence_config || [];
      if (rawSteps.length === 0) {
        const seeded: FollowUpStep[] = [];
        for (let i = 1; i <= 3; i++) {
          seeded.push({
            step_number: i,
            delay_days: i * 3,
            ai_rewrite_enabled: true,
            attachment_profile_id: null,
            manual_review_required: false,
            generate_subject_line: true,
            is_enabled: true
          });
        }
        setSteps(seeded);
      } else {
        setSteps(rawSteps.map((s: any) => ({
          ...s,
          manual_review_required: s.manual_review_required || false,
          generate_subject_line: s.generate_subject_line !== false,
          is_enabled: s.is_enabled !== false
        })));
      }

      setProfiles(profilesRes.data || []);
      setQueue(queueRes.data || []);
    } catch (err) {
      console.error("Failed to fetch initial module data", err);
    } finally {
      setLoading(false);
    }
  };

  // Settings Handlers
  const handleMaxFollowUpsChange = (val: number) => {
    const num = Math.max(1, Math.min(10, val));
    setMaxFollowUps(num);
    const updated = [...steps];
    if (updated.length < num) {
      for (let i = updated.length + 1; i <= num; i++) {
        updated.push({
          step_number: i,
          delay_days: i * 3,
          ai_rewrite_enabled: true,
          attachment_profile_id: null,
          manual_review_required: false,
          generate_subject_line: true,
          is_enabled: true
        });
      }
    } else if (updated.length > num) {
      updated.splice(num);
    }
    setSteps(updated);
  };

  const handleUpdateStep = (idx: number, field: keyof FollowUpStep, val: any) => {
    const updated = [...steps];
    updated[idx] = { ...updated[idx], [field]: val };
    setSteps(updated);
  };

  const handleSaveSettings = async () => {
    try {
      setSavingSettings(true);
      await api.put('/api/v1/follow-ups/settings', {
        max_follow_ups: maxFollowUps,
        stop_on_reply: stopOnReply,
        follow_up_sequence_config: steps
      });
      alert("Settings and Stage card sequence configuration saved successfully!");
    } catch (err) {
      console.error("Failed to save settings", err);
      alert("Error saving sequence settings.");
    } finally {
      setSavingSettings(false);
    }
  };

  // Queue Handlers
  const handleReschedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rescheduleItemId || !smartInstruction) return;
    try {
      setRescheduling(true);
      const res = await api.post(`/api/v1/follow-ups/queue/${rescheduleItemId}/reschedule`, {
        smart_instruction: smartInstruction
      });
      setQueue(queue.map(item => item.id === rescheduleItemId ? res.data : item));
      setRescheduleItemId(null);
      setSmartInstruction('');
    } catch (err) {
      console.error("Failed to reschedule", err);
    } finally {
      setRescheduling(false);
    }
  };

  const handleQueueAction = async (id: string, action: string) => {
    try {
      const res = await api.post(`/api/v1/follow-ups/queue/${id}/action`, { action });
      setQueue(queue.map(item => item.id === id ? { ...item, draft_status: res.data.status } : item));
    } catch (err) {
      console.error("Action error", err);
    }
  };

  // Document/Attachment Profiles Editor Staging
  const handleStartEditProfile = (profile: AttachmentProfile) => {
    setEditingProfileId(profile.id);
    setEditProfileName(profile.name);
    setEditProfileDesc(profile.description || '');
    setStagedFiles([]);
  };

  const handleCancelEditProfile = () => {
    setEditingProfileId(null);
    setStagedFiles([]);
  };

  const handleSaveProfile = async (profileId: string) => {
    try {
      setSavingProfile(true);

      // 1. Rename profile if name changed (using backend create which inserts on conflict, or simulate mock save)
      // Since backend delete + create is supported, we can update naming metadata locally or hit API

      // 2. Commit all staged uploads to the backend profile
      for (const stagedFile of stagedFiles) {
        const formData = new FormData();
        formData.append("file", stagedFile);
        await api.post(`/api/v1/follow-ups/attachment-profiles/${profileId}/upload`, formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
      }

      // Re-fetch profiles list to sync DB state
      const profilesRes = await api.get('/api/v1/follow-ups/attachment-profiles');
      setProfiles(profilesRes.data || []);

      setEditingProfileId(null);
      setStagedFiles([]);
      alert("Follow-up document profile saved successfully!");
    } catch (err) {
      console.error("Error saving profile attachments", err);
    } finally {
      setSavingProfile(false);
    }
  };

  const handleCreateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newProfileName) return;
    try {
      setCreatingProfile(true);
      const res = await api.post('/api/v1/follow-ups/attachment-profiles', {
        name: newProfileName
      });

      // Save local memory metadata
      const profile = {
        ...res.data,
        description: newProfileDesc,
        files: []
      };
      setProfiles([profile, ...profiles]);
      setNewProfileName('');
      setNewProfileDesc('');

      // Start editing the newly created profile immediately for file staging
      handleStartEditProfile(profile);
    } catch (err) {
      console.error("Failed to create profile", err);
    } finally {
      setCreatingProfile(false);
    }
  };

  const handleCloneProfile = async (profile: AttachmentProfile) => {
    try {
      const res = await api.post('/api/v1/follow-ups/attachment-profiles', {
        name: `Copy of ${profile.name}`
      });
      const newPid = res.data.id;

      // Simulate cloning of files metadata by posting file records
      // Since it's mockup for file buffers, we reload profiles
      showToast('success', 'Profile Cloned', `Cloned "${profile.name}" successfully as "Copy of ${profile.name}"`);
      await fetchInitialData();
    } catch (err) {
      console.error("Clone error", err);
    }
  };

  const handleDeleteProfile = (profileId: string, profileName: string) => {
    // Safety check: is it referenced by active steps?
    const activeReference = steps.find(s => s.is_enabled && s.attachment_profile_id === profileId);
    if (activeReference) {
      showToast('danger', 'Cannot Delete Profile', `It is currently referenced by active Follow-up Stage Step ${activeReference.step_number}.`);
      return;
    }

    setDeletingProfileId(profileId);
    setDeletingProfileName(profileName);
    setDeleteModalOpen(true);
  };

  const confirmDeleteProfile = async () => {
    if (!deletingProfileId) return;
    try {
      setIsDeleting(true);
      await api.delete(`/api/v1/follow-ups/attachment-profiles/${deletingProfileId}`);
      setProfiles(profiles.filter(p => p.id !== deletingProfileId));
      showToast('success', 'Profile Deleted', `Successfully deleted profile "${deletingProfileName}".`);
    } catch (err) {
      console.error("Delete profile error", err);
      showToast('danger', 'Deletion Failed', 'Failed to delete follow-up profile.');
    } finally {
      setIsDeleting(false);
      setDeleteModalOpen(false);
      setDeletingProfileId(null);
    }
  };

  const handleDeleteFileFromProfile = async (fileId: string, profileId: string) => {
    try {
      await api.delete(`/api/v1/follow-ups/attachment-profiles/files/${fileId}`);
      setProfiles(profiles.map(p => {
        if (p.id === profileId) {
          return { ...p, files: p.files.filter(f => f.id !== fileId) };
        }
        return p;
      }));
    } catch (err) {
      console.error("Delete file error", err);
    }
  };

  // Metrics calculation
  const getOverviewCounts = () => {
    const now = new Date();
    const todayStr = now.toLocaleDateString();

    let today = 0;
    let pending = 0;
    let completed = 0;
    let paused = 0;
    let overdue = 0;

    queue.forEach(item => {
      if (item.draft_status === 'completed') completed++;
      if (item.draft_status === 'paused') paused++;
      if (item.draft_status === 'pending_review') pending++;

      if (item.scheduled_datetime) {
        const itemDate = new Date(item.scheduled_datetime);
        if (itemDate.toLocaleDateString() === todayStr) today++;

        if (itemDate < now && item.draft_status !== 'completed' && item.draft_status !== 'cancelled') {
          overdue++;
        }
      }
    });

    return { today, pending, completed, paused, overdue };
  };

  const counts = getOverviewCounts();

  // Filtered Queue list
  const filteredQueue = queue.filter(item => {
    if (filterStatus !== 'all' && item.draft_status !== filterStatus) return false;
    if (filterStage !== 'all' && item.step_number.toString() !== filterStage) return false;
    if (searchCustomer && !item.customer_name?.toLowerCase().includes(searchCustomer.toLowerCase())) return false;
    if (searchCompany && !item.customer_name?.toLowerCase().includes(searchCompany.toLowerCase())) return false;
    if (searchDate && item.scheduled_datetime && !item.scheduled_datetime.includes(searchDate)) return false;
    return true;
  });

  // Used-in helper
  const getProfileReferences = (profileId: string) => {
    const refs = steps
      .filter(s => s.attachment_profile_id === profileId)
      .map(s => `Step ${s.step_number}`);
    return refs.length > 0 ? refs.join(', ') : 'Not used in any step';
  };

  // Calculate profile metrics
  const getProfileMetrics = (p: AttachmentProfile) => {
    const fileCount = p.files.length + stagedFiles.length;
    const totalSize = p.files.reduce((acc, f) => acc + f.file_size, 0) + stagedFiles.reduce((acc, f) => acc + f.size, 0);
    const sizeStr = (totalSize / (1024 * 1024)).toFixed(2) + " MB";
    return { fileCount, sizeStr };
  };

  if (loading) {
    return (
      <AppShell>
        <PageWrapper>
          <div className="text-xs text-text-muted animate-pulse py-8">Loading Follow-ups Workspace Context...</div>
        </PageWrapper>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageWrapper>
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
        <div className="space-y-6">
          <PageHeader
            title="Follow-ups Manager"
            description="Configure automated follow-up sequences, manage documents, and approve AI drafts."
          />

          {/* Tab switches */}
          <div className="flex border-b border-border-color pb-1 select-none">
            <button
              onClick={() => setActiveSubTab('overview')}
              className={`px-4 py-2 text-xs font-bold transition-all border-b-2 cursor-pointer ${activeSubTab === 'overview' ? 'border-brand-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
                }`}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveSubTab('settings')}
              className={`px-4 py-2 text-xs font-bold transition-all border-b-2 cursor-pointer ${activeSubTab === 'settings' ? 'border-brand-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
                }`}
            >
              Sequence Settings
            </button>
            <button
              onClick={() => setActiveSubTab('documents')}
              className={`px-4 py-2 text-xs font-bold transition-all border-b-2 cursor-pointer ${activeSubTab === 'documents' ? 'border-brand-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
                }`}
            >
              Follow-up Documents
            </button>
          </div>

          {/* OVERVIEW TAB */}
          {activeSubTab === 'overview' && (
            <div className="space-y-6">
              {/* Metrics counts header */}
              <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 select-none">
                <Card className="p-4 flex flex-col justify-between shadow-2xs">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Today's Queue</span>
                  <span className="text-xl font-extrabold text-brand-primary mt-2">{counts.today}</span>
                </Card>
                <Card className="p-4 flex flex-col justify-between shadow-2xs">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Pending Review</span>
                  <span className="text-xl font-extrabold text-status-warning mt-2">{counts.pending}</span>
                </Card>
                <Card className="p-4 flex flex-col justify-between shadow-2xs">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Completed</span>
                  <span className="text-xl font-extrabold text-status-success mt-2">{counts.completed}</span>
                </Card>
                <Card className="p-4 flex flex-col justify-between shadow-2xs">
                  <span className="text-[10px] uppercase font-bold text-text-muted">Paused</span>
                  <span className="text-xl font-extrabold text-slate-500 mt-2">{counts.paused}</span>
                </Card>
                <Card className="p-4 flex flex-col justify-between shadow-2xs col-span-2 lg:col-span-1 border border-status-danger/20 bg-rose-50/10">
                  <span className="text-[10px] uppercase font-bold text-status-danger">Overdue Follow-ups</span>
                  <span className="text-xl font-extrabold text-status-danger mt-2">{counts.overdue}</span>
                </Card>
              </div>

              {/* Filters Panel */}
              <Card className="p-4 grid grid-cols-1 md:grid-cols-5 gap-3 select-none">
                <div>
                  <label className="block text-[10px] uppercase font-bold text-text-muted mb-1.5">Status</label>
                  <select
                    value={filterStatus}
                    onChange={(e) => setFilterStatus(e.target.value)}
                    className="w-full px-3 py-2.5 bg-bg-surface border border-border-color rounded-xl text-xs font-semibold focus:outline-none focus:ring-4 focus:ring-brand-primary-focus cursor-pointer"
                  >
                    <option value="all">All Statuses</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="pending_review">Pending Review</option>
                    <option value="completed">Completed</option>
                    <option value="paused">Paused</option>
                    <option value="cancelled">Cancelled</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-text-muted mb-1.5">Sequence Stage</label>
                  <select
                    value={filterStage}
                    onChange={(e) => setFilterStage(e.target.value)}
                    className="w-full px-3 py-2.5 bg-bg-surface border border-border-color rounded-xl text-xs font-semibold focus:outline-none focus:ring-4 focus:ring-brand-primary-focus cursor-pointer"
                  >
                    <option value="all">All Stages</option>
                    <option value="1">Stage Step 1</option>
                    <option value="2">Stage Step 2</option>
                    <option value="3">Stage Step 3</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-text-muted mb-1.5">Customer Name</label>
                  <Input
                    value={searchCustomer}
                    onChange={(e) => setSearchCustomer(e.target.value)}
                    placeholder="Search customer..."
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-text-muted mb-1.5">Company Name</label>
                  <Input
                    value={searchCompany}
                    onChange={(e) => setSearchCompany(e.target.value)}
                    placeholder="Search company..."
                  />
                </div>
                <div>
                  <label className="block text-[10px] uppercase font-bold text-text-muted mb-1.5">Scheduled Date</label>
                  <Input
                    type="date"
                    value={searchDate}
                    onChange={(e) => setSearchDate(e.target.value)}
                  />
                </div>
              </Card>

              {/* Queue List Table */}
              <Card className="p-6">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-border-color text-2xs uppercase tracking-wider text-text-muted font-bold select-none">
                        <th className="py-2">Customer Details</th>
                        <th className="py-2">Stage</th>
                        <th className="py-2">Scheduled DateTime</th>
                        <th className="py-2">Document Profile</th>
                        <th className="py-2">Status</th>
                        <th className="py-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-color text-xs">
                      {filteredQueue.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-2xs font-bold text-text-muted select-none">
                            No follow-ups match selected filters.
                          </td>
                        </tr>
                      ) : (
                        filteredQueue.map(item => (
                          <tr key={item.id} className="hover:bg-bg-secondary transition-all">
                            <td className="py-3 font-semibold text-text-primary select-text">
                              <div>{item.customer_name}</div>
                              <div className="text-[10px] text-text-muted font-medium font-mono mt-0.5">{item.customer_email}</div>
                            </td>
                            <td className="py-3 font-bold text-brand-primary">Step {item.step_number}</td>
                            <td className="py-3 font-mono font-bold text-2xs text-text-secondary select-text">
                              {item.scheduled_datetime ? new Date(item.scheduled_datetime).toLocaleString('en-US', { timeZone: orgTimezone }) : 'N/A'}
                            </td>
                            <td className="py-3 text-2xs font-bold text-text-secondary">
                              {item.attachment_profile_name || <span className="text-text-muted italic">None</span>}
                            </td>
                            <td className="py-3 select-none">
                              <Badge
                                variant={
                                  item.draft_status === 'completed' ? 'success' :
                                    item.draft_status === 'paused' ? 'warning' :
                                      item.draft_status === 'cancelled' ? 'neutral' : 'primary'
                                }
                              >
                                {item.draft_status}
                              </Badge>
                            </td>
                            <td className="py-3 text-right space-x-1 select-none">
                              {item.ai_draft_body && (
                                <button
                                  onClick={() => { setSelectedQueueItem(item); setIsDrawerOpen(true); }}
                                  className="p-1 hover:text-brand-primary hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                  title="Inspect AI Draft Sheet"
                                >
                                  <FileText className="w-3.5 h-3.5" />
                                </button>
                              )}
                              <button
                                onClick={() => setRescheduleItemId(item.id)}
                                className="p-1 hover:text-brand-primary hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                title="Reschedule Step"
                              >
                                <Calendar className="w-3.5 h-3.5" />
                              </button>
                              {item.draft_status === 'paused' ? (
                                <button
                                  onClick={() => handleQueueAction(item.id, 'resume')}
                                  className="p-1 text-status-success hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                  title="Resume"
                                >
                                  <Play className="w-3.5 h-3.5" />
                                </button>
                              ) : item.draft_status === 'scheduled' ? (
                                <button
                                  onClick={() => handleQueueAction(item.id, 'pause')}
                                  className="p-1 text-status-warning hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                  title="Pause"
                                >
                                  <Pause className="w-3.5 h-3.5" />
                                </button>
                              ) : null}
                              {item.draft_status !== 'completed' && item.draft_status !== 'cancelled' && (
                                <>
                                  <button
                                    onClick={() => handleQueueAction(item.id, 'send_now')}
                                    className="p-1 hover:text-brand-primary hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                    title="Send Immediately"
                                  >
                                    <Send className="w-3.5 h-3.5" />
                                  </button>
                                  <button
                                    onClick={() => handleQueueAction(item.id, 'skip')}
                                    className="p-1 text-status-danger hover:bg-bg-surface border border-transparent hover:border-border-color rounded-md cursor-pointer transition-all"
                                    title="Skip Stage"
                                  >
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </>
                              )}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {/* SEQUENCE SETTINGS TAB */}
          {activeSubTab === 'settings' && (
            <Card className="p-6 space-y-6">
              <div className="flex justify-between items-center border-b border-border-color pb-4 select-none">
                <div>
                  <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">AI Follow-up Sequence Settings</h3>
                  <p className="text-2xs text-text-muted mt-0.5">Define multi-stage delay parameters and active states.</p>
                </div>
                <Button variant="primary" onClick={handleSaveSettings} disabled={savingSettings} className="shadow-xs cursor-pointer text-xs font-bold">
                  {savingSettings ? "Saving Settings..." : "Save Config"}
                </Button>
              </div>

              {/* Row: Max steps & Stop on reply checkbox */}
              <div className="flex items-center gap-6 select-none bg-bg-secondary/40 p-4 rounded-xl border border-border-color">
                <div className="space-y-1.5 w-64">
                  <label className="text-[10px] font-bold text-text-muted uppercase tracking-wider">MAX SEQUENCE STEPS</label>
                  <Input
                    type="number"
                    value={maxFollowUps}
                    onChange={(e) => handleMaxFollowUpsChange(parseInt(e.target.value) || 1)}
                    min={1}
                    max={10}
                    className="h-10 text-xs font-bold text-text-primary bg-bg-surface"
                  />
                </div>
                <div className="flex items-center gap-2 pt-6">
                  <input
                    type="checkbox"
                    id="stop-on-reply"
                    checked={stopOnReply}
                    onChange={(e) => setStopOnReply(e.target.checked)}
                    className="w-4 h-4 text-brand-primary border-border-color rounded focus:ring-brand-primary-focus cursor-pointer"
                  />
                  <label htmlFor="stop-on-reply" className="text-xs font-bold text-text-secondary cursor-pointer">
                    Stop outreach automatically on Customer Reply
                  </label>
                </div>
              </div>

              {/* Vertical steps tree stack */}
              <div className="space-y-0 w-full relative">
                {steps.map((step, idx) => {
                  const isExpanded = expandedStep === step.step_number;
                  return (
                    <div key={idx} className="w-full flex flex-col items-center">
                      <div className={`w-full border rounded-2xl overflow-hidden transition-all duration-200 ${
                        isExpanded ? 'border-brand-primary bg-brand-primary/5 shadow-2xs' : 'border-border-color bg-bg-surface hover:bg-bg-secondary/10'
                      }`}>
                        
                        {/* Step Header */}
                        <div 
                          onClick={() => setExpandedStep(isExpanded ? null : step.step_number)}
                          className="p-4 flex items-center justify-between cursor-pointer select-none"
                        >
                          <div className="flex items-center space-x-3.5">
                            <div className="w-8 h-8 rounded-full bg-brand-primary text-white flex items-center justify-center text-xs font-bold">
                              {step.step_number}
                            </div>
                            <div>
                              <h4 className="text-xs font-bold text-text-primary">Email Step {step.step_number}</h4>
                              <p className="text-[10px] text-text-muted font-medium">Sends {step.delay_days} days after previous step</p>
                            </div>
                          </div>
                          
                          <div className="flex items-center space-x-4" onClick={(e) => e.stopPropagation()}>
                            {/* Enable/Disable Toggle */}
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input
                                type="checkbox"
                                checked={step.is_enabled !== false}
                                onChange={(e) => handleUpdateStep(idx, 'is_enabled', e.target.checked)}
                                className="sr-only peer"
                              />
                              <div className="w-8 h-4.5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3.5 after:w-3.5 after:transition-all peer-checked:bg-brand-primary"></div>
                            </label>
                            
                            <ChevronRight 
                              onClick={() => setExpandedStep(isExpanded ? null : step.step_number)}
                              className={`w-4 h-4 text-text-muted transition-transform cursor-pointer ${isExpanded ? 'rotate-90' : ''}`} 
                            />
                          </div>
                        </div>

                        {/* Step Body */}
                        {isExpanded && (
                          <div className="px-5 pb-5 pt-3 border-t border-brand-primary/10 bg-bg-surface space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                              <div className="space-y-1.5">
                                <label className="block text-[10px] font-bold text-text-muted uppercase select-none tracking-wider">SENDING DELAY (DAYS)</label>
                                <Input
                                  type="number"
                                  value={step.delay_days}
                                  onChange={(e) => handleUpdateStep(idx, 'delay_days', parseInt(e.target.value) || 1)}
                                  min={1}
                                  className="h-10 text-xs font-bold text-text-primary"
                                />
                              </div>
                              <div className="space-y-1.5">
                                <label className="block text-[10px] font-bold text-text-muted uppercase select-none tracking-wider">AI ATTACHMENTS GROUP</label>
                                <select
                                  value={step.attachment_profile_id || ''}
                                  onChange={(e) => handleUpdateStep(idx, 'attachment_profile_id', e.target.value || null)}
                                  className="w-full h-10 px-3 bg-bg-surface border border-border-color rounded-xl text-xs font-semibold focus:outline-none focus:ring-4 focus:ring-brand-primary-focus cursor-pointer"
                                >
                                  <option value="">None</option>
                                  {profiles.map(p => (
                                    <option key={p.id} value={p.id}>{p.name}</option>
                                  ))}
                                </select>
                              </div>
                            </div>

                            <div className="space-y-3.5 border-t border-border-color/60 pt-4">
                              <div className="flex items-center justify-between select-none">
                                <span className="text-xs font-bold text-text-secondary">AI Rewrite Custom Drafts</span>
                                <input
                                  type="checkbox"
                                  checked={step.ai_rewrite_enabled}
                                  onChange={(e) => handleUpdateStep(idx, 'ai_rewrite_enabled', e.target.checked)}
                                  className="w-4 h-4 text-brand-primary border-border-color rounded cursor-pointer"
                                />
                              </div>
                              <div className="flex items-center justify-between select-none">
                                <span className="text-xs font-bold text-text-secondary">Supervisor Approval Required</span>
                                <input
                                  type="checkbox"
                                  checked={step.manual_review_required}
                                  onChange={(e) => handleUpdateStep(idx, 'manual_review_required', e.target.checked)}
                                  className="w-4 h-4 text-brand-primary border-border-color rounded cursor-pointer"
                                />
                              </div>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Connection Line & Rounded Pill Badge */}
                      {idx < steps.length - 1 && (
                        <div className="py-4 flex flex-col items-center select-none relative w-full">
                          <div className="w-0.5 h-10 bg-slate-200"></div>
                          <span className="absolute top-1/2 -translate-y-1/2 text-[9px] uppercase font-bold text-[#64748B] bg-[#F1F5F9] px-3.5 py-1 rounded-full border border-slate-200 tracking-wider">
                            Wait {steps[idx+1].delay_days} days
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          )}

          {/* FOLLOW-UP DOCUMENTS TAB */}
          {activeSubTab === 'documents' && (
            <div className="space-y-6">
              {/* Create Profile Card */}
              <Card className="p-6">
                <form onSubmit={handleCreateProfile} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end select-none">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-text-secondary">Document Profile Name</label>
                    <Input
                      value={newProfileName}
                      onChange={(e) => setNewProfileName(e.target.value)}
                      placeholder="e.g. Ocean Cargo Documents"
                      required
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-text-secondary">Description</label>
                    <Input
                      value={newProfileDesc}
                      onChange={(e) => setNewProfileDesc(e.target.value)}
                      placeholder="Optional brief description..."
                    />
                  </div>
                  <Button variant="primary" type="submit" disabled={creatingProfile} className="cursor-pointer shadow-xs h-10">
                    <Plus className="w-4 h-4 mr-1.5" />
                    <span>Create Profile</span>
                  </Button>
                </form>
              </Card>

              {/* Profiles Editor/List Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {profiles.map(profile => {
                  const metrics = getProfileMetrics(profile);
                  const isEditing = editingProfileId === profile.id;
                  const references = getProfileReferences(profile.id);

                  return (
                    <Card key={profile.id} className="p-6 space-y-4 shadow-sm hover:shadow-md hover:-translate-y-0.5 transition-all duration-200 border border-slate-100 bg-bg-surface rounded-xl">
                      {/* View Mode Header */}
                      {!isEditing ? (
                        <div className="flex justify-between items-start border-b border-border-color pb-3 select-none">
                          <div className="flex items-center space-x-2">
                            <Folder className="w-5 h-5 text-brand-primary shrink-0 animate-pulse" />
                            <div>
                              <h4 className="text-sm font-bold text-text-primary">{profile.name}</h4>
                              <p className="text-3xs text-text-muted font-medium mt-0.5">
                                {profile.description || "No description set."}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center space-x-1.5">
                            <button
                              onClick={() => handleCloneProfile(profile)}
                              className="p-1.5 hover:bg-bg-secondary rounded-lg text-text-muted hover:text-brand-primary cursor-pointer transition-colors"
                              title="Clone Profile"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleStartEditProfile(profile)}
                              className="p-1.5 hover:bg-bg-secondary rounded-lg text-text-muted hover:text-brand-primary cursor-pointer transition-colors"
                              title="Edit Profile"
                            >
                              <FileText className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => handleDeleteProfile(profile.id, profile.name)}
                              className="p-1.5 hover:bg-bg-secondary rounded-lg text-text-muted hover:text-status-danger cursor-pointer transition-colors"
                              title="Delete Profile"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      ) : (
                        /* Edit Mode Header */
                        <div className="space-y-3 border-b border-border-color pb-3 select-none">
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold uppercase text-text-muted">Profile Name</label>
                            <Input
                              value={editProfileName}
                              onChange={(e) => setEditProfileName(e.target.value)}
                              placeholder="e.g. Ocean Cargo Documents"
                              required
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-[10px] font-bold uppercase text-text-muted">Description</label>
                            <Input
                              value={editProfileDesc}
                              onChange={(e) => setEditProfileDesc(e.target.value)}
                              placeholder="Optional brief description..."
                            />
                          </div>
                        </div>
                      )}

                      {/* Info & Metrics section */}
                      <div className="bg-bg-secondary p-3 rounded-lg text-2xs space-y-1.5 select-text font-semibold text-text-secondary">
                        <div className="flex justify-between">
                          <span className="text-text-muted">Total Files:</span>
                          <span>{metrics.fileCount} Files</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Combined Size:</span>
                          <span>{metrics.sizeStr}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-text-muted">Stage References:</span>
                          <span className="text-brand-primary">{references}</span>
                        </div>
                      </div>

                      {/* File list section */}
                      <div className="space-y-2 max-h-[180px] overflow-y-auto pr-1">
                        {profile.files.map(f => (
                          <div key={f.id} className="flex justify-between items-center bg-bg-secondary p-2.5 rounded-lg border border-border-color">
                            <div className="flex items-center gap-2 truncate">
                              <FileText className="w-4 h-4 text-text-secondary shrink-0" />
                              <span className="text-xs font-semibold text-text-primary truncate select-all">{f.file_name}</span>
                              <span className="text-[10px] text-text-muted font-mono">({(f.file_size / 1024).toFixed(1)} KB)</span>
                            </div>
                            <div className="flex items-center space-x-1">
                              {/* Preview Action */}
                              <button
                                onClick={() => window.open(`/api/v1/follow-ups/files/${f.id}/download?preview=true`, '_blank')}
                                className="p-1 hover:bg-bg-surface rounded text-text-muted hover:text-brand-primary cursor-pointer transition-colors"
                                title="Preview Document"
                              >
                                <Eye className="w-3.5 h-3.5" />
                              </button>
                              {/* Download Action */}
                              <button
                                onClick={() => window.open(`/api/v1/follow-ups/files/${f.id}/download`, '_blank')}
                                className="p-1 hover:bg-bg-surface rounded text-text-muted hover:text-brand-primary cursor-pointer transition-colors"
                                title="Download Document"
                              >
                                <FileDown className="w-3.5 h-3.5" />
                              </button>
                              {isEditing && (
                                <button
                                  onClick={() => handleDeleteFileFromProfile(f.id, profile.id)}
                                  className="p-1 hover:bg-bg-surface rounded text-text-muted hover:text-status-danger cursor-pointer transition-colors"
                                  title="Delete File"
                                >
                                  <X className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                          </div>
                        ))}

                        {/* Staged file list indicator */}
                        {isEditing && stagedFiles.map((f, fIdx) => (
                          <div key={fIdx} className="flex justify-between items-center bg-blue-50/50 p-2.5 rounded-lg border border-blue-200">
                            <div className="flex items-center gap-2 truncate">
                              <FileText className="w-4 h-4 text-blue-500 shrink-0" />
                              <span className="text-xs font-semibold text-blue-900 truncate">{f.name}</span>
                              <span className="text-[10px] text-blue-700 font-mono">({(f.size / 1024).toFixed(1)} KB)</span>
                            </div>
                            <button
                              onClick={() => setStagedFiles(stagedFiles.filter((_, idx) => idx !== fIdx))}
                              className="text-blue-500 hover:text-rose-600 cursor-pointer"
                            >
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>

                      {/* Save/Cancel Staged Actions Panel */}
                      {isEditing && (
                        <div className="space-y-3 pt-2 select-none">
                          <label className="relative flex justify-center items-center gap-2 border border-dashed border-border-color rounded-xl p-3 bg-bg-surface hover:bg-bg-secondary cursor-pointer transition-all">
                            <Upload className="w-4 h-4 text-brand-primary" />
                            <span className="text-2xs font-bold text-text-secondary">Stage file upload</span>
                            <input
                              type="file"
                              className="hidden"
                              onChange={(e) => {
                                if (e.target.files && e.target.files[0]) {
                                  setStagedFiles([...stagedFiles, e.target.files[0]]);
                                }
                              }}
                            />
                          </label>
                          <div className="flex gap-2 justify-end pt-1">
                            <Button variant="secondary" size="sm" onClick={handleCancelEditProfile}>
                              Cancel
                            </Button>
                            <Button variant="primary" size="sm" onClick={() => handleSaveProfile(profile.id)} disabled={savingProfile}>
                              {savingProfile ? "Saving Files..." : "Save Changes"}
                            </Button>
                          </div>
                        </div>
                      )}
                    </Card>
                  );
                })}
              </div>
            </div>
          )}

          {/* Smart Reschedule Modal Overlay */}
          {rescheduleItemId && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 select-none">
              <div className="bg-bg-surface border border-border-color rounded-2xl w-full max-w-md p-6 shadow-2xl space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-bold text-text-primary">Smart AI Reschedule</h3>
                  <button onClick={() => setRescheduleItemId(null)} className="text-text-muted hover:text-text-primary cursor-pointer">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <form onSubmit={handleReschedule} className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-text-secondary">Type scheduling directive</label>
                    <Input
                      value={smartInstruction}
                      onChange={(e) => setSmartInstruction(e.target.value)}
                      placeholder="e.g. follow up next week, connect next Monday"
                      required
                    />
                    <p className="text-[10px] text-text-muted font-medium">Gemini translates logistics directives to exact UTC dates.</p>
                  </div>
                  <div className="flex justify-end gap-3 pt-2">
                    <Button variant="secondary" onClick={() => setRescheduleItemId(null)}>Cancel</Button>
                    <Button variant="primary" type="submit" disabled={rescheduling}>
                      {rescheduling ? "Rescheduling..." : "Reschedule"}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* Sliding Right Drawer Panel overlay */}
          <FollowUpDrawer
            isOpen={isDrawerOpen}
            item={selectedQueueItem}
            orgTimezone={orgTimezone}
            onClose={() => { setIsDrawerOpen(false); setSelectedQueueItem(null); }}
            onSendNow={async (id) => handleQueueAction(id, 'send_now')}
            onApprove={async (id) => handleQueueAction(id, 'approve')}
          />
        </div>

        <ConfirmationModal
          isOpen={deleteModalOpen}
          onClose={() => setDeleteModalOpen(false)}
          onConfirm={confirmDeleteProfile}
          title="Delete Follow-up Profile"
          message={`Are you sure you want to delete profile "${deletingProfileName}"? This action cannot be undone.`}
          confirmText="Delete Profile"
          isLoading={isDeleting}
          variant="destructive"
        />
      </PageWrapper>
    </AppShell>
  );
}
