import axios from 'axios';
import { useTenantStore } from '../store/tenant-store';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
  withCredentials: true, // Crucial: sends HttpOnly session cookies automatically
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach Organization ID context header
api.interceptors.request.use(
  (config) => {
    const state = useTenantStore.getState();
    if (state.user?.organization_id) {
      config.headers['X-Organization-ID'] = state.user.organization_id;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);
