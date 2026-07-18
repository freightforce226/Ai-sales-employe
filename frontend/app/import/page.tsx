'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader } from '../../components/layout/page-wrapper';
import { Card } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Badge } from '../../components/ui/feedback';
import { 
  Upload, 
  ArrowRight, 
  Check, 
  AlertTriangle, 
  FileSpreadsheet, 
  Trash2,
  RefreshCw,
  History
} from 'lucide-react';
import { api } from '../../lib/api';
import { useTenantStore } from '../../store/tenant-store';

interface BatchStats {
  id?: string;
  status: string;
  file_name?: string;
  success_count: number;
  duplicate_count: number;
  error_count: number;
  processed_rows: number;
  total_rows: number;
  created_at: string;
}

interface BatchError {
  row?: number;
  row_number?: number;
  value?: string;
  company_name?: string;
  email?: string;
  message?: string;
  errors?: Array<{ field: string; reason: string }>;
}

interface HistoryItem {
  id: string;
  file_name: string;
  status: string;
  created_at: string;
  success_count: number;
  total_rows: number;
  error_count?: number;
  duplicate_count?: number;
}

interface AxiosErrorLike {
  response?: {
    data?: {
      detail?: string;
    };
  };
}

// Fields required by the database structure
const DB_FIELDS = [
  { key: 'company_name', label: 'Company Name', required: true, desc: 'Name of the business cargo buyer' },
  { key: 'contact_name', label: 'Contact Name', required: false, desc: 'First and last name of the operations manager' },
  { key: 'contact_email', label: 'Contact Email', required: true, desc: 'Direct corporate email address' },
  { key: 'industry', label: 'Industry Sector', required: false, desc: 'Primary manufacturing or shipping trade field' }
];

