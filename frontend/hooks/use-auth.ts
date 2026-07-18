import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { api } from '../lib/api';
import { useTenantStore } from '../store/tenant-store';
import axios from 'axios';

export function useAuth() {
  const router = useRouter();
  const pathname = usePathname();
  const { user, initializeTenant, clearTenant, isTenantInitialized } = useTenantStore();
  const [isLoading, setIsLoading] = useState(true);

  const fetchProfileAndBranding = async (): Promise<boolean> => {
    try {
      // Check for hash parameters (email confirmation redirect)
      if (typeof window !== 'undefined' && window.location.hash) {
        const hash = window.location.hash.substring(1);
        const params = new URLSearchParams(hash);
        const accessToken = params.get('access_token');
        const refreshToken = params.get('refresh_token');
        const expiresIn = params.get('expires_in');
        
        if (accessToken) {
          try {
            await api.post('/api/v1/auth/session', {
              access_token: accessToken,
              refresh_token: refreshToken,
              expires_in: expiresIn ? parseInt(expiresIn, 10) : 3600
            });
            // Clear hash so it doesn't trigger again or look ugly
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
          } catch (sessionErr) {
            console.error('Failed to set session from URL hash', sessionErr);
          }
        }
      }

      // 1. Fetch current profile, organization, and branding dynamically in one call
      const res = await api.get('/api/v1/auth/me');
      const { user: userProfile, branding: brandingData } = res.data;

      // 2. Initialize Zustand store
      initializeTenant(userProfile, {
        company_name: brandingData?.company_name || 'FreightForce',
        logo_url: brandingData?.logo_url,
        primary_color: brandingData?.theme_config?.primary_color || '#2563EB',
        secondary_color: brandingData?.theme_config?.secondary_color || '#0F172A',
        accent_color: brandingData?.theme_config?.accent_color || '#F97316',
        favicon_url: brandingData?.theme_config?.favicon_url,
      });

      setIsLoading(false);
      return true;
    } catch (err: any) {
      // If unauthorized, try to refresh token once
      if (err.response?.status === 401 && pathname !== '/login' && pathname !== '/register') {
        try {
          await api.post('/api/v1/auth/refresh');
          // Retry profile load
          const retryRes = await api.get('/api/v1/auth/me');
          const { user: userProfile, branding: brandingData } = retryRes.data;
          
          initializeTenant(userProfile, {
            company_name: brandingData?.company_name || 'FreightForce',
            logo_url: brandingData?.logo_url,
            primary_color: brandingData?.theme_config?.primary_color || '#2563EB',
            secondary_color: brandingData?.theme_config?.secondary_color || '#0F172A',
            accent_color: brandingData?.theme_config?.accent_color || '#F97316',
            favicon_url: brandingData?.theme_config?.favicon_url,
          });
          setIsLoading(false);
          return true;
        } catch (refreshErr) {
          clearTenant();
          setIsLoading(false);
          router.push('/login');
          return false;
        }
      }

      clearTenant();
      setIsLoading(false);
      if (pathname !== '/login' && pathname !== '/register' && pathname !== '/onboarding') {
        router.push('/login');
      }
      return false;
    }
  };

  useEffect(() => {
    fetchProfileAndBranding();
  }, [pathname]);

  return { user, isLoading, isTenantInitialized, refreshAuth: fetchProfileAndBranding };
}
