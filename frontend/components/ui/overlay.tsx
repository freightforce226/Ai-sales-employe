/**
 * Purpose: Implements centered modals, sliding drawers, timelines, and tab switchers.
 * Responsibility: Coordinating overlay animations, backdrop blurs, viewport locks, and ARIA modal focus bindings.
 */

'use client';

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X } from 'lucide-react';

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}

export function Drawer({ isOpen, onClose, title, children }: DrawerProps) {
  // Lock body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop blur overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/30 backdrop-blur-xs z-40 cursor-default"
          />

          {/* Sliding panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="fixed inset-y-0 right-0 w-full max-w-md bg-bg-surface border-l border-border-color shadow-2xl z-50 flex flex-col h-full select-none"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-5 border-b border-border-color/60 shrink-0">
              <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">{title || 'Details'}</h3>
              <button 
                onClick={onClose} 
                className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
              >
                <X className="w-4.5 h-4.5" />
              </button>
            </div>
            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
}

export function Modal({ isOpen, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/40 backdrop-blur-xs z-45"
          />

          <div className="fixed inset-0 flex items-center justify-center p-4 z-50 pointer-events-none">
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="bg-bg-surface border border-border-color rounded-2xl shadow-xl w-full max-w-lg overflow-hidden pointer-events-auto select-none"
            >
              {/* Header */}
              <div className="flex items-center justify-between p-5 border-b border-border-color/60">
                <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">{title || 'Prompt'}</h3>
                <button 
                  onClick={onClose} 
                  className="p-1.5 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer"
                >
                  <X className="w-4.5 h-4.5" />
                </button>
              </div>
              {/* Content */}
              <div className="p-6">
                {children}
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}

interface TimelineItem {
  title: string;
  description: string;
  time: string;
  icon?: React.ReactNode;
}

interface TimelineProps {
  items: TimelineItem[];
  className?: string;
}

export function Timeline({ items, className = '' }: TimelineProps) {
  return (
    <div className={`space-y-6 ${className}`}>
      {items.map((item, idx) => (
        <div key={idx} className="relative flex gap-4 pl-6 group">
          {/* Timeline Connector Line */}
          {idx !== items.length - 1 && (
            <div className="absolute left-[9px] top-[22px] bottom-[-24px] w-[2px] bg-border-color/65" />
          )}

          {/* Timeline bullet / icon */}
          <div className="absolute left-0 top-[2px] w-5 h-5 rounded-full border-2 border-border-color bg-bg-surface flex items-center justify-center shrink-0">
            {item.icon ? (
              <div className="text-text-secondary w-3.5 h-3.5 flex items-center justify-center">{item.icon}</div>
            ) : (
              <div className="w-1.5 h-1.5 rounded-full bg-text-secondary" />
            )}
          </div>

          <div className="space-y-1">
            <div className="flex items-baseline justify-between gap-4">
              <h4 className="text-xs font-bold text-text-primary">{item.title}</h4>
              <span className="text-[10px] text-text-muted font-semibold">{item.time}</span>
            </div>
            <p className="text-xs text-text-secondary font-medium leading-relaxed">{item.description}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

interface Tab {
  id: string;
  label: string;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, activeTab, onChange, className = '' }: TabsProps) {
  return (
    <div className={`flex border-b border-border-color/60 gap-4 select-none ${className}`}>
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`
              relative py-2.5 text-xs font-bold uppercase tracking-wider cursor-pointer transition-colors
              ${isActive ? 'text-brand-primary' : 'text-text-secondary hover:text-text-primary'}
            `}
          >
            {tab.label}
            {isActive && (
              <motion.div
                layoutId="active-tab-line"
                className="absolute bottom-0 left-0 right-0 h-[2px] bg-brand-primary"
                transition={{ duration: 0.12 }}
              />
            )}
          </button>
        );
      })}
    </div>
  );
}