export default function CSVImportPage() {
  const router = useRouter();
  const { user } = useTenantStore();
  const [step, setStep] = useState(1);
  const [file, setFile] = useState<File | null>(null);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvPreviewRows, setCsvPreviewRows] = useState<string[][]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadUrl, setUploadUrl] = useState('');
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [confirmedMappings, setConfirmedMappings] = useState<Record<string, boolean>>({});
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchStats, setBatchStats] = useState<BatchStats | null>(null);
  const [batchErrors, setBatchErrors] = useState<BatchError[]>([]);
  const [historyList, setHistoryList] = useState<HistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [allParsedRows, setAllParsedRows] = useState<string[][]>([]);
  const [headerRowIndex, setHeaderRowIndex] = useState<number>(0);
  const [savedTemplates, setSavedTemplates] = useState<any[]>([]);

  // Poll status interval references
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    fetchImportHistory();
    fetchSavedTemplates();
  }, []);

  const fetchSavedTemplates = async () => {
    try {
      const res = await api.get('/api/v1/import/mappings');
      setSavedTemplates(res.data);
    } catch (err) {
      console.error('Failed to load saved mapping templates', err);
    }
  };

  const fetchImportHistory = async () => {
    try {
      setIsLoadingHistory(true);
      const res = await api.get('/api/v1/import/history');
      setHistoryList(res.data);
    } catch (err) {
      console.error('Failed to load past import statistics', err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  // Step 1: Handle file drop & reading headers locally
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (selectedFile.name.endsWith('.csv')) {
        setFile(selectedFile);
        parseHeadersLocally(selectedFile);
      }
    }
  };

  const parseCSVLine = (line: string): string[] => {
    const result: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === ',' && !inQuotes) {
        result.push(current.trim().replace(/^["']|["']$/g, ''));
        current = '';
      } else {
        current += char;
      }
    }
    result.push(current.trim().replace(/^["']|["']$/g, ''));
    return result;
  };

  const getMappingConfidence = (fieldKey: string, mappedHeader: string): number => {
    if (!mappedHeader) return 0;
    const fk = fieldKey.toLowerCase();
    const h = mappedHeader.toLowerCase();
    
    if (h === fk) return 100;
    if (h.replace(/[\s_-]/g, '') === fk.replace(/[\s_-]/g, '')) return 98;
    
    if (fk === 'company_name') {
      if (h.includes('company') && h.includes('name')) return 98;
      if (h === 'company' || h === 'firm' || h === 'organization') return 95;
      if (h.includes('company') || h.includes('organization') || h.includes('org')) return 90;
      if (h.includes('name')) return 75;
    }
    if (fk === 'contact_name') {
      if (h === 'name' || h === 'contact' || h === 'contact name' || h === 'full name') return 95;
      if (h.includes('name') || h.includes('contact') || h.includes('person')) return 85;
    }
    if (fk === 'contact_email') {
      if (h === 'email' || h === 'mail' || h === 'contact email') return 99;
      if (h.includes('email') || h.includes('mail')) return 95;
    }
    if (fk === 'industry') {
      if (h === 'industry' || h === 'sector') return 99;
      if (h.includes('industry') || h.includes('sector') || h.includes('trade')) return 90;
    }
    
    if (h.includes(fk) || fk.includes(h)) return 70;
    return 60; // base confidence
  };

  const scoreRow = (cells: string[]): number => {
    const cleanCells = cells.map(c => c.trim().toLowerCase()).filter(c => c !== '');
    if (cleanCells.length <= 1) {
      return 0; // Ignore rows that look like title headers (e.g. only 1 column)
    }

    const CONFIDENCE_KEYWORDS = [
      'company', 'importer', 'contact', 'email', 'mail', 'phone', 'address', 
      'industry', 'sector', 'website', 'linkedin', 'name', 's/l', 'serial', 
      'goods', 'description', 'detail', 'client', 'phone number', 'zip', 
      'state', 'city', 'country'
    ];

    const IGNORE_PHRASES = [
      'importers list', 'customer report', 'export data', 'report list', 
      'export list', 'export report', 'import list', 'import report'
    ];

    let score = 0;
    
    // Penalize if the entire row contains generic report phrases
    const rowText = cleanCells.join(' ');
    for (const phrase of IGNORE_PHRASES) {
      if (rowText.includes(phrase)) {
        score -= 50;
      }
    }

    for (const cell of cleanCells) {
      // Penalize long text cells (e.g., descriptions or titles)
      if (cell.length > 40) {
        score -= 15;
        continue;
      }
      
      // Match keywords
      for (const kw of CONFIDENCE_KEYWORDS) {
        if (cell === kw) {
          score += 25; // Exact match gets high weight
        } else if (cell.includes(kw)) {
          score += 10; // Partial match
        }
      }
      
      // Add a small incentive for having actual non-empty cells
      score += 1;
    }

    return Math.max(0, score);
  };

  const applyMappingTemplateOrGuess = (headers: string[], templates: any[]) => {
    // 1. Try to find a matching template
    const headersSet = new Set(headers.map(h => h.trim().toLowerCase()));
    const matchingTemplate = templates.find(t => {
      let templateHeaders: string[] = [];
      try {
        templateHeaders = typeof t.headers === 'string' ? JSON.parse(t.headers) : t.headers;
      } catch (err) {
        templateHeaders = t.headers || [];
      }
      if (templateHeaders.length === 0) return false;
      const templateSet = new Set(templateHeaders.map(h => h.trim().toLowerCase()));
      // Compare sets
      if (templateSet.size !== headersSet.size) return false;
      for (const item of templateSet) {
        if (!headersSet.has(item)) return false;
      }
      return true;
    });

    if (matchingTemplate) {
      let colMapping = {};
      try {
        colMapping = typeof matchingTemplate.column_mapping === 'string' ? JSON.parse(matchingTemplate.column_mapping) : matchingTemplate.column_mapping;
      } catch (err) {
        colMapping = matchingTemplate.column_mapping || {};
      }
      setMapping(colMapping);
      console.log("Successfully applied persisted template mapping:", matchingTemplate.mapping_name);
      return;
    }

    // 2. Fall back to smart mapping heuristic guess
    const initialMapping: Record<string, string> = {};
    DB_FIELDS.forEach(field => {
      let bestMatch = '';
      let bestScore = 0;
      headers.forEach(h => {
        const score = getMappingConfidence(field.key, h);
        if (score > bestScore) {
          bestScore = score;
          bestMatch = h;
        }
      });
      // Suggest mapping only if confidence is 50% or higher
      if (bestScore >= 50) {
        initialMapping[field.key] = bestMatch;
      }
    });
    setMapping(initialMapping);
  };

  const handleHeaderRowChange = (index: number) => {
    setHeaderRowIndex(index);
    if (allParsedRows.length > index) {
      const headers = allParsedRows[index];
      setCsvHeaders(headers);
      
      const previewRows = allParsedRows.slice(index + 1, index + 6)
        .filter(row => row.length > 0);
      setCsvPreviewRows(previewRows);
      
      applyMappingTemplateOrGuess(headers, savedTemplates);
    }
  };

  const parseHeadersLocally = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.split('\n').map(l => l.trim()).filter(l => l !== '');
      if (lines.length > 0) {
        const parsedRows = lines.slice(0, 15).map(line => parseCSVLine(line));
        setAllParsedRows(parsedRows);

        // Scan first 10 rows before deciding the header row
        let bestIndex = 0;
        let maxScore = -1;
        const limit = Math.min(10, parsedRows.length);
        for (let i = 0; i < limit; i++) {
          const score = scoreRow(parsedRows[i]);
          if (score > maxScore) {
            maxScore = score;
            bestIndex = i;
          }
        }

        setHeaderRowIndex(bestIndex);
        const headers = parsedRows[bestIndex];
        setCsvHeaders(headers);

        const previewRows = parsedRows.slice(bestIndex + 1, bestIndex + 6)
          .filter(row => row.length > 0);
        setCsvPreviewRows(previewRows);

        applyMappingTemplateOrGuess(headers, savedTemplates);
      }
    };
    reader.readAsText(file);
  };

  // Step 2: Upload file to storage bucket via FastAPI
  const handleUploadSubmit = async () => {
    if (!file) return;
    try {
      setIsUploading(true);
      const formData = new FormData();
      formData.append('file', file);
      formData.append('header_row', String(headerRowIndex));
      const res = await api.post('/api/v1/import/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadUrl(res.data.storage_path);
      setStep(2);
    } catch (err) {
      const error = err as AxiosErrorLike;
      alert(error.response?.data?.detail || 'Supabase storage uploading failed.');
    } finally {
      setIsUploading(false);
    }
  };

  // Step 3: Map Columns
  const handleMappingChange = (fieldKey: string, csvHeader: string) => {
    setMapping(prev => ({ ...prev, [fieldKey]: csvHeader }));
  };

  const handleStartImport = async () => {
    // Check required fields
    const missing = DB_FIELDS.filter(f => f.required && !mapping[f.key]);
    if (missing.length > 0) {
      alert(`Please map all required columns: ${missing.map(m => m.label).join(', ')}`);
      return;
    }

    try {
      setIsUploading(true);
      const res = await api.post('/api/v1/import/start', {
        storage_path: uploadUrl,
        column_mapping: mapping,
        headers: csvHeaders,
        header_row: headerRowIndex,
        file_name: file?.name || 'import.csv'
      });
      setBatchId(res.data.batch_id);
      setStep(4);
      setIsPolling(true);
    } catch (err) {
      const error = err as AxiosErrorLike;
      alert(error.response?.data?.detail || 'Failed to start import pipeline.');
    } finally {
      setIsUploading(false);
    }
  };

  // Polling import batch progress details
  useEffect(() => {
    if (!isPolling || !batchId) return;

    let pollCount = 0;
    const maxPolls = 30; // 60 seconds maximum

    const interval = setInterval(async () => {
      pollCount++;
      if (pollCount > maxPolls) {
        setIsPolling(false);
        clearInterval(interval);
        alert("The import pipeline is processing in the background. You can check the final results in the Recent Imports logs below once completed.");
        setStep(1);
        setFile(null);
        fetchImportHistory();
        return;
      }

      try {
        const res = await api.get(`/api/v1/import/batches/${batchId}`);
        setBatchStats(res.data);
        
        if (res.data.status === 'completed' || res.data.status === 'failed' || res.data.status === 'partial') {
          setIsPolling(false);
          clearInterval(interval);
          
          // Fetch error details if failed rows exist
          if (res.data.error_count > 0) {
            const errRes = await api.get(`/api/v1/import/batches/${batchId}/errors`);
            setBatchErrors(errRes.data.errors);
          }
          setStep(5);
          fetchImportHistory();
        }
      } catch (err) {
        console.error('Progress polling failure:', err);
        setIsPolling(false);
        clearInterval(interval);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [isPolling, batchId]);

  const handleViewReport = async (reportBatchId: string) => {
    try {
      setIsLoadingHistory(true);
      const res = await api.get(`/api/v1/import/batches/${reportBatchId}`);
      setBatchStats(res.data);
      
      if (res.data.error_count > 0) {
        const errRes = await api.get(`/api/v1/import/batches/${reportBatchId}/errors`);
        setBatchErrors(errRes.data.errors || []);
      } else {
        setBatchErrors([]);
      }
      setStep(5);
    } catch (err) {
      console.error('Failed to load batch report:', err);
      alert('Failed to load import batch report.');
    } finally {
      setIsLoadingHistory(false);
    }
  };

  return (
    <AppShell>
      <PageWrapper>
        <PageHeader 
          breadcrumbs={[{ label: 'Operations' }, { label: 'CSV Import' }]}
          title="Customer Import Workspace"
          description="Populate your pipeline with cargo shipping customers and freight prospects."
        />

        {/* Step Indicator Panel */}
        <div className="flex items-center justify-between max-w-3xl mx-auto mb-10 select-none">
          {[
            { idx: 1, label: 'Upload File' },
            { idx: 2, label: 'Map Columns' },
            { idx: 3, label: 'Data Preview' },
            { idx: 4, label: 'Importing' },
            { idx: 5, label: 'Summary' }
          ].map((s) => (
            <React.Fragment key={s.idx}>
              {s.idx > 1 && (
                <div className={`flex-1 h-[2px] mx-4 transition-colors ${step >= s.idx ? 'bg-brand-primary' : 'bg-border-color'}`} />
              )}
              <div className="flex flex-col items-center space-y-2">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all border ${
                  step === s.idx 
                    ? 'bg-brand-primary text-white border-brand-primary shadow-xs'
                    : step > s.idx 
                      ? 'bg-emerald-500 text-white border-emerald-500'
                      : 'bg-bg-surface text-text-muted border-border-color'
                }`}>
                  {step > s.idx ? <Check className="w-4 h-4" /> : s.idx}
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-wider ${step === s.idx ? 'text-text-primary' : 'text-text-muted'}`}>
                  {s.label}
                </span>
              </div>
            </React.Fragment>
          ))}
        </div>

        {/* MAIN STEPS CONTAINER */}
        <div className="max-w-4xl mx-auto">
          
          {/* STEP 1: Upload CSV */}
          {step === 1 && (
            <div className="space-y-8">
              <Card variant="standard" className="text-center p-12">
                <div className="max-w-md mx-auto space-y-6">
                  <div className="w-16 h-16 rounded-2xl bg-bg-secondary border border-border-color flex items-center justify-center text-text-muted mx-auto select-none">
                    <Upload className="w-8 h-8" />
                  </div>
                  <div className="space-y-1.5">
                    <h3 className="text-sm font-bold text-text-primary">Upload your Customer CSV</h3>
                    <p className="text-xs text-text-muted">Accepts standard .csv containing contacts data</p>
                  </div>

                  <div className="relative border border-dashed border-border-color rounded-xl p-6 bg-[#F8FAFC] hover:bg-slate-50 transition-colors">
                    <input 
                      type="file" 
                      accept=".csv" 
                      onChange={handleFileChange}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    {file ? (
                      <div className="flex items-center justify-center space-x-2">
                        <FileSpreadsheet className="w-4 h-4 text-emerald-500" />
                        <span className="text-xs font-bold text-text-primary truncate">{file.name}</span>
                        <span className="text-[10px] text-text-muted">({(file.size / 1024).toFixed(1)} KB)</span>
                        <button onClick={(e) => { e.preventDefault(); setFile(null); }} className="p-1 hover:text-red-500 cursor-pointer">
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-text-secondary font-medium">Drag & drop or click to choose CSV file</span>
                    )}
                  </div>

                  {file && allParsedRows.length > 0 && (
                    <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-border-color text-left space-y-3">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-text-secondary">Detected Column Header Row:</label>
                        <div className="flex items-center space-x-2">
                          <select
                            value={headerRowIndex}
                            onChange={(e) => handleHeaderRowChange(Number(e.target.value))}
                            className="text-xs font-bold text-text-primary bg-bg-surface border border-border-color rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-primary"
                          >
                            {Array.from({ length: Math.min(10, allParsedRows.length) }, (_, i) => (
                              <option key={i} value={i}>Row {i + 1}</option>
                            ))}
                          </select>
                        </div>
                      </div>
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-text-muted">Detected Column Names:</span>
                        <div className="flex flex-wrap gap-1">
                          {csvHeaders.filter(h => h.trim() !== '').map((h, i) => (
                            <span key={i} className="text-[9px] font-semibold bg-bg-surface text-text-secondary border border-border-color px-2 py-0.5 rounded-md truncate max-w-[150px]">
                              {h}
                            </span>
                          ))}
                          {csvHeaders.filter(h => h.trim() !== '').length === 0 && (
                            <span className="text-[10px] text-amber-600 font-medium">No headers detected in this row</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="pt-2 border-t border-border-color/60">
                    <p className="text-[10px] font-bold text-text-muted uppercase tracking-wider mb-2">Supported Data Formats</p>
                    <div className="flex flex-wrap justify-center gap-1.5">
                      {['Apollo', 'LinkedIn', 'HubSpot', 'Zoho', 'Microsoft Excel', 'Custom CSV'].map((src) => (
                        <span key={src} className="text-[9px] font-bold bg-bg-secondary text-text-secondary border border-border-color/60 px-2 py-0.5 rounded-md">
                          {src}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="pt-2 flex justify-center">
                    <Button 
                      variant="primary" 
                      disabled={!file} 
                      isLoading={isUploading}
                      onClick={handleUploadSubmit}
                      rightIcon={<ArrowRight className="w-4 h-4" />}
                    >
                      Continue to Mapping
                    </Button>
                  </div>
                </div>
              </Card>


            </div>
          )}

          {/* STEP 2: Smart Column Mapping */}
          {step === 2 && (
            <Card variant="standard" className="space-y-6">
              <div className="pb-4 border-b border-border-color flex justify-between items-center">
                <div>
                  <h3 className="text-sm font-bold text-text-primary">Match CSV Columns</h3>
                  <p className="text-xs text-text-muted">Link headers to required database contact fields</p>
                </div>
                <Badge variant="primary">AI Smart Guess Active</Badge>
              </div>

              <div className="space-y-4">
                {DB_FIELDS.map((field) => (
                  <div key={field.key} className="flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 rounded-xl bg-bg-secondary/40 border border-border-color">
                    <div className="space-y-0.5 max-w-sm">
                      <div className="flex items-center space-x-1.5">
                        <span className="text-xs font-bold text-text-primary">{field.label}</span>
                        {field.required ? (
                          <span className="text-[10px] font-bold text-status-danger bg-status-danger-bg border border-status-danger/10 px-1.5 py-0.2 rounded-md">Required</span>
                        ) : (
                          <span className="text-[10px] text-text-muted bg-[#F8FAFC] border border-border-color px-1.5 py-0.2 rounded-md">Optional</span>
                        )}
                      </div>
                      <p className="text-[11px] text-text-muted leading-relaxed">{field.desc}</p>
                    </div>

                    <div className="w-full md:w-60 space-y-2">
                      <select 
                        value={mapping[field.key] || ''} 
                        onChange={(e) => handleMappingChange(field.key, e.target.value)}
                        className="w-full text-xs font-semibold text-text-primary bg-bg-surface border border-border-color rounded-lg px-3.5 py-2.5 shadow-2xs focus:border-brand-primary focus:outline-none focus:ring-4 focus:ring-brand-primary-focus appearance-none cursor-pointer"
                      >
                        <option value="">-- Ignore this column --</option>
                        {csvHeaders.map(h => (
                          <option key={h} value={h}>{h}</option>
                        ))}
                      </select>
                      {mapping[field.key] && (
                        <div className="flex items-center justify-between text-[10px] px-1">
                          <span className="font-semibold text-text-secondary">
                            Confidence:{' '}
                            <span className={getMappingConfidence(field.key, mapping[field.key]) >= 85 ? 'text-emerald-600' : 'text-amber-600 font-bold'}>
                              {getMappingConfidence(field.key, mapping[field.key])}%
                            </span>
                          </span>
                          {getMappingConfidence(field.key, mapping[field.key]) < 85 && (
                            <label className="flex items-center space-x-1 cursor-pointer select-none">
                              <input 
                                type="checkbox"
                                checked={!!confirmedMappings[field.key]}
                                onChange={(e) => setConfirmedMappings(prev => ({ ...prev, [field.key]: e.target.checked }))}
                                className="w-3.5 h-3.5 text-brand-primary border-border-color rounded focus:ring-brand-primary"
                              />
                              <span className="font-bold text-amber-700">Confirm</span>
                            </label>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-4 flex justify-between border-t border-border-color">
                <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
                <Button 
                  variant="primary" 
                  onClick={() => {
                    const unconfirmed = DB_FIELDS.filter(f => 
                      mapping[f.key] && 
                      getMappingConfidence(f.key, mapping[f.key]) < 85 && 
                      !confirmedMappings[f.key]
                    );
                    if (unconfirmed.length > 0) {
                      alert(`Please confirm the low-confidence mapping(s) for: ${unconfirmed.map(m => m.label).join(', ')}`);
                      return;
                    }
                    setStep(3);
                  }}
                >
                  Preview Mapping
                </Button>
              </div>
            </Card>
          )}

          {/* STEP 3: Preview Mapped Records */}
          {step === 3 && (
            <Card variant="standard" className="space-y-6">
              <div>
                <h3 className="text-sm font-bold text-text-primary">Verify Preview Mapping</h3>
                <p className="text-xs text-text-muted">Inspect how the first few records will load into the schema</p>
              </div>

              <div className="border border-border-color rounded-xl overflow-hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-bg-secondary/40 border-b border-border-color">
                      {DB_FIELDS.filter(f => mapping[f.key]).map(f => (
                        <th key={f.key} className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em]">{f.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-color/60 text-xs">
                    {csvPreviewRows.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50">
                        {DB_FIELDS.filter(f => mapping[f.key]).map(f => {
                          const csvColIdx = csvHeaders.indexOf(mapping[f.key]);
                          return (
                            <td key={f.key} className="p-3 text-text-secondary font-semibold font-mono">
                              {csvColIdx !== -1 ? row[csvColIdx] || 'N/A' : 'N/A'}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="pt-4 flex justify-between border-t border-border-color">
                <Button variant="secondary" onClick={() => setStep(2)}>Back</Button>
                <Button variant="primary" onClick={handleStartImport} isLoading={isUploading}>
                  Start Import Execution
                </Button>
              </div>
            </Card>
          )}

          {/* STEP 4: Live Processing Progress */}
          {step === 4 && (
            <Card variant="standard" className="text-center p-12 space-y-6">
              <div className="w-12 h-12 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-brand-primary mx-auto animate-spin">
                <RefreshCw className="w-6 h-6" />
              </div>
              <div className="space-y-1.5 max-w-sm mx-auto">
                <h3 className="text-sm font-bold text-text-primary">Executing Data Pipeline</h3>
                <p className="text-xs text-text-muted leading-relaxed">
                  n8n workflow is currently normalizing rows, verifying fields, checking duplicates, and upserting customers records.
                </p>
              </div>

              {batchStats && (
                <div className="max-w-md mx-auto bg-[#F8FAFC] border border-border-color rounded-xl p-4 space-y-3">
                  <div className="flex justify-between text-xs font-semibold text-text-secondary">
                    <span>Processed rows</span>
                    <span className="font-mono">{batchStats.processed_rows} / {batchStats.total_rows || '...'}</span>
                  </div>
                  {batchStats.total_rows > 0 && (
                    <div className="w-full h-2 bg-slate-200 rounded-full overflow-hidden">
                      <div 
                        style={{ width: `${(batchStats.processed_rows / batchStats.total_rows) * 100}%` }}
                        className="h-full bg-brand-primary transition-all duration-300"
                      />
                    </div>
                  )}
                  <div className="flex justify-around pt-2 text-[10px] font-bold text-text-muted uppercase tracking-wider">
                    <div>Success: <span className="text-emerald-600 font-mono">{batchStats.success_count}</span></div>
                    <div>Duplicates: <span className="text-amber-600 font-mono">{batchStats.duplicate_count}</span></div>
                    <div>Errors: <span className="text-rose-600 font-mono">{batchStats.error_count}</span></div>
                  </div>
                </div>
              )}
            </Card>
          )}

          {/* STEP 5: Import Summary & Error Reports */}
          {step === 5 && batchStats && (
            <div className="space-y-6">
              <Card variant="standard" className="space-y-6 border-t-4 border-t-emerald-500">
                <div className="flex justify-between items-start">
                  <div>
                    <h3 className="text-sm font-bold text-text-primary">CSV Import Summary</h3>
                    <p className="text-xs text-text-muted">Batch ID: <span className="font-mono text-[10px] font-bold">{batchStats.id}</span></p>
                  </div>
                  <Badge variant="success">Completed</Badge>
                </div>

                <div className="grid grid-cols-4 gap-4 text-center">
                  <div className="p-4 bg-[#F8FAFC] border border-border-color rounded-xl">
                    <span className="block text-[10px] font-bold text-text-muted uppercase tracking-wider">Total Rows</span>
                    <span className="text-xl font-bold text-text-primary font-mono">{batchStats.total_rows}</span>
                  </div>
                  <div className="p-4 bg-emerald-50/50 border border-emerald-100 rounded-xl">
                    <span className="block text-[10px] font-bold text-emerald-600 uppercase tracking-wider">Upserted</span>
                    <span className="text-xl font-bold text-emerald-600 font-mono">{batchStats.success_count}</span>
                  </div>
                  <div className="p-4 bg-amber-50/50 border border-amber-100 rounded-xl">
                    <span className="block text-[10px] font-bold text-amber-600 uppercase tracking-wider">Duplicates</span>
                    <span className="text-xl font-bold text-amber-600 font-mono">{batchStats.duplicate_count}</span>
                  </div>
                  <div className="p-4 bg-rose-50/50 border border-rose-100 rounded-xl">
                    <span className="block text-[10px] font-bold text-rose-600 uppercase tracking-wider">Failed Rows</span>
                    <span className="text-xl font-bold text-rose-600 font-mono">{batchStats.error_count}</span>
                  </div>
                </div>

                {batchStats.error_count > 0 && batchErrors.length > 0 && (
                  <div className="space-y-3 pt-4 border-t border-border-color">
                    <h4 className="text-xs font-bold text-text-primary flex items-center gap-1.5">
                      <AlertTriangle className="w-4 h-4 text-status-warning" />
                      <span>Pipeline Error Logs</span>
                    </h4>
                    <div className="border border-border-color rounded-xl overflow-hidden max-h-60 overflow-y-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-bg-secondary/40 border-b border-border-color sticky top-0">
                            <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider w-16">Row #</th>
                            <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Raw Value</th>
                            <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Validation Error</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border-color/60">
                          {batchErrors.map((err, idx) => {
                            const rowNum = err.row_number ?? err.row ?? 'N/A';
                            const rawVal = err.email || err.company_name || err.value || 'N/A';
                            const errorMsg = err.errors && err.errors.length > 0
                              ? err.errors.map(e => e.reason).join(', ')
                              : (err.message || 'Validation failed');
                            return (
                              <tr key={idx} className="hover:bg-slate-50">
                                <td className="p-3 font-semibold text-text-muted font-mono">{rowNum}</td>
                                <td className="p-3 text-text-secondary font-mono truncate max-w-xs">{rawVal}</td>
                                <td className="p-3 font-semibold text-status-danger">{errorMsg}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                <div className="pt-4 flex justify-end gap-3 border-t border-border-color">
                  <Button variant="secondary" onClick={() => { setStep(1); setFile(null); setBatchStats(null); setBatchErrors([]); }}>
                    Import Another File
                  </Button>
                  <Button variant="secondary" onClick={() => router.push('/campaigns')}>
                    Create Campaign
                  </Button>
                  <Button variant="primary" onClick={() => router.push('/customers')}>
                    View Customers
                  </Button>
                </div>
              </Card>
            </div>
          )}

          {/* RECENT IMPORTS LOGS */}
          <div className="mt-12 space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary flex items-center gap-1.5">
              <History className="w-4 h-4 text-text-muted" />
              <span>Recent Imports History Logs</span>
            </h3>
            {isLoadingHistory ? (
              <div className="py-4 text-center text-xs text-text-muted bg-bg-surface border border-border-color rounded-xl">Loading import logs...</div>
            ) : historyList.length === 0 ? (
              <div className="py-4 text-center text-xs text-text-muted bg-bg-surface border border-border-color rounded-xl">No past imports found.</div>
            ) : (
              <div className="bg-bg-surface border border-border-color rounded-xl overflow-hidden shadow-sm">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-bg-secondary/40 border-b border-border-color">
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em]">File Name</th>
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em]">Imported By</th>
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em]">Imported At</th>
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em] text-center">Total Rows</th>
                      <th className="p-3 text-[10px] font-bold text-emerald-600 uppercase tracking-[0.06em] text-center">Success</th>
                      <th className="p-3 text-[10px] font-bold text-amber-600 uppercase tracking-[0.06em] text-center">Duplicates</th>
                      <th className="p-3 text-[10px] font-bold text-rose-600 uppercase tracking-[0.06em] text-center">Errors</th>
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em]">Status</th>
                      <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-[0.06em] text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border-color/60">
                    {historyList.map((hist) => (
                      <tr key={hist.id} className="hover:bg-slate-50">
                        <td className="p-3 font-semibold text-text-primary truncate max-w-[150px]">{hist.file_name}</td>
                        <td className="p-3 text-text-secondary">{user?.full_name || 'Active User'}</td>
                        <td className="p-3 text-text-muted font-mono">{new Date(hist.created_at).toLocaleString()}</td>
                        <td className="p-3 text-center font-mono font-semibold">{hist.total_rows}</td>
                        <td className="p-3 text-center font-mono font-semibold text-emerald-600">{hist.success_count}</td>
                        <td className="p-3 text-center font-mono font-semibold text-amber-600">{hist.duplicate_count ?? 0}</td>
                        <td className="p-3 text-center font-mono font-semibold text-rose-600">{hist.error_count ?? 0}</td>
                        <td className="p-3">
                          <Badge variant={hist.status === 'completed' ? 'success' : hist.status === 'processing' ? 'primary' : 'danger'}>
                            {hist.status}
                          </Badge>
                        </td>
                        <td className="p-3 text-right">
                          <Button variant="secondary" size="sm" onClick={() => handleViewReport(hist.id)}>
                            View Report
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </PageWrapper>
    </AppShell>
  );
}
