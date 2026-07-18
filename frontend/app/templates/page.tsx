'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { Card, MetricCard } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/feedback';
import { Input, Select } from '../../components/ui/input';
import { 
  FileText, 
  Plus, 
  Search, 
  Trash2, 
  Copy, 
  Edit3, 
  Eye, 
  ChevronRight, 
  ChevronLeft,
  X,
  AlertTriangle,
  FolderOpen,
  Clipboard,
  Info,
  ChevronDown
} from 'lucide-react';
import { api } from '../../lib/api';
import { useTenantStore } from '../../store/tenant-store';
import { SignatureTab } from '../../components/signature-tab';

interface Template {
  id: string;
  organization_id: string;
  template_name: string;
  name: string;
  industry: string;
  industry_tag: string;
  subject: string;
  example_subject: string;
  body: string;
  example_body: string;
  status: 'active' | 'draft';
  is_active: boolean;
  template_type: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

interface TemplateStats {
  total: number;
  active: number;
  draft: number;
  industriesCount: number;
}

const CATEGORIZED_VARIABLES = {
  "Customer Information": [
    { name: 'company_name', label: '🏢 Company Name', desc: "Replaced with the customer's company name." },
    { name: 'contact_name', label: '👤 Contact Name', desc: "Replaced with the recipient's name." },
    { name: 'industry', label: '🏭 Industry', desc: "Replaced with the cargo trade sector." },
    { name: 'country', label: '🌍 Country', desc: "Replaced with the customer's country." },
    { name: 'website', label: '🌐 Website', desc: "Replaced with the customer's website." },
    { name: 'phone', label: '☎ Phone Number', desc: "Replaced with the customer's phone number." }
  ],
  "Sender Information": [
    { name: 'sender_name', label: '👤 Sender Name', desc: "Replaced with your full name." },
    { name: 'sender_company', label: '🏢 Sender Company', desc: "Replaced with your company name." },
    { name: 'current_date', label: '📅 Current Date', desc: "Replaced with today's date." }
  ]
};

const VARIABLES = [
  { name: 'company_name', label: 'Company Name' },
  { name: 'contact_name', label: 'Contact Name' },
  { name: 'industry', label: 'Industry' },
  { name: 'country', label: 'Country' },
  { name: 'website', label: 'Website' },
  { name: 'phone', label: 'Phone Number' },
  { name: 'sender_name', label: 'Sender Name' },
  { name: 'sender_company', label: 'Sender Company' },
  { name: 'current_date', label: 'Current Date' }
];

const STARTER_TEMPLATE = `Hi {{contact_name}},

Hope you're doing well.

I wanted to connect regarding your logistics requirements at {{company_name}}.

We specialize in freight forwarding and international shipping.

Would you be available for a quick discussion this week?

Regards,

{{sender_name}}
{{sender_company}}`;

export default function TemplatesPage() {
  const [activeTab, setActiveTab] = useState<'templates' | 'signature'>('templates');
  const router = useRouter();
  const { user } = useTenantStore();

  // Search & Filters state
  const [search, setSearch] = useState('');
  const [industryFilter, setIndustryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortOrder, setSortOrder] = useState('recently_updated');
  
  // Data lists & loading state
  const [templates, setTemplates] = useState<Template[]>([]);
  const [industriesList, setIndustriesList] = useState<string[]>([]);
  const [totalTemplates, setTotalTemplates] = useState(0);
  const [loading, setLoading] = useState(true);
  
  // Pagination
  const [page, setPage] = useState(1);
  const limit = 8;

  // Editor Modal States
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<Template | null>(null);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved');
  const [saveSuccessMessage, setSaveSuccessMessage] = useState(false);
  
  // Editor form values
  const [formName, setFormName] = useState('');
  const [formIndustry, setFormIndustry] = useState('');
  const [formStatus, setFormStatus] = useState<'active' | 'draft'>('draft');
  const [formSubject, setFormSubject] = useState('');
  const [formBody, setFormBody] = useState(''); // Stores plain text with newlines

  // Collapsible Signature panel

  // Searchable Industry Dropdown
  const [isIndustryDropdownOpen, setIsIndustryDropdownOpen] = useState(false);
  const [industrySearch, setIndustrySearch] = useState('');
  const industryDropdownRef = useRef<HTMLDivElement>(null);

  // Real-time Validation warnings
  const [validationWarnings, setValidationWarnings] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Centered Preview details modal
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [previewTemplate, setPreviewTemplate] = useState<Template | null>(null);

  // Stats calculations
  const [stats, setStats] = useState<TemplateStats>({
    total: 0,
    active: 0,
    draft: 0,
    industriesCount: 0
  });

  useEffect(() => {
    fetchTemplates();
    fetchIndustries();
  }, [page, industryFilter, statusFilter, sortOrder]);

  // Handle Search input change with debounce
  useEffect(() => {
    const delayDebounce = setTimeout(() => {
      setPage(1);
      fetchTemplates();
    }, 350);
    return () => clearTimeout(delayDebounce);
  }, [search]);

  // Close industry dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (industryDropdownRef.current && !industryDropdownRef.current.contains(e.target as Node)) {
        setIsIndustryDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);


