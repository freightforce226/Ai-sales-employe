import { create } from 'zustand';

export interface TenantBranding {
  company_name: string;
  logo_url?: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  favicon_url?: string;
}

export interface UserProfile {
  id: string;
  organization_id: string;
  full_name: string;
  email: string;
  role: string;
  is_active: boolean;
}

interface TenantState {
  user: UserProfile | null;
  branding: TenantBranding | null;
  isAuthenticated: boolean;
  isTenantInitialized: boolean;
  setUser: (user: UserProfile | null) => void;
  setBranding: (branding: TenantBranding | null) => void;
  initializeTenant: (user: UserProfile, branding: TenantBranding) => void;
  clearTenant: () => void;
}

export const useTenantStore = create<TenantState>((set) => ({
  user: null,
  branding: null,
  isAuthenticated: false,
  isTenantInitialized: false,
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setBranding: (branding) => set({ branding }),
  initializeTenant: (user, branding) =>
    set({
      user,
      branding,
      isAuthenticated: true,
      isTenantInitialized: true,
    }),
  clearTenant: () =>
    set({
      user: null,
      branding: null,
      isAuthenticated: false,
      isTenantInitialized: false,
    }),
}));
