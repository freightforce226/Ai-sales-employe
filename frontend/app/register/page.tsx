'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../../lib/api';
import Link from 'next/link';
import axios from 'axios';

export default function RegisterPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [confirmRequired, setConfirmRequired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Unified Registration Details
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [companyName, setCompanyName] = useState('');

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || !fullName || !companyName) {
      setError('Please fill in all fields');
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const res = await api.post('/api/v1/auth/signup', {
        email,
        password,
        full_name: fullName,
        company_name: companyName,
      });

      if (res.data.confirmation_required) {
        setConfirmRequired(true);
      } else {
        setStep(2); // Go to Connect Outlook step
      }
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to complete registration');
      } else {
        setError('An unexpected error occurred');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleConnectOutlook = async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/v1/oauth/connect');
      window.location.href = res.data.authorization_url;
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        setError(err.response?.data?.detail || 'Failed to initiate Outlook connection');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to initiate Outlook connection');
      }
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col justify-center px-4 py-12 sm:px-6 lg:px-8 bg-brand-surface selection:bg-brand-primary/10">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="mx-auto h-12 w-12 rounded-xl bg-brand-primary shadow-sm flex items-center justify-center font-bold text-white text-2xl tracking-tighter">
          FF
        </div>
        <h2 className="mt-6 text-3xl font-extrabold tracking-tight text-brand-secondary">
          {confirmRequired
            ? 'Verify your email'
            : step === 2
            ? 'Connect Outlook'
            : 'Create your workspace'}
        </h2>
        <p className="mt-2 text-sm text-brand-muted">
          {confirmRequired
            ? 'Confirm your registration to continue'
            : step === 1
            ? 'Get started with FreightForce AI in seconds'
            : 'Final Step: Integrate email mailbox'}
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-brand-background py-8 px-6 shadow-sm border border-slate-100 rounded-xl sm:px-10">
          {error && (
            <div className="mb-6 rounded-lg bg-brand-danger/10 p-4 border border-brand-danger/20">
              <div className="text-xs font-semibold text-brand-danger">{error}</div>
            </div>
          )}

          {confirmRequired ? (
            <div className="space-y-6 text-center">
              <div className="py-4 flex justify-center">
                <div className="p-4 rounded-full bg-blue-50 text-blue-600">
                  <svg className="w-12 h-12 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 19v-8.93a2 2 0 01.89-1.664l8-5.333a2 2 0 012.22 0l8 5.333A2 2 0 0121 10.07V19M3 19a2 2 0 002 2h14a2 2 0 002-2M3 19l6.75-4.5M21 19l-6.75-4.5M3 10l6.75 4.5M21 10l-6.75 4.5m0 0l-1.14.76a2 2 0 01-2.22 0l-1.14-.76" />
                  </svg>
                </div>
              </div>

              <p className="text-sm text-brand-secondary font-medium">
                We have sent a verification link to <span className="font-bold text-brand-primary">{email}</span>.
              </p>
              <p className="text-xs text-brand-muted leading-relaxed">
                Please check your inbox, click the confirmation link to activate your account, and then return here to log in.
              </p>

              <button
                onClick={() => router.push('/login')}
                className="w-full flex justify-center py-2.5 px-4 rounded-lg text-sm font-semibold text-white bg-brand-primary shadow-sm hover:opacity-90 transition-all cursor-pointer"
              >
                Go to Sign in
              </button>
            </div>
          ) : step === 1 ? (
            <form className="space-y-6" onSubmit={handleSignup}>
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">Full Name</label>
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="John Doe"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">Company Name</label>
                <input
                  type="text"
                  required
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="Logistics Inc."
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">Email address</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="name@company.com"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-brand-secondary">Password</label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5 block w-full rounded-lg border border-slate-200 px-3.5 py-2 text-sm text-brand-text placeholder-slate-400 shadow-sm focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary transition-all"
                  placeholder="••••••••"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center rounded-lg bg-brand-primary px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
              >
                {loading ? 'Creating Workspace...' : 'Register Workspace'}
              </button>
            </form>
          ) : (
            <div className="space-y-6 text-center">
              <div className="py-4 flex justify-center">
                <div className="p-4 rounded-full bg-blue-50 text-blue-600">
                  <svg className="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
              </div>

              <p className="text-sm text-brand-muted">
                Your workspace is ready! To start sending automated outreach campaigns, connect your corporate Outlook email account.
              </p>

              <button
                onClick={handleConnectOutlook}
                disabled={loading}
                className="w-full flex justify-center py-2.5 px-4 rounded-lg text-sm font-semibold text-white bg-brand-primary shadow-sm hover:opacity-90 disabled:opacity-50 transition-all cursor-pointer"
              >
                {loading ? 'Connecting...' : 'Connect Microsoft Outlook'}
              </button>

              <button
                onClick={() => router.push('/dashboard')}
                className="mt-2 text-xs font-semibold text-brand-muted hover:text-brand-primary transition-all cursor-pointer block w-full text-center"
              >
                Skip for now, go to dashboard
              </button>
            </div>
          )}

          {!confirmRequired && step === 1 && (
            <p className="mt-6 text-center text-xs text-brand-muted">
              Already have a workspace?{' '}
              <Link href="/login" className="font-semibold text-brand-primary hover:underline transition-all">
                Sign in
              </Link>
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
