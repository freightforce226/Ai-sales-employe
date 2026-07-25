'use client';

import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, AlertTriangle, Trash2, Info, Loader2 } from 'lucide-react';

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: 'destructive' | 'warning' | 'default';
  isLoading?: boolean;
}

export function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  variant = 'destructive',
  isLoading = false
}: ConfirmationModalProps) {

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

  const getVariantStyles = () => {
    switch (variant) {
      case 'destructive':
        return {
          icon: <Trash2 className="w-5 h-5 text-red-600" />,
          iconBg: 'bg-red-50 border border-red-200/50',
          confirmBtn: 'bg-red-600 hover:bg-red-700 text-white focus:ring-red-500',
        };
      case 'warning':
        return {
          icon: <AlertTriangle className="w-5 h-5 text-amber-600" />,
          iconBg: 'bg-amber-50 border border-amber-200/50',
          confirmBtn: 'bg-amber-600 hover:bg-amber-700 text-white focus:ring-amber-500',
        };
      default:
        return {
          icon: <Info className="w-5 h-5 text-brand-primary" />,
          iconBg: 'bg-blue-50 border border-blue-200/50',
          confirmBtn: 'bg-brand-primary hover:bg-brand-primary-hover text-white focus:ring-brand-primary',
        };
    }
  };

  const styles = getVariantStyles();

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
            onClick={isLoading ? undefined : onClose}
            className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 cursor-default"
          />

          {/* Centered Modal Container */}
          <div className="fixed inset-0 flex items-center justify-center p-4 z-50 pointer-events-none">
            <motion.div
              initial={{ scale: 0.96, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.96, opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="bg-bg-surface border border-border-color rounded-2xl shadow-2xl w-full max-w-md overflow-hidden pointer-events-auto select-none flex flex-col"
            >
              {/* Header block with icon */}
              <div className="p-5 flex items-start gap-4">
                <div className={`p-2.5 rounded-xl shrink-0 ${styles.iconBg}`}>
                  {styles.icon}
                </div>
                <div className="space-y-1 flex-1">
                  <h3 className="text-sm font-bold text-text-primary uppercase tracking-wider">{title}</h3>
                  <p className="text-xs text-text-secondary leading-relaxed font-sans pr-4">{message}</p>
                </div>
                <button
                  disabled={isLoading}
                  onClick={onClose}
                  className="p-1 text-text-secondary hover:text-text-primary hover:bg-bg-secondary rounded-lg transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <X className="w-4.5 h-4.5" />
                </button>
              </div>

              {/* Action Buttons footer */}
              <div className="px-5 py-4 border-t border-border-color bg-bg-secondary flex justify-end gap-3 shrink-0">
                <button
                  disabled={isLoading}
                  onClick={onClose}
                  className="px-4 py-2 border border-border-color bg-bg-surface text-text-secondary hover:bg-bg-secondary text-xs font-semibold rounded-xl transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {cancelText}
                </button>
                <button
                  disabled={isLoading}
                  onClick={onConfirm}
                  className={`px-4 py-2 text-xs font-bold rounded-xl transition-all shadow-xs cursor-pointer flex items-center justify-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed ${styles.confirmBtn}`}
                >
                  {isLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{confirmText}</span>
                </button>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
