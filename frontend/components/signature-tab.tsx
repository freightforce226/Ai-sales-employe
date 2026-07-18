'use client';

import React, { useState, useEffect } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { api } from '../lib/api';
import { 
  User, 
  Briefcase, 
  Folder, 
  Phone, 
  Globe, 
  Link as LinkIcon, 
  Image as ImageIcon, 
  Save, 
  CheckCircle,
  Monitor,
  Smartphone,
  Trash2,
  AlertCircle,
  Edit,
  Eye,
  Settings,
  Calendar,
  X
} from 'lucide-react';

interface SignatureSettings {
  is_configured: boolean;
  sender_name: string;
  designation: string;
  department: string;
  phone: string;
  website: string;
  linkedin_url: string;
  signature_html: string;
  footer_image_name: string | null;
  footer_image_content_type: string | null;
  footer_image_size: number | null;
  footer_image_path: string | null;
  footer_image_url?: string;
  updated_at?: string;
}

export function SignatureTab() {
  const [signature, setSignature] = useState<SignatureSettings>({
    is_configured: false,
    sender_name: '',
    designation: '',
    department: '',
    phone: '',
    website: '',
    linkedin_url: '',
    signature_html: '',
    footer_image_name: null,
    footer_image_content_type: null,
    footer_image_size: null,
    footer_image_path: null,
    footer_image_url: '',
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  
  // View states
  const [viewMode, setViewMode] = useState<'summary' | 'form'>('summary');
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);
  
  // Errors & success
  const [uploadError, setUploadError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [previewViewport, setPreviewViewport] = useState<'desktop' | 'mobile'>('desktop');

  useEffect(() => {
    fetchSignature();
  }, []);

  const fetchSignature = async () => {
    try {
      setIsLoading(true);
      const res = await api.get('/api/v1/organization/settings/signature');
      setSignature({
        is_configured: res.data.is_configured,
        sender_name: res.data.sender_name || '',
        designation: res.data.designation || '',
        department: res.data.department || '',
        phone: res.data.phone || '',
        website: res.data.website || '',
        linkedin_url: res.data.linkedin_url || '',
        signature_html: res.data.signature_html || '',
        footer_image_name: res.data.footer_image_name || null,
        footer_image_content_type: res.data.footer_image_content_type || null,
        footer_image_size: res.data.footer_image_size || null,
        footer_image_path: res.data.footer_image_path || null,
        footer_image_url: res.data.footer_image_url || '',
        updated_at: res.data.updated_at,
      });
      
      if (res.data.is_configured) {
        setViewMode('summary');
      } else {
        setViewMode('form');
      }
    } catch (err) {
      console.error('Failed to fetch signature settings', err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setIsSaving(true);
      setSuccessMsg('');
      
      const payload = {
        sender_name: signature.sender_name.trim(),
        designation: signature.designation.trim(),
        department: signature.department.trim() || null,
        phone: signature.phone.trim() || null,
        website: signature.website.trim() || null,
        linkedin_url: signature.linkedin_url.trim() || null,
        footer_image_name: signature.footer_image_name,
        footer_image_content_type: signature.footer_image_content_type,
        footer_image_size: signature.footer_image_size,
        footer_image_path: signature.footer_image_path,
        signature_html: '',
      };

      const res = await api.put('/api/v1/organization/settings/signature', payload);
      setSignature({
        is_configured: true,
        sender_name: res.data.sender_name || '',
        designation: res.data.designation || '',
        department: res.data.department || '',
        phone: res.data.phone || '',
        website: res.data.website || '',
        linkedin_url: res.data.linkedin_url || '',
        signature_html: res.data.signature_html || '',
        footer_image_name: res.data.footer_image_name || null,
        footer_image_content_type: res.data.footer_image_content_type || null,
        footer_image_size: res.data.footer_image_size || null,
        footer_image_path: res.data.footer_image_path || null,
        footer_image_url: res.data.footer_image_url || '',
        updated_at: res.data.updated_at,
      });
      setSuccessMsg('Signature settings saved successfully!');
      setTimeout(() => {
        setSuccessMsg('');
        setViewMode('summary');
      }, 1500);
    } catch (err) {
      console.error('Failed to save signature settings', err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async () => {
    const confirm = window.confirm(
      "Are you sure you want to delete this email signature?\n\nFuture outbound emails will no longer include a default signature until a new one is configured."
    );
    if (!confirm) return;

    try {
      setIsLoading(true);
      await api.delete('/api/v1/organization/settings/signature');
      setSignature({
        is_configured: false,
        sender_name: '',
        designation: '',
        department: '',
        phone: '',
        website: '',
        linkedin_url: '',
        signature_html: '',
        footer_image_name: null,
        footer_image_content_type: null,
        footer_image_size: null,
        footer_image_path: null,
        footer_image_url: '',
        updated_at: undefined,
      });
      setViewMode('form');
    } catch (err) {
      console.error('Failed to delete signature settings', err);
      alert('Failed to delete email signature.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleBannerUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadError('');
    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post('/api/v1/organization/settings/signature/banner', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });
      setSignature(prev => ({
        ...prev,
        footer_image_name: res.data.footer_image_name,
        footer_image_content_type: res.data.footer_image_content_type,
        footer_image_size: res.data.footer_image_size,
        footer_image_path: res.data.footer_image_path,
        footer_image_url: res.data.footer_image_url,
      }));
    } catch (err: any) {
      console.error('Failed to upload banner', err);
      setUploadError(err.response?.data?.detail || 'Failed to upload image. Max file size: 2MB.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleRemoveBanner = () => {
    setSignature(prev => ({
      ...prev,
      footer_image_name: null,
      footer_image_content_type: null,
      footer_image_size: null,
      footer_image_path: null,
    }));
  };

  const handleChange = (key: keyof SignatureSettings, value: string) => {
    setSignature(prev => ({ ...prev, [key]: value }));
  };

  const getBannerUrl = () => {
    return signature.footer_image_url || '';
  };

  // Compile signature markup for live preview dynamically on frontend
  const compileLivePreviewHtml = () => {
    const { sender_name, designation, department, phone, website, linkedin_url, footer_image_path } = signature;
    
    if (!sender_name && !designation) {
      return `
        <div style="font-family: Segoe UI, Helvetica, Arial, sans-serif; font-size: 13px; color: #94a3b8; text-align: center; padding: 40px 20px; border: 2px dashed #e2e8f0; border-radius: 8px;">
          <p style="margin: 0; font-weight: 600;">No signature configured yet</p>
          <p style="margin: 4px 0 0 0; font-size: 11px;">Complete the sender details to generate your preview.</p>
        </div>
      `;
    }

    const parts = ["Best regards,"];
    if (sender_name) {
      parts.push(`<strong>${sender_name}</strong>`);
    }
    
    const titleParts = [];
    if (designation) titleParts.push(designation);
    if (department) titleParts.push(department);
    if (titleParts.length > 0) {
      parts.push(titleParts.join(" - "));
    }
    
    const contactParts = [];
    if (phone) contactParts.push(`Phone: ${phone}`);
    if (contactParts.length > 0) {
      parts.push(contactParts.join(" | "));
    }
    
    const webParts = [];
    if (website) webParts.push(`Web: ${website}`);
    if (linkedin_url) webParts.push(`LinkedIn: ${linkedin_url}`);
    if (webParts.length > 0) {
      parts.push(webParts.join(" | "));
    }

    const compiledSignature = `<div style="font-size: 13px; color: #555555; font-family: Segoe UI, Helvetica, Arial, sans-serif;">${parts.join('<br>')}</div>`;
    const compiledBanner = footer_image_path ? `
      <div style="margin-top: 16px;">
        <img src="${getBannerUrl()}" alt="Banner" style="max-width: 100%; height: auto; border: 0; display: block;" />
      </div>
    ` : '';

    return `
      <div style="font-family: Segoe UI, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #333333; width: 100%; max-width: 600px; margin: 0 auto; background: #ffffff;">
        <p style="margin-bottom: 12px;">Dear Customer Name,</p>
        <p style="margin-bottom: 16px;">This is a mock presentation of your email content. The signature below will automatically be attached to templates and outbound campaign emails.</p>
        <div style="border-top: 1px solid #eeeeee; padding-top: 16px; margin-top: 24px;">
          ${compiledSignature}
          ${compiledBanner}
        </div>
      </div>
    `;
  };

  if (isLoading) {
    return (
      <div className="py-12 flex justify-center items-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-primary"></div>
      </div>
    );
  }

  // 1. Summary View
  if (viewMode === 'summary' && signature.is_configured) {
    return (
      <div className="space-y-6">
        {/* Signature Status & Actions Summary Card */}
        <Card className="p-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div className="flex items-start space-x-4">
              <div className="p-3.5 bg-[rgba(37,99,235,0.08)] rounded-xl text-brand-primary">
                <Settings className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-text-primary">Default Email Signature</h3>
                <p className="text-xs text-text-secondary leading-normal">
                  Configure sender parameters, custom templates, and branding banners for all automated emails.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-2 text-[10px] font-semibold text-text-muted select-none">
                  <span className="flex items-center gap-1">
                    <Calendar className="w-3.5 h-3.5" />
                    Last updated: {signature.updated_at ? new Date(signature.updated_at).toLocaleDateString() : 'N/A'}
                  </span>
                  <span>•</span>
                  <span className="text-status-success bg-status-success/10 px-2 py-0.5 rounded-full border border-status-success/15 font-bold">
                    🟢 Active Settings
                  </span>
                </div>
              </div>
            </div>

            {/* Actions list */}
            <div className="flex items-center gap-2 shrink-0 md:self-center">
              <Button variant="secondary" size="sm" onClick={() => setIsPreviewOpen(true)} className="flex items-center gap-1.5 cursor-pointer">
                <Eye className="w-3.5 h-3.5" />
                <span>View Render</span>
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setViewMode('form')} className="flex items-center gap-1.5 cursor-pointer">
                <Edit className="w-3.5 h-3.5" />
                <span>Edit Settings</span>
              </Button>
              <Button variant="danger" size="sm" onClick={handleDelete} className="flex items-center gap-1.5 cursor-pointer">
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete</span>
              </Button>
            </div>
          </div>
        </Card>

        {/* Info Grid Card */}
        <Card className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="space-y-2 col-span-2">
            <span className="text-[10px] uppercase font-bold text-text-muted tracking-wider block">Sender Details</span>
            <div className="text-xs font-semibold text-text-primary space-y-1">
              <p>Name: <span className="font-bold">{signature.sender_name}</span></p>
              <p>Designation: <span>{signature.designation}</span></p>
              {signature.department && <p>Department: <span>{signature.department}</span></p>}
              {signature.phone && <p>Phone: <span>{signature.phone}</span></p>}
            </div>
          </div>

          <div className="space-y-2">
            <span className="text-[10px] uppercase font-bold text-text-muted tracking-wider block">Online Profiles & Assets</span>
            <div className="text-xs font-semibold text-text-primary space-y-1">
              {signature.website && <p>Web: <a href={`https://${signature.website}`} target="_blank" rel="noreferrer" className="text-brand-primary hover:underline">{signature.website}</a></p>}
              {signature.linkedin_url && <p>LinkedIn: <span className="text-slate-500 break-all">{signature.linkedin_url}</span></p>}
              {signature.footer_image_path && (
                <div className="flex items-center space-x-1.5 pt-1 text-[10px] text-emerald-600 font-bold">
                  <CheckCircle className="w-3.5 h-3.5 shrink-0" />
                  <span>Banner Image Attached</span>
                </div>
              )}
            </div>
          </div>
        </Card>

        {/* View render Modal */}
        {isPreviewOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs select-none">
            <div className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-3xl h-[80vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
              <div className="flex items-center justify-between p-5 border-b border-border-color bg-bg-surface shrink-0">
                <div>
                  <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">Email Signature Preview</h3>
                  <p className="text-[10px] text-text-muted">Simulate how recipient client apps render your signature</p>
                </div>
                <div className="flex items-center space-x-4">
                  <div className="flex border border-border-color rounded-lg overflow-hidden bg-bg-primary p-0.5">
                    <button 
                      onClick={() => setPreviewViewport('desktop')}
                      className={`p-1.5 rounded cursor-pointer ${
                        previewViewport === 'desktop' ? 'bg-slate-100 text-text-primary' : 'text-slate-400 hover:text-text-primary'
                      }`}
                      title="Desktop Preview"
                    >
                      <Monitor className="w-4 h-4" />
                    </button>
                    <button 
                      onClick={() => setPreviewViewport('mobile')}
                      className={`p-1.5 rounded cursor-pointer ${
                        previewViewport === 'mobile' ? 'bg-slate-100 text-text-primary' : 'text-slate-400 hover:text-text-primary'
                      }`}
                      title="Mobile Preview"
                    >
                      <Smartphone className="w-4 h-4" />
                    </button>
                  </div>
                  <button 
                    onClick={() => setIsPreviewOpen(false)}
                    className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
                  >
                    <X className="w-4.5 h-4.5" />
                  </button>
                </div>
              </div>

              <div className="flex-1 bg-slate-50 p-6 flex justify-center items-start overflow-y-auto">
                <div 
                  className={`bg-white shadow-md border border-slate-200 transition-all duration-300 rounded-lg p-6 ${
                    previewViewport === 'mobile' ? 'w-[340px]' : 'w-full max-w-2xl'
                  }`}
                >
                  <div dangerouslySetInnerHTML={{ __html: compileLivePreviewHtml() }} />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // 2. Empty / Edit Form View
  return (
    <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
      {/* Left Column: Form & Editor */}
      <div className="xl:col-span-3 space-y-6">
        <Card className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-text-primary">
              {signature.is_configured ? 'Edit Email Signature' : 'Configure Sender Signature Profile'}
            </h2>
            {signature.is_configured && (
              <Button variant="secondary" size="sm" onClick={() => setViewMode('summary')} className="cursor-pointer">
                Cancel Edit
              </Button>
            )}
          </div>
          <form onSubmit={handleSave} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">Sender Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.sender_name}
                    onChange={(e) => handleChange('sender_name', e.target.value)}
                    placeholder="Enter full sender name (e.g. Rahul Sharma)"
                    className="pl-9"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">Designation</label>
                <div className="relative">
                  <Briefcase className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.designation}
                    onChange={(e) => handleChange('designation', e.target.value)}
                    placeholder="Enter job designation (e.g. Account Executive)"
                    className="pl-9"
                    required
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">Department (Optional)</label>
                <div className="relative">
                  <Folder className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.department}
                    onChange={(e) => handleChange('department', e.target.value)}
                    placeholder="Enter department name (e.g. Operations)"
                    className="pl-9"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">Phone Number (Optional)</label>
                <div className="relative">
                  <Phone className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.phone}
                    onChange={(e) => handleChange('phone', e.target.value)}
                    placeholder="e.g. +91 98765 43210"
                    className="pl-9"
                  />
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">Website (Optional)</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.website}
                    onChange={(e) => handleChange('website', e.target.value)}
                    placeholder="e.g. www.freightforce.ai"
                    className="pl-9"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-text-secondary mb-1.5">LinkedIn URL (Optional)</label>
                <div className="relative">
                  <LinkIcon className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
                  <Input 
                    value={signature.linkedin_url}
                    onChange={(e) => handleChange('linkedin_url', e.target.value)}
                    placeholder="e.g. linkedin.com/in/username"
                    className="pl-9"
                  />
                </div>
              </div>
            </div>

            {/* Optional Banner Image Upload */}
            <div>
              <label className="block text-xs font-bold text-text-secondary mb-1.5">Optional Footer Image (Logo Strip / Banner)</label>
              {signature.footer_image_path ? (
                <div className="flex items-center justify-between p-3 border border-border-color bg-slate-50 rounded-lg">
                  <div className="flex items-center space-x-3 truncate">
                    <ImageIcon className="w-5 h-5 text-brand-primary shrink-0" />
                    <div className="truncate">
                      <p className="text-xs font-bold text-text-primary truncate">{signature.footer_image_name}</p>
                      <p className="text-[10px] text-text-secondary">
                        {signature.footer_image_size ? `${(signature.footer_image_size / 1024).toFixed(1)} KB` : ''}
                      </p>
                    </div>
                  </div>
                  <button 
                    type="button" 
                    onClick={handleRemoveBanner}
                    className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 transition-all cursor-pointer"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="relative border-2 border-dashed border-border-color hover:border-brand-primary transition-colors rounded-lg p-6 text-center">
                  <input
                    type="file"
                    accept="image/png, image/jpeg, image/webp"
                    onChange={handleBannerUpload}
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    disabled={isUploading}
                  />
                  <ImageIcon className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                  <p className="text-xs font-bold text-text-primary">
                    {isUploading ? 'Uploading Image...' : 'Upload Signature Banner Image'}
                  </p>
                  <p className="text-[10px] text-text-secondary mt-1">PNG, JPG, JPEG, WEBP up to 2MB</p>
                </div>
              )}
              {uploadError && (
                <div className="flex items-center gap-1.5 text-status-danger text-[11px] font-semibold mt-1.5">
                  <AlertCircle className="w-3.5 h-3.5" />
                  <span>{uploadError}</span>
                </div>
              )}
            </div>

            {/* Form Action Footer */}
            <div className="flex items-center justify-between pt-4 border-t border-border-color">
              {successMsg && (
                <div className="flex items-center text-status-success text-xs font-semibold">
                  <CheckCircle className="w-4 h-4 mr-1.5" />
                  {successMsg}
                </div>
              )}
              <Button 
                type="submit" 
                isLoading={isSaving} 
                className="ml-auto flex items-center gap-1.5"
              >
                <Save className="w-4 h-4" />
                Save Settings
              </Button>
            </div>
          </form>
        </Card>
      </div>

      {/* Right Column: Live Viewport Simulator */}
      <div className="xl:col-span-2 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-text-secondary uppercase tracking-wider">Live Render Preview</h3>
          <div className="flex border border-border-color rounded-lg overflow-hidden bg-bg-primary p-0.5">
            <button 
              onClick={() => setPreviewViewport('desktop')}
              className={`p-1.5 rounded cursor-pointer ${
                previewViewport === 'desktop' ? 'bg-slate-100 text-text-primary' : 'text-slate-400 hover:text-text-primary'
              }`}
              title="Desktop Preview"
            >
              <Monitor className="w-4 h-4" />
            </button>
            <button 
              onClick={() => setPreviewViewport('mobile')}
              className={`p-1.5 rounded cursor-pointer ${
                previewViewport === 'mobile' ? 'bg-slate-100 text-text-primary' : 'text-slate-400 hover:text-text-primary'
              }`}
              title="Mobile Preview"
            >
              <Smartphone className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Viewport Emulator Frame */}
        <div className="flex justify-center items-start bg-slate-50 border border-border-color rounded-xl p-4 min-h-[460px] overflow-hidden">
          <div 
            className={`bg-white shadow-md border border-slate-200 transition-all duration-300 rounded-lg p-6 overflow-y-auto ${
              previewViewport === 'mobile' ? 'w-[340px] min-h-[420px]' : 'w-full min-h-[420px]'
            }`}
          >
            <div dangerouslySetInnerHTML={{ __html: compileLivePreviewHtml() }} />
          </div>
        </div>
      </div>
    </div>
  );
}
