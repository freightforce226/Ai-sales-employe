'use client';

import React, { useState, useEffect, useRef } from 'react';
import { api } from '../../lib/api';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper } from '../../components/layout/page-wrapper';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge, Alert } from '../../components/ui/feedback';
import { Input, Select } from '../../components/ui/input';
import { 
  Plus, CheckCircle, AlertTriangle, X, Play, ArrowLeft, Send, 
  Clock, Paperclip, Eye, Upload, Trash2, Calendar, FileText, 
  Settings, Users, ShieldAlert, Check, Copy, ChevronDown, ChevronUp, RefreshCw,
  AlertCircle, CheckCircle2, Info, XCircle
} from 'lucide-react';

interface RecipientItem {
  id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
  country: string;
  shipment_mode: string;
  trade_direction: string;
  industry: string;
  status: string;
  sent_at: string | null;
  delivery_status: string;
  replied_at: string | null;
  last_activity: string | null;
  failure_reason: string | null;
}

interface TenantAttachment {
  id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  storage_path: string;
  created_at?: string;
}

export default function MarketingCampaignsPage() {
  // Navigation tabs: 'overview' | 'execution' | 'settings' | 'attachments'
  const [activeTab, setActiveTab] = useState<'overview' | 'execution' | 'settings' | 'attachments'>('overview');
  
  // Active states
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(true);
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>('');
  
  // Available marketing-specific attachments
  const [availableAttachments, setAvailableAttachments] = useState<TenantAttachment[]>([]);
  const [loadingAvailable, setLoadingAvailable] = useState(false);

  // Recipient list & analytics for chosen campaign
  const [recipients, setRecipients] = useState<RecipientItem[]>([]);
  const [metrics, setMetrics] = useState<any>({
    total_targeted: 0,
    sent: 0,
    delivered: 0,
    opened: 0,
    replied: 0,
    failed: 0,
    open_rate: 0.0,
    reply_rate: 0.0
  });
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);

  // Overview Tab Search & Filters State
  const [searchCompany, setSearchCompany] = useState('');
  const [searchCustomer, setSearchCustomer] = useState('');
  const [filterRegion, setFilterRegion] = useState('all'); // domestic/overseas
  const [filterShipmentMode, setFilterShipmentMode] = useState('all');
  const [filterTradeDir, setFilterTradeDir] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterDate, setFilterDate] = useState('');

  // Settings Configuration State
  const [campaignName, setCampaignName] = useState('');
  const [campaignType, setCampaignType] = useState<'Festival' | 'Sales' | 'Price Drop' | 'Custom' | 'Promotional Services'>('Festival');
  const [sendMode, setSendMode] = useState<'now' | 'schedule'>('now');
  const [scheduledTime, setScheduledTime] = useState('');
  
  // Predefined structured parameters
  const [festivalOccasion, setFestivalOccasion] = useState('Diwali');
  const [festivalContext, setFestivalContext] = useState('');
  
  const [priceDropRoute, setPriceDropRoute] = useState('');
  const [priceDropPrevRate, setPriceDropPrevRate] = useState('');
  const [priceDropNewRate, setPriceDropNewRate] = useState('');
  const [priceDropValidity, setPriceDropValidity] = useState('');
  
  const [salesService, setSalesService] = useState('');
  const [salesOpportunity, setSalesOpportunity] = useState('');
  const [salesValidity, setSalesValidity] = useState('');

  // Promotional Services parameters
  const [promoRegion, setPromoRegion] = useState('');
  const [promoFocus, setPromoFocus] = useState('');
  
  const [additionalInstructions, setAdditionalInstructions] = useState('');

  // Action Loading Status
  const [isLocking, setIsLocking] = useState<Record<string, boolean>>({});
  const [isApproving, setIsApproving] = useState<Record<string, boolean>>({});
  const [isLaunching, setIsLaunching] = useState<Record<string, boolean>>({});

  // Audience filters
  const [enableFilters, setEnableFilters] = useState(false);
  const [audienceFilters, setAudienceFilters] = useState({
    country: '',
    shipment_mode: '',
    trade_direction: '',
    industry: '',
    customer_type: ''
  });

  // Staged files metadata array assigned to this campaign
  const [stagedFiles, setStagedFiles] = useState<{ id: string; name: string; storage_path: string }[]>([]);
  const [uploadingFile, setUploadingFile] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Modal / Feedback logs
  const [errorMsg, setErrorMsg] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string>('');

  interface Toast {
    id: string;
    variant: 'success' | 'danger' | 'warning' | 'info';
    title: string;
    description: string;
  }
  const [toasts, setToasts] = useState<Toast[]>([]);

  const showToast = (variant: 'success' | 'danger' | 'warning' | 'info', title: string, description: string) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts(prev => [...prev, { id, variant, title, description }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 5000);
  };

  useEffect(() => {
    if (successMsg) {
      showToast('success', 'Success', successMsg);
      setSuccessMsg('');
    }
  }, [successMsg]);

  useEffect(() => {
    if (errorMsg) {
      showToast('danger', 'Error', errorMsg);
      setErrorMsg('');
    }
  }, [errorMsg]);

  // Email Log Viewer modal state
  const [selectedEmailLogId, setSelectedEmailLogId] = useState<string | null>(null);
  const [emailLogDetail, setEmailLogDetail] = useState<any | null>(null);
  const [loadingEmailLog, setLoadingEmailLog] = useState(false);

  // Execution Progress state
  const [executionProgress, setExecutionProgress] = useState<{
    campaign_id: string;
    status: string;
    total: number;
    sent: number;
    failed: number;
    pending: number;
    sending: number;
    skipped: number;
    completed: number;
    progress_percent: number;
  } | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(false);

  // Campaign Approval & Edit states
  const [showApprovalModal, setShowApprovalModal] = useState(false);
  const [approvalCampaignId, setApprovalCampaignId] = useState('');
  const [approvalContentId, setApprovalContentId] = useState('');
  const [approvalSubject, setApprovalSubject] = useState('');
  const [approvalHtmlBody, setApprovalHtmlBody] = useState('');
  const [approvalPlainText, setApprovalPlainText] = useState('');
  const [isGeneratingApprovalContent, setIsGeneratingApprovalContent] = useState(false);
  const [isSavingApproval, setIsSavingApproval] = useState(false);

  const fetchExecutionProgress = async (id: string) => {
    if (!id) return;
    setLoadingProgress(true);
    try {
      const res = await api.get(`/api/v1/marketing/campaigns/${id}/execution-progress`);
      setExecutionProgress(res.data);
    } catch (err) {
      console.error("Failed to fetch campaign execution progress metrics:", err);
    } finally {
      setLoadingProgress(false);
    }
  };

  const fetchEmailLogDetail = async (emailLogId: string) => {
    setLoadingEmailLog(true);
    setSelectedEmailLogId(emailLogId);
    try {
      const res = await api.get(`/api/v1/marketing/email-logs/${emailLogId}`);
      setEmailLogDetail(res.data);
    } catch (err) {
      console.error("Failed to fetch email log details", err);
      setErrorMsg("Failed to retrieve outbound email details.");
    } finally {
      setLoadingEmailLog(false);
    }
  };

  // Accordion Expand States
  const [expandInfo, setExpandInfo] = useState(true);
  const [expandParams, setExpandParams] = useState(true);
  const [expandAudience, setExpandAudience] = useState(true);
  const [expandExecution, setExpandExecution] = useState(true);
  const [expandAttachments, setExpandAttachments] = useState(true);

  const selectedCampaign = campaigns.find(c => c.id === selectedCampaignId);
  const isDraft = !selectedCampaign || selectedCampaign.status === 'draft';
  const isFilterEditable = !selectedCampaignId || (selectedCampaign && selectedCampaign.status === 'completed');

  const isDirty = (() => {
    if (!selectedCampaignId) return false;
    if (!selectedCampaign) return false;
    
    let dbParams: Record<string, any> = {};
    if (selectedCampaign.custom_prompt) {
      try {
        dbParams = JSON.parse(selectedCampaign.custom_prompt);
      } catch (e) {}
    }
    
    if (campaignName !== selectedCampaign.name) return true;
    if (campaignType !== (selectedCampaign.campaign_type || 'Festival')) return true;
    
    const dbFilters = selectedCampaign.audience_filters || {};
    if (enableFilters !== (Object.keys(dbFilters).length > 0)) return true;
    if (enableFilters) {
      if (audienceFilters.country !== (dbFilters.country || '')) return true;
      if (audienceFilters.shipment_mode !== (dbFilters.shipment_mode || '')) return true;
      if (audienceFilters.trade_direction !== (dbFilters.trade_direction || '')) return true;
      if (audienceFilters.industry !== (dbFilters.industry || '')) return true;
    }
    
    const dbScheduled = selectedCampaign.scheduled_at ? new Date(selectedCampaign.scheduled_at).toISOString().slice(0, 16) : '';
    const currentScheduled = sendMode === 'schedule' && scheduledTime ? new Date(scheduledTime).toISOString().slice(0, 16) : '';
    if (currentScheduled !== dbScheduled) return true;
    
    if (campaignType === 'Festival') {
      if (festivalOccasion !== (dbParams.festival_occasion || 'Diwali')) return true;
      if (festivalContext !== (dbParams.message_context || '')) return true;
    } else if (campaignType === 'Price Drop') {
      if (priceDropRoute !== (dbParams.route_service || '')) return true;
      if (priceDropPrevRate !== (dbParams.previous_rate || '')) return true;
      if (priceDropNewRate !== (dbParams.new_rate || '')) return true;
      if (priceDropValidity !== (dbParams.validity || '')) return true;
    } else if (campaignType === 'Sales') {
      if (salesService !== (dbParams.promoted_service || '')) return true;
      if (salesOpportunity !== (dbParams.target_opportunity || '')) return true;
      if (salesValidity !== (dbParams.validity || '')) return true;
    } else if (campaignType === 'Promotional Services') {
      if (promoRegion !== (dbParams.region || '')) return true;
      if (promoFocus !== (dbParams.logistics_focus || '')) return true;
    }
    if (additionalInstructions !== (dbParams.additional_instructions || '')) return true;
    
    const dbAttachments = dbParams.attachments || [];
    if (stagedFiles.length !== dbAttachments.length) return true;
    for (let i = 0; i < stagedFiles.length; i++) {
      if (stagedFiles[i].id !== dbAttachments[i].id) return true;
    }
    
    return false;
  })();

  // Polling execution state when campaign is running or active
  useEffect(() => {
    if (!selectedCampaignId) return;

    let isMounted = true;
    let timeoutId: any = null;
    const abortController = new AbortController();

    const poll = async () => {
      if (!isMounted) return;
      if (document.visibilityState === 'hidden') {
        // Pause polling when browser tab is inactive/hidden
        timeoutId = setTimeout(poll, 10000);
        return;
      }

      try {
        // Query lightweight campaign status first to prevent heavy analytical DB load
        const statusRes = await api.get(`/api/v1/marketing/campaigns/${selectedCampaignId}`, {
          signal: abortController.signal
        });
        const currentCampaign = statusRes.data;

        if (!currentCampaign || (currentCampaign.status !== 'running' && currentCampaign.status !== 'active')) {
          // Fetch final completed metrics one last time and refresh main list state
          await fetchCampaignAnalytics(selectedCampaignId);
          if (activeTab === 'execution') {
            await fetchExecutionProgress(selectedCampaignId);
          }
          await loadCampaigns();
          return;
        }

        // Fetch full campaign analytics only if campaign status warrants updates
        await fetchCampaignAnalytics(selectedCampaignId);

        // Fetch execution progress if execution progress is selected
        if (activeTab === 'execution') {
          await fetchExecutionProgress(selectedCampaignId);
        }
      } catch (err) {
        if (err instanceof Error && err.name === 'CanceledError') {
          return;
        }
        console.error("Error during campaign analytics background poll", err);
      }

      // Schedule next request only after the previous request successfully completes
      if (isMounted) {
        timeoutId = setTimeout(poll, 10000);
      }
    };

    // Trigger initial poll
    poll();

    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
      abortController.abort(); // Cancel pending network requests immediately on unmount/selection change
    };
  }, [selectedCampaignId, activeTab]);

  // Load campaigns dataset
  const loadCampaigns = async () => {
    setLoadingCampaigns(true);
    setErrorMsg('');
    try {
      const res = await api.get('/api/v1/marketing/campaigns');
      const data = res.data || [];
      setCampaigns(data);
      if (data.length > 0 && !selectedCampaignId) {
        setSelectedCampaignId(data[0].id);
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg('Failed to retrieve campaigns dataset.');
    } finally {
      setLoadingCampaigns(false);
    }
  };

  // Load available attachments from tenant global list, filtered to marketing files only
  const loadAvailableAttachments = async () => {
    setLoadingAvailable(true);
    try {
      const res = await api.get('/api/v1/attachments?limit=100');
      const allFiles = res.data?.attachments || [];
      // Strictly isolate by matching file_type === 'marketing'
      const marketingOnly = allFiles.filter((att: any) => att.file_type === 'marketing');
      setAvailableAttachments(marketingOnly);
    } catch (err) {
      console.error('Failed to load available attachments', err);
    } finally {
      setLoadingAvailable(false);
    }
  };

  useEffect(() => {
    loadCampaigns();
    loadAvailableAttachments();
  }, []);

  // Fetch campaign metrics and recipient logs
  const fetchCampaignAnalytics = async (id: string) => {
    if (!id) return;
    setLoadingAnalytics(true);
    try {
      const res = await api.get(`/api/v1/marketing/campaigns/${id}/analytics`);
      setRecipients(res.data?.recipients || []);
      setMetrics(res.data?.metrics || {
        total_targeted: 0,
        sent: 0,
        delivered: 0,
        opened: 0,
        replied: 0,
        failed: 0,
        open_rate: 0.0,
        reply_rate: 0.0
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingAnalytics(false);
    }
  };

  // Hydrate form inputs only when selecting a new campaign or explicitly switching
  useEffect(() => {
    if (selectedCampaignId) {
      fetchCampaignAnalytics(selectedCampaignId);
      fetchExecutionProgress(selectedCampaignId);
    }
  }, [selectedCampaignId]);

  // Hydrate form inputs only when selecting a new campaign or explicitly switching
  useEffect(() => {
    if (selectedCampaignId) {
      const current = campaigns.find(c => c.id === selectedCampaignId);
      if (current) {
        setCampaignName(current.name);
        setCampaignType(current.campaign_type || 'Festival');
        setAudienceFilters(current.audience_filters || {
          country: '',
          shipment_mode: '',
          trade_direction: '',
          industry: '',
          customer_type: ''
        });
        setEnableFilters(Object.keys(current.audience_filters || {}).length > 0);

        let params: Record<string, any> = {};
        if (current.custom_prompt) {
          try {
            params = JSON.parse(current.custom_prompt);
          } catch (e) {
            console.error('Failed to parse structured campaign settings', e);
          }
        }

        // Hydrate structured fields
        setFestivalOccasion(params.festival_occasion || 'Diwali');
        setFestivalContext(params.message_context || '');
        setPriceDropRoute(params.route_service || '');
        setPriceDropPrevRate(params.previous_rate || '');
        setPriceDropNewRate(params.new_rate || '');
        setPriceDropValidity(params.validity || '');
        setSalesService(params.promoted_service || '');
        setSalesOpportunity(params.target_opportunity || '');
        setSalesValidity(params.validity || '');
        setPromoRegion(params.region || '');
        setPromoFocus(params.logistics_focus || '');
        setAdditionalInstructions(params.additional_instructions || '');

        // Load campaign-wise attachments list
        if (params.attachments) {
          setStagedFiles(params.attachments);
        } else {
          setStagedFiles([]);
        }

        // Hydrate scheduling parameters
        if (current.scheduled_at) {
          setSendMode('schedule');
          const localDate = new Date(current.scheduled_at);
          const offset = localDate.getTimezoneOffset();
          const adjustedDate = new Date(localDate.getTime() - offset * 60 * 1000);
          setScheduledTime(adjustedDate.toISOString().slice(0, 16));
        } else {
          setSendMode('now');
          setScheduledTime('');
        }
      }
    }
  }, [selectedCampaignId]); // Only trigger when the active campaign selection changes

  // Handle saving settings
  const handleSaveSettings = async () => {
    setErrorMsg('');
    setSuccessMsg('');
    setIsSaving(true);
    try {
      const activeFilters: Record<string, string> = {};
      if (enableFilters) {
        Object.entries(audienceFilters).forEach(([key, val]) => {
          if (val) activeFilters[key] = val;
        });
      }

      const desc = `Marketing outreach of type ${campaignType}.`;

      // Build structured parameters map
      const params: Record<string, any> = {
        attachments: stagedFiles // Save selected attachments inside custom_prompt JSON
      };
      if (campaignType === 'Festival') {
        params.festival_occasion = festivalOccasion;
        params.message_context = festivalContext;
      } else if (campaignType === 'Price Drop') {
        params.route_service = priceDropRoute;
        params.previous_rate = priceDropPrevRate;
        params.new_rate = priceDropNewRate;
        params.validity = priceDropValidity;
      } else if (campaignType === 'Sales') {
        params.promoted_service = salesService;
        params.target_opportunity = salesOpportunity;
        params.validity = salesValidity;
      } else if (campaignType === 'Promotional Services') {
        params.region = promoRegion;
        params.logistics_focus = promoFocus;
      }
      params.additional_instructions = additionalInstructions;

      let finalScheduledAt: string | null = null;
      if (sendMode === 'schedule' && scheduledTime) {
        finalScheduledAt = new Date(scheduledTime).toISOString();
      }

      let responseCampaign;
      if (selectedCampaignId) {
        const payload: Record<string, any> = {
          name: campaignName,
          description: desc,
          campaign_type: campaignType,
          custom_prompt: JSON.stringify(params),
          scheduled_at: finalScheduledAt
        };
        if (isFilterEditable) {
          payload.audience_filters = activeFilters;
        }
        await api.put(`/api/v1/marketing/campaigns/${selectedCampaignId}`, payload);
        setSuccessMsg('Campaign settings saved successfully!');
      } else {
        // Create new campaign
        const payload = {
          name: campaignName,
          description: desc,
          campaign_type: campaignType,
          audience_filters: activeFilters,
          custom_prompt: JSON.stringify(params),
          scheduled_at: finalScheduledAt
        };
        const res = await api.post('/api/v1/marketing/campaigns', payload);
        responseCampaign = res.data;
        setSelectedCampaignId(res.data.id);
        setSuccessMsg('Campaign created successfully!');
      }

      await loadCampaigns();
      if (responseCampaign) {
        setSelectedCampaignId(responseCampaign.id);
      }
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.response?.data?.detail || 'Failed to save configuration settings.');
    } finally {
      setIsSaving(false);
    }
  };

  // Lock target audience snapshot
  const handleLockAudience = async (id: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    setIsLocking(prev => ({ ...prev, [id]: true }));
    try {
      const res = await api.post(`/api/v1/marketing/campaigns/${id}/lock`);
      setSuccessMsg(`Target audience successfully locked with ${res.data.recipients_locked} matching records.`);
      await fetchCampaignAnalytics(id);
      await loadCampaigns();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to lock target audience snapshot.');
    } finally {
      setIsLocking(prev => ({ ...prev, [id]: false }));
    }
  };

  // Trigger creative copy generation and open preview/edit modal
  const handleStartApprovalFlow = async (id: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    setIsApproving(prev => ({ ...prev, [id]: true }));
    try {
      const current = campaigns.find(c => c.id === id);
      let params = {};
      if (current && current.custom_prompt) {
        try {
          params = JSON.parse(current.custom_prompt);
        } catch (e) {
          console.error(e);
        }
      }

      // 1. Generate content internally (in draft state)
      const genRes = await api.post(`/api/v1/marketing/campaigns/${id}/generate-content`, {
        structured_parameters: params,
        force_regenerate: true
      });

      // 2. Open approval preview modal with the generated copy
      setApprovalCampaignId(id);
      setApprovalContentId(genRes.data.id);
      setApprovalSubject(genRes.data.subject || '');
      setApprovalHtmlBody(genRes.data.html_body || '');
      setApprovalPlainText(genRes.data.plain_text || '');
      setShowApprovalModal(true);
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to generate internal AI creative copy.');
    } finally {
      setIsApproving(prev => ({ ...prev, [id]: false }));
    }
  };

  // Save the edited content template and approve the campaign
  const handleConfirmAndApprove = async () => {
    setErrorMsg('');
    setSuccessMsg('');
    setIsSavingApproval(true);
    try {
      // 1. PUT the updated draft template changes back to DB
      await api.put(`/api/v1/marketing/campaigns/${approvalCampaignId}/contents/${approvalContentId}`, {
        subject: approvalSubject,
        html_body: approvalHtmlBody,
        plain_text: approvalPlainText
      });

      // 2. Approve and associate templates creative
      await api.post(`/api/v1/marketing/campaigns/${approvalCampaignId}/contents/${approvalContentId}/approve`, {
        attachments: stagedFiles
      });

      setSuccessMsg('AI copy template approved and saved successfully.');
      setShowApprovalModal(false);
      await loadCampaigns();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to save and approve campaign creative.');
    } finally {
      setIsSavingApproval(false);
    }
  };

  // Activate / Launch Campaign
  const handleActivateCampaign = async (id: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    setIsLaunching(prev => ({ ...prev, [id]: true }));
    try {
      await api.post(`/api/v1/marketing/campaigns/${id}/activate`);
      setSuccessMsg('Campaign launched successfully! Operations queue scheduled.');
      await loadCampaigns();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to launch outreach.');
    } finally {
      setIsLaunching(prev => ({ ...prev, [id]: false }));
    }
  };

  // Duplicate an existing campaign
  const handleDuplicateCampaign = async (id: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    try {
      const res = await api.post(`/api/v1/marketing/campaigns/${id}/duplicate`);
      setSuccessMsg(`Duplicated campaign successfully: ${res.data.name}`);
      await loadCampaigns();
      setSelectedCampaignId(res.data.id);
      setActiveTab('settings');
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to duplicate campaign.');
    }
  };

  // Delete Campaign
  const handleDeleteCampaign = async (id: string) => {
    setErrorMsg('');
    setSuccessMsg('');
    try {
      await api.delete(`/api/v1/marketing/campaigns/${id}`);
      setSuccessMsg('Campaign deleted successfully.');
      setConfirmDeleteId('');
      if (selectedCampaignId === id) {
        setSelectedCampaignId('');
      }
      await loadCampaigns();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || 'Failed to delete campaign.');
    }
  };

  // Handle actual file upload to existing Supabase engine
  const handleUploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setErrorMsg('');
    setUploadingFile(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Strictly tag as marketing file_type to ensure isolation
      formData.append("attachment_type", "marketing");
      formData.append("always_attach", "false");

      const res = await api.post('/api/v1/attachments', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      const newFile = {
        id: res.data.id,
        name: res.data.file_name,
        storage_path: res.data.storage_path
      };
      setStagedFiles([...stagedFiles, newFile]);
      await loadAvailableAttachments();
      setSuccessMsg(`Uploaded document "${res.data.file_name}" successfully.`);
    } catch (err: any) {
      console.error(err);
      setErrorMsg(err.response?.data?.detail || 'Attachment upload failed.');
    } finally {
      setUploadingFile(false);
    }
  };

  // Associate or detach attachment from campaign settings state
  const handleToggleAttachment = (attachment: TenantAttachment) => {
    const exists = stagedFiles.find(f => f.id === attachment.id);
    if (exists) {
      setStagedFiles(stagedFiles.filter(f => f.id !== attachment.id));
    } else {
      setStagedFiles([...stagedFiles, {
        id: attachment.id,
        name: attachment.file_name,
        storage_path: attachment.storage_path
      }]);
    }
  };

  // Remove attachment from selected campaign state array (Detach)
  const handleDetachFile = (idx: number) => {
    setStagedFiles(stagedFiles.filter((_, i) => i !== idx));
    setSuccessMsg('Attachment detached from campaign settings.');
  };

  // Filter recipient logs
  const filteredRecipients = recipients.filter(item => {
    if (searchCustomer && !item.contact_name?.toLowerCase().includes(searchCustomer.toLowerCase())) return false;
    if (searchCompany && !item.company_name?.toLowerCase().includes(searchCompany.toLowerCase())) return false;
    if (filterStatus !== 'all' && item.status !== filterStatus) return false;
    if (filterShipmentMode !== 'all' && item.shipment_mode !== filterShipmentMode) return false;
    if (filterTradeDir !== 'all' && item.trade_direction !== filterTradeDir) return false;
    if (filterRegion === 'domestic' && item.country?.toLowerCase() !== 'india') return false;
    if (filterRegion === 'overseas' && item.country?.toLowerCase() === 'india') return false;
    return true;
  });

  return (
    <AppShell>
      <PageWrapper>
        {/* Toast Container */}
        <div className="fixed top-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none select-none">
          {toasts.map((t) => (
            <div 
              key={t.id}
              className={`pointer-events-auto p-4 rounded-xl border shadow-lg flex items-start gap-3 transition-all duration-300 transform translate-x-0 ${
                t.variant === 'success' ? 'bg-[#ECFDF5]/95 border-emerald-200/50 text-emerald-950' :
                t.variant === 'danger' ? 'bg-[#FFF5F5]/95 border-rose-200/50 text-rose-950' :
                t.variant === 'warning' ? 'bg-[#FFFBEB]/95 border-amber-200/50 text-amber-950' :
                'bg-[#EFF6FF]/95 border-blue-200/50 text-blue-950'
              }`}
            >
              <div className="shrink-0 mt-0.5">
                {t.variant === 'success' && <CheckCircle2 className="w-4 h-4 text-emerald-500" />}
                {t.variant === 'danger' && <XCircle className="w-4 h-4 text-rose-500" />}
                {t.variant === 'warning' && <AlertCircle className="w-4 h-4 text-amber-500" />}
                {t.variant === 'info' && <Info className="w-4 h-4 text-blue-500" />}
              </div>
              <div className="flex-1 space-y-1">
                <h5 className="text-xs font-bold leading-none">{t.title}</h5>
                <p className="text-[11px] font-medium leading-relaxed opacity-90">{t.description}</p>
              </div>
              <button 
                onClick={() => setToasts(prev => prev.filter(item => item.id !== t.id))}
                className="p-1 hover:bg-black/5 rounded-lg transition-colors cursor-pointer text-current opacity-70 hover:opacity-100 shrink-0"
              >
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>

        {/* Dynamic header with page actions and selector */}
        <div className="flex justify-between items-center border-b border-border-color pb-4 mb-6 select-none">
          <div>
            <h1 className="text-lg font-black text-text-primary uppercase tracking-wider">Marketing Campaigns</h1>
            <p className="text-2xs text-text-muted mt-0.5">Define business parameters, targeting context, and stage attachments.</p>
          </div>

          <div className="flex items-center gap-4">
            {campaigns.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-2xs font-bold text-text-secondary uppercase">Campaign:</span>
                <select
                  value={selectedCampaignId}
                  onChange={e => setSelectedCampaignId(e.target.value)}
                  className="rounded-lg border border-border-color bg-bg-surface text-text-primary px-3 py-1.5 text-xs font-semibold focus:outline-none focus:border-brand-primary"
                >
                  {campaigns.map(camp => (
                    <option key={camp.id} value={camp.id}>
                      {camp.name} — {
                        camp.status === 'completed' ? '✓ Completed' :
                        camp.status === 'running' ? '● Running' :
                        camp.status === 'active' ? '● Active' :
                        camp.status === 'approved' ? '✨ Approved' :
                        camp.status === 'audience_locked' ? '🔒 Locked' :
                        `✎ ${camp.status}`
                      }
                    </option>
                  ))}
                </select>
              </div>
            )}

            <Button 
              variant="primary" 
              onClick={startNewCampaignFlow}
              leftIcon={<Plus className="w-4 h-4" />}
            >
              New Campaign
            </Button>
          </div>
        </div>

        {/* Tab Selection Bar */}
        <div className="flex border-b border-border-color pb-px select-none mb-6">
          {(['overview', 'execution-progress', 'execution', 'settings', 'attachments'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2.5 text-xs font-bold transition-all border-b-2 -mb-px cursor-pointer uppercase tracking-wider ${
                activeTab === tab ? 'border-brand-primary text-brand-primary font-black' : 'border-transparent text-text-muted hover:text-text-primary'
              }`}
            >
              {tab === 'settings' ? 'Campaign Settings' : tab === 'attachments' ? 'Campaign Attachments' : tab === 'execution-progress' ? 'Execution Progress' : tab}
            </button>
          ))}
        </div>

        {/* ---------------- SUB-TAB 1: OVERVIEW & ANALYTICS ---------------- */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            
            {/* Metric Cards Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <Card className="p-4 flex flex-col justify-between shadow-2xs border-t-2 border-t-brand-primary">
                <span className="text-[10px] uppercase font-bold text-text-muted">Total Targeted</span>
                <span className="text-xl font-extrabold text-brand-primary mt-2">{metrics.total_targeted}</span>
              </Card>
              <Card className="p-4 flex flex-col justify-between shadow-2xs border-t-2 border-t-status-success">
                <span className="text-[10px] uppercase font-bold text-text-muted">Delivered</span>
                <span className="text-xl font-extrabold text-status-success mt-2">{metrics.delivered}</span>
              </Card>
              <Card className="p-4 flex flex-col justify-between shadow-2xs border-t-2 border-t-status-warning">
                <span className="text-[10px] uppercase font-bold text-text-muted">Replies</span>
                <span className="text-xl font-extrabold text-status-warning mt-2">{metrics.replied}</span>
              </Card>
              <Card className="p-4 flex flex-col justify-between shadow-2xs border-t-2 border-t-status-danger">
                <span className="text-[10px] uppercase font-bold text-text-muted">Reply Rate</span>
                <span className="text-xl font-extrabold text-status-danger mt-2">{metrics.reply_rate}%</span>
              </Card>
            </div>

            {/* Customer Engagement History */}
            <Card className="p-4 space-y-4">
              <div className="flex justify-between items-center border-b border-border-color pb-3 select-none">
                <div>
                  <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Customer Engagement History</h4>
                  <p className="text-2xs text-text-secondary mt-0.5">Interaction and reply tracking records for this campaign.</p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => selectedCampaignId && fetchCampaignAnalytics(selectedCampaignId)}>
                  <RefreshCw className="w-3.5 h-3.5 mr-1" /> Reload
                </Button>
              </div>

              {/* Filters */}
              <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
                <Input 
                  placeholder="Company"
                  value={searchCompany}
                  onChange={e => setSearchCompany(e.target.value)}
                  className="h-9 text-xs"
                />
                <Input 
                  placeholder="Customer"
                  value={searchCustomer}
                  onChange={e => setSearchCustomer(e.target.value)}
                  className="h-9 text-xs"
                />
                <Select 
                  value={filterRegion}
                  onChange={e => setFilterRegion(e.target.value)}
                  options={[
                    { label: '-- Region --', value: 'all' },
                    { label: 'Domestic', value: 'domestic' },
                    { label: 'Overseas', value: 'overseas' }
                  ]}
                />
                <Select 
                  value={filterShipmentMode}
                  onChange={e => setFilterShipmentMode(e.target.value)}
                  options={[
                    { label: '-- Mode --', value: 'all' },
                    { label: 'SEA', value: 'SEA' },
                    { label: 'AIR', value: 'AIR' }
                  ]}
                />
                <Select 
                  value={filterTradeDir}
                  onChange={e => setFilterTradeDir(e.target.value)}
                  options={[
                    { label: '-- Trade --', value: 'all' },
                    { label: 'EXPORT', value: 'EXPORT' },
                    { label: 'IMPORT', value: 'IMPORT' }
                  ]}
                />
                <Select 
                  value={filterStatus}
                  onChange={e => setFilterStatus(e.target.value)}
                  options={[
                    { label: '-- Status --', value: 'all' },
                    { label: 'Pending', value: 'pending' },
                    { label: 'Sent', value: 'sent' },
                    { label: 'Failed', value: 'failed' }
                  ]}
                />
              </div>

              {/* Recipient Logs Table */}
              <div className="overflow-x-auto">
                {loadingAnalytics ? (
                  <div className="p-12 text-center text-text-secondary text-xs">Loading analytics...</div>
                ) : filteredRecipients.length === 0 ? (
                  <div className="p-12 text-center text-text-muted text-xs font-semibold select-none">
                    No recipients matching filters.
                  </div>
                ) : (
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-border-color bg-bg-secondary text-text-secondary text-[11px] font-bold uppercase tracking-wider">
                        <th className="p-3">Company Name</th>
                        <th className="p-3">Contact</th>
                        <th className="p-3">Sent At</th>
                        <th className="p-3">Delivery Status</th>
                        <th className="p-3">Replied</th>
                        <th className="p-3">Last Activity</th>
                        <th className="p-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border-color">
                      {filteredRecipients.map((item) => (
                        <tr key={item.id} className="hover:bg-bg-secondary/40 transition text-xs font-semibold text-text-primary">
                          <td className="p-3">{item.company_name}</td>
                          <td className="p-3">
                            <div>{item.contact_name}</div>
                            <div className="text-[10px] text-text-muted mt-0.5">{item.contact_email}</div>
                          </td>
                          <td className="p-3 text-text-secondary font-mono text-[10px]">
                            {item.sent_at ? new Date(item.sent_at).toLocaleString() : '—'}
                          </td>
                          <td className="p-3">
                            {item.status === 'skipped' || item.is_suppressed ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-900 border border-amber-300" title={item.bounce_reason || "Recipient has a confirmed hard bounce."}>
                                Skipped — Hard Bounce
                              </span>
                            ) : (
                              <Badge variant={
                                item.status === 'sent' || item.status === 'completed' ? 'success' :
                                item.status === 'failed' ? 'danger' : 'warning'
                              }>
                                {item.status}
                              </Badge>
                            )}
                          </td>
                          <td className="p-3">
                            {item.replied_at ? (
                              <Badge variant="success">Yes</Badge>
                            ) : (
                              <span className="text-text-muted">—</span>
                            )}
                          </td>
                          <td className="p-3 text-text-secondary font-mono text-[10px]">
                            {item.last_activity ? new Date(item.last_activity).toLocaleDateString() : '—'}
                          </td>
                          <td className="p-3 text-right">
                            {item.email_log_id ? (
                              <button
                                onClick={() => fetchEmailLogDetail(item.email_log_id)}
                                className="px-2 py-1 bg-brand-primary/10 hover:bg-brand-primary/20 text-brand-primary text-[10px] font-bold rounded transition uppercase tracking-wider"
                              >
                                View Email
                              </button>
                            ) : (
                              <span className="text-text-muted text-[10px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </Card>
          </div>
        )}
        {/* ---------------- SUB-TAB 1.5: EXECUTION PROGRESS ---------------- */}
        {activeTab === 'execution-progress' && (
          <div className="space-y-6">
            <Card className="p-6 space-y-6">
              <div className="flex justify-between items-center border-b border-border-color pb-3 select-none">
                <div>
                  <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Campaign Execution Live Progress</h4>
                  <p className="text-2xs text-text-secondary mt-0.5">Real-time tracking of recipient communications processed from the database.</p>
                </div>
                <Button variant="ghost" size="sm" onClick={() => selectedCampaignId && fetchExecutionProgress(selectedCampaignId)}>
                  <RefreshCw className="w-3.5 h-3.5 mr-1" /> Reload Progress
                </Button>
              </div>

              {!selectedCampaignId ? (
                <div className="text-center py-12 text-xs text-text-muted select-none">
                  Please select or configure a campaign to view live progress.
                </div>
              ) : loadingProgress && !executionProgress ? (
                <div className="text-center py-12 text-xs text-text-secondary">
                  Loading execution progress details...
                </div>
              ) : !executionProgress ? (
                <div className="text-center py-12 text-xs text-text-muted italic select-none">
                  No active execution progress logs found for the selected campaign.
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Progress Bar */}
                  <div className="space-y-2">
                    <div className="w-full h-3 bg-bg-secondary rounded-full overflow-hidden border border-border-color">
                      <div
                        className="h-full bg-brand-primary rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, executionProgress.progress_percent)}%` }}
                      ></div>
                    </div>
                    <div className="flex justify-between text-xs text-text-muted">
                      <span>{executionProgress.completed} of {executionProgress.total} recipients processed</span>
                      <span className="font-bold text-brand-primary">
                        {executionProgress.progress_percent}%
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-center">
                    <div className="bg-emerald-50/15 border border-emerald-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider block">Sent</span>
                      <span className="text-lg font-bold text-status-success">{executionProgress.sent}</span>
                    </div>
                    <div className="bg-rose-50/15 border border-rose-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-rose-800 uppercase tracking-wider block">Failed</span>
                      <span className="text-lg font-bold text-status-danger">{executionProgress.failed}</span>
                    </div>
                    <div className="bg-amber-50/15 border border-amber-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-amber-800 uppercase tracking-wider block">Sending</span>
                      <span className="text-lg font-bold text-status-warning">{executionProgress.sending}</span>
                    </div>
                    <div className="bg-slate-50/15 border border-slate-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-slate-800 uppercase tracking-wider block">Pending</span>
                      <span className="text-lg font-bold text-text-secondary">{executionProgress.pending}</span>
                    </div>
                    <div className="bg-gray-50/15 border border-gray-100 rounded-xl p-3">
                      <span className="text-[10px] font-bold text-gray-800 uppercase tracking-wider block">Skipped</span>
                      <span className="text-lg font-bold text-text-muted">{executionProgress.skipped}</span>
                    </div>
                  </div>

                  <div className="border border-border-color rounded-xl p-4 bg-bg-secondary/20 space-y-2 text-xs">
                    <div className="flex justify-between">
                      <span className="font-bold text-text-muted uppercase">Status:</span>
                      <Badge variant={executionProgress.status === 'completed' ? 'success' : 'warning'}>
                        {executionProgress.status.toUpperCase()}
                      </Badge>
                    </div>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* ---------------- SUB-TAB 2: EXECUTION CONTROL ---------------- */}
        {activeTab === 'execution' && (
          <div className="space-y-6">
            <Card className="p-4 space-y-4">
              <h4 className="text-xs font-bold text-text-primary uppercase tracking-wider">Authoritative Campaigns Manager</h4>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-border-color bg-bg-secondary text-text-secondary text-[11px] font-bold uppercase tracking-wider">
                      <th className="p-3">Campaign Name</th>
                      <th className="p-3">Type</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Send Mode</th>
                      <th className="p-3">Scheduled Time</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-color">
                    {campaigns.map((camp) => (
                      <tr key={camp.id} className="hover:bg-bg-secondary/40 transition text-xs font-semibold text-text-primary">
                        <td className="p-3 font-bold text-brand-primary">{camp.name}</td>
                        <td className="p-3">{camp.campaign_type}</td>
                        <td className="p-3">
                          <Badge variant={
                            camp.status === 'active' ? 'success' : 
                            camp.status === 'approved' ? 'success' : 
                            camp.status === 'draft' ? 'warning' : 'neutral'
                          }>
                            {camp.status}
                          </Badge>
                        </td>
                        <td className="p-3 uppercase text-2xs">{camp.scheduled_at ? 'scheduled' : 'immediate'}</td>
                        <td className="p-3 text-text-secondary font-mono text-[10px]">
                          {camp.scheduled_at ? new Date(camp.scheduled_at).toLocaleString() : '—'}
                        </td>
                        <td className="p-3 text-right space-x-2">
                          <Button size="sm" variant="secondary" onClick={() => { setSelectedCampaignId(camp.id); setActiveTab('settings'); }}>
                            Edit
                          </Button>
                          <Button size="sm" variant="secondary" onClick={() => handleDuplicateCampaign(camp.id)}>
                            Duplicate
                          </Button>

                          {camp.status === 'draft' && (
                            <Button 
                              size="sm" 
                              variant="primary" 
                              onClick={() => handleLockAudience(camp.id)}
                              isLoading={isLocking[camp.id]}
                              disabled={isLocking[camp.id]}
                            >
                              {isLocking[camp.id] ? 'Locking...' : 'Lock'}
                            </Button>
                          )}
                          {camp.status === 'audience_locked' && (
                            <Button 
                              size="sm" 
                              variant="primary" 
                              onClick={() => handleStartApprovalFlow(camp.id)}
                              isLoading={isApproving[camp.id]}
                              disabled={isApproving[camp.id]}
                            >
                              {isApproving[camp.id] ? 'Generating...' : 'Approve'}
                            </Button>
                          )}
                          {camp.status === 'approved' && (
                            <Button 
                              size="sm" 
                              variant="primary" 
                              onClick={() => handleActivateCampaign(camp.id)}
                              isLoading={isLaunching[camp.id]}
                              disabled={isLaunching[camp.id]}
                            >
                              {isLaunching[camp.id] ? 'Launching...' : 'Launch'}
                            </Button>
                          )}

                          {camp.status !== 'active' && (
                            <Button size="sm" variant="ghost" className="text-status-danger hover:bg-status-danger-bg/10" onClick={() => setConfirmDeleteId(camp.id)}>
                              Delete
                            </Button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>

            {confirmDeleteId && (
              <Card className="p-4 border border-status-danger bg-status-danger-bg/5 space-y-3">
                <div className="flex items-center gap-2 text-status-danger font-bold text-xs select-none">
                  <ShieldAlert className="w-4 h-4" />
                  <span>Confirm Campaign Deletion</span>
                </div>
                <p className="text-2xs text-text-secondary">
                  Are you absolutely sure you want to delete this campaign? This action is permanent and cannot be undone.
                </p>
                <div className="flex gap-2 select-none">
                  <Button size="sm" variant="primary" className="bg-status-danger hover:bg-status-danger/90" onClick={() => handleDeleteCampaign(confirmDeleteId)}>
                    Yes, Delete
                  </Button>
                  <Button size="sm" variant="secondary" onClick={() => setConfirmDeleteId('')}>
                    Cancel
                  </Button>
                </div>
              </Card>
            )}
          </div>
        )}

        {/* ---------------- SUB-TAB 3: CAMPAIGN CONFIGURATION SETTINGS ---------------- */}
        {activeTab === 'settings' && (
          <div className="space-y-6 max-w-4xl mx-auto">
            <div className="flex justify-between items-center select-none">
              <h2 className="text-xs font-bold text-text-muted uppercase tracking-wider">Configure Campaign Business Parameters</h2>
              <Button 
                variant="primary" 
                onClick={handleSaveSettings} 
                isLoading={isSaving} 
                className="shadow-xs text-xs font-bold font-sans"
              >
                Save Campaign Configuration
              </Button>
            </div>

            {/* Section A: Campaign Information Accordion */}
            <Card className="overflow-hidden">
              <div 
                onClick={() => setExpandInfo(!expandInfo)}
                className="p-4 bg-bg-secondary border-b border-border-color flex justify-between items-center cursor-pointer select-none"
              >
                <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider">A. Campaign Information</h4>
                {expandInfo ? <ChevronUp className="w-4 h-4 text-brand-primary" /> : <ChevronDown className="w-4 h-4 text-brand-primary" />}
              </div>
              {expandInfo && (
                <div className="p-6 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Input 
                      label="Campaign Name"
                      value={campaignName}
                      onChange={e => setCampaignName(e.target.value)}
                      placeholder="E.g., Special Diwali Rate Offer"
                      required
                    />
                    <Select 
                      label="Campaign Type"
                      value={campaignType}
                      onChange={e => setCampaignType(e.target.value as any)}
                      options={[
                        { label: 'Festival Greetings', value: 'Festival' },
                        { label: 'Price Drop Commercial', value: 'Price Drop' },
                        { label: 'Sales Push Promo', value: 'Sales' },
                        { label: 'Custom Outreach Campaign', value: 'Custom' },
                        { label: 'Promotional Services [SPECIAL • AI B2B OUTREACH + REGIONAL INSIGHTS]', value: 'Promotional Services' }
                      ]}
                    />
                  </div>
                </div>
              )}
            </Card>

            {/* Section B: Business Parameters Accordion */}
            <Card className="overflow-hidden">
              <div 
                onClick={() => setExpandParams(!expandParams)}
                className="p-4 bg-bg-secondary border-b border-border-color flex justify-between items-center cursor-pointer select-none"
              >
                <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider">B. Business Parameters</h4>
                {expandParams ? <ChevronUp className="w-4 h-4 text-brand-primary" /> : <ChevronDown className="w-4 h-4 text-brand-primary" />}
              </div>
              {expandParams && (
                <div className="p-6 space-y-4">
                  {campaignType === 'Festival' && (
                    <div className="space-y-4 p-4 rounded-xl bg-bg-secondary/40 border border-border-color">
                      <Input 
                        label="Festival / Occasion"
                        value={festivalOccasion}
                        onChange={e => setFestivalOccasion(e.target.value)}
                        placeholder="E.g., Diwali, Christmas, Eid, Chinese New Year"
                      />
                      <Input 
                        label="Greeting context / Business Context"
                        value={festivalContext}
                        onChange={e => setFestivalContext(e.target.value)}
                        placeholder="E.g., Wish holiday joy and mention seasonal operations schedule."
                      />
                    </div>
                  )}

                  {campaignType === 'Price Drop' && (
                    <div className="space-y-4 p-4 rounded-xl bg-bg-secondary/40 border border-border-color">
                      <Input 
                        label="Route / lane or Service description"
                        value={priceDropRoute}
                        onChange={e => setPriceDropRoute(e.target.value)}
                        placeholder="E.g., Air Freight Mumbai to London Heathrow"
                      />
                      {/* Price/Rate inputs hidden for new Price Drop campaigns; read-only for historical campaigns */}
                      {selectedCampaignId ? (
                        <div className="grid grid-cols-2 gap-4">
                          <Input 
                            label="Previous Rate"
                            value={priceDropPrevRate}
                            onChange={e => setPriceDropPrevRate(e.target.value)}
                            placeholder="E.g., $4.20 per kg"
                            disabled
                          />
                          <Input 
                            label="New Rate"
                            value={priceDropNewRate}
                            onChange={e => setPriceDropNewRate(e.target.value)}
                            placeholder="E.g., $3.60 per kg"
                            disabled
                          />
                        </div>
                      ) : null}
                      <Input 
                        label="Validity period"
                        value={priceDropValidity}
                        onChange={e => setPriceDropValidity(e.target.value)}
                        placeholder="E.g., Valid for cargo bookings in September"
                      />
                    </div>
                  )}

                  {campaignType === 'Sales' && (
                    <div className="space-y-4 p-4 rounded-xl bg-bg-secondary/40 border border-border-color">
                      <Input 
                        label="Promoted Cargo Service"
                        value={salesService}
                        onChange={e => setSalesService(e.target.value)}
                        placeholder="E.g., Ocean Freight LCL logistics solutions"
                      />
                      <Input 
                        label="Booking Opportunity"
                        value={salesOpportunity}
                        onChange={e => setSalesOpportunity(e.target.value)}
                        placeholder="E.g., Secure spaces for peak season shipping."
                      />
                      <Input 
                        label="Validity Deadline"
                        value={salesValidity}
                        onChange={e => setSalesValidity(e.target.value)}
                        placeholder="E.g., Book before August 31"
                      />
                    </div>
                  )}

                  {campaignType === 'Promotional Services' && (
                    <div className="space-y-4 p-4 rounded-xl bg-bg-secondary/40 border border-border-color">
                      <div className="grid grid-cols-2 gap-4">
                        <Input 
                          label="Region"
                          value={promoRegion}
                          onChange={e => setPromoRegion(e.target.value)}
                          placeholder="E.g., China, Germany, UAE"
                          required
                        />
                        <Input 
                          label="Logistics / Trade Focus"
                          value={promoFocus}
                          onChange={e => setPromoFocus(e.target.value)}
                          placeholder="E.g., Air Freight, Road Freight, Ocean Freight"
                          required
                        />
                      </div>
                    </div>
                  )}

                  {campaignType === 'Custom' && (
                    <div className="p-4 rounded-xl bg-bg-secondary/40 border border-border-color space-y-4">
                      <Input 
                        label="Campaign business details context"
                        value={additionalInstructions}
                        onChange={e => setAdditionalInstructions(e.target.value)}
                        placeholder="Provide logistics business goals context..."
                      />
                    </div>
                  )}

                  {campaignType !== 'Custom' && (
                    <Input 
                      label="Additional Business Notes"
                      value={additionalInstructions}
                      onChange={e => setAdditionalInstructions(e.target.value)}
                      placeholder="E.g., Mention priority custom clearance speed."
                    />
                  )}
                </div>
              )}
            </Card>

            {/* Section C: Audience Targeting Accordion */}
            <Card className="overflow-hidden">
              <div 
                onClick={() => setExpandAudience(!expandAudience)}
                className="p-4 bg-bg-secondary border-b border-border-color flex justify-between items-center cursor-pointer select-none"
              >
                <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider">C. Audience Targeting</h4>
                {expandAudience ? <ChevronUp className="w-4 h-4 text-brand-primary" /> : <ChevronDown className="w-4 h-4 text-brand-primary" />}
              </div>
              {expandAudience && (
                <div className="p-6 space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-semibold text-text-secondary">Enable filters criteria to narrow down target customer audience list.</span>
                    <label className="flex items-center gap-2 text-xs font-bold cursor-pointer select-none">
                      <input 
                        type="checkbox"
                        checked={enableFilters}
                        onChange={e => setEnableFilters(e.target.checked)}
                        disabled={!isFilterEditable}
                        className="rounded border-border-color text-brand-primary"
                      />
                      Enable filters
                    </label>
                  </div>

                  {enableFilters && (
                    <div className="grid grid-cols-2 gap-4">
                      <Input 
                        label="Country"
                        value={audienceFilters.country}
                        onChange={e => setAudienceFilters({ ...audienceFilters, country: e.target.value })}
                        placeholder="E.g., India"
                        disabled={!isFilterEditable}
                      />
                      <Select 
                        label="Shipment Mode"
                        value={audienceFilters.shipment_mode}
                        onChange={e => setAudienceFilters({ ...audienceFilters, shipment_mode: e.target.value })}
                        disabled={!isFilterEditable}
                        options={[
                          { label: '-- All modes --', value: '' },
                          { label: 'SEA', value: 'SEA' },
                          { label: 'AIR', value: 'AIR' }
                        ]}
                      />
                      <Select 
                        label="Trade Direction"
                        value={audienceFilters.trade_direction}
                        onChange={e => setAudienceFilters({ ...audienceFilters, trade_direction: e.target.value })}
                        disabled={!isFilterEditable}
                        options={[
                          { label: '-- All directions --', value: '' },
                          { label: 'EXPORT', value: 'EXPORT' },
                          { label: 'IMPORT', value: 'IMPORT' }
                        ]}
                      />
                      <Input 
                        label="Industry"
                        value={audienceFilters.industry}
                        onChange={e => setAudienceFilters({ ...audienceFilters, industry: e.target.value })}
                        placeholder="E.g., Electronics"
                        disabled={!isFilterEditable}
                      />
                    </div>
                  ) }
                </div>
              )}
            </Card>

            {/* Section D: Execution Settings Accordion */}
            <Card className="overflow-hidden">
              <div 
                onClick={() => setExpandExecution(!expandExecution)}
                className="p-4 bg-bg-secondary border-b border-border-color flex justify-between items-center cursor-pointer select-none"
              >
                <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider">D. Execution Settings</h4>
                {expandExecution ? <ChevronUp className="w-4 h-4 text-brand-primary" /> : <ChevronDown className="w-4 h-4 text-brand-primary" />}
              </div>
              {expandExecution && (
                <div className="p-6 space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <Select 
                      label="Send Mode"
                      value={sendMode}
                      onChange={e => setSendMode(e.target.value as any)}
                      options={[
                        { label: 'Send Immediately', value: 'now' },
                        { label: 'Schedule Later', value: 'schedule' }
                      ]}
                    />
                    {sendMode === 'schedule' && (
                      <Input 
                        label="Schedule Time"
                        type="datetime-local"
                        value={scheduledTime}
                        onChange={e => setScheduledTime(e.target.value)}
                        required
                      />
                    )}
                  </div>
                </div>
              )}
            </Card>

            {/* Section E: Campaign Attachments Accordion */}
            <Card className="overflow-hidden">
              <div 
                onClick={() => setExpandAttachments(!expandAttachments)}
                className="p-4 bg-bg-secondary border-b border-border-color flex justify-between items-center cursor-pointer select-none"
              >
                <h4 className="text-xs font-bold text-brand-primary uppercase tracking-wider">E. Campaign Attachments</h4>
                {expandAttachments ? <ChevronUp className="w-4 h-4 text-brand-primary" /> : <ChevronDown className="w-4 h-4 text-brand-primary" />}
              </div>
              {expandAttachments && (
                <div className="p-6 space-y-4">
                  <span className="text-2xs text-text-secondary font-semibold">Select from the available marketing-specific documents for this campaign. Go to Campaign Attachments to upload new documents.</span>
                  {loadingAvailable ? (
                    <div className="text-2xs text-text-muted italic">Loading available attachments...</div>
                  ) : availableAttachments.length === 0 ? (
                    <div className="text-2xs text-text-muted italic">No marketing attachments available. Upload files in Tab 4.</div>
                  ) : (
                    <div className="grid grid-cols-2 gap-3 max-h-48 overflow-y-auto border border-border-color p-3 rounded-xl bg-bg-secondary/40">
                      {availableAttachments.map(attachment => {
                        const isSelected = stagedFiles.some(f => f.id === attachment.id);
                        return (
                          <label 
                            key={attachment.id}
                            className="flex items-center gap-2.5 p-2 rounded-lg border border-border-color/60 hover:bg-bg-surface cursor-pointer select-none text-2xs font-semibold text-text-primary"
                          >
                            <input 
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleToggleAttachment(attachment)}
                              className="rounded text-brand-primary border-border-color"
                            />
                            <span className="truncate">{attachment.file_name}</span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </Card>            
          </div>
        )}

        {/* ---------------- SUB-TAB 4: CAMPAIGN ATTACHMENTS ---------------- */}
        {activeTab === 'attachments' && (
          <div className="space-y-6 max-w-4xl mx-auto">
            <Card className="p-6 space-y-6">
              <div className="flex justify-between items-center border-b border-border-color pb-4 select-none">
                <div>
                  <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Staged Campaign Documents</h3>
                  <p className="text-2xs text-text-muted mt-0.5">Manage and upload documents specifically assigned to the active campaign.</p>
                </div>
                <input 
                  type="file"
                  ref={fileInputRef}
                  onChange={handleUploadFile}
                  className="hidden"
                  accept=".pdf,.png,.jpg,.jpeg,.gif,.webp"
                />
                <Button 
                  variant="primary" 
                  onClick={() => fileInputRef.current?.click()}
                  isLoading={uploadingFile}
                  leftIcon={<Upload className="w-4 h-4" />}
                >
                  Upload Document
                </Button>
              </div>

              <p className="text-xs text-text-secondary">Attach brochures or spreadsheet catalogs. These documents are associated with the selected campaign version and resolved by the execution delivery engine.</p>

              {stagedFiles.length === 0 ? (
                <div className="text-center py-12 border-2 border-dashed border-border-color rounded-2xl text-text-secondary text-xs">
                  No attachments uploaded or associated with this campaign.
                </div>
              ) : (
                <div className="space-y-3">
                  {stagedFiles.map((file, idx) => (
                    <div key={idx} className="flex justify-between items-center p-3 bg-bg-secondary border border-border-color rounded-2xl text-xs font-semibold text-text-primary">
                      <span className="flex items-center gap-2">
                        <Paperclip className="w-4 h-4 text-brand-primary" />
                        {file.name}
                      </span>
                      <Button 
                        size="sm" 
                        variant="ghost" 
                        onClick={() => handleDetachFile(idx)}
                        className="text-status-danger hover:bg-status-danger-bg/10"
                      >
                        Remove
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}
      </PageWrapper>

      {/* Outbound Email Detail Modal */}
      {selectedEmailLogId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs select-none">
          <div className="bg-bg-primary border border-border-color rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
            <div className="flex justify-between items-center p-4 border-b border-border-color bg-bg-secondary">
              <div>
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Outbound Email Detail</h3>
                <p className="text-[10px] text-text-muted mt-0.5">Reference ID: {selectedEmailLogId}</p>
              </div>
              <button
                onClick={() => {
                  setSelectedEmailLogId(null);
                  setEmailLogDetail(null);
                }}
                className="text-text-muted hover:text-text-primary transition p-1 hover:bg-bg-primary rounded-lg text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-5 flex-1 overflow-y-auto space-y-4">
              {loadingEmailLog ? (
                <div className="py-12 text-center text-text-secondary text-xs">Loading email content...</div>
              ) : !emailLogDetail ? (
                <div className="py-12 text-center text-text-muted text-xs font-semibold">Failed to load email details.</div>
              ) : (
                <div className="space-y-4 select-text">
                  <div className="grid grid-cols-[80px_1fr] text-xs border-b border-border-color/60 pb-3 gap-y-2">
                    <span className="font-bold text-text-muted uppercase">To:</span>
                    <span className="text-text-primary font-semibold">
                      {emailLogDetail.to_name ? `${emailLogDetail.to_name} <${emailLogDetail.to_email}>` : emailLogDetail.to_email}
                    </span>

                    <span className="font-bold text-text-muted uppercase">Subject:</span>
                    <span className="text-text-primary font-bold">{emailLogDetail.subject}</span>

                    <span className="font-bold text-text-muted uppercase">Date:</span>
                    <span className="text-text-secondary font-mono text-[11px]">
                      {emailLogDetail.sent_at ? new Date(emailLogDetail.sent_at).toLocaleString() : '—'}
                    </span>
                  </div>

                  <div className="border border-border-color rounded-xl bg-bg-secondary/40 p-4 min-h-[250px] overflow-x-auto text-xs text-text-primary leading-relaxed">
                    {emailLogDetail.body ? (
                      <div dangerouslySetInnerHTML={{ __html: emailLogDetail.body }} />
                    ) : (
                      <pre className="whitespace-pre-wrap font-sans text-text-muted select-none">No body content available.</pre>
                    )}
                  </div>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-border-color flex justify-end bg-bg-secondary/30">
              <Button
                variant="secondary"
                onClick={() => {
                  setSelectedEmailLogId(null);
                  setEmailLogDetail(null);
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Campaign Approval Creative Preview & Edit Modal */}
      {showApprovalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs select-none">
          <div className="bg-bg-primary border border-border-color rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden">
            <div className="flex justify-between items-center p-4 border-b border-border-color bg-bg-secondary">
              <div>
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Approve Campaign Creative Template</h3>
                <p className="text-[10px] text-text-muted mt-0.5">Review, customize, and edit the AI-generated subject and body layout prior to locking it for launch.</p>
              </div>
              <button
                onClick={() => {
                  setShowApprovalModal(false);
                }}
                className="text-text-muted hover:text-text-primary transition p-1 hover:bg-bg-primary rounded-lg text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="p-6 flex-1 overflow-y-auto space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                
                {/* Edit Form */}
                <div className="space-y-4">
                  <h4 className="text-[11px] font-bold text-brand-primary uppercase tracking-wider">Edit Template</h4>
                  
                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-secondary uppercase">Email Subject</label>
                    <input 
                      type="text"
                      value={approvalSubject}
                      onChange={e => setApprovalSubject(e.target.value)}
                      className="w-full h-10 px-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-xs font-semibold focus:border-brand-primary focus:outline-none"
                      placeholder="Enter subject line..."
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[10px] font-bold text-text-secondary uppercase">Email Body Text</label>
                    <textarea 
                      value={approvalPlainText}
                      onChange={e => {
                        const val = e.target.value;
                        setApprovalPlainText(val);
                        const p = val.split('\n\n').map(x => '<p>' + x.replace(/\n/g, '<br/>') + '</p>').join('');
                        setApprovalHtmlBody(p);
                      }}
                      className="w-full h-[320px] p-3 rounded-lg border border-border-color bg-bg-surface text-text-primary text-xs font-sans focus:border-brand-primary focus:outline-none resize-none leading-relaxed"
                      placeholder="Enter email body content..."
                    />
                  </div>
                </div>

                {/* Live Preview Panel */}
                <div className="space-y-4 flex flex-col">
                  <h4 className="text-[11px] font-bold text-status-success uppercase tracking-wider">Live Preview</h4>
                  
                  <div className="border border-border-color rounded-xl flex-1 bg-white p-4 min-h-[380px] overflow-auto text-xs text-black leading-relaxed">
                    <div className="border-b border-gray-100 pb-2 mb-3">
                      <div className="text-[10px] text-gray-400 font-bold uppercase">Subject:</div>
                      <div className="font-bold text-gray-800 text-xs">{approvalSubject || "(No Subject)"}</div>
                    </div>
                    {approvalHtmlBody ? (
                      <div dangerouslySetInnerHTML={{ __html: approvalHtmlBody }} />
                    ) : (
                      <span className="text-gray-400 italic">No template body generated.</span>
                    )}
                  </div>
                </div>

              </div>
            </div>

            <div className="p-4 border-t border-border-color flex justify-end gap-3 bg-bg-secondary/30 select-none">
              <Button
                variant="secondary"
                onClick={() => {
                  setShowApprovalModal(false);
                }}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleConfirmAndApprove}
                isLoading={isSavingApproval}
                disabled={isSavingApproval || !approvalSubject || !approvalHtmlBody}
              >
                Confirm & Approve Template
              </Button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );

  function startNewCampaignFlow() {
    setSelectedCampaignId('');
    setCampaignName('');
    setCampaignType('Festival');
    setFestivalOccasion('Diwali');
    setFestivalContext('');
    setPriceDropRoute('');
    setPriceDropPrevRate('');
    setPriceDropNewRate('');
    setPriceDropValidity('');
    setSalesService('');
    setSalesOpportunity('');
    setSalesValidity('');
    setPromoRegion('');
    setPromoFocus('');
    setAdditionalInstructions('');
    setEnableFilters(false);
    setAudienceFilters({
      country: '',
      shipment_mode: '',
      trade_direction: '',
      industry: '',
      customer_type: ''
    });
    setStagedFiles([]);
    setRecipients([]);
    setActiveTab('settings');
  }
}
