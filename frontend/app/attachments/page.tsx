'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { Card, MetricCard } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge, Alert } from '../../components/ui/feedback';
import { Input, Select } from '../../components/ui/input';
import { ConfirmationModal } from '../../components/ui/confirmation-modal';
import {
  FileText,
  Plus,
  Search,
  Trash2,
  Eye,
  Upload,
  X,
  AlertTriangle,
  Info,
  RefreshCw,
  Download
} from 'lucide-react';
import { api } from '../../lib/api';
import { useTenantStore } from '../../store/tenant-store';

interface Attachment {
  id: string;
  organization_id: string;
  attachment_name: string;
  file_name: string;
  attachment_type: string;
  file_type: string;
  storage_path: string;
  file_path: string;
  is_active: boolean;
  attach_to_every_email: boolean;
  file_size: number;
  created_at: string | null;
  industry_tag: string | null;
}

const ATTACHMENT_TYPES = [
  "Company Profile",
  "Pricing Sheet",
  "Product Brochure",
  "Service Catalogue",
  "Presentation",
  "Case Study",
  "Footer Document",
  "Other"
];

// Helper to format file size
const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

export default function AttachmentsPage() {
  const router = useRouter();
  const { user } = useTenantStore();

  // Search & Loading state
  const [search, setSearch] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const limit = 8;

  // Modals state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  const [isReplaceOpen, setIsReplaceOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);

  // Selected records
  const [selectedAttachment, setSelectedAttachment] = useState<Attachment | null>(null);

  // Preview blob URL — fetched via axios (with cookies) to avoid cross-origin auth failure
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Form states
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState('Product Brochure');
  const [formAlwaysAttach, setFormAlwaysAttach] = useState(true); // Default ON
  const [formStatus, setFormStatus] = useState('active'); // active or draft
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const [errors, setErrors] = useState<Record<string, string>>({});
  const [actionLoading, setActionLoading] = useState(false);

  // Modal states
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deletingAttachment, setDeletingAttachment] = useState<Attachment | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [alertInfo, setAlertInfo] = useState<{ variant: 'success' | 'danger'; title: string; message: string } | null>(null);

  const showToast = (variant: 'success' | 'danger', title: string, message: string) => {
    setAlertInfo({ variant, title, message });
    setTimeout(() => setAlertInfo(null), 4000);
  };

  // Stats calculation
  const [stats, setStats] = useState({
    total: 0,
    active: 0,
    alwaysAttached: 0,
    storageUsed: 0
  });

  useEffect(() => {
    fetchAttachments();
  }, [page]);

  useEffect(() => {
    const delayDebounce = setTimeout(() => {
      setPage(1);
      fetchAttachments();
    }, 350);
    return () => clearTimeout(delayDebounce);
  }, [search]);

  // Fetch file as blob when preview modal opens — avoids cross-origin cookie auth failure
  useEffect(() => {
    if (!isPreviewOpen || !selectedAttachment) {
      // Revoke old blob URL to free memory
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
        setPreviewBlobUrl(null);
      }
      setPreviewError(null);
      return;
    }

    const loadBlob = async () => {
      setPreviewLoading(true);
      setPreviewError(null);
      try {
        const response = await api.get(
          `/api/v1/attachments/${selectedAttachment.id}/download`,
          {
            params: { preview: true },
            responseType: 'blob'
          }
        );

        // Force the correct MIME type on the blob based on file extension from storage_path
        const lowerPath = (selectedAttachment.storage_path || selectedAttachment.file_path || '').toLowerCase();
        let mimeType = 'application/pdf'; // Default fallback
        if (lowerPath.endsWith('.png')) mimeType = 'image/png';
        else if (lowerPath.endsWith('.jpg') || lowerPath.endsWith('.jpeg')) mimeType = 'image/jpeg';
        else if (lowerPath.endsWith('.gif')) mimeType = 'image/gif';
        else if (lowerPath.endsWith('.webp')) mimeType = 'image/webp';

        const blob = new Blob([response.data], { type: mimeType });
        const url = URL.createObjectURL(blob);
        setPreviewBlobUrl(url);
      } catch (err) {
        console.error('Failed to load preview blob', err);
        setPreviewError('Could not load preview. Please try downloading instead.');
      } finally {
        setPreviewLoading(false);
      }
    };

    loadBlob();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPreviewOpen, selectedAttachment?.id]);

  const fetchAttachments = async () => {
    try {
      setLoading(true);
      const res = await api.get('/api/v1/attachments', {
        params: {
          page,
          limit,
          q: search || undefined
        }
      });
      setAttachments(res.data.attachments);
      setTotal(res.data.total);

      // Fetch all for summary calculations
      const allRes = await api.get('/api/v1/attachments', { params: { limit: 1000 } });
      const all: Attachment[] = allRes.data.attachments;

      const active = all.filter(a => a.is_active).length;
      const alwaysAttached = all.filter(a => a.attach_to_every_email && a.is_active).length;
      const storageUsed = all.reduce((sum, a) => sum + (a.file_size || 0), 0);

      setStats({
        total: all.length,
        active,
        alwaysAttached,
        storageUsed
      });
    } catch (err) {
      console.error("Failed to fetch attachments", err);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const newErrors = { ...errors };
    delete newErrors.file;

    // Validate type (PDF and common images)
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    const isImg = file.type.startsWith('image/') || file.name.toLowerCase().match(/\.(png|jpg|jpeg|gif|webp)$/);
    if (!isPdf && !isImg) {
      newErrors.file = "Only PDF documents and images (PNG, JPEG, GIF, WEBP) are allowed.";
      setErrors(newErrors);
      setSelectedFile(null);
      return;
    }

    // Validate size (20MB)
    if (file.size > 20 * 1024 * 1024) {
      newErrors.file = "File exceeds the maximum 20MB limit.";
      setErrors(newErrors);
      setSelectedFile(null);
      return;
    }

    setSelectedFile(file);
    setErrors(newErrors);

    // Default attachment name to filename if blank
    if (!formName) {
      setFormName(file.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const handleOpenUploadModal = () => {
    setFormName('');
    setFormType('Product Brochure');
    setFormAlwaysAttach(true); // Default ON
    setFormStatus('active');
    setSelectedFile(null);
    setErrors({});
    setIsUploadOpen(true);
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    const newErrors: Record<string, string> = {};

    if (!formName.trim()) newErrors.name = "Attachment name is required.";
    if (!selectedFile) newErrors.file = "Please select a PDF file.";

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    try {
      setActionLoading(true);
      const formData = new FormData();
      formData.append('file', selectedFile!);
      formData.append('attachment_name', formName);
      formData.append('attachment_type', formType);
      formData.append('always_attach', String(formAlwaysAttach));
      formData.append('status_state', formStatus);

      await api.post('/api/v1/attachments', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setIsUploadOpen(false);
      fetchAttachments();
    } catch (err: any) {
      console.error(err);
      const msg = err.response?.data?.detail || "Upload failed.";
      setErrors({ file: msg });
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenEditModal = (att: Attachment) => {
    setSelectedAttachment(att);
    setFormName(att.attachment_name);
    setFormType(att.attachment_type);
    setFormAlwaysAttach(att.attach_to_every_email);
    setFormStatus(att.is_active ? 'active' : 'draft');
    setErrors({});
    setIsEditOpen(true);
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      setErrors({ name: "Attachment name is required." });
      return;
    }

    try {
      setActionLoading(true);
      await api.put(`/api/v1/attachments/${selectedAttachment?.id}`, null, {
        params: {
          attachment_name: formName,
          attachment_type: formType,
          always_attach: formAlwaysAttach,
          is_active: formStatus === 'active'
        }
      });
      setIsEditOpen(false);
      fetchAttachments();
    } catch (err: any) {
      console.error(err);
      setErrors({ name: err.response?.data?.detail || "Update failed." });
    } finally {
      setActionLoading(false);
    }
  };

  const handleOpenReplaceModal = (att: Attachment) => {
    setSelectedAttachment(att);
    setSelectedFile(null);
    setErrors({});
    setIsReplaceOpen(true);
  };

  const handleReplaceFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrors({ file: "Please select a replacement PDF file." });
      return;
    }

    try {
      setActionLoading(true);
      const formData = new FormData();
      formData.append('file', selectedFile!);

      await api.post(`/api/v1/attachments/${selectedAttachment?.id}/replace`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setIsReplaceOpen(false);
      fetchAttachments();
    } catch (err: any) {
      console.error(err);
      setErrors({ file: err.response?.data?.detail || "Replacement failed." });
    } finally {
      setActionLoading(false);
    }
  };

  const confirmDelete = async () => {
    if (!deletingAttachment) return;
    try {
      setIsDeleting(true);
      await api.delete(`/api/v1/attachments/${deletingAttachment.id}`);
      showToast('success', 'Attachment Deleted', `Successfully deleted "${deletingAttachment.attachment_name}".`);
      fetchAttachments();
    } catch (err) {
      console.error(err);
      showToast('danger', 'Deletion Failed', 'Failed to delete attachment.');
    } finally {
      setIsDeleting(false);
      setDeleteModalOpen(false);
      setDeletingAttachment(null);
    }
  };

  const handleOpenPreview = (att: Attachment) => {
    setSelectedAttachment(att);
    setPreviewBlobUrl(null);
    setPreviewError(null);
    setIsPreviewOpen(true);
  };

  const handleClosePreview = () => {
    setIsPreviewOpen(false);
    // blob URL cleanup happens inside the useEffect cleanup above
  };

  const handleDownloadBlob = () => {
    if (!previewBlobUrl || !selectedAttachment) return;
    const a = document.createElement('a');
    a.href = previewBlobUrl;
    a.download = selectedAttachment.file_name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const totalPages = Math.ceil(total / limit) || 1;

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
        <PageHeader
          title="Email Attachments"
          description="Manage campaign attachments sent automatically with outreach emails"
          actions={
            <Button variant="primary" onClick={handleOpenUploadModal} className="flex items-center gap-1.5 shadow-sm">
              <Plus className="w-4 h-4" />
              <span>Upload PDF</span>
            </Button>
          }
        />

        <div className="space-y-6 max-w-7xl mx-auto pb-10">

          {/* STATS PANEL */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 select-none">
            <MetricCard
              title="Total Attachments"
              value={stats.total}
              icon={<FileText className="w-5 h-5 text-brand-primary" />}
            />
            <MetricCard
              title="Active Attachments"
              value={stats.active}
              icon={<Badge variant="success" className="px-2 py-0.5 font-bold">Active</Badge>}
            />
            <MetricCard
              title="Always Attached"
              value={stats.alwaysAttached}
              icon={<Badge variant="primary" className="px-2 py-0.5 font-bold">Always</Badge>}
            />
            <MetricCard
              title="Storage Used"
              value={formatFileSize(stats.storageUsed)}
              icon={<Info className="w-5 h-5 text-text-muted" />}
            />
          </div>

          {/* TABLE HEADER FILTER BOX */}
          <Card className="p-4 flex flex-col sm:flex-row items-center gap-3">
            <div className="relative flex-1 w-full">
              <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search attachments by name..."
                className="pl-10 text-xs font-semibold text-text-primary placeholder-text-muted w-full bg-bg-surface"
              />
            </div>
          </Card>

          {/* ATTACHMENTS LIST TABLE */}
          <Card className="overflow-hidden border border-border-color shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-[#F8FAFC] border-b border-border-color text-[10px] font-bold text-text-muted uppercase tracking-wider select-none">
                    <th className="py-3 px-5">Attachment Name</th>
                    <th className="py-3 px-4">Type</th>
                    <th className="py-3 px-4">Size</th>
                    <th className="py-3 px-4 text-center">Always Attach</th>
                    <th className="py-3 px-4 text-center">Status</th>
                    <th className="py-3 px-4">Uploaded Date</th>
                    <th className="py-3 px-5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-color/60 bg-bg-surface">
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-text-muted select-none">
                        <div className="flex flex-col items-center justify-center gap-2">
                          <RefreshCw className="w-6 h-6 text-brand-primary animate-spin" />
                          <span className="font-semibold">Loading attachments...</span>
                        </div>
                      </td>
                    </tr>
                  ) : attachments.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-text-muted font-semibold select-none">
                        No attachments found. Upload a PDF brochure or sheet to get started.
                      </td>
                    </tr>
                  ) : (
                    attachments.map((att) => (
                      <tr key={att.id} className="hover:bg-bg-secondary/20 transition-colors">
                        <td className="py-3.5 px-5 font-bold text-text-primary truncate max-w-[200px]" title={att.attachment_name}>
                          {att.attachment_name}
                        </td>
                        <td className="py-3.5 px-4 font-semibold text-text-secondary">
                          {att.attachment_type}
                        </td>
                        <td className="py-3.5 px-4 font-mono text-text-muted">
                          {formatFileSize(att.file_size)}
                        </td>
                        <td className="py-3.5 px-4 text-center select-none">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${att.attach_to_every_email
                              ? 'bg-blue-50 text-blue-700 border border-blue-200'
                              : 'bg-gray-50 text-gray-500 border border-gray-200'
                            }`}>
                            {att.attach_to_every_email ? 'Yes' : 'No'}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 text-center select-none">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold ${att.is_active
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : 'bg-amber-50 text-amber-700 border border-amber-200'
                            }`}>
                            {att.is_active ? '🟢 Active' : '🟡 Draft'}
                          </span>
                        </td>
                        <td className="py-3.5 px-4 font-mono text-text-muted">
                          {att.created_at ? new Date(att.created_at).toLocaleDateString() : 'N/A'}
                        </td>
                        <td className="py-3.5 px-5 text-right select-none space-x-1">
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenPreview(att)}
                            className="p-1.5 h-auto text-text-secondary hover:text-brand-primary"
                            title="Preview Attachment"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenEditModal(att)}
                            className="p-1.5 h-auto text-text-secondary hover:text-brand-primary"
                            title="Edit Settings"
                          >
                            <Info className="w-3.5 h-3.5" />
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => handleOpenReplaceModal(att)}
                            className="p-1.5 h-auto text-text-secondary hover:text-brand-primary"
                            title="Replace File"
                          >
                            <RefreshCw className="w-3.5 h-3.5" />
                          </Button>
                           <Button
                             variant="secondary"
                             onClick={() => {
                               setDeletingAttachment(att);
                               setDeleteModalOpen(true);
                             }}
                             className="p-1.5 h-auto text-text-secondary hover:text-status-danger"
                             title="Delete Attachment"
                           >
                             <Trash2 className="w-3.5 h-3.5" />
                           </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* PAGINATION PANEL */}
            {totalPages > 1 && (
              <div className="border-t border-border-color px-5 py-4 flex items-center justify-between bg-bg-surface select-none">
                <span className="text-[11px] font-semibold text-text-muted">
                  Showing Page <strong className="text-text-primary">{page}</strong> of <strong className="text-text-primary">{totalPages}</strong>
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    disabled={page === 1}
                    onClick={() => setPage(prev => prev - 1)}
                    className="p-1 px-3 text-xs"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={page === totalPages}
                    onClick={() => setPage(prev => prev + 1)}
                    className="p-1 px-3 text-xs"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* UPLOAD PDF MODAL */}
        {isUploadOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
            <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-lg flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface shrink-0">
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Upload PDF Attachment</h3>
                <button onClick={() => setIsUploadOpen(false)} className="text-text-secondary hover:text-text-primary p-1.5 hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer">
                  <X className="w-4.5 h-4.5" />
                </button>
              </div>

              <form onSubmit={handleUpload} className="p-6 space-y-4">
                <div>
                  <Input
                    label="Attachment Name *"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. FreightForce Presentation 2026"
                    className="bg-bg-surface text-xs font-semibold text-text-primary"
                    error={errors.name}
                  />
                </div>

                <div>
                  <label className="block text-2xs font-bold text-text-muted uppercase tracking-wider mb-1.5">Attachment Type *</label>
                  <Select
                    value={formType}
                    onChange={(e) => setFormType(e.target.value)}
                    className="bg-bg-surface text-xs font-semibold text-text-primary w-full"
                    options={ATTACHMENT_TYPES.map(type => ({ label: type, value: type }))}
                  />
                </div>

                {/* FILE PICKER */}
                <div>
                  <label className="block text-2xs font-bold text-text-muted uppercase tracking-wider mb-1.5">Upload Document * (PDF or Image, Max 20MB)</label>
                  <div className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer ${errors.file ? 'border-status-danger bg-rose-50/10' : 'border-border-color hover:border-brand-primary'
                    }`}>
                    <input
                      type="file"
                      id="pdf-upload"
                      accept=".pdf,.png,.jpg,.jpeg,.gif,.webp"
                      className="hidden"
                      onChange={handleFileChange}
                    />
                    <label htmlFor="pdf-upload" className="cursor-pointer flex flex-col items-center justify-center gap-2">
                      <Upload className="w-8 h-8 text-text-muted" />
                      {selectedFile ? (
                        <div className="space-y-1">
                          <span className="block text-xs font-bold text-brand-primary">{selectedFile.name}</span>
                          <span className="block text-[10px] text-text-muted font-mono">{formatFileSize(selectedFile.size)}</span>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <span className="block text-xs font-bold text-text-secondary">Click to upload file</span>
                          <span className="block text-[10px] text-text-muted">PDF or image files (maximum size 20MB)</span>
                        </div>
                      )}
                    </label>
                  </div>
                  {errors.file && <p className="text-[10px] font-bold text-status-danger mt-1.5">{errors.file}</p>}
                </div>

                {/* ALWAYS ATTACH TOGGLE */}
                <div className="flex items-center justify-between p-3.5 bg-[#F8FAFC] border border-border-color rounded-xl">
                  <div className="space-y-0.5">
                    <span className="block text-xs font-bold text-text-primary">Always Attach To Every Email</span>
                    <span className="block text-[10px] text-text-muted font-semibold">Include automatically in outreach campaigns</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formAlwaysAttach}
                      onChange={(e) => setFormAlwaysAttach(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:height-4 after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                {/* STATUS PICKER */}
                <div className="flex items-center justify-between p-3.5 bg-[#F8FAFC] border border-border-color rounded-xl">
                  <div className="space-y-0.5">
                    <span className="block text-xs font-bold text-text-primary">Status State</span>
                    <span className="block text-[10px] text-text-muted font-semibold">Draft attachments are never sent</span>
                  </div>
                  <Select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value)}
                    className="bg-bg-surface text-2xs font-bold uppercase py-1 w-28 text-center"
                    options={[
                      { label: 'Active', value: 'active' },
                      { label: 'Draft', value: 'draft' }
                    ]}
                  />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <Button type="button" variant="secondary" onClick={() => setIsUploadOpen(false)}>Cancel</Button>
                  <Button type="submit" variant="primary" disabled={actionLoading} className="shadow-sm">
                    {actionLoading ? "Uploading..." : "Upload Document"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* EDIT SETTINGS MODAL */}
        {isEditOpen && selectedAttachment && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
            <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-md flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface shrink-0">
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Edit Attachment Settings</h3>
                <button onClick={() => setIsEditOpen(false)} className="text-text-secondary hover:text-text-primary p-1.5 hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer">
                  <X className="w-4.5 h-4.5" />
                </button>
              </div>

              <form onSubmit={handleUpdate} className="p-6 space-y-4">
                <div>
                  <Input
                    label="Attachment Name *"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Pricing Brochure"
                    className="bg-bg-surface text-xs font-semibold text-text-primary"
                    error={errors.name}
                  />
                </div>

                <div>
                  <label className="block text-2xs font-bold text-text-muted uppercase tracking-wider mb-1.5">Attachment Type *</label>
                  <Select
                    value={formType}
                    onChange={(e) => setFormType(e.target.value)}
                    className="bg-bg-surface text-xs font-semibold text-text-primary w-full"
                    options={ATTACHMENT_TYPES.map(type => ({ label: type, value: type }))}
                  />
                </div>

                {/* ALWAYS ATTACH TOGGLE */}
                <div className="flex items-center justify-between p-3.5 bg-[#F8FAFC] border border-border-color rounded-xl">
                  <div className="space-y-0.5">
                    <span className="block text-xs font-bold text-text-primary">Always Attach To Every Email</span>
                    <span className="block text-[10px] text-text-muted font-semibold">Include automatically in outreach campaigns</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formAlwaysAttach}
                      onChange={(e) => setFormAlwaysAttach(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:height-4 after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                  </label>
                </div>

                {/* STATUS PICKER */}
                <div className="flex items-center justify-between p-3.5 bg-[#F8FAFC] border border-border-color rounded-xl">
                  <div className="space-y-0.5">
                    <span className="block text-xs font-bold text-text-primary">Status State</span>
                    <span className="block text-[10px] text-text-muted font-semibold">Draft attachments are never sent</span>
                  </div>
                  <Select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value)}
                    className="bg-bg-surface text-2xs font-bold uppercase py-1 w-28 text-center"
                    options={[
                      { label: 'Active', value: 'active' },
                      { label: 'Draft', value: 'draft' }
                    ]}
                  />
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <Button type="button" variant="secondary" onClick={() => setIsEditOpen(false)}>Cancel</Button>
                  <Button type="submit" variant="primary" disabled={actionLoading} className="shadow-sm">
                    {actionLoading ? "Updating..." : "Save Settings"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* REPLACE PDF MODAL */}
        {isReplaceOpen && selectedAttachment && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
            <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-md flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface shrink-0">
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Replace PDF Document</h3>
                <button onClick={() => setIsReplaceOpen(false)} className="text-text-secondary hover:text-text-primary p-1.5 hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer">
                  <X className="w-4.5 h-4.5" />
                </button>
              </div>

              <form onSubmit={handleReplaceFile} className="p-6 space-y-4">
                <div className="bg-[#F8FAFC] p-3 border border-border-color rounded-xl text-2xs text-text-secondary select-text space-y-1">
                  <div>Replacing document file for attachment:</div>
                  <strong className="text-xs text-text-primary block">{selectedAttachment.attachment_name}</strong>
                  <div className="text-[10px] text-text-muted">Current file size: {formatFileSize(selectedAttachment.file_size)}</div>
                </div>

                <div>
                  <label className="block text-2xs font-bold text-text-muted uppercase tracking-wider mb-1.5">Select Replacement PDF or Image * (Max 20MB)</label>
                  <div className={`border-2 border-dashed rounded-xl p-6 text-center transition-colors cursor-pointer ${errors.file ? 'border-status-danger bg-rose-50/10' : 'border-border-color hover:border-brand-primary'
                    }`}>
                    <input
                      type="file"
                      id="pdf-replace-input"
                      accept=".pdf,.png,.jpg,.jpeg,.gif,.webp"
                      className="hidden"
                      onChange={handleFileChange}
                    />
                    <label htmlFor="pdf-replace-input" className="cursor-pointer flex flex-col items-center justify-center gap-2">
                      <Upload className="w-8 h-8 text-text-muted" />
                      {selectedFile ? (
                        <div className="space-y-1">
                          <span className="block text-xs font-bold text-brand-primary">{selectedFile.name}</span>
                          <span className="block text-[10px] text-text-muted font-mono">{formatFileSize(selectedFile.size)}</span>
                        </div>
                      ) : (
                        <div className="space-y-1">
                          <span className="block text-xs font-bold text-text-secondary">Click to choose new file</span>
                          <span className="block text-[10px] text-text-muted">PDF or image documents only</span>
                        </div>
                      )}
                    </label>
                  </div>
                  {errors.file && <p className="text-[10px] font-bold text-status-danger mt-1.5">{errors.file}</p>}
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <Button type="button" variant="secondary" onClick={() => setIsReplaceOpen(false)}>Cancel</Button>
                  <Button type="submit" variant="primary" disabled={actionLoading} className="shadow-sm">
                    {actionLoading ? "Replacing..." : "Replace File"}
                  </Button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* EMBEDDED PREVIEW MODAL */}
        {isPreviewOpen && selectedAttachment && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
            <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-4xl h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">

              {/* Header */}
              <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface shrink-0">
                <div className="space-y-0.5">
                  <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">{selectedAttachment.attachment_name}</h3>
                  <div className="flex items-center gap-2 text-[10px] text-text-muted font-semibold">
                    <span>{selectedAttachment.attachment_type}</span>
                    <span>•</span>
                    <span>{formatFileSize(selectedAttachment.file_size)}</span>
                    <span>•</span>
                    <span>{selectedAttachment.is_active ? '🟢 Active' : '🟡 Draft'}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {/* Download via blob URL (avoids cross-origin auth issues) */}
                  <button
                    onClick={handleDownloadBlob}
                    disabled={!previewBlobUrl}
                    className="p-2 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors flex items-center gap-1 text-xs font-bold disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                    title="Download file"
                  >
                    <Download className="w-4 h-4" />
                    <span>Download</span>
                  </button>
                  <button onClick={handleClosePreview} className="text-text-secondary hover:text-text-primary p-1.5 hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer">
                    <X className="w-4.5 h-4.5" />
                  </button>
                </div>
              </div>

              {/* Embedded Document Viewer — uses blob URL fetched via axios (with cookies) */}
              <div className="flex-1 bg-[#525659] overflow-hidden p-0 relative">
                {previewLoading ? (
                  /* Loading skeleton */
                  <div className="w-full h-full flex flex-col items-center justify-center gap-3 text-white/70 select-none">
                    <RefreshCw className="w-8 h-8 animate-spin" />
                    <span className="text-sm font-semibold">Loading preview...</span>
                  </div>
                ) : previewError ? (
                  /* Error state */
                  <div className="w-full h-full flex flex-col items-center justify-center gap-3 text-white/70 select-none p-8 text-center">
                    <AlertTriangle className="w-10 h-10 text-amber-400" />
                    <span className="text-sm font-semibold">{previewError}</span>
                  </div>
                ) : previewBlobUrl && (selectedAttachment.storage_path || selectedAttachment.file_path || '').toLowerCase().match(/\.(png|jpg|jpeg|gif|webp)$/) ? (
                  /* Image preview */
                  <div className="w-full h-full flex items-center justify-center bg-[#2b2b2b] p-4 overflow-auto">
                    <img
                      src={previewBlobUrl}
                      alt={selectedAttachment.attachment_name}
                      className="max-w-full max-h-full object-contain rounded-lg shadow-md select-text"
                    />
                  </div>
                ) : previewBlobUrl ? (
                  /* PDF / other document preview via blob URL with object/embed tags */
                  <object
                    data={previewBlobUrl}
                    type="application/pdf"
                    className="w-full h-full border-0"
                  >
                    <embed
                      src={previewBlobUrl}
                      type="application/pdf"
                      className="w-full h-full border-0"
                    />
                  </object>
                ) : null}
              </div>

              {/* Footer Controls */}
              <div className="p-4 border-t border-border-color shrink-0 flex justify-end gap-3 bg-bg-surface">
                <Button variant="secondary" onClick={handleClosePreview}>
                  Close
                </Button>
                <Button
                  variant="primary"
                  onClick={() => { handleClosePreview(); handleOpenReplaceModal(selectedAttachment); }}
                  className="shadow-sm"
                >
                  Replace File
                </Button>
              </div>
            </div>
          </div>
        )}

        <ConfirmationModal
          isOpen={deleteModalOpen}
          onClose={() => setDeleteModalOpen(false)}
          onConfirm={confirmDelete}
          title="Delete Attachment"
          message={`Are you sure you want to permanently delete "${deletingAttachment?.attachment_name}"? This action cannot be undone.`}
          confirmText="Delete Attachment"
          isLoading={isDeleting}
          variant="destructive"
        />
      </PageWrapper>
    </AppShell>
  );
}
