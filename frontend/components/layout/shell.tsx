'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  LayoutDashboard, 
  Users, 
  Send, 
  FileText, 
  Settings, 
  Bell, 
  Building, 
  LogOut,
  ChevronDown,
  FileSpreadsheet,
  BarChart3,
  Paperclip,
  MoreHorizontal,
  Menu,
  Clock,
  MessageSquare
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
  const [showUserDropdown, setShowUserDropdown] = useState(false);
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

  // Primary destinations visible on both desktop & mobile bottom nav
  const primaryNavItems = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Customers', href: '/customers', icon: Users },
    { name: 'CSV Import', href: '/import', icon: FileSpreadsheet },
    { name: 'Templates', href: '/templates', icon: FileText },
    { name: 'Follow-ups', href: '/follow-ups', icon: Clock },
  ];

  // Secondary destinations accessed via collapsable sidebar or 'More' overlay
  const secondaryNavItems = [
    { name: 'Campaigns', href: '/campaigns', icon: Send },
    { name: 'Engagement', href: '/engagement', icon: Send },
    { name: '🤖 AI Customer Replies', href: '/ai-replies', icon: MessageSquare },
    { name: 'Attachments', href: '/attachments', icon: Paperclip },
    { name: 'Analytics', href: '/analytics', icon: BarChart3 },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  return (
    <div className="h-screen flex flex-col md:flex-row bg-bg-primary text-text-primary overflow-hidden font-sans">
      
      {/* 1. Desktop Left Sidebar (Hidden on mobile) */}
      <motion.aside 
        animate={{ width: isCollapsed ? '64px' : '240px' }}
        transition={{ duration: 0.18, ease: 'easeInOut' }}
        className="hidden md:flex flex-col h-screen sticky top-0 bg-sidebar-bg border-r border-sidebar-border text-sidebar-text z-40 shrink-0 select-none"
      >
        {/* Organization Switcher / Header */}
        <div className="p-4 border-b border-sidebar-border flex items-center justify-between relative h-16 shrink-0">
          {isCollapsed ? (
            <button 
              onClick={toggleSidebar}
              className="w-full flex items-center justify-center p-1 hover:bg-white/5 rounded-lg text-slate-450 hover:text-white transition-colors cursor-pointer"
            >
              <Menu className="w-5 h-5" />
            </button>
          ) : (
            <>
              <div 
                onClick={() => setShowOrgDropdown(!showOrgDropdown)}
                className="flex items-center space-x-2.5 cursor-pointer overflow-hidden flex-1"
              >
                <div className="w-7.5 h-7.5 rounded-lg bg-brand-primary flex items-center justify-center font-bold text-white text-sm tracking-tight shrink-0 shadow-md">
                  {branding?.company_name ? branding.company_name.charAt(0).toUpperCase() : 'FF'}
                </div>
                <div className="truncate flex-1 pr-1">
                  <h2 className="text-xs font-bold text-white leading-tight truncate">
                    {branding?.company_name || 'FreightForce'}
                  </h2>
                  <p className="text-[10px] text-slate-400 font-medium">Tenant Hub</p>
                </div>
                <ChevronDown className="w-3 h-3 text-slate-450 shrink-0" />
              </div>
              <button 
                onClick={toggleSidebar}
                className="p-1.5 hover:bg-white/5 rounded-lg text-slate-450 hover:text-white transition-colors cursor-pointer shrink-0 ml-1"
              >
                <Menu className="w-4 h-4" />
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
                className="absolute top-14 left-4 right-4 bg-slate-900 border border-slate-800 rounded-xl shadow-xl z-50 p-2 text-xs"
              >
                <div className="px-2 py-1.5 font-bold text-slate-500 uppercase tracking-wider text-[9px]">
                  Organizations
                </div>
                <div className="flex items-center space-x-2 p-2 rounded-lg bg-slate-800 text-white font-medium cursor-default">
                  <Building className="w-4 h-4 text-brand-primary" />
                  <span className="truncate">{branding?.company_name || 'FreightForce'}</span>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Sidebar Navigation Items */}
        <div className="flex-1 px-3 py-4 space-y-6 overflow-y-auto">
          {/* Main Group */}
          <div className="space-y-1">
            {!isCollapsed && (
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-[0.08em] px-3.5 mb-2 select-none">
                Workspace
              </div>
            )}
            {primaryNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center py-2 transition-colors relative group rounded-lg ${
                    isCollapsed ? 'justify-center px-0' : 'px-3.5 space-x-3'
                  } ${
                    isActive 
                      ? 'text-white font-medium bg-[rgba(37,99,235,0.15)] border-l-2 border-l-brand-primary' 
                      : 'text-slate-455 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className={`w-4.5 h-4.5 shrink-0 ${isActive ? 'text-brand-accent' : 'text-slate-500'}`} />
                  {!isCollapsed && <span className="text-xs sm:text-sm">{item.name}</span>}

                  {/* Tooltip on Collapsed Sidebar */}
                  {isCollapsed && (
                    <div className="absolute left-16 bg-slate-950 text-white text-[10px] font-bold px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 border border-slate-800">
                      {item.name}
                    </div>
                  )}
                </Link>
              );
            })}
          </div>

          {/* Tools & Settings Group */}
          <div className="space-y-1">
            {!isCollapsed && (
              <div className="text-[10px] uppercase font-bold text-slate-500 tracking-[0.08em] px-3.5 mb-2 select-none">
                Operations
              </div>
            )}
            {secondaryNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center py-2 transition-colors relative group rounded-lg ${
                    isCollapsed ? 'justify-center px-0' : 'px-3.5 space-x-3'
                  } ${
                    isActive 
                      ? 'text-white font-medium bg-[rgba(37,99,235,0.15)] border-l-2 border-l-brand-primary' 
                      : 'text-slate-455 hover:text-white hover:bg-white/5'
                  }`}
                >
                  <Icon className={`w-4.5 h-4.5 shrink-0 ${isActive ? 'text-brand-accent' : 'text-slate-500'}`} />
                  {!isCollapsed && <span className="text-xs sm:text-sm">{item.name}</span>}

                  {/* Tooltip on Collapsed Sidebar */}
                  {isCollapsed && (
                    <div className="absolute left-16 bg-slate-950 text-white text-[10px] font-bold px-2 py-1 rounded shadow-md opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-50 border border-slate-800">
                      {item.name}
                    </div>
                  )}
                </Link>
              );
            })}
          </div>
        </div>



        {/* Desktop Profile / Footer */}
        <div className="p-4 border-t border-sidebar-border mt-auto relative shrink-0">
          <div 
            onClick={() => !isCollapsed && setShowUserDropdown(!showUserDropdown)}
            className={`flex items-center space-x-3 cursor-pointer ${isCollapsed ? 'justify-center' : ''}`}
          >
            <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center border border-slate-700 text-white font-bold text-xs shrink-0">
              {user?.full_name ? user.full_name.charAt(0).toUpperCase() : 'U'}
            </div>
            {!isCollapsed && (
              <div className="truncate flex-1 pr-2">
                <p className="text-xs font-bold text-white truncate leading-none mb-0.5">
                  {user?.full_name || 'Active User'}
                </p>
                <p className="text-[10px] text-slate-500 truncate leading-none">
                  {user?.email || 'user@domain.com'}
                </p>
              </div>
            )}
          </div>

          {/* User Menu Dropdown */}
          <AnimatePresence>
            {showUserDropdown && !isCollapsed && (
              <motion.div 
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.12 }}
                className="absolute bottom-16 left-4 right-4 bg-slate-900 border border-slate-800 rounded-xl shadow-xl z-50 p-1.5 text-xs text-slate-300"
              >
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center space-x-2.5 p-2 rounded-lg hover:bg-red-500/10 hover:text-red-400 font-semibold text-left transition-colors cursor-pointer"
                >
                  <LogOut className="w-4 h-4 text-slate-400 group-hover:text-red-400" />
                  <span>Sign out</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.aside>

      {/* 2. Mobile Bottom Navigation (Hidden on desktop) */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 pb-safe z-40 bg-white/95 backdrop-blur-md border-t border-border-color flex justify-around items-center px-2 select-none">
        {primaryNavItems.map((item) => {
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
              <Icon className="w-5 h-5" />
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
                {secondaryNavItems.map((item) => {
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
                      <Icon className="w-6 h-6 mb-2" />
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
        
        {/* Mobile Top Header (Status triggers and profile) */}
        <header className="md:hidden flex items-center justify-between px-4 py-3 bg-white text-text-primary sticky top-0 z-30 shadow-xs border-b border-border-color">
          <div className="flex items-center space-x-2">
            <div className="w-7 h-7 rounded-lg bg-brand-primary flex items-center justify-center font-bold text-white text-xs shadow-sm">
              FF
            </div>
            <span className="text-xs font-bold tracking-tight">{branding?.company_name || 'FreightForce'}</span>
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
        <div className="flex-1 relative w-full overflow-y-auto">
          {children}
        </div>
      </div>
    </div>
  );
}

