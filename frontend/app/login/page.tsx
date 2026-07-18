'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../../lib/api';
import Link from 'next/link';
import axios from 'axios';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await api.post('/api/v1/auth/login', {
        email,
        password,
      });
      router.push('/dashboard');
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Invalid email or password');
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col justify-center px-4 py-12 sm:px-6 lg:px-8 bg-brand-surface selection:bg-brand-primary/10">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        {/* Dynamic logo representation */}
        <div className="mx-auto h-12 w-12 rounded-xl bg-brand-primary shadow-sm flex items-center justify-center font-bold text-white text-2xl tracking-tighter">
          FF
        </div>
        <h2 className="mt-6 text-3xl font-extrabold tracking-tight text-brand-secondary">
          FreightForce AI
        </h2>
        <p className="mt-2 text-sm text-brand-muted">
          AI Sales Agent for Freight Forwarding
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-brand-background py-8 px-6 shadow-sm border border-slate-100 rounded-xl sm:px-10">
          <form className="space-y-6" onSubmit={handleLogin}>
            {error && (
              <div className="rounded-lg bg-brand-danger/10 p-4 border border-brand-danger/20">
                <div className="text-xs font-semibold text-brand-danger">{error}</div>
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">
                Email address
              </label>
              <div className="mt-1.5">
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="name@company.com"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">
                  Password
                </label>
              </div>
              <div className="mt-1.5">
                <input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="••••••••"
                />
              </div>
            </div>

            <div>
              <button
                type="submit"
                disabled={loading}
                className="flex w-full justify-center rounded-lg bg-brand-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-brand-primary focus:ring-offset-2 disabled:opacity-50 transition-all cursor-pointer"
              >
                {loading ? 'Signing in...' : 'Sign in to Workspace'}
              </button>
            </div>
          </form>

          <p className="mt-6 text-center text-xs text-brand-muted">
            Don&apos;t have a workspace?{' '}
            <Link href="/register" className="font-semibold text-brand-primary hover:underline transition-all">
              Create an Organization
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
