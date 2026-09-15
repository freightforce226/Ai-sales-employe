'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Home, 
  Users, 
  Megaphone, 
  FileText, 
  Settings, 
  Bell, 
  Building, 
  LogOut,
  ChevronDown,
  FileSpreadsheet,
  Paperclip,
  MoreHorizontal,
  Menu,
  Clock,
  Sparkles,
  Send,
  Activity,
  ChevronsLeft,
  ChevronsRight,
  Mail,
  BarChart3
} from 'lucide-react';
import { useTenantStore } from '../../store/tenant-store';
import { api } from '../../lib/api';

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  
  const { branding, user, clearTenant } = useTenantStore();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [showOrgDropdown, setShowOrgDropdown] = useState(false);
  const [showMobileMore, setShowMobileMore] = useState(false);
  const notificationsCount = 3;

  // Synchronize collapse state with local storage
  useEffect(() => {
    const saved = localStorage.getItem('sidebar-collapsed');
    if (saved === 'true') {
      setIsCollapsed(true);
    }
  }, []);

  const toggleSidebar = () => {
    const nextState = !isCollapsed;
    setIsCollapsed(nextState);
    localStorage.setItem('sidebar-collapsed', String(nextState));
  };

  const handleLogout = async () => {
    try {
      await api.post('/api/v1/auth/logout');
    } catch (err) {
      console.error('Failed to log out', err);
    }
    clearTenant();
    router.push('/login');
  };

  // Nav Items with colorful icon assignments matching the reference design
  const navItems = [
    { name: 'Dashboard', href: '/dashboard', icon: Home, color: 'text-blue-400' },
    { name: 'Customers', href: '/customers', icon: Users, color: 'text-slate-300' },
    { name: 'CSV Import', href: '/import', icon: FileSpreadsheet, color: 'text-cyan-400' },
    { name: 'Templates', href: '/templates', icon: FileText, color: 'text-indigo-400' },
    { name: 'Campaigns', href: '/marketing', icon: Megaphone, color: 'text-purple-400' },
    { name: 'Follow-ups', href: '/follow-ups', icon: Send, color: 'text-emerald-400' },
    { name: 'Engagement', href: '/engagement', icon: Activity, color: 'text-rose-400' },
    { name: 'AI Replies', href: '/ai-replies', icon: Sparkles, color: 'text-amber-400' },
    { name: 'Attachments', href: '/attachments', icon: Paperclip, color: 'text-sky-400' },
    { name: 'Settings', href: '/settings', icon: Settings, color: 'text-slate-400' },
  ];

  // Get user initials
  const userInitials = user?.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : 'GS';

  return (
    <div className="h-screen flex flex-col md:flex-row bg-bg-primary text-text-primary overflow-hidden font-sans">
      
      {/* 1. Desktop Modern Left Sidebar (Matches Reference Design) */}
      <motion.aside 
        animate={{ width: isCollapsed ? 64 : 240 }}
        transition={{ duration: 0.18, ease: 'easeInOut' }}
        className="hidden md:flex flex-col h-screen sticky top-0 bg-[#0B1329] border-r border-slate-800/80 text-white z-40 shrink-0 select-none overflow-x-hidden"
      >
        {/* Header / FreightForce AI Logo */}
        <div className="p-4 border-b border-slate-800/60 flex items-center justify-between h-16 shrink-0 overflow-hidden">
          {isCollapsed ? (
            <div className="w-full flex items-center justify-center">
              <button 
                onClick={toggleSidebar}
                title="Expand Sidebar"
                aria-label="Expand Sidebar"
                className="w-10 h-10 rounded-xl bg-blue-600 text-white font-black italic text-lg flex items-center justify-center hover:bg-blue-500 transition-all cursor-pointer shadow-md"
              >
                F
              </button>
            </div>
          ) : (
            <>
              <div 
                onClick={() => setShowOrgDropdown(!showOrgDropdown)}
                className="flex items-center space-x-2.5 cursor-pointer overflow-hidden flex-1 group"
              >
                <div className="w-8 h-8 rounded-xl bg-blue-600 text-white font-black italic text-base flex items-center justify-center shrink-0 shadow-md">
                  F
                </div>
                <div className="truncate flex-1 pr-1">
                  <h2 className="text-sm font-bold text-white leading-tight truncate tracking-tight">
                    FreightForce <span className="text-blue-400">AI</span>
                  </h2>
                  <p className="text-[10px] text-slate-400 font-medium truncate">
                    {branding?.company_name || 'Tenant Workspace'}
                  </p>
                </div>
              </div>
              <button 
                onClick={toggleSidebar}
                title="Collapse Sidebar"
                aria-label="Collapse Sidebar"
                className="p-1.5 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors cursor-pointer shrink-0"
              >
                <ChevronsLeft className="w-4 h-4" />
              </button>
            </>
          )}

          {/* Org Switcher Dropdown */}
          <AnimatePresence>
            {showOrgDropdown && !isCollapsed && (
              <motion.div 
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.12 }}
                className="absolute top-14 left-3 right-3 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl z-50 p-2 text-xs"
              >
                <div className="px-2 py-1.5 font-bold text-slate-500 uppercase tracking-wider text-[9px]">
                  Active Organization
                </div>
                <div className="flex items-center space-x-2 p-2 rounded-lg bg-slate-800 text-white font-medium cursor-default">
                  <Building className="w-4 h-4 text-blue-400" />
                  <span className="truncate">{branding?.company_name || 'FreightForce Tenant'}</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Navigation Section */}
        <div className="flex-1 px-3 py-4 space-y-1.5 overflow-y-auto overflow-x-hidden custom-scrollbar">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                aria-label={item.name}
                className={`flex items-center transition-all relative group ${
                  isCollapsed ? 'justify-center h-10 w-full rounded-xl px-0' : 'px-3.5 py-2.5 rounded-xl space-x-3'
                } ${
                  isActive 
                    ? 'bg-[#1D4ED8] text-white font-semibold shadow-md' 
                    : 'text-slate-300 hover:text-white hover:bg-white/10'
                }`}
              >
                <Icon className={`w-4.5 h-4.5 shrink-0 ${isActive ? 'text-white' : item.color}`} />
                {!isCollapsed && <span className="text-xs font-semibold tracking-tight truncate">{item.name}</span>}

                {/* Tooltip on Collapsed Sidebar */}
                {isCollapsed && (
                  <div className="absolute left-[70px] bg-slate-900 border border-slate-700/80 text-white font-semibold text-xs px-2.5 py-1.5 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-all pointer-events-none whitespace-nowrap z-50">
                    {item.name}
                  </div>
                )}
              </Link>
            );
          })}
        </div>

        {/* User Profile & Sign Out Footer */}
        <div className="p-3.5 border-t border-slate-800/60 mt-auto relative shrink-0 overflow-hidden bg-[#080E1F]">
          {isCollapsed ? (
            <div className="flex flex-col items-center space-y-3 py-1">
              <div 
                className="w-8 h-8 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shadow-md cursor-pointer"
                title={user?.full_name || 'Gourav Sharma'}
              >
                {userInitials}
              </div>
              <button
                onClick={handleLogout}
                title="Sign Out"
                aria-label="Sign Out"
                className="relative group p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors cursor-pointer"
              >
                <LogOut className="w-4.5 h-4.5" />
                <div className="absolute left-[70px] bg-slate-900 border border-slate-700/80 text-white font-semibold text-xs px-2.5 py-1.5 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-all pointer-events-none whitespace-nowrap z-50">
                  Sign Out
                </div>
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2.5 truncate">
                <div className="w-8 h-8 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shrink-0 shadow-md">
                  {userInitials}
                </div>
                <div className="truncate">
                  <p className="text-xs font-bold text-white truncate leading-tight">
                    {user?.full_name || 'Gourav Sharma'}
                  </p>
                  <p className="text-[10px] text-slate-400 truncate leading-tight mt-0.5">
                    {user?.email || 'Administrator'}
                  </p>
                </div>
              </div>
              <button
                onClick={handleLogout}
                title="Sign Out"
                aria-label="Sign Out"
                className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer shrink-0 ml-1"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </motion.aside>

      {/* 2. Mobile Bottom Navigation (Hidden on desktop) */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 pb-safe z-40 bg-white/95 backdrop-blur-md border-t border-border-color flex justify-around items-center px-2 select-none">
        {navItems.slice(0, 5).map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex flex-col items-center py-1 px-3 relative h-full justify-center transition-all ${
                isActive ? 'text-brand-primary' : 'text-slate-450 hover:text-slate-700'
              }`}
            >
              {isActive && (
                <div 
                  className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-[2px] bg-brand-primary"
                />
              )}
              <Icon className={`w-5 h-5 ${item.color}`} />
              <span className="text-[10px] font-medium mt-1">{item.name}</span>
            </Link>
          );
        })}
        <button
          onClick={() => setShowMobileMore(true)}
          className="flex flex-col items-center py-1 px-3 relative h-full justify-center transition-all text-slate-450 hover:text-slate-700 cursor-pointer"
        >
          <MoreHorizontal className="w-5 h-5" />
          <span className="text-[10px] font-medium mt-1">More</span>
        </button>
      </nav>

      {/* Mobile More Sheet Drawer */}
      <AnimatePresence>
        {showMobileMore && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowMobileMore(false)}
              className="fixed inset-0 bg-black/40 z-45 md:hidden"
            />
            <motion.div 
              initial={{ translateY: '100%' }}
              animate={{ translateY: 0 }}
              exit={{ translateY: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 200 }}
              className="fixed bottom-0 left-0 right-0 bg-white rounded-t-2xl z-50 p-6 md:hidden border-t border-border-color pb-10"
            >
              <div className="w-12 h-1 bg-slate-200 rounded-full mx-auto mb-6" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-text-muted mb-4">Operations</h3>
              <div className="grid grid-cols-4 gap-4">
                {navItems.slice(5).map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href;
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      onClick={() => setShowMobileMore(false)}
                      className={`flex flex-col items-center p-3 rounded-xl border ${
                        isActive ? 'bg-brand-primary/5 border-brand-primary text-brand-primary' : 'border-border-color text-text-secondary bg-bg-primary'
                      }`}
                    >
                      <Icon className={`w-6 h-6 mb-2 ${item.color}`} />
                      <span className="text-[10px] font-bold text-center leading-none">{item.name}</span>
                    </Link>
                  );
                })}
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* 3. Main Frame Workspace Wrapper */}
      <div className="flex-1 flex flex-col min-w-0 bg-bg-primary pb-16 md:pb-0 overflow-x-hidden">
        
        {/* Mobile Top Header */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white text-text-primary sticky top-0 z-30 shadow-xs border-b border-border-color">
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center font-black text-white text-xs italic shadow-sm">
              F
            </div>
            <span className="text-xs font-bold tracking-tight">FreightForce <span className="text-blue-500">AI</span></span>
          </div>
          
          <div className="flex items-center space-x-3">
            <button className="p-1 text-slate-400 hover:text-slate-600 rounded-lg relative cursor-pointer">
              <Bell className="w-4.5 h-4.5" />
              {notificationsCount > 0 && (
                <span className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full bg-status-danger animate-ping"></span>
              )}
            </button>
            <button 
              onClick={handleLogout}
              className="p-1 text-slate-400 hover:text-red-500 rounded-lg cursor-pointer"
            >
              <LogOut className="w-4.5 h-4.5" />
            </button>
          </div>
        </header>

        {/* Main Content Pane */}
        <div className="flex-1 relative w-full overflow-y-auto overflow-x-hidden">
          {children}
        </div>
      </div>
    </div>
  );
}
