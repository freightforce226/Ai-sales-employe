'use client';

import React, { useEffect } from 'react';
import { useTenantStore } from '../store/tenant-store';

export function BrandProvider({ children }: { children: React.ReactNode }) {
  const branding = useTenantStore((state) => state.branding);

  useEffect(() => {
    const root = document.documentElement;

    // Apply colors or fallbacks
    const primary = branding?.primary_color || '#2563EB';
    const secondary = branding?.secondary_color || '#0F172A';
    const accent = branding?.accent_color || '#F97316';
    const background = '#FFFFFF';
    const surface = '#F8FAFC';
    const text = '#0F172A';
    const muted = '#64748B';
    const success = '#10B981';
    const danger = '#EF4444';

    root.style.setProperty('--brand-primary', primary);
    root.style.setProperty('--brand-secondary', secondary);
    root.style.setProperty('--brand-accent', accent);
    root.style.setProperty('--brand-background', background);
    root.style.setProperty('--brand-surface', surface);
    root.style.setProperty('--brand-text', text);
    root.style.setProperty('--brand-muted', muted);
    root.style.setProperty('--brand-success', success);
    root.style.setProperty('--brand-danger', danger);

    // Apply favicon dynamically if set
    if (branding?.favicon_url) {
      let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
      if (!link) {
        link = document.createElement('link');
        link.rel = 'icon';
        document.getElementsByTagName('head')[0].appendChild(link);
      }
      link.href = branding.favicon_url;
    }
  }, [branding]);

  return <>{children}</>;
}
