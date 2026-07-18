/**
 * Purpose: Implements standard page layout wrappers, page headers, breadcrumbs, grids, and filters templates.
 * Responsibility: Enforcing layout structure, margin/padding consistency, and alignment across all workspace pages.
 */

'use client';

import React from 'react';
import Link from 'next/link';

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  breadcrumbs?: BreadcrumbItem[];
  title: string;
  description?: string;
  actions?: React.ReactNode;
}

export function PageHeader({ breadcrumbs, title, description, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center md:justify-between pb-6 border-b border-border-color/60 gap-4 mb-6">
      <div className="space-y-1">
        {/* Breadcrumb path */}
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav className="flex items-center space-x-1.5 text-2xs font-bold uppercase tracking-wider text-text-secondary select-none">
            {breadcrumbs.map((crumb, idx) => (
              <React.Fragment key={idx}>
                {idx > 0 && <span className="text-text-muted">/</span>}
                {crumb.href ? (
                  <Link href={crumb.href} className="hover:text-brand-primary transition-colors">
                    {crumb.label}
                  </Link>
                ) : (
                  <span className="text-text-muted">{crumb.label}</span>
                )}
              </React.Fragment>
            ))}
          </nav>
        )}
        
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-text-primary">
          {title}
        </h1>
        {description && (
          <p className="text-xs sm:text-sm text-text-secondary font-medium max-w-3xl">
            {description}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center space-x-2.5 shrink-0 self-start md:self-center">
          {actions}
        </div>
      )}
    </div>
  );
}

interface PageWrapperProps {
  children: React.ReactNode;
  className?: string;
}

export function PageWrapper({ children, className = "" }: PageWrapperProps) {
  return (
    <div className={`p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6 sm:space-y-8 ${className}`}>
      {children}
    </div>
  );
}

interface SectionProps {
  title?: string;
  description?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function Section({ title, description, children, actions, className = "" }: SectionProps) {
  return (
    <section className={`space-y-4 ${className}`}>
      {(title || description || actions) && (
        <div className="flex items-center justify-between pb-2 border-b border-border-color/30">
          <div className="space-y-0.5">
            {title && <h2 className="text-sm font-bold text-text-primary uppercase tracking-wider">{title}</h2>}
            {description && <p className="text-xs text-text-secondary font-medium">{description}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </div>
      )}
      <div>
        {children}
      </div>
    </section>
  );
}

interface GridProps {
  cols?: 1 | 2 | 3 | 4 | 5 | 6;
  gap?: "sm" | "md" | "lg";
  children: React.ReactNode;
  className?: string;
}

export function Grid({ cols = 3, gap = "md", children, className = "" }: GridProps) {
  const colClasses = {
    1: "grid-cols-1",
    2: "grid-cols-1 md:grid-cols-2",
    3: "grid-cols-1 md:grid-cols-3",
    4: "grid-cols-2 lg:grid-cols-4",
    5: "grid-cols-2 md:grid-cols-3 lg:grid-cols-5",
    6: "grid-cols-2 md:grid-cols-3 lg:grid-cols-6",
  };

  const gapClasses = {
    sm: "gap-3",
    md: "gap-4 sm:gap-6",
    lg: "gap-6 sm:gap-8",
  };

  return (
    <div className={`grid ${colClasses[cols]} ${gapClasses[gap]} ${className}`}>
      {children}
    </div>
  );
}

interface PageFilterBarProps {
  searchVal?: string;
  onSearchChange?: (val: string) => void;
  searchPlaceholder?: string;
  filters?: React.ReactNode;
  tabs?: React.ReactNode;
}

export function PageFilterBar({ 
  searchVal = "", 
  onSearchChange, 
  searchPlaceholder = "Search...", 
  filters,
  tabs 
}: PageFilterBarProps) {
  return (
    <div className="flex flex-col gap-4 p-4 bg-bg-surface border border-border-color rounded-2xl shadow-sm">
      {tabs && <div className="border-b border-border-color/50 pb-2">{tabs}</div>}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        {onSearchChange && (
          <div className="relative flex-1 max-w-sm">
            <input
              type="text"
              value={searchVal}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder={searchPlaceholder}
              className="w-full text-xs font-medium text-text-primary placeholder-text-muted bg-bg-primary border border-border-color rounded-xl px-3.5 py-2 focus:border-brand-primary focus:outline-none transition-colors"
            />
          </div>
        )}
        
        {filters && (
          <div className="flex items-center space-x-2 sm:ml-auto">
            {filters}
          </div>
        )}
      </div>
    </div>
  );
}
