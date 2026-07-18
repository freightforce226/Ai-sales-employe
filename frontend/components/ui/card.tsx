/**
 * Purpose: Implements standard container wrappers, metric display blocks, action cards, and glass components.
 * Responsibility: Supporting soft border radiuses (16-20px), low-contrast elevation shading, spacing variations, and responsive card grids.
 */

'use client';

import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'standard' | 'action' | 'glass' | 'secondary';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

export function Card({
  variant = 'standard',
  padding = 'lg',
  children,
  className = '',
  ...props
}: CardProps) {
  
  const baseStyle = "rounded-xl border transition-all duration-180 bg-bg-surface border-border-color shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]";
  
  const variants = {
    standard: "bg-bg-surface border-border-color",
    action: "bg-bg-surface border-border-color hover:border-slate-300 hover:shadow-[0_4px_16px_rgba(0,0,0,0.08)] cursor-pointer",
    glass: "bg-bg-surface/75 backdrop-blur-md border-border-color/60",
    secondary: "bg-bg-secondary border-transparent shadow-none",
  };

  const paddings = {
    none: "p-0",
    sm: "p-4",
    md: "p-4 sm:p-5",
    lg: "p-6",
  };

  return (
    <div
      className={`${baseStyle} ${variants[variant]} ${paddings[padding]} ${className}`}
      {...props}
    >
      {children}
    </div>
  );
}

interface MetricCardProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  value: string | number;
  change?: string;
  isPositive?: boolean;
  subtitle?: string;
  icon?: React.ReactNode;
}

export function MetricCard({
  title,
  value,
  change,
  isPositive = true,
  subtitle,
  icon,
  className = '',
  ...props
}: MetricCardProps) {
  return (
    <Card 
      padding="lg"
      className={`flex flex-col justify-between hover:border-slate-300 transition-all border-t-2 border-t-brand-primary ${className}`} 
      {...props}
    >
      <div className="flex items-center justify-between w-full">
        <span className="text-[11px] font-bold text-text-muted uppercase tracking-[0.06em]">{title}</span>
        {icon && (
          <div className="p-2 bg-bg-secondary border border-border-color/30 rounded-xl text-text-secondary select-none">
            {icon}
          </div>
        )}
      </div>

      <div className="mt-5 flex items-baseline justify-between w-full">
        <div className="space-y-1">
          <span className="text-2xl sm:text-3xl font-bold text-text-primary tracking-tight font-mono">{value}</span>
          {subtitle && <p className="text-[10px] text-text-muted font-medium">{subtitle}</p>}
        </div>

        {change && (
          <span className={`text-[10px] sm:text-xs font-bold flex items-center gap-0.5 px-2 py-0.5 rounded-lg border ${
            isPositive 
              ? 'text-status-success bg-status-success-bg border-status-success/15' 
              : 'text-status-danger bg-status-danger-bg border-status-danger/15'
          }`}>
            {isPositive ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            <span>{change}</span>
          </span>
        )}
      </div>
    </Card>
  );
}
