/**
 * Purpose: Implements atomic button variants (primary, secondary, outline, ghost, danger) and sizing scales.
 * Responsibility: Supporting micro-interactions, loading spinners, state disabled overrides, and custom icon configurations.
 */

'use client';

import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg' | 'xl';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  leftIcon,
  rightIcon,
  className = '',
  disabled,
  children,
  ...props
}: ButtonProps) {
  
  const baseStyle = "inline-flex items-center justify-center font-bold tracking-tight rounded-lg transition-all duration-120 focus:outline-none select-none shrink-0";
  
  const variants = {
    primary: "bg-brand-primary text-text-inverse shadow-[inset_0_1px_0_rgba(255,255,255,0.2),0_1px_2px_rgba(0,0,0,0.05)] hover:bg-brand-primary-hover active:scale-[0.99] border border-transparent focus:ring-4 focus:ring-brand-primary-focus",
    secondary: "bg-[rgba(0,0,0,0.04)] text-text-secondary border border-border-color shadow-[0_1px_2px_rgba(0,0,0,0.02)] hover:bg-[rgba(0,0,0,0.08)] hover:border-slate-300 active:scale-[0.99] focus:ring-4 focus:ring-brand-primary-focus",
    outline: "bg-transparent text-brand-primary border border-[#BFDBFE] hover:bg-[#EFF6FF] active:scale-[0.99] focus:ring-4 focus:ring-brand-primary-focus", // Brand Outline
    ghost: "bg-transparent text-text-secondary hover:bg-[rgba(0,0,0,0.04)] hover:text-text-primary focus:ring-4 focus:ring-brand-primary-focus",
    danger: "bg-[rgba(220,38,38,0.08)] text-status-danger border border-status-danger/30 hover:bg-[rgba(220,38,38,0.16)] active:scale-[0.99] focus:ring-4 focus:ring-status-danger/10",
  };

  const sizes = {
    sm: "text-[11px] px-3 py-1 gap-1.5 h-[30px]",
    md: "text-xs px-4 py-2 gap-2 h-[36px]",
    lg: "text-xs px-5 py-2.5 gap-2 h-[44px]",
    xl: "text-sm px-6 py-3.5 gap-2.5 h-[52px]",
  };

  const isDisabled = disabled || isLoading;

  return (
    <button
      disabled={isDisabled}
      className={`
        ${baseStyle} 
        ${variants[variant]} 
        ${sizes[size]} 
        ${isDisabled ? 'opacity-50 cursor-not-allowed active:scale-100' : 'cursor-pointer'} 
        ${className}
      `}
      {...props}
    >
      {isLoading && (
        <svg className="animate-spin -ml-1 mr-2 h-3.5 w-3.5 text-current" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      
      {!isLoading && leftIcon && <span className="flex items-center">{leftIcon}</span>}
      <span>{children}</span>
      {!isLoading && rightIcon && <span className="flex items-center">{rightIcon}</span>}
    </button>
  );
}
