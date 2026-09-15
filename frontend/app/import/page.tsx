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
  History,
  Sparkles,
  Image as ImageIcon,
  Loader2,
  AlertCircle,
  FileImage
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
  { key: 'industry', label: 'Industry Sector', required: false, desc: 'Primary manufacturing or shipping trade field' },
  { key: 'country', label: 'Country', required: false, desc: 'Country location of the business' },
  { key: 'designation', label: 'Designation', required: false, desc: 'Job role/title of the contact person' },
  { key: 'phone', label: 'Phone', required: false, desc: 'Contact telephone or mobile number' },
  { key: 'website', label: 'Website', required: false, desc: 'Official company website URL' },
  { key: 'linkedin', label: 'LinkedIn', required: false, desc: 'LinkedIn profile URL of the contact' },
  { key: 'address', label: 'Address', required: false, desc: 'Street address details of the facility' },
  { key: 'city', label: 'City', required: false, desc: 'City of the business office' },
  { key: 'state', label: 'State', required: false, desc: 'State or province of the business' },
  { key: 'shipment_mode', label: 'Shipment Mode', required: false, desc: 'Preferred shipment mode (e.g. air, ocean)' },
  { key: 'trade_direction', label: 'Trade Direction', required: false, desc: 'Import, export, or both' },
  { key: 'customer_type', label: 'Customer Type', required: false, desc: 'Type of customer (e.g. importer, exporter)' },
  { key: 'trade_region', label: 'Trade Region', required: false, desc: 'Trade market/region (e.g. APAC, EMEA)' },
  { key: 'goods_description', label: 'Goods Description', required: false, desc: 'Description of shipped goods or commodities' }
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
  const [userOverrides, setUserOverrides] = useState<Record<string, boolean>>({});
  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchStats, setBatchStats] = useState<BatchStats | null>(null);
  const [batchErrors, setBatchErrors] = useState<BatchError[]>([]);
  const [historyList, setHistoryList] = useState<HistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [allParsedRows, setAllParsedRows] = useState<string[][]>([]);
  const [headerRowIndex, setHeaderRowIndex] = useState<number>(0);
  const [savedTemplates, setSavedTemplates] = useState<any[]>([]);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState<string>('');

  // AI OCR States
  const [activeTab, setActiveTab] = useState<'csv' | 'ocr'>('csv');
  const [ocrFiles, setOcrFiles] = useState<File[]>([]);
  const [ocrProcessingState, setOcrProcessingState] = useState<'IDLE' | 'UPLOADING' | 'AI_ANALYZING' | 'EXTRACTING' | 'REVIEW_READY' | 'IMPORTING' | 'SUCCESS' | 'ERROR'>('IDLE');
  const [ocrCandidates, setOcrCandidates] = useState<any[]>([]);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [importedSummary, setImportedSummary] = useState<{ imported: number; skipped: number } | null>(null);

  // Error Recovery States
  const [editingRowNumber, setEditingRowNumber] = useState<number | null>(null);
  const [editingFields, setEditingFields] = useState<Record<string, string>>({});
  const [isSavingCorrection, setIsSavingCorrection] = useState(false);
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [isLoadingCorrectionRow, setIsLoadingCorrectionRow] = useState(false);

  // Poll status interval references
  const [isPolling, setIsPolling] = useState(false);

  useEffect(() => {
    fetchImportHistory();
    fetchSavedTemplates();
  }, []);

  const handleOcrFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      if (selectedFiles.length + ocrFiles.length > 5) {
        alert("Maximum 5 images allowed per extraction request.");
        return;
      }
      
      const allowedExts = ['.png', '.jpg', '.jpeg', '.webp'];
      const validFiles = selectedFiles.filter(f => {
        const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase();
        const sizeValid = f.size <= 10 * 1024 * 1024; // 10MB
        return allowedExts.includes(ext) && sizeValid;
      });

      if (validFiles.length !== selectedFiles.length) {
        alert("Some files were skipped. Supported formats are PNG, JPG, JPEG, WEBP (Max 10MB per image).");
      }

      setOcrFiles(prev => [...prev, ...validFiles]);
    }
  };

  const handleOcrExtract = async () => {
    if (ocrFiles.length === 0) return;
    try {
      setOcrError(null);
      setOcrProcessingState('UPLOADING');
      
      setTimeout(() => setOcrProcessingState('AI_ANALYZING'), 800);
      setTimeout(() => setOcrProcessingState('EXTRACTING'), 2000);

      const formData = new FormData();
      ocrFiles.forEach(f => {
        formData.append('files', f);
      });

      const res = await api.post('/api/v1/import/ocr/extract', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setOcrCandidates(res.data.candidates.map((c: any, index: number) => ({
        ...c,
        id: index,
        bypass_duplicate: false
      })));
      setOcrProcessingState('REVIEW_READY');
    } catch (err: any) {
      console.error(err);
      setOcrError(err.response?.data?.detail || "AI extraction failed. Please try again with a clearer image.");
      setOcrProcessingState('ERROR');
    }
  };

  const handleCandidateChange = (index: number, field: string, value: any) => {
    setOcrCandidates(prev => prev.map((c, i) => i === index ? { ...c, [field]: value } : c));
  };

  const handleOcrConfirm = async () => {
    try {
      setOcrProcessingState('IMPORTING');
      const res = await api.post('/api/v1/import/ocr/confirm', {
        leads: ocrCandidates
      });
      setImportedSummary({
        imported: res.data.imported_count,
        skipped: res.data.skipped_count
      });
      setOcrProcessingState('SUCCESS');
      fetchImportHistory();
    } catch (err: any) {
      console.error(err);
      setOcrError(err.response?.data?.detail || "Failed to import selected leads.");
      setOcrProcessingState('ERROR');
    }
  };

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

  const uploadFileAndGetHeaders = async (selectedFile: File, chosenSheetName = '') => {
    try {
      setIsUploading(true);
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('header_row', '0');
      if (chosenSheetName) {
        formData.append('sheet_name', chosenSheetName);
      }
      const res = await api.post('/api/v1/import/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadUrl(res.data.storage_path);
      if (res.data.headers) {
        setCsvHeaders(res.data.headers);
        applyMappingTemplateOrGuess(res.data.headers, savedTemplates);
      }
      if (res.data.all_rows_preview) {
        setAllParsedRows(res.data.all_rows_preview);
        const index = res.data.header_row_used ?? 0;
        setHeaderRowIndex(index);
        const previewRows = res.data.all_rows_preview.slice(index + 1, index + 6)
          .filter((row: any) => row.length > 0);
        setCsvPreviewRows(previewRows);
      }
      if (res.data.sheet_names) {
        setSheetNames(res.data.sheet_names);
        if (res.data.sheet_names.length > 0) {
          setSelectedSheet(chosenSheetName || res.data.sheet_names[0]);
        }
      }
    } catch (err) {
      const error = err as AxiosErrorLike;
      alert(error.response?.data?.detail || 'Failed to detect headers from file.');
      setFile(null);
    } finally {
      setIsUploading(false);
    }
  };

  const handleSheetChange = async (sheetName: string) => {
    setSelectedSheet(sheetName);
    if (file) {
      await uploadFileAndGetHeaders(file, sheetName);
    }
  };

  // Step 1: Handle file drop & reading headers locally
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      const allowedExts = ['.csv', '.tsv', '.txt', '.xlsx', '.xls', '.xlsm'];
      const fileExt = selectedFile.name.substring(selectedFile.name.lastIndexOf('.')).toLowerCase();
      if (allowedExts.includes(fileExt)) {
        setFile(selectedFile);
        uploadFileAndGetHeaders(selectedFile);
      } else {
        alert("Unsupported file format. Please upload CSV, TSV, TXT, XLS, XLSX, or XLSM.");
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

  const getMappingConfidence = (fieldKey: string, mappedHeader: string, sampleValues: string[] = []): number => {
    if (!mappedHeader) return 0;
    const fk = fieldKey.toLowerCase();
    const h = mappedHeader.toLowerCase().trim();
    
    // Exact matching
    if (h === fk) return 100;
    if (h.replace(/[\s_-]/g, '') === fk.replace(/[\s_-]/g, '')) return 98;
    
    let aliasScore = 0;
    
    if (fk === 'company_name') {
      if (/^(company|firm|organization|org|customer|client|business)(_name|\s+name)?$/i.test(h)) {
        aliasScore = 95;
      } else if (h.includes('company') || h.includes('organization') || h.includes('customer') || h.includes('client')) {
        aliasScore = 90;
      }
    } else if (fk === 'contact_name') {
      if (/^(contact|person|contact\s+person|contact\s+name|full\s+name|name)$/i.test(h)) {
        aliasScore = 95;
      } else if (h.includes('name') || h.includes('contact') || h.includes('person') || h.includes('buyer')) {
        aliasScore = 85;
      }
    } else if (fk === 'contact_email') {
      if (/^(email|mail|contact\s+email|email\s+address|e-mail)$/i.test(h)) {
        aliasScore = 98;
      } else if (h.includes('email') || h.includes('mail')) {
        aliasScore = 92;
      }
    } else if (fk === 'phone') {
      if (/^(phone|mobile|telephone|tel|whatsapp|contact\s+number|mobile\s+number|phone\s+number|mobile\s+no)$/i.test(h)) {
        aliasScore = 95;
      } else if (h.includes('phone') || h.includes('mobile') || h.includes('tel') || h.includes('contact')) {
        aliasScore = 75;
      }
    } else if (fk === 'designation') {
      if (/^(designation|title|job\s+title|position|role|contact\s+designation)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'website') {
      if (/^(website|web|company\s+website|website\s+url|url)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'linkedin') {
      if (/^(linkedin|linkedin\s+url|linkedin\s+profile|linkedin\s+profile\s+url)$/i.test(h)) {
        aliasScore = 98;
      }
    } else if (fk === 'industry') {
      if (/^(industry|industry\s+sector|sector|industry\s+type|business\s+type)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'country') {
      if (/^(country|country\s+name)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'city') {
      if (/^(city|city\s+name|town)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'state') {
      if (/^(state|state\s+name|province|state\/province)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'address') {
      if (/^(address|full\s+address|company\s+address|office\s+address|location)$/i.test(h)) {
        aliasScore = 95;
      }
    } else if (fk === 'goods_description') {
      if (/^(goods|goods\s+description|product|products|commodity|commodities|items|cargo|product\s+description)$/i.test(h)) {
        aliasScore = 95;
      }
    }
    
    // Perform cell validation boosts
    if (sampleValues.length > 0) {
      let emailMatches = 0;
      let phoneMatches = 0;
      let urlMatches = 0;
      let countryMatches = 0;
      let cityMatches = 0;
      let designationMatches = 0;
      
      const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      const phoneRegex = /^(\+?\d{1,4}[-.\s]?)?\(?\d{3,5}\)?[-.\s]?\d{3,5}[-.\s]?\d{3,9}$/;
      const urlRegex = /^(https?:\/\/)?(www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(\/\S*)?$/;
      const designationKeywords = ['manager', 'director', 'ceo', 'vp', 'executive', 'sales', 'rep', 'lead', 'partner', 'officer', 'head', 'owner', 'proprietor', 'assistant', 'asst', 'supervisor', 'admin'];
      const countries = ['india', 'china', 'usa', 'united states', 'uae', 'vietnam', 'singapore', 'malaysia', 'bangladesh', 'germany', 'uk', 'france', 'italy', 'spain', 'canada', 'australia', 'japan', 'korea'];
      const cities = ['mumbai', 'delhi', 'ghaziabad', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'pune', 'gurgaon', 'noida', 'ahmedabad', 'shenzhen', 'shanghai', 'guangzhou', 'ningbo', 'qingdao', 'new york', 'london', 'tokyo', 'singapore', 'dubai'];
      
      sampleValues.forEach(val => {
        const v = val.trim().toLowerCase();
        if (!v) return;
        if (emailRegex.test(v)) emailMatches++;
        if (phoneRegex.test(v) && v.replace(/[^\d]/g, '').length >= 7) phoneMatches++;
        if (urlRegex.test(v)) urlMatches++;
        if (designationKeywords.some(kw => v.includes(kw))) designationMatches++;
        if (countries.includes(v)) countryMatches++;
        if (cities.includes(v)) cityMatches++;
      });
      
      const len = sampleValues.length;
      if (fk === 'contact_email' && (emailMatches / len) >= 0.5) return 100;
      if (fk === 'phone' && (phoneMatches / len) >= 0.5) return 100;
      if (fk === 'website' && (urlMatches / len) >= 0.5 && !h.includes('linkedin')) return 98;
      if (fk === 'linkedin' && (urlMatches / len) >= 0.5 && h.includes('linkedin')) return 100;
      if (fk === 'designation' && (designationMatches / len) >= 0.5) return 95;
      if (fk === 'country' && (countryMatches / len) >= 0.5) return 98;
      if (fk === 'city' && (cityMatches / len) >= 0.5) return 98;
      
      // Override vague headers if values are strong
      if ((phoneMatches / len) >= 0.8 && fk === 'phone') return 95;
      if ((emailMatches / len) >= 0.8 && fk === 'contact_email') return 95;
    }
    
    if (aliasScore > 0) return aliasScore;
    
    // Partial substring fallback
    if (h.includes(fk) || fk.includes(h)) return 70;
    return 0;
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
      let colMapping: Record<string, string> = {};
      try {
        colMapping = typeof matchingTemplate.column_mapping === 'string' ? JSON.parse(matchingTemplate.column_mapping) : matchingTemplate.column_mapping;
      } catch (err) {
        colMapping = matchingTemplate.column_mapping || {};
      }
      setMapping(prev => {
        const merged: Record<string, string> = { ...colMapping };
        Object.keys(prev).forEach(k => {
          if (userOverrides[k]) {
            merged[k] = prev[k];
          }
        });
        return merged;
      });
      console.log("Successfully applied persisted template mapping:", matchingTemplate.mapping_name);
      return;
    }

    // 2. Fall back to smart mapping heuristic guess
    const initialMapping: Record<string, string> = {};
    const mappedCSVHeaders = new Set<string>();

    // Mark overridden values as already mapped
    DB_FIELDS.forEach(field => {
      if (userOverrides[field.key]) {
        const val = mapping[field.key];
        if (val) {
          mappedCSVHeaders.add(val);
        }
      }
    });

    // Prioritize required fields
    const sortedFields = [...DB_FIELDS].sort((a, b) => (a.required ? -1 : 1));

    sortedFields.forEach(field => {
      if (userOverrides[field.key]) {
        return;
      }
      let bestMatch = '';
      let bestScore = 0;
      headers.forEach(h => {
        if (mappedCSVHeaders.has(h)) {
          return;
        }
        
        const colIdx = headers.indexOf(h);
        const sampleValues = csvPreviewRows.map(row => row[colIdx]).filter(Boolean);
        
        const score = getMappingConfidence(field.key, h, sampleValues);
        if (score > bestScore) {
          bestScore = score;
          bestMatch = h;
        }
      });
      
      // Auto-select only if confidence score is >= 70
      if (bestScore >= 70 && bestMatch) {
        initialMapping[field.key] = bestMatch;
        mappedCSVHeaders.add(bestMatch);
      } else {
        initialMapping[field.key] = '';
      }
    });

    setMapping(prev => {
      const merged = { ...prev };
      DB_FIELDS.forEach(field => {
        if (!userOverrides[field.key]) {
          merged[field.key] = initialMapping[field.key] || '';
        }
      });
      return merged;
    });
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
      if (selectedSheet) {
        formData.append('sheet_name', selectedSheet);
      }
      const res = await api.post('/api/v1/import/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadUrl(res.data.storage_path);
      if (res.data.headers) {
        setCsvHeaders(res.data.headers);
        applyMappingTemplateOrGuess(res.data.headers, savedTemplates);
      }
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
    setUserOverrides(prev => ({ ...prev, [fieldKey]: true }));
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
          
          // Always fetch error log — validation errors exist regardless of webhook status
          try {
            const errRes = await api.get(`/api/v1/import/batches/${batchId}/errors`);
            // Filter out system-level webhook_error entries that are not user-correctable row errors
            const allErrors = errRes.data.errors || [];
            const rowErrors = allErrors.filter((e: any) => e.row_number !== undefined && e.row_number !== null);
            setBatchErrors(rowErrors);
          } catch (errFetchErr) {
            console.error('Failed to fetch error details:', errFetchErr);
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
      setBatchId(reportBatchId);
      
      // Always fetch error log to show all validation failures
      try {
        const errRes = await api.get(`/api/v1/import/batches/${reportBatchId}/errors`);
        const allErrors = errRes.data.errors || [];
        // Filter out system-level webhook_error entries
        const rowErrors = allErrors.filter((e: any) => e.row_number !== undefined && e.row_number !== null);
        setBatchErrors(rowErrors);
      } catch (errFetchErr) {
        console.error('Failed to fetch error log:', errFetchErr);
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

  const getBatchAgeInHours = (batch: { completed_at?: string; created_at: string }) => {
    const t = batch.completed_at || batch.created_at;
    if (!t) return 999;
    const diffMs = Date.now() - new Date(t).getTime();
    return diffMs / (1000 * 3600);
  };

  const getRecoveryWindowString = (batch: { completed_at?: string; created_at: string }) => {
    const t = batch.completed_at || batch.created_at;
    if (!t) return "Recovery window expired";
    const diffMs = Date.now() - new Date(t).getTime();
    const ageHrs = diffMs / (1000 * 3600);
    if (ageHrs > 10) {
      return "Recovery window expired";
    }
    const remainingMs = (10 * 3600 * 1000) - diffMs;
    const hrs = Math.floor(remainingMs / (1000 * 3600));
    const mins = Math.floor((remainingMs % (1000 * 3600)) / (1000 * 60));
    return `Recovery available · ${hrs}h ${mins}m remaining`;
  };

  const isRecoverableError = (errorText: string) => {
    if (!errorText) return false;
    const t = errorText.toLowerCase();
    return (
      t.includes('email') ||
      t.includes('invalid') ||
      t.includes('domain') ||
      t.includes('syntax') ||
      t.includes('tld') ||
      t.includes('company name missing') ||
      t.includes('missing') ||
      t.includes('whitespace') ||
      t.includes('dot') ||
      t.includes('top-level')
    );
  };


  const handleStartEdit = async (rowNumber: number) => {
    if (!batchId) return;
    try {
      setIsLoadingCorrectionRow(true);
      setCorrectionError(null);
      setEditingRowNumber(rowNumber);
      
      const res = await api.get(`/api/v1/import/batches/${batchId}/errors/${rowNumber}`);
      setEditingFields(res.data.row_data || {});
    } catch (err) {
      console.error("Failed to load row data for edit:", err);
      alert("Failed to load row details for editing.");
      setEditingRowNumber(null);
    } finally {
      setIsLoadingCorrectionRow(false);
    }
  };

  const handleSaveCorrection = async (rowNumber: number) => {
    if (!batchId) return;
    try {
      setIsSavingCorrection(true);
      setCorrectionError(null);
      
      const payload = {
        company_name: editingFields.company_name || "",
        contact_name: editingFields.contact_name || "",
        contact_email: editingFields.contact_email || "",
        industry: editingFields.industry || "",
        phone: editingFields.phone || "",
        website: editingFields.website || "",
        designation: editingFields.designation || "",
        address: editingFields.address || "",
        city: editingFields.city || "",
        state: editingFields.state || "",
        country: editingFields.country || "",
        shipment_mode: editingFields.shipment_mode || "",
        trade_direction: editingFields.trade_direction || "",
        customer_type: editingFields.customer_type || "",
        trade_region: editingFields.trade_region || "",
        linkedin: editingFields.linkedin || "",
        goods_description: editingFields.goods_description || ""
      };
      
      const res = await api.post(`/api/v1/import/batches/${batchId}/errors/${rowNumber}/correct`, payload);
      
      if (res.data.success) {
        if (batchStats) {
          const nextFailed = Math.max(0, batchStats.error_count - 1);
          const nextSuccess = batchStats.success_count + 1;
          const nextStatus = nextFailed === 0 ? "completed" : batchStats.status;
          setBatchStats({
            ...batchStats,
            error_count: nextFailed,
            success_count: nextSuccess,
            status: nextStatus
          });
        }
        
        setBatchErrors(prev => prev.filter(err => {
          const rNum = err.row_number ?? err.row;
          return rNum !== rowNumber;
        }));
        
        setEditingRowNumber(null);
      }
    } catch (err: any) {
      console.error("Failed to save row correction:", err);
      const errMsg = err.response?.data?.detail?.errors?.[0] || err.response?.data?.detail || "Validation failed.";
      setCorrectionError(errMsg);
    } finally {
      setIsSavingCorrection(false);
    }
  };

  const handleDownloadErrorCsv = async () => {
    if (!batchId) return;
    try {
      const res = await api.get(`/api/v1/import/batches/${batchId}/errors/download`, {
        responseType: 'blob'
      });
      const blob = new Blob([res.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `import_errors_${batchId}.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Failed to download error CSV:", err);
      alert("Failed to download error CSV.");
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
        {activeTab === 'csv' && (
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
        )}

        {/* MAIN STEPS CONTAINER */}
        <div className="max-w-4xl mx-auto">
          {step === 1 && (
            <div className="flex border-b border-border-color mb-8">
              <button
                className={`py-3 px-6 text-sm font-bold border-b-2 transition-all ${
                  activeTab === 'csv'
                    ? 'border-brand-primary text-text-primary'
                    : 'border-transparent text-text-muted hover:text-text-secondary'
                }`}
                onClick={() => setActiveTab('csv')}
              >
                CSV / Spreadsheet Import
              </button>
              <button
                className={`py-3 px-6 text-sm font-bold border-b-2 transition-all flex items-center space-x-1.5 ${
                  activeTab === 'ocr'
                    ? 'border-brand-primary text-text-primary'
                    : 'border-transparent text-text-muted hover:text-text-secondary'
                }`}
                onClick={() => setActiveTab('ocr')}
              >
                <Sparkles className="w-4 h-4 text-indigo-500 animate-pulse" />
                <span>OCR with AI</span>
              </button>
            </div>
          )}

          {/* STEP 1: Upload CSV */}
          {step === 1 && activeTab === 'csv' && (
            <div className="space-y-8">
              <Card variant="standard" className="text-center p-12">
                <div className="max-w-md mx-auto space-y-6">
                  <div className="w-16 h-16 rounded-2xl bg-bg-secondary border border-border-color flex items-center justify-center text-text-muted mx-auto select-none">
                    <Upload className="w-8 h-8" />
                  </div>
                  <div className="space-y-1.5">
                    <h3 className="text-sm font-bold text-text-primary">Upload your Customer Data</h3>
                    <p className="text-xs text-text-muted">Accepts CSV, TSV, TXT, XLS, XLSX, and XLSM files</p>
                  </div>

                  <div className="relative border border-dashed border-border-color rounded-xl p-6 bg-[#F8FAFC] hover:bg-slate-50 transition-colors">
                    <input 
                      type="file" 
                      accept=".csv,.tsv,.txt,.xlsx,.xls,.xlsm" 
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
                      {sheetNames.length > 1 && (
                        <div className="flex items-center justify-between border-b border-border-color pb-3">
                          <label className="text-xs font-bold text-text-secondary">Select Worksheet:</label>
                          <select
                            value={selectedSheet}
                            onChange={(e) => handleSheetChange(e.target.value)}
                            className="text-xs font-bold text-text-primary bg-bg-surface border border-border-color rounded-md px-2 py-1 focus:outline-none focus:ring-1 focus:ring-brand-primary cursor-pointer"
                          >
                            {sheetNames.map((name) => (
                              <option key={name} value={name}>{name}</option>
                            ))}
                          </select>
                        </div>
                      )}
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

          {step === 1 && activeTab === 'ocr' && (
            <div className="space-y-8 animate-fadeIn">
              {ocrProcessingState === 'IDLE' && (
                <Card variant="standard" className="p-12 text-center space-y-6">
                  <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-500 mx-auto">
                    <Sparkles className="w-8 h-8 animate-pulse" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-lg font-bold text-text-primary">OCR with AI</h3>
                    <p className="text-sm text-text-muted max-w-md mx-auto">
                      Turn business cards, catalog pages, and contact list screenshots into ready-to-use leads.
                    </p>
                  </div>

                  <div className="max-w-md mx-auto border border-dashed border-indigo-200 rounded-xl p-8 bg-[#F8FAFF] hover:bg-indigo-50/30 transition-colors relative">
                    <input
                      type="file"
                      multiple
                      accept="image/png, image/jpeg, image/jpg, image/webp"
                      onChange={handleOcrFileChange}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <div className="flex flex-col items-center space-y-3">
                      <ImageIcon className="w-8 h-8 text-indigo-400" />
                      <span className="text-xs font-semibold text-text-secondary">
                        Drag & drop or click to upload contact images
                      </span>
                      <span className="text-[10px] text-text-muted">
                        Supports PNG, JPG, JPEG, WEBP • Max 5 files • Up to 10MB per image
                      </span>
                    </div>
                  </div>

                  {ocrFiles.length > 0 && (
                    <div className="max-w-md mx-auto p-4 rounded-xl border border-border-color bg-bg-surface text-left space-y-3">
                      <div className="flex items-center justify-between border-b border-border-color pb-2">
                        <span className="text-xs font-bold text-text-primary">Selected Files ({ocrFiles.length})</span>
                        <button
                          onClick={() => setOcrFiles([])}
                          className="text-[10px] font-bold text-red-500 hover:underline cursor-pointer"
                        >
                          Clear All
                        </button>
                      </div>
                      <div className="space-y-1.5 max-h-40 overflow-y-auto pr-1">
                        {ocrFiles.map((f, i) => {
                          const previewUrl = URL.createObjectURL(f);
                          return (
                            <div key={i} className="flex items-center justify-between text-xs p-2 bg-slate-50 border border-border-color rounded-lg">
                              <div className="flex items-center space-x-2 truncate">
                                <img
                                  src={previewUrl}
                                  alt="preview"
                                  className="w-8 h-8 object-cover rounded-md border border-border-color flex-shrink-0"
                                  onLoad={() => URL.revokeObjectURL(previewUrl)}
                                />
                                <div className="flex flex-col truncate">
                                  <span className="font-semibold text-text-primary truncate">{f.name}</span>
                                  <span className="text-[10px] text-text-muted">({(f.size / 1024).toFixed(1)} KB)</span>
                                </div>
                              </div>
                              <button
                                onClick={() => setOcrFiles(prev => prev.filter((_, idx) => idx !== i))}
                                className="text-text-muted hover:text-red-500 cursor-pointer"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          );
                        })}
                      </div>
                      <div className="pt-2">
                        <Button
                          variant="primary"
                          onClick={handleOcrExtract}
                          className="w-full flex items-center justify-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 border-indigo-600 hover:border-indigo-700 cursor-pointer"
                        >
                          <Sparkles className="w-4 h-4" />
                          <span>Analyze & Extract Leads</span>
                        </Button>
                      </div>
                    </div>
                  )}
                </Card>
              )}

              {/* Step-based Shimmer Loader */}
              {(ocrProcessingState === 'UPLOADING' || ocrProcessingState === 'AI_ANALYZING' || ocrProcessingState === 'EXTRACTING') && (
                <Card variant="standard" className="p-16 text-center space-y-8 bg-bg-surface border border-indigo-100 shadow-md max-w-md mx-auto">
                  <div className="relative w-20 h-20 mx-auto flex items-center justify-center">
                    <div className="absolute inset-0 rounded-full border-4 border-indigo-100 border-t-indigo-600 animate-spin" />
                    <Sparkles className="w-8 h-8 text-indigo-500 animate-pulse" />
                  </div>

                  <div className="space-y-4 max-w-sm mx-auto">
                    <h3 className="text-base font-bold text-text-primary">✨ OCR with AI</h3>
                    
                    <div className="space-y-2.5 text-left border border-border-color rounded-xl p-4 bg-slate-50">
                      <div className="flex items-center space-x-2.5 text-xs font-semibold">
                        <Check className="w-4 h-4 text-emerald-500" />
                        <span className="text-text-secondary">Reading image context</span>
                      </div>
                      <div className="flex items-center space-x-2.5 text-xs font-semibold">
                        {ocrProcessingState === 'UPLOADING' ? (
                          <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                        ) : (
                          <Check className="w-4 h-4 text-emerald-500" />
                        )}
                        <span className={ocrProcessingState === 'UPLOADING' ? 'text-text-primary' : 'text-text-secondary'}>
                          Finding people & companies
                        </span>
                      </div>
                      <div className="flex items-center space-x-2.5 text-xs font-semibold">
                        {ocrProcessingState === 'AI_ANALYZING' ? (
                          <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                        ) : ocrProcessingState === 'EXTRACTING' ? (
                          <Check className="w-4 h-4 text-emerald-500" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-border-color" />
                        )}
                        <span className={ocrProcessingState === 'AI_ANALYZING' ? 'text-text-primary' : 'text-text-muted'}>
                          Extracting contact details
                        </span>
                      </div>
                      <div className="flex items-center space-x-2.5 text-xs font-semibold">
                        {ocrProcessingState === 'EXTRACTING' ? (
                          <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                        ) : (
                          <div className="w-4 h-4 rounded-full border border-border-color" />
                        )}
                        <span className={ocrProcessingState === 'EXTRACTING' ? 'text-text-primary' : 'text-text-muted'}>
                          Structuring lead records
                        </span>
                      </div>
                    </div>

                    <p className="text-xs text-text-muted italic animate-pulse">
                      {ocrProcessingState === 'UPLOADING' && "Uploading your contact images..."}
                      {ocrProcessingState === 'AI_ANALYZING' && "Gemini is examining business visual context..."}
                      {ocrProcessingState === 'EXTRACTING' && "Structuring contacts and details..."}
                    </p>
                  </div>
                </Card>
              )}

              {ocrProcessingState === 'ERROR' && (
                <Card variant="standard" className="p-8 text-center space-y-4 max-w-md mx-auto">
                  <AlertCircle className="w-12 h-12 text-red-500 mx-auto" />
                  <h3 className="text-sm font-bold text-text-primary">Extraction Failed</h3>
                  <p className="text-xs text-text-muted max-w-sm mx-auto">{ocrError}</p>
                  <Button
                    variant="outline"
                    onClick={() => { setOcrProcessingState('IDLE'); setOcrFiles([]); }}
                    className="mx-auto cursor-pointer"
                  >
                    Try Again
                  </Button>
                </Card>
              )}

              {/* Step 3: REVIEW_READY */}
              {ocrProcessingState === 'REVIEW_READY' && (
                <div className="space-y-6 animate-fadeIn max-w-3xl mx-auto">
                  <div className="flex justify-between items-center border-b border-border-color pb-4">
                    <div>
                      <h3 className="text-lg font-bold text-text-primary">✨ AI Extraction Complete</h3>
                      <p className="text-xs text-text-muted">
                        We found {ocrCandidates.length} potential lead{ocrCandidates.length !== 1 ? 's' : ''} from {ocrFiles.length} image{ocrFiles.length !== 1 ? 's' : ''}. Review and edit the extracted details before importing.
                      </p>
                    </div>
                    <div className="flex space-x-2">
                      <Button
                        variant="outline"
                        onClick={() => { setOcrProcessingState('IDLE'); setOcrFiles([]); setOcrCandidates([]); }}
                        className="text-xs py-1.5 cursor-pointer"
                      >
                        Cancel
                      </Button>
                      <Button
                        variant="primary"
                        onClick={handleOcrConfirm}
                        className="text-xs py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold border-indigo-600 hover:border-indigo-700 cursor-pointer"
                      >
                        Import Selected Leads ({ocrCandidates.length})
                      </Button>
                    </div>
                  </div>

                  <div className="space-y-6">
                    {ocrCandidates.map((cand, idx) => (
                      <Card key={cand.id} className="p-6 border border-border-color bg-bg-surface hover:shadow-sm transition-shadow relative space-y-6 max-w-2xl mx-auto">
                        <div className="flex justify-between items-start">
                          <span className="text-xs font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-md px-2.5 py-1 select-none">
                            ✨ AI Extracted Lead
                          </span>
                          {cand.is_duplicate && (
                            <span className="text-[10px] font-bold text-amber-600 bg-amber-50 border border-amber-100 rounded-md px-2.5 py-1 flex items-center space-x-1 select-none animate-pulse">
                              <AlertTriangle className="w-3 h-3 flex-shrink-0" />
                              <span>Duplicate Warning</span>
                            </span>
                          )}
                        </div>

                        {cand.is_duplicate && (
                          <div className="p-3 rounded-lg border border-amber-200 bg-amber-50 text-xs text-amber-800 flex flex-col space-y-1">
                            <span className="font-bold">{cand.duplicate_reason}</span>
                            <label className="flex items-center space-x-1.5 cursor-pointer">
                              <input
                                type="checkbox"
                                checked={cand.bypass_duplicate}
                                onChange={(e) => handleCandidateChange(idx, 'bypass_duplicate', e.target.checked)}
                                className="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
                              />
                              <span className="font-semibold">Import this customer anyway</span>
                            </label>
                          </div>
                        )}

                        <div className="space-y-4">
                          <div>
                            <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1.5">Company Name</label>
                            <input
                              type="text"
                              value={cand.company_name}
                              onChange={(e) => handleCandidateChange(idx, 'company_name', e.target.value)}
                              className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface font-semibold"
                              placeholder="Not detected"
                            />
                          </div>

                          <div className="border-t border-border-color/60 pt-4 space-y-4">
                            <h4 className="text-[10px] font-bold uppercase tracking-wider text-indigo-600/90">Contact Information</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">Contact Name</label>
                                <input
                                  type="text"
                                  value={cand.contact_name || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'contact_name', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface"
                                  placeholder="Not detected"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">Designation</label>
                                <input
                                  type="text"
                                  value={cand.designation || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'designation', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface"
                                  placeholder="Not detected"
                                />
                              </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">Contact Email</label>
                                <input
                                  type="text"
                                  value={cand.contact_email || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'contact_email', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface font-mono"
                                  placeholder="Not detected"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">Phone</label>
                                <input
                                  type="text"
                                  value={cand.phone || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'phone', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface font-mono"
                                  placeholder="Not detected"
                                />
                              </div>
                            </div>
                          </div>

                          <div className="border-t border-border-color/60 pt-4 space-y-4">
                            <h4 className="text-[10px] font-bold uppercase tracking-wider text-indigo-600/90">Online Presence</h4>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">Website</label>
                                <input
                                  type="text"
                                  value={cand.website || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'website', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface"
                                  placeholder="Not detected"
                                />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1">LinkedIn</label>
                                <input
                                  type="text"
                                  value={cand.linkedin || ''}
                                  onChange={(e) => handleCandidateChange(idx, 'linkedin', e.target.value)}
                                  className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface"
                                  placeholder="Not detected"
                                />
                              </div>
                            </div>
                          </div>

                          <div className="border-t border-border-color/60 pt-4">
                            <label className="block text-[10px] font-bold text-text-muted uppercase tracking-wider mb-1.5">Notes / Services Details</label>
                            <textarea
                              rows={2}
                              value={cand.notes || ''}
                              onChange={(e) => handleCandidateChange(idx, 'notes', e.target.value)}
                              className="w-full bg-slate-50 border border-border-color rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:bg-bg-surface resize-none"
                              placeholder="Extra details from business card..."
                            />
                          </div>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              )}

              {/* IMPORTING State */}
              {ocrProcessingState === 'IMPORTING' && (
                <Card variant="standard" className="p-16 text-center space-y-4">
                  <Loader2 className="w-12 h-12 text-indigo-600 animate-spin mx-auto" />
                  <h3 className="text-sm font-bold text-text-primary">Saving Contacts to Pipeline...</h3>
                  <p className="text-xs text-text-muted">Importing verified leads, checking database structures...</p>
                </Card>
              )}

              {/* SUCCESS State */}
              {ocrProcessingState === 'SUCCESS' && (
                <Card variant="standard" className="p-12 text-center space-y-6">
                  <div className="w-16 h-16 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-500 mx-auto animate-bounce">
                    <Check className="w-8 h-8" />
                  </div>
                  <div className="space-y-2">
                    <h3 className="text-lg font-bold text-text-primary">Import Completed Successfully</h3>
                    <p className="text-xs text-text-muted max-w-sm mx-auto">
                      AI OCR Import completed. {importedSummary?.imported} leads were successfully added to your contact pipeline (Skipped: {importedSummary?.skipped} duplicate entries).
                    </p>
                  </div>
                  <div className="pt-2 flex justify-center space-x-3">
                    <Button
                      variant="outline"
                      onClick={() => {
                        setOcrProcessingState('IDLE');
                        setOcrFiles([]);
                        setOcrCandidates([]);
                      }}
                      className="text-xs cursor-pointer"
                    >
                      Process More Images
                    </Button>
                    <Button
                      variant="primary"
                      onClick={() => {
                        setActiveTab('csv');
                        setOcrProcessingState('IDLE');
                        setOcrFiles([]);
                        setOcrCandidates([]);
                      }}
                      className="text-xs cursor-pointer"
                    >
                      Go to CSV History
                    </Button>
                  </div>
                </Card>
              )}
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
                      <div className="text-[10px] font-semibold px-1">
                        {!mapping[field.key] ? (
                          field.required ? (
                            <span className="text-status-danger bg-status-danger-bg border border-status-danger/10 px-2 py-0.5 rounded-md font-bold">
                              ⚠ Required field is not mapped
                            </span>
                          ) : (
                            <span className="text-text-muted bg-bg-secondary px-2 py-0.5 rounded-md font-semibold">
                              Not Mapped
                            </span>
                          )
                        ) : userOverrides[field.key] ? (
                          mapping[field.key] === '' ? (
                            <span className="text-text-muted bg-[#F1F5F9] border border-slate-200 px-2 py-0.5 rounded-md font-semibold">
                              Ignored by User
                            </span>
                          ) : (
                            <span className="text-brand-primary bg-[#EFF6FF] border border-blue-200 px-2 py-0.5 rounded-md font-bold">
                              ✓ User Selection
                            </span>
                          )
                        ) : (
                          (() => {
                            const colIdx = csvHeaders.indexOf(mapping[field.key]);
                            const sampleValues = csvPreviewRows.map(row => row[colIdx]).filter(Boolean);
                            const conf = getMappingConfidence(field.key, mapping[field.key], sampleValues);
                            if (conf >= 85) {
                              return (
                                <span className="text-emerald-600 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md font-semibold">
                                  ✓ AI Suggested ({conf}%)
                                </span>
                              );
                            } else {
                              return (
                                <span className="text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md font-bold">
                                  ⚠ Review Suggested Mapping ({conf}%)
                                </span>
                              );
                            }
                          })()
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>

              <div className="pt-4 flex justify-between border-t border-border-color">
                <Button variant="secondary" onClick={() => setStep(1)}>Back</Button>
                <Button 
                  variant="primary" 
                  onClick={() => {
                    const missing = DB_FIELDS.filter(f => f.required && !mapping[f.key]);
                    if (missing.length > 0) {
                      alert(`Please map all required columns: ${missing.map(m => m.label).join(', ')}`);
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

                {batchErrors.length > 0 && (() => {
                  const isStatsRecoveryActive = getBatchAgeInHours(batchStats) <= 10;
                  return (
                    <div className="space-y-3 pt-4 border-t border-border-color">
                      <h4 className="text-xs font-bold text-text-primary flex items-center justify-between">
                        <div className="flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-status-warning" />
                          <span>Pipeline Error Logs</span>
                          <span className="text-[10px] font-normal text-text-muted">
                            ({getRecoveryWindowString(batchStats)})
                          </span>
                        </div>
                        {isStatsRecoveryActive && (
                          <button
                            onClick={handleDownloadErrorCsv}
                            className="text-[10px] font-bold text-indigo-600 hover:underline flex items-center space-x-1 cursor-pointer"
                          >
                            <Upload className="w-3 h-3 rotate-180" />
                            <span>Download Error CSV</span>
                          </button>
                        )}
                      </h4>
                      <div className="border border-border-color rounded-xl overflow-hidden max-h-80 overflow-y-auto">
                        <table className="w-full text-left border-collapse text-xs">
                          <thead>
                            <tr className="bg-bg-secondary/40 border-b border-border-color sticky top-0">
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider w-14">Row #</th>
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Company</th>
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Contact</th>
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Invalid Email</th>
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider">Validation Error</th>
                              <th className="p-3 text-[10px] font-bold text-text-muted uppercase tracking-wider text-right w-24">Action</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border-color/60">
                            {batchErrors.map((err, idx) => {
                              const rowNum = err.row_number ?? err.row ?? 0;
                              const companyName = (err as any).company_name || 'N/A';
                              const contactName = (err as any).contact_name || 'N/A';
                              const rawVal = (err as any).original_email || err.email || err.value || 'N/A';
                              const errorMsg = err.errors && err.errors.length > 0
                                ? err.errors.map(e => e.reason).join(', ')
                                : ((err as any).error_message || err.message || 'Validation failed');
                              const isRecoverable = isRecoverableError(errorMsg);
                              const isEditing = editingRowNumber === rowNum;

                              
                              return (
                                <React.Fragment key={idx}>
                                  <tr className={`hover:bg-slate-50 ${isEditing ? 'bg-slate-50/50' : ''}`}>
                                    <td className="p-3 font-semibold text-text-muted font-mono">{rowNum}</td>
                                    <td className="p-3 text-text-primary font-medium truncate max-w-[120px]">{companyName}</td>
                                    <td className="p-3 text-text-secondary truncate max-w-[100px]">{contactName}</td>
                                    <td className="p-3 text-text-secondary font-mono truncate max-w-[150px]">{rawVal}</td>
                                    <td className="p-3 font-semibold text-status-danger">{errorMsg}</td>
                                    <td className="p-3 text-right">
                                      {isStatsRecoveryActive && isRecoverable && !isEditing && (
                                        <button
                                          onClick={() => handleStartEdit(rowNum)}
                                          className="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 cursor-pointer"
                                        >
                                          Edit
                                        </button>
                                      )}
                                      {isStatsRecoveryActive && !isRecoverable && (
                                        <span className="text-[10px] text-text-muted select-none">Non-correctable</span>
                                      )}
                                      {!isStatsRecoveryActive && (
                                        <span className="text-[10px] text-text-muted select-none">Expired</span>
                                      )}
                                    </td>
                                  </tr>
                                {isEditing && (
                                  <tr className="bg-slate-50/80 border-b border-border-color">
                                    <td colSpan={6} className="p-4 space-y-3">
                                      {isLoadingCorrectionRow ? (
                                        <div className="flex items-center space-x-2 text-xs text-text-muted">
                                          <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-500" />
                                          <span>Fetching original data...</span>
                                        </div>
                                      ) : (
                                        <div className="space-y-3 text-left">
                                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                            <div>
                                              <label className="block text-[9px] font-bold text-text-muted uppercase tracking-wider mb-1">Company Name</label>
                                              <input
                                                type="text"
                                                value={editingFields.company_name || ""}
                                                onChange={(e) => setEditingFields(prev => ({ ...prev, company_name: e.target.value }))}
                                                className="w-full bg-white border border-border-color rounded-md px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500"
                                                placeholder="Company Name"
                                              />
                                            </div>
                                            <div>
                                              <label className="block text-[9px] font-bold text-text-muted uppercase tracking-wider mb-1">Contact Name</label>
                                              <input
                                                type="text"
                                                value={editingFields.contact_name || ""}
                                                onChange={(e) => setEditingFields(prev => ({ ...prev, contact_name: e.target.value }))}
                                                className="w-full bg-white border border-border-color rounded-md px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500"
                                                placeholder="Contact Name"
                                              />
                                            </div>
                                            <div>
                                              <label className="block text-[9px] font-bold text-text-muted uppercase tracking-wider mb-1">Contact Email</label>
                                              <input
                                                type="text"
                                                value={editingFields.contact_email || ""}
                                                onChange={(e) => setEditingFields(prev => ({ ...prev, contact_email: e.target.value }))}
                                                className="w-full bg-white border border-border-color rounded-md px-2 py-1 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-indigo-500"
                                                placeholder="Contact Email"
                                              />
                                            </div>
                                          </div>
                                          {correctionError && (
                                            <div className="text-[10px] text-rose-600 font-semibold flex items-center space-x-1">
                                              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                                              <span>{correctionError}</span>
                                            </div>
                                          )}
                                          <div className="flex justify-end space-x-2">
                                            <Button
                                              variant="secondary"
                                              size="sm"
                                              onClick={() => setEditingRowNumber(null)}
                                              disabled={isSavingCorrection}
                                              className="text-[10px] py-1 cursor-pointer"
                                            >
                                              Cancel
                                            </Button>
                                            <Button
                                              variant="primary"
                                              size="sm"
                                              onClick={() => handleSaveCorrection(rowNum)}
                                              isLoading={isSavingCorrection}
                                              className="text-[10px] py-1 bg-indigo-600 hover:bg-indigo-700 text-white border-indigo-600/90 hover:border-indigo-700/90 cursor-pointer"
                                            >
                                              Save & Revalidate
                                            </Button>
                                          </div>
                                        </div>
                                      )}
                                    </td>
                                  </tr>
                                )}
                              </React.Fragment>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ); })()}

                <div className="pt-4 flex justify-end gap-3 border-t border-border-color">
                  <Button variant="secondary" onClick={() => { setStep(1); setFile(null); setBatchStats(null); setBatchErrors([]); setBatchId(null); }}>
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
          {activeTab === 'csv' && (
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
          )}
        </div>
      </PageWrapper>
    </AppShell>
  );
}