  const fetchTemplates = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/v1/templates', {
        params: {
          page,
          limit,
          q: search || undefined,
          industry: industryFilter || undefined,
          status: statusFilter || undefined,
          sort: sortOrder
        }
      });
      setTemplates(res.data.templates);
      setTotalTemplates(res.data.total);
      
      // Calculate statistics dynamically
      const allRes = await api.get('/api/v1/templates', { params: { limit: 1000 } });
      const list = allRes.data.templates as Template[];
      const activeCount = list.filter(t => t.status === 'active').length;
      const uniqueInds = new Set(list.map(t => t.industry));
      setStats({
        total: list.length,
        active: activeCount,
        draft: list.length - activeCount,
        industriesCount: uniqueInds.size
      });
    } catch (err) {
      console.error("Failed to fetch templates", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchIndustries = async () => {
    try {
      const res = await api.get('/api/v1/templates/industries');
      setIndustriesList(res.data);
    } catch (err) {
      console.error("Failed to fetch industries dropdown list", err);
    }
  };

  // Keyboard shortcut Ctrl+S
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        if (isEditorOpen) {
          e.preventDefault();
          handleSaveTemplate();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isEditorOpen, formName, formIndustry, formStatus, formSubject, formBody, editingTemplate]);

  // Convert plain text with newlines to HTML for saving
  const textToHtml = (text: string) => {
    if (!text) return '';
    return text
      .split('\n')
      .map(paragraph => {
        const clean = paragraph.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        if (!clean.trim()) return '<p><br/></p>';
        return `<p>${clean}</p>`;
      })
      .join('');
  };

  // Convert HTML back to plain text for textarea editing
  const htmlToText = (html: string) => {
    if (!html) return '';
    return html
      .replace(/<\/p>/g, '\n')
      .replace(/<p>/g, '')
      .replace(/<br\s*\/?>/g, '\n')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      // strip any other remaining HTML tags safely
      .replace(/<[^>]*>/g, '')
      .trim();
  };

  // Real-time validation warning logic
  useEffect(() => {
    const warnings: string[] = [];
    const allowed = new Set(VARIABLES.map(v => v.name));

    const checkText = (text: string, sourceName: string) => {
      const openCount = (text.match(/\{\{/g) || []).length;
      const closeCount = (text.match(/\}\}/g) || []).length;
      if (openCount !== closeCount) {
        warnings.push(`Malformed braces in ${sourceName}. Make sure all placeholder variables are enclosed in double curly braces, e.g. {{company_name}}.`);
      }

      const unmatchedLeft = text.match(/\{\{[a-zA-Z0-9_]+(?!\}\})/g);
      const unmatchedRight = text.match(/(?<!\{\{)[a-zA-Z0-9_]+\}\}/g);
      if (unmatchedLeft || unmatchedRight) {
        warnings.push(`Malformed tags in ${sourceName}. Ensure all variables are fully closed.`);
      }

      const regex = /\{\{(.*?)\}\}/g;
      let match;
      while ((match = regex.exec(text)) !== null) {
        const tag = match[1];
        const clean = tag.trim();
        if (tag !== clean) {
          warnings.push(`Variable "{{${tag}}}" inside ${sourceName} contains invalid spaces. Try "{{${clean}}}" instead.`);
        } else if (!allowed.has(clean)) {
          let closest = 'company_name';
          if (clean.includes('company')) closest = 'company_name';
          else if (clean.includes('name') || clean.includes('contact')) closest = 'contact_name';
          else if (clean.includes('ind')) closest = 'industry';
          else if (clean.includes('count')) closest = 'country';
          else if (clean.includes('web') || clean.includes('site')) closest = 'website';
          else if (clean.includes('phone') || clean.includes('tel')) closest = 'phone';
          else if (clean.includes('date')) closest = 'current_date';
          else if (clean.includes('sender')) closest = 'sender_name';
          
          warnings.push(`The variable "{{${clean}}}" doesn't exist inside ${sourceName}. Try "{{${closest}}}" instead.`);
        }
      }

      const singleBraces = text.match(/(?<!\{)\{([a-zA-Z0-9_ ]+)\}(?!\})/g);
      if (singleBraces) {
        for (const single of singleBraces) {
          const clean = single.replace(/[{}]/g, '').trim();
          if (allowed.has(clean)) {
            warnings.push(`Malformed placeholder in ${sourceName}: "${single}". Try "{{${clean}}}" instead.`);
          }
        }
      }
    };

    checkText(formSubject, 'Subject');
    checkText(formBody, 'Email Template');
    setValidationWarnings(warnings);
    
    if (formName || formSubject || formBody) {
      setSaveStatus('unsaved');
    }
  }, [formSubject, formBody, formName, formIndustry, formStatus]);

  const handleCopyVariable = (variableName: string) => {
    navigator.clipboard.writeText(`{{${variableName}}}`);
    alert(`Copied {{${variableName}}} to clipboard!`);
  };

  const handleLoadStarterTemplate = () => {
    const confirm = window.confirm("Load Starter Template? This will replace your current email body text.");
    if (confirm) {
      setFormBody(STARTER_TEMPLATE);
      setHasUnsavedChanges(true);
    }
  };

  const handleOpenCreateModal = () => {
    setEditingTemplate(null);
    setFormName('');
    setFormIndustry(industriesList[0] || 'Steel');
    setFormStatus('draft');
    setFormSubject('');
    setFormBody('');
    setErrors({});
    setValidationWarnings([]);
    setHasUnsavedChanges(false);
    setSaveStatus('saved');
    setIsEditorOpen(true);
  };

  const handleOpenEditModal = (t: Template) => {
    setEditingTemplate(t);
    setFormName(t.template_name);
    setFormIndustry(t.industry);
    setFormStatus(t.status);
    setFormSubject(t.subject);
    setFormBody(htmlToText(t.body));
    setErrors({});
    setValidationWarnings([]);
    setHasUnsavedChanges(false);
    setSaveStatus('saved');
    setIsEditorOpen(true);
  };

  const handleCloseEditorModal = () => {
    if (hasUnsavedChanges || saveStatus === 'unsaved') {
      const confirm = window.confirm("You have unsaved changes. Are you sure you want to discard them?");
      if (!confirm) return;
    }
    setIsEditorOpen(false);
  };

  const validateFields = () => {
    const errs: Record<string, string> = {};
    if (!formName.trim()) errs.name = "Template name is required";
    if (formName.length > 100) errs.name = "Template name cannot exceed 100 characters";
    if (!formIndustry) errs.industry = "Standard industry sector is required";
    if (!formSubject.trim()) errs.subject = "Email subject is required";
    if (formSubject.length > 200) errs.subject = "Subject cannot exceed 200 characters";
    if (!formBody.trim()) errs.body = "Email body content is required";

    if (validationWarnings.length > 0) {
      errs.placeholder = "Please resolve the malformed or unrecognized variables highlighted below.";
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSaveTemplate = async () => {
    if (!validateFields()) return;

    const htmlBody = textToHtml(formBody);

    const payload = {
      template_name: formName,
      industry: formIndustry,
      subject: formSubject,
      body: htmlBody,
      status: formStatus
    };

    try {
      setSaveStatus('saving');
      if (editingTemplate) {
        await api.put(`/api/v1/templates/${editingTemplate.id}`, payload);
      } else {
        await api.post('/api/v1/templates', payload);
      }
      setHasUnsavedChanges(false);
      setSaveStatus('saved');
      setSaveSuccessMessage(true);
      setTimeout(() => setSaveSuccessMessage(false), 3000);
      setIsEditorOpen(false);
      fetchTemplates();
    } catch (err: any) {
      setSaveStatus('unsaved');
      console.error(err);
      alert(err.response?.data?.detail || "An error occurred while saving the template.");
    }
  };

  const handleDuplicate = async (t: Template) => {
    try {
      await api.post(`/api/v1/templates/${t.id}/duplicate`);
      fetchTemplates();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to duplicate template.");
    }
  };

  const handleDelete = async (t: Template) => {
    const confirm = window.confirm(`Delete this template permanently?\n\nThis action cannot be undone.`);
    if (!confirm) return;

    try {
      await api.delete(`/api/v1/templates/${t.id}`);
      fetchTemplates();
    } catch (err) {
      console.error(err);
      alert("Failed to delete template.");
    }
  };

  const getRenderedPreview = (bodyText: string, subjectText: string) => {
    let renderedSubject = subjectText || '';
    let bodyWithHtmlParagraphs = textToHtml(bodyText);

    const replacements: Record<string, string> = {
      company_name: "ABC Industries",
      contact_name: "Rahul Sharma",
      industry: "Manufacturing",
      country: "India",
      website: "www.abcindustries.com",
      phone: "+91 98765 43210",
      sender_name: user?.full_name || "Sanjay",
      sender_company: "FreightForce AI",
      current_date: new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' })
    };

    Object.entries(replacements).forEach(([key, val]) => {
      const regex = new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g');
      bodyWithHtmlParagraphs = bodyWithHtmlParagraphs.replace(regex, val);
      renderedSubject = renderedSubject.replace(regex, val);
    });

    return {
      subject: renderedSubject,
      body: bodyWithHtmlParagraphs
    };
  };

  const handleOpenPreviewDrawer = (t: Template) => {
    setPreviewTemplate(t);
    setIsPreviewOpen(true);
  };

  const filteredIndustries = industriesList.filter(ind => 
    ind.toLowerCase().includes(industrySearch.toLowerCase())
  );

  return (
    <AppShell>
      <PageWrapper>
        <div className="space-y-6">
          <PageHeader 
            title="Templates & Signatures"
            description="Manage reusable email templates and default organization signatures."
            actions={
              activeTab === 'templates' && (
                <Button variant="primary" onClick={handleOpenCreateModal} className="flex items-center gap-1.5 cursor-pointer shadow-sm">
                  <Plus className="w-4 h-4" />
                  <span>New Template</span>
                </Button>
              )
            }
          />

          {/* Tab Switcher */}
          <div className="flex border-b border-border-color pb-1 mb-4 select-none">
            <button
              onClick={() => setActiveTab('templates')}
              className={`px-4 py-2 text-xs font-bold transition-all border-b-2 cursor-pointer ${
                activeTab === 'templates' ? 'border-brand-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              Templates
            </button>
            <button
              onClick={() => setActiveTab('signature')}
              className={`px-4 py-2 text-xs font-bold transition-all border-b-2 cursor-pointer ${
                activeTab === 'signature' ? 'border-brand-primary text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              Signature Settings
            </button>
          </div>

          {activeTab === 'signature' ? (
            <SignatureTab />
          ) : (
            <>
              {/* METRICS */}
              {loading ? (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  {[...Array(4)].map((_, i) => (
                    <Card key={i} className="animate-pulse flex flex-col justify-between p-6">
                      <div className="h-4 bg-bg-secondary w-20 rounded" />
                      <div className="h-8 bg-bg-secondary w-28 rounded mt-4" />
                    </Card>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  <MetricCard title="Total Templates" value={stats.total} />
                  <MetricCard title="Active Templates" value={stats.active} />
                  <MetricCard title="Draft Templates" value={stats.draft} />
                  <MetricCard title="Industries Covered" value={stats.industriesCount} />
                </div>
              )}

              {/* FILTERS */}
          <Card variant="standard" padding="md" className="space-y-4 shadow-2xs">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="w-4 h-4 text-text-muted absolute left-3.5 top-3.5" />
                <input 
                  type="text" 
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search template name, subject..."
                  className="w-full text-xs font-semibold text-text-primary placeholder-text-muted bg-bg-surface border border-border-color rounded-lg pl-10 pr-3.5 py-2.5 focus:outline-none focus:border-brand-primary"
                />
              </div>

              {/* Filter Industry */}
              <Select 
                options={[
                  { label: "All Industries", value: "" },
                  ...industriesList.map(ind => ({ label: ind, value: ind }))
                ]}
                value={industryFilter}
                onChange={(e) => { setIndustryFilter(e.target.value); setPage(1); }}
              />

              {/* Filter Status */}
              <Select 
                options={[
                  { label: "All Statuses", value: "" },
                  { label: "Active", value: "active" },
                  { label: "Draft", value: "draft" }
                ]}
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
              />

              {/* Sort */}
              <Select 
                options={[
                  { label: "Recently Updated", value: "recently_updated" },
                  { label: "Name A-Z", value: "name_asc" },
                  { label: "Created Date", value: "created_date" },
                  { label: "Industry Tag", value: "industry" }
                ]}
                value={sortOrder}
                onChange={(e) => { setSortOrder(e.target.value); setPage(1); }}
              />
            </div>
          </Card>

          {/* TOAST NOTIFICATION */}
          {saveSuccessMessage && (
            <div className="fixed bottom-6 right-6 bg-status-success text-white px-5 py-3 rounded-xl shadow-lg z-50 text-xs font-bold animate-bounce">
              Template Saved Successfully ✓
            </div>
          )}

          {/* TABLE LISTING */}
          {loading ? (
            <Card variant="standard" padding="none" className="overflow-hidden shadow-2xs">
              <div className="p-4 space-y-3 animate-pulse">
                <div className="h-6 bg-bg-secondary w-full rounded" />
                <div className="h-10 bg-bg-secondary w-full rounded" />
                <div className="h-10 bg-bg-secondary w-full rounded" />
              </div>
            </Card>
          ) : templates.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-16 bg-bg-surface border border-border-color border-dashed rounded-3xl text-center space-y-5 shadow-none max-w-xl mx-auto">
              <div className="w-14 h-14 rounded-2xl bg-bg-primary border border-border-color flex items-center justify-center text-text-muted select-none shrink-0">
                <FolderOpen className="w-6 h-6 text-brand-primary" />
              </div>
              <div className="space-y-1.5">
                <h3 className="text-[17px] font-bold text-text-primary tracking-normal">No templates yet</h3>
                <p className="text-xs text-text-muted leading-relaxed max-w-xs mx-auto">Create your first outreach template to start engaging customers.</p>
              </div>
              <Button variant="primary" onClick={handleOpenCreateModal} className="flex items-center gap-1.5">
                <Plus className="w-4 h-4" />
                <span>Create your first template</span>
              </Button>
            </div>
          ) : (
            <Card variant="standard" padding="none" className="overflow-hidden shadow-2xs border border-border-color">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-bg-secondary/40 border-b border-border-color font-bold text-text-muted uppercase tracking-wider select-none">
                      <th className="p-4">Template Name</th>
                      <th className="p-4">Industry</th>
                      <th className="p-4">Subject</th>
                      <th className="p-4 text-center">Status</th>
                      <th className="p-4">Updated At</th>
                      <th className="p-4 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-color/60 font-semibold text-text-secondary">
                    {templates.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-50 transition-colors">
                        <td className="p-4 font-bold text-text-primary truncate max-w-xs">{t.template_name}</td>
                        <td className="p-4">
                          <Badge variant="neutral">{t.industry}</Badge>
                        </td>
                        <td className="p-4 truncate max-w-xs font-mono text-[11px] text-text-muted">{t.subject}</td>
                        <td className="p-4 text-center">
                          <Badge variant={t.status === 'active' ? 'success' : 'neutral'}>
                            {t.status === 'active' ? '🟢 Active' : '🟡 Draft'}
                          </Badge>
                        </td>
                        <td className="p-4 text-text-muted font-normal">{new Date(t.updated_at).toLocaleDateString()}</td>
                        <td className="p-4 text-right flex items-center justify-end gap-1.5">
                          <Button variant="secondary" size="sm" onClick={() => handleOpenPreviewDrawer(t)} title="View">
                            <Eye className="w-3.5 h-3.5 text-text-muted" />
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => handleOpenEditModal(t)} title="Edit">
                            <Edit3 className="w-3.5 h-3.5 text-text-muted" />
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => handleDuplicate(t)} title="Duplicate">
                            <Copy className="w-3.5 h-3.5 text-text-muted" />
                          </Button>
                          <Button variant="secondary" size="sm" onClick={() => handleDelete(t)} title="Delete" className="text-status-danger hover:bg-rose-50 border-rose-100 hover:text-status-danger transition-all">
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* PAGINATION */}
              {totalTemplates > limit && (
                <div className="flex items-center justify-between p-4 bg-[#F8FAFC] border-t border-border-color text-xs font-semibold text-text-muted select-none">
                  <span>Showing {(page - 1) * limit + 1} to {Math.min(page * limit, totalTemplates)} of {totalTemplates} templates</span>
                  <div className="flex items-center gap-1.5">
                    <Button 
                      variant="secondary" 
                      size="sm" 
                      disabled={page === 1}
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <span className="px-2">Page {page} of {Math.ceil(totalTemplates / limit)}</span>
                    <Button 
                      variant="secondary" 
                      size="sm" 
                      disabled={page * limit >= totalTemplates}
                      onClick={() => setPage(p => p + 1)}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          )}
          </>
          )}

          {/* VIEW TEMPLATE CENTERED MODAL */}
          {isPreviewOpen && previewTemplate && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
              <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-3xl h-[80vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-border-color shrink-0 bg-bg-surface">
                  <div>
                    <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Template Information</h3>
                    <p className="text-[10px] text-text-muted">Inspect variables and rendered previews below</p>
                  </div>
                  <button 
                    onClick={() => setIsPreviewOpen(false)}
                    className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
                  >
                    <X className="w-4.5 h-4.5" />
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                  {/* Meta stats */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center select-none shrink-0">
                    <div className="p-3 bg-[#F8FAFC] border border-border-color rounded-xl">
                      <span className="block text-[9px] font-bold text-text-muted uppercase tracking-wider">Industry</span>
                      <span className="text-xs font-bold text-text-primary">{previewTemplate.industry}</span>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-border-color rounded-xl">
                      <span className="block text-[9px] font-bold text-text-muted uppercase tracking-wider">Status</span>
                      <span className="text-xs font-bold text-text-primary">{previewTemplate.status === 'active' ? '🟢 Active' : '🟡 Draft'}</span>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-border-color rounded-xl">
                      <span className="block text-[9px] font-bold text-text-muted uppercase tracking-wider">Created</span>
                      <span className="text-xs font-bold text-text-primary font-mono">{new Date(previewTemplate.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-border-color rounded-xl">
                      <span className="block text-[9px] font-bold text-text-muted uppercase tracking-wider">Updated</span>
                      <span className="text-xs font-bold text-text-primary font-mono">{new Date(previewTemplate.updated_at).toLocaleDateString()}</span>
                    </div>
                  </div>

                  {/* Mail Preview Box */}
                  <div className="border border-border-color rounded-xl bg-bg-surface overflow-hidden shadow-xs select-text">
                    <div className="border-b border-border-color px-4 py-3 bg-[#F8FAFC] space-y-1">
                      <div className="text-2xs text-text-muted font-semibold">Subject:</div>
                      <div className="text-xs font-bold text-text-primary mt-0.5">
                        {getRenderedPreview(htmlToText(previewTemplate.body), previewTemplate.subject).subject}
                      </div>
                    </div>
                    {/* Rendered Body */}
                    <div 
                      className="p-5 text-xs text-text-secondary leading-relaxed font-sans min-h-[180px] prose prose-sm"
                      dangerouslySetInnerHTML={{ 
                        __html: getRenderedPreview(htmlToText(previewTemplate.body), previewTemplate.subject).body 
                      }}
                    />
                    
                  </div>
                </div>

                {/* Footer Buttons */}
                <div className="p-4 border-t border-border-color shrink-0 flex justify-end gap-3 bg-bg-surface">
                  <Button variant="secondary" onClick={() => setIsPreviewOpen(false)}>
                    Close
                  </Button>
                  <Button variant="primary" onClick={() => { setIsPreviewOpen(false); handleOpenEditModal(previewTemplate); }}>
                    Edit Template
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* SIMPLIFIED CREATE TEMPLATE MODAL */}
          {isEditorOpen && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
              <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-[85vw] h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
                
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-border-color shrink-0 bg-bg-surface">
                  <div className="space-y-0.5">
                    <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">
                      Create Email Template
                    </h3>
                    <div className="flex items-center gap-2 select-none text-[10px] text-text-muted font-medium">
                      {saveStatus === 'saved' && <span className="text-emerald-600 font-bold flex items-center gap-1">Saved ✓</span>}
                      {saveStatus === 'saving' && <span className="text-brand-primary font-bold animate-pulse">Saving changes...</span>}
                      {saveStatus === 'unsaved' && <span className="text-amber-600 font-bold flex items-center gap-1">Draft not saved yet</span>}
                      <span>•</span>
                      <span>Press <kbd className="bg-bg-secondary px-1.5 py-0.5 rounded font-mono font-bold">Ctrl + S</kbd> to save</span>
                    </div>
                  </div>
                  <button 
                    onClick={handleCloseEditorModal}
                    className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
                  >
                    <X className="w-4.5 h-4.5" />
                  </button>
                </div>

                {/* Split Compose Layout */}
                <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-2">
                  
                  {/* Left Column: Form & Clean Textarea */}
                  <div className="border-r border-border-color overflow-y-auto p-6 space-y-5 h-full">
                    {/* Basic Info */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 shrink-0">
                      <div className="sm:col-span-2">
                        <Input 
                          label="Template Name *"
                          value={formName}
                          onChange={(e) => { setFormName(e.target.value); setHasUnsavedChanges(true); }}
                          placeholder="e.g. Steel Importers Followup"
                          error={errors.name}
                        />
                      </div>
                      
                      {/* Searchable dropdown selector */}
                      <div className="space-y-1.5 relative" ref={industryDropdownRef}>
                        <label className="block text-xs font-medium text-text-secondary">Industry *</label>
                        <button
                          type="button"
                          onClick={() => setIsIndustryDropdownOpen(!isIndustryDropdownOpen)}
                          className="w-full flex items-center justify-between text-xs font-semibold text-text-primary bg-bg-surface border border-border-color rounded-lg px-3.5 py-2.5 shadow-2xs hover:border-slate-300 focus:outline-none transition-colors"
                        >
                          <span>{formIndustry || "Select Industry"}</span>
                          <ChevronDown className="w-4 h-4 text-text-muted" />
                        </button>
                        
                        {isIndustryDropdownOpen && (
                          <div className="absolute top-full left-0 right-0 mt-1 bg-bg-surface border border-border-color rounded-lg shadow-lg z-30 max-h-52 overflow-y-auto flex flex-col p-1.5 space-y-1">
                            <input 
                              type="text" 
                              value={industrySearch}
                              onChange={(e) => setIndustrySearch(e.target.value)}
                              placeholder="Search industry..."
                              className="w-full text-xs border border-border-color rounded px-2.5 py-1.5 focus:outline-none focus:border-brand-primary shrink-0"
                            />
                            <div className="flex-1 overflow-y-auto space-y-0.5">
                              {filteredIndustries.map(ind => (
                                <button
                                  key={ind}
                                  type="button"
                                  onClick={() => {
                                    setFormIndustry(ind);
                                    setIsIndustryDropdownOpen(false);
                                    setHasUnsavedChanges(true);
                                  }}
                                  className={`w-full text-left text-xs font-semibold px-2.5 py-1.5 rounded transition-colors ${
                                    formIndustry === ind ? 'bg-brand-primary text-white' : 'hover:bg-bg-secondary text-text-primary'
                                  }`}
                                >
                                  {ind}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {errors.industry && <p className="text-[10px] font-bold text-status-danger">{errors.industry}</p>}
                      </div>
                    </div>

                    {/* Status Toggle & explanation helper */}
                    <div className="bg-[#F8FAFC] border border-border-color/60 p-4 rounded-xl space-y-3 shrink-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-text-primary select-none">Outreach Status *</span>
                        <div className="flex items-center gap-2">
                          <button 
                            type="button"
                            onClick={() => { setFormStatus('draft'); setHasUnsavedChanges(true); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors cursor-pointer border ${
                              formStatus === 'draft' 
                                ? 'bg-bg-surface border-border-color text-text-primary shadow-2xs' 
                                : 'bg-transparent border-transparent text-text-muted hover:text-text-primary'
                            }`}
                          >
                            🟡 Draft
                          </button>
                          <button 
                            type="button"
                            onClick={() => { setFormStatus('active'); setHasUnsavedChanges(true); }}
                            className={`px-3 py-1.5 text-xs font-bold rounded-lg transition-colors cursor-pointer border ${
                              formStatus === 'active' 
                                ? 'bg-status-success/15 border-status-success/20 text-status-success shadow-2xs' 
                                : 'bg-transparent border-transparent text-text-muted hover:text-text-primary'
                            }`}
                          >
                            🟢 Active
                          </button>
                        </div>
                      </div>
                      
                      <div className="text-[10px] text-text-muted space-y-1 font-semibold leading-relaxed border-t border-border-color/40 pt-2 select-none">
                        <div><strong>Draft:</strong> Draft templates are saved but never used in campaigns.</div>
                        <div><strong>Active:</strong> Only Active templates are available for customer outreach.</div>
                      </div>
                    </div>

                    {/* Subject input */}
                    <div className="space-y-1 shrink-0">
                      <Input 
                        label="Subject Line *"
                        value={formSubject}
                        onChange={(e) => { setFormSubject(e.target.value); setHasUnsavedChanges(true); }}
                        placeholder="e.g. Shipment rates update for {{company_name}}"
                        error={errors.subject}
                      />
                      <div className="text-[10px] text-text-muted font-mono leading-none pt-1">
                        <strong>Subject Preview:</strong> {getRenderedPreview('', formSubject).subject || '(Empty Subject)'}
                      </div>
                    </div>

                    {/* How Personalization Works Help box */}
                    <div className="bg-blue-50 border border-blue-150 p-4 rounded-xl flex gap-3 text-xs text-blue-900 leading-relaxed shrink-0 select-none">
                      <Info className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
                      <div className="space-y-1">
                        <strong className="block text-[11px] text-blue-950 font-bold uppercase tracking-wider">How Personalization Works</strong>
                        <p className="text-2xs font-medium">Placeholders inside double curly braces will automatically match details for each client. For example: <code>Hello {"{{contact_name}}"}</code> becomes <code>Hello Rahul Sharma</code>.</p>
                      </div>
                    </div>

                    {/* Email body Clean Textarea */}
                    <div className="space-y-1.5 flex-1 flex flex-col min-h-[220px]">
                      <div className="flex justify-between items-baseline shrink-0 select-none">
                        <label className="block text-xs font-medium text-text-secondary">Email Template *</label>
                        <button
                          type="button"
                          onClick={handleLoadStarterTemplate}
                          className="text-[10px] font-bold text-brand-primary hover:text-brand-primary-hover hover:underline cursor-pointer"
                        >
                          Load Starter Template
                        </button>
                      </div>
                      
                      <textarea
                        value={formBody}
                        onChange={(e) => { setFormBody(e.target.value); setHasUnsavedChanges(true); }}
                        placeholder={
                          "Paste your outreach email here.\n\nYou can use variables like {{company_name}} or {{contact_name}} to personalize each email automatically."
                        }
                        className={`block w-full text-xs font-semibold text-text-primary placeholder-text-muted bg-bg-surface border border-border-color rounded-xl px-4 py-3 shadow-2xs focus:border-brand-primary focus:outline-none focus:ring-4 focus:ring-brand-primary-focus flex-1 resize-none leading-relaxed font-sans ${
                          errors.body ? 'border-status-danger focus:border-status-danger' : ''
                        }`}
                      />
                      {errors.body && <p className="text-[10px] font-bold text-status-danger shrink-0">{errors.body}</p>}
                    </div>

                  </div>

                  {/* Right Column: Preview */}
                  <div className="bg-[#F8FAFC] overflow-y-auto p-6 flex flex-col space-y-5 h-full">
                    
                    {/* Live Warnings warnings box */}
                    {validationWarnings.length > 0 && (
                      <div className="bg-rose-50 border border-rose-250 p-4 rounded-xl space-y-2 shrink-0">
                        <h5 className="text-xs font-bold text-status-danger flex items-center gap-1.5 select-none">
                          <AlertTriangle className="w-4 h-4 text-status-danger" />
                          <span>Validation issues detected</span>
                        </h5>
                        <ul className="list-disc pl-4 text-[10px] font-semibold text-rose-800 space-y-1">
                          {validationWarnings.map((w, idx) => (
                            <li key={idx}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Compact Email Client Preview Panel (Fills Right Column) */}
                    <div className="flex-1 flex flex-col space-y-2.5 h-full min-h-[350px]">
                      <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block select-none">Email Preview</span>
                      <div className="flex-1 border border-border-color rounded-xl bg-bg-surface overflow-hidden shadow-xs flex flex-col">
                        
                        {/* Fake Mail Client Header */}
                        <div className="border-b border-border-color px-4 py-3 bg-[#F8FAFC] space-y-1 shrink-0 select-text text-2xs text-text-muted font-bold leading-normal">
                          <div className="flex justify-between">
                            <span>From: {user?.full_name || "Sanjay"} &lt;sanjay@freightforce.ai&gt;</span>
                            <span>Today</span>
                          </div>
                          <div>To: Rahul Sharma &lt;rahul@abc.com&gt;</div>
                          <div className="text-xs font-bold text-text-primary pt-1 truncate">
                            Subject: {getRenderedPreview(formBody, formSubject).subject || '(Subject Line)'}
                          </div>
                        </div>

                        {/* Rendering Body Area */}
                        <div 
                          className="p-5 text-xs text-text-secondary leading-relaxed font-sans flex-1 overflow-y-auto prose prose-sm focus:outline-none"
                          dangerouslySetInnerHTML={{ 
                            __html: getRenderedPreview(formBody, formSubject).body 
                          }}
                        />
                      </div>
                    </div>
                  </div>

                </div>

                {/* Footer Controls */}
                <div className="p-4 border-t border-border-color shrink-0 flex justify-end gap-3 bg-bg-surface">
                  <Button variant="secondary" onClick={handleCloseEditorModal}>
                    Cancel
                  </Button>
                  <Button variant="primary" onClick={handleSaveTemplate} className="shadow-sm">
                    Save Changes
                  </Button>
                </div>
              </div>
            </div>
          )}

        </div>
      </PageWrapper>
    </AppShell>
  );
}
