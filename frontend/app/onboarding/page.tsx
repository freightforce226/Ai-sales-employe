'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function OnboardingRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/register');
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-surface">
      <div className="text-sm font-medium text-brand-muted">Loading your workspace signup...</div>
    </div>
  );
}
