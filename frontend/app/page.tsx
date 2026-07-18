'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '../hooks/use-auth';

export default function HomePage() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const { isLoading, isTenantInitialized } = useAuth();

  useEffect(() => {
    if (mounted && !isLoading) {
      if (isTenantInitialized) {
        router.push('/dashboard');
      } else {
        router.push('/login');
      }
    }
  }, [mounted, isLoading, isTenantInitialized, router]);

  if (!mounted) {
    return null;
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-surface">
      <div className="text-sm font-medium text-brand-muted">Redirecting to your workspace...</div>
    </div>
  );
}
