/**
 * Purpose: Implements standard text inputs, textareas, selectors, and search input layouts.
 * Responsibility: Supporting focus ring aesthetics, disabled/error validation borders, placeholder shading, and ARIA inputs alignment.
 */

'use client';

import React from 'react';
import { Search } from 'lucide-react';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className = '', disabled, ...props }, ref) => {
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label className="block text-xs font-medium text-text-secondary">
            {label}
          </label>
        )}
        <input
          ref={ref}
          disabled={disabled}
          className={`
            block w-full text-xs font-semibold text-text-primary placeholder-text-muted bg-bg-surface border border-border-color rounded-lg px-3.5 py-2.5 shadow-2xs transition-colors focus:border-brand-primary focus:bg-bg-surface focus:outline-none focus:ring-4 focus:ring-brand-primary-focus
            ${error ? 'border-status-danger focus:border-status-danger focus:ring-status-danger/10' : ''}
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="text-[10px] font-bold text-status-danger">{error}</p>
        )}
      </div>
    );
  }
);
Input.displayName = 'Input';

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, className = '', disabled, ...props }, ref) => {
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label className="block text-xs font-medium text-text-secondary">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          disabled={disabled}
          className={`
            block w-full text-xs font-semibold text-text-primary placeholder-text-muted bg-bg-surface border border-border-color rounded-lg px-3.5 py-2.5 shadow-2xs transition-colors focus:border-brand-primary focus:bg-bg-surface focus:outline-none focus:ring-4 focus:ring-brand-primary-focus min-h-[100px] resize-y
            ${error ? 'border-status-danger focus:border-status-danger focus:ring-status-danger/10' : ''}
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
            ${className}
          `}
          {...props}
        />
        {error && (
          <p className="text-[10px] font-bold text-status-danger">{error}</p>
        )}
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: { label: string; value: string }[];
}

export const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, options, className = '', disabled, ...props }, ref) => {
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label className="block text-xs font-medium text-text-secondary">
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            disabled={disabled}
            className={`
              block w-full text-xs font-semibold text-text-primary bg-bg-surface border border-border-color rounded-lg px-3.5 py-2.5 shadow-2xs transition-colors focus:border-brand-primary focus:bg-bg-surface focus:outline-none focus:ring-4 focus:ring-brand-primary-focus appearance-none cursor-pointer
              ${error ? 'border-status-danger focus:border-status-danger' : ''}
              ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
              ${className}
            `}
            {...props}
          >
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3.5 text-text-secondary">
            <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
              <path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z" />
            </svg>
          </div>
        </div>
        {error && (
          <p className="text-[10px] font-bold text-status-danger">{error}</p>
        )}
      </div>
    );
  }
);
Select.displayName = 'Select';

interface SearchBarProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onSearch?: (value: string) => void;
}

export function SearchBar({ onSearch, className = '', ...props }: SearchBarProps) {
  return (
    <div className="relative w-full">
      <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-text-muted">
        <Search className="h-4 w-4" />
      </div>
      <input
        type="text"
        onChange={(e) => onSearch && onSearch(e.target.value)}
        className={`
          block w-full pl-10 pr-3.5 py-2 bg-bg-surface border border-border-color rounded-lg text-xs font-semibold text-text-primary placeholder-text-muted shadow-2xs focus:border-brand-primary focus:bg-bg-surface focus:outline-none transition-colors
          ${className}
        `}
        {...props}
      />
    </div>
  );
}
