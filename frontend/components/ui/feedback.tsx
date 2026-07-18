/**
 * Purpose: Implements badges, avatars, alert banners, loading skeletons, and empty state illustrations.
 * Responsibility: Supporting micro-animations, loading states, status color tags, and user guidance copy templates.
 */

'use client';

import React from 'react';
import { AlertCircle, CheckCircle2, Info, XCircle } from 'lucide-react';
import { Button } from './button';

interface BadgeProps {
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'neutral';
  children: React.ReactNode;
  className?: string;
}

export function Badge({
  variant = 'neutral',
  children,
  className = '',
}: BadgeProps) {
  const styles = {
    primary: "text-brand-primary bg-brand-primary/5 border-[#BFDBFE]",
    success: "text-status-success bg-status-success-bg border-status-success/15",
    warning: "text-status-warning bg-status-warning-bg border-status-warning/15",
    danger: "text-status-danger bg-status-danger-bg border-status-danger/15",
    neutral: "text-text-secondary bg-[#F8FAFC] border-border-color",
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-[4px] border text-[11px] font-medium ${styles[variant]} ${className}`}>
      {children}
    </span>
  );
}

interface AvatarProps {
  name: string;
  src?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export function Avatar({
  name,
  src,
  size = 'md',
  className = '',
}: AvatarProps) {
  const sizes = {
    sm: "w-6 h-6 text-[10px]",
    md: "w-8 h-8 text-xs",
    lg: "w-12 h-12 text-base",
  };

  const initials = name
    .split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className={`relative shrink-0 select-none rounded-full flex items-center justify-center bg-bg-secondary border border-border-color font-bold text-text-secondary overflow-hidden ${sizes[size]} ${className}`}>
      {src ? (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img src={src} alt={name} className="w-full h-full object-cover" />
      ) : (
        <span>{initials || 'U'}</span>
      )}
    </div>
  );
}

interface AlertProps {
  variant?: 'info' | 'success' | 'warning' | 'danger';
  title: string;
  description?: string;
  onClose?: () => void;
  className?: string;
}

export function Alert({
  variant = 'info',
  title,
  description,
  onClose,
  className = '',
}: AlertProps) {
  const styles = {
    info: { container: "bg-blue-50/50 border-blue-200/50 text-blue-800", icon: <Info className="w-4 h-4 text-blue-500" /> },
    success: { container: "bg-status-success-bg/55 border-status-success/20 text-emerald-950", icon: <CheckCircle2 className="w-4 h-4 text-status-success" /> },
    warning: { container: "bg-status-warning-bg/55 border-status-warning/20 text-amber-950", icon: <AlertCircle className="w-4 h-4 text-status-warning" /> },
    danger: { container: "bg-status-danger-bg/55 border-status-danger/20 text-red-950", icon: <XCircle className="w-4 h-4 text-status-danger" /> },
  };

  return (
    <div className={`flex items-start p-4 border rounded-2xl shadow-2xs gap-3 ${styles[variant].container} ${className}`}>
      <div className="shrink-0 mt-0.5">
        {styles[variant].icon}
      </div>
      <div className="flex-1 space-y-1">
        <h5 className="text-xs font-bold leading-none">{title}</h5>
        {description && <p className="text-xs opacity-90 font-medium leading-relaxed">{description}</p>}
      </div>
      {onClose && (
        <button 
          onClick={onClose} 
          className="p-1 hover:bg-black/5 rounded-lg transition-colors cursor-pointer text-current opacity-70 hover:opacity-100 shrink-0"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

interface SkeletonProps {
  className?: string;
  variant?: 'text' | 'rect' | 'circle';
}

export function Skeleton({
  className = '',
  variant = 'rect',
}: SkeletonProps) {
  const styles = {
    text: "h-3 w-3/4 rounded-md",
    rect: "h-20 w-full rounded-xl",
    circle: "h-10 w-10 rounded-full",
  };

  return (
    <div className={`bg-bg-secondary animate-pulse shrink-0 ${styles[variant]} ${className}`} />
  );
}

interface EmptyStateProps {
  title: string;
  description: string;
  illustration?: React.ReactNode;
  primaryAction?: { label: string; onClick: () => void };
  secondaryAction?: { label: string; onClick: () => void };
  className?: string;
}

export function EmptyState({
  title,
  description,
  illustration,
  primaryAction,
  secondaryAction,
  className = '',
}: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center justify-center p-8 sm:p-12 bg-bg-surface border border-border-color border-dashed rounded-3xl text-center max-w-xl mx-auto shadow-none space-y-6 ${className}`}>
      {illustration ? (
        <div className="text-text-muted select-none shrink-0">{illustration}</div>
      ) : (
        <div className="w-14 h-14 rounded-xl bg-[#F8FAFC] border border-border-color flex items-center justify-center text-text-muted select-none shrink-0">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0a2 2 0 01-2 2H6a2 2 0 01-2-2m16 0V9a2 2 0 00-2-2H6a2 2 0 00-2 2v2m14 5V12a2 2 0 00-2-2H6a2 2 0 00-2 2v3m14 0a2 2 0 01-2 2H6a2 2 0 01-2-2" />
          </svg>
        </div>
      )}
      
      <div className="space-y-1.5">
        <h3 className="text-[17px] font-bold text-text-primary tracking-normal">{title}</h3>
        <p className="text-sm text-text-muted font-normal leading-relaxed max-w-xs mx-auto">{description}</p>
      </div>

      {(primaryAction || secondaryAction) && (
        <div className="flex flex-wrap items-center justify-center gap-3">
          {secondaryAction && (
            <Button variant="secondary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
          {primaryAction && (
            <Button variant="primary" onClick={primaryAction.onClick}>
              {primaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
