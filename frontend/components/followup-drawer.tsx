import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Send, CheckCircle, FileText, Mail, Calendar, User, Building } from 'lucide-react';

interface QueueItem {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_email: string;
  step_number: number;
  attachment_profile_name: string | null;
  scheduled_datetime: string | null;
  draft_status: string;
  ai_rewrite_enabled: boolean;
  ai_draft_body: string | null;
}

interface FollowUpDrawerProps {
  isOpen: boolean;
  item: QueueItem | null;
  orgTimezone?: string;
  onClose: () => void;
  onSendNow: (id: string) => Promise<void>;
  onApprove: (id: string) => Promise<void>;
}

export function FollowUpDrawer({ isOpen, item, orgTimezone = 'UTC', onClose, onSendNow, onApprove }: FollowUpDrawerProps) {
  if (!item) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black z-50 cursor-pointer select-none"
          />

          {/* Slide-out Drawer */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ duration: 0.25, ease: 'easeInOut' }}
            className="fixed right-0 top-0 bottom-0 w-full max-w-xl bg-bg-surface border-l border-border-color shadow-2xl z-55 flex flex-col justify-between overflow-hidden"
          >
            {/* Header */}
            <div className="p-5 border-b border-border-color bg-[#F8FAFC] flex justify-between items-center select-none">
              <div className="flex items-center space-x-2.5">
                <FileText className="w-5 h-5 text-brand-primary" />
                <div>
                  <h3 className="text-sm font-bold text-text-primary">AI Draft Inspector</h3>
                  <p className="text-2xs text-text-muted mt-0.5">Review and approve generated email before dispatch.</p>
                </div>
              </div>
              <button 
                onClick={onClose}
                className="p-1 hover:bg-bg-secondary rounded-lg text-text-muted hover:text-text-primary transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content Body */}
            <div className="flex-1 p-6 space-y-6 overflow-y-auto">
              {/* Customer Metadata Card */}
              <div className="bg-bg-secondary p-4 rounded-xl border border-border-color grid grid-cols-2 gap-4 text-2xs font-semibold text-text-secondary leading-normal select-text">
                <div className="flex items-center space-x-2">
                  <User className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <div className="text-[10px] text-text-muted uppercase font-bold select-none">Customer</div>
                    <div className="text-text-primary mt-0.5">{item.customer_name}</div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Mail className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <div className="text-[10px] text-text-muted uppercase font-bold select-none">Email Address</div>
                    <div className="text-text-primary mt-0.5 font-mono truncate" title={item.customer_email}>{item.customer_email}</div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Building className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <div className="text-[10px] text-text-muted uppercase font-bold select-none">Stage Stage</div>
                    <div className="text-brand-primary mt-0.5 font-bold">Follow-up Step {item.step_number}</div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <div className="text-[10px] text-text-muted uppercase font-bold select-none">Scheduled For</div>
                    <div className="text-text-primary mt-0.5 font-mono">
                      {item.scheduled_datetime ? new Date(item.scheduled_datetime).toLocaleString('en-US', { timeZone: orgTimezone }) : 'N/A'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Email Body Draft Box */}
              <div className="space-y-2 flex-1 flex flex-col">
                <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block select-none">Generated Email Copy</span>
                <div className="border border-border-color rounded-xl p-5 bg-bg-surface text-xs text-text-secondary leading-relaxed font-sans min-h-[250px] max-h-[450px] overflow-y-auto whitespace-pre-wrap select-text shadow-2xs">
                  {item.ai_draft_body || "Email body copy draft will be calculated dynamically on dispatch date using the latest contextual profile elements."}
                </div>
              </div>
            </div>

            {/* Footer actions */}
            <div className="p-4 border-t border-border-color bg-bg-surface flex justify-end gap-3 select-none">
              <button 
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-text-secondary bg-bg-secondary hover:bg-border-color rounded-xl transition-all cursor-pointer border border-border-color"
              >
                Close
              </button>
              {item.draft_status !== 'completed' && item.draft_status !== 'cancelled' && (
                <>
                  <button 
                    onClick={async () => {
                      await onApprove(item.id);
                      onClose();
                    }}
                    className="px-4 py-2 text-xs font-bold text-white bg-status-success hover:bg-status-success/90 rounded-xl transition-all cursor-pointer shadow-sm flex items-center gap-1.5"
                  >
                    <CheckCircle className="w-4 h-4" />
                    <span>Approve Draft</span>
                  </button>
                  <button 
                    onClick={async () => {
                      await onSendNow(item.id);
                      onClose();
                    }}
                    className="px-4 py-2 text-xs font-bold text-white bg-brand-primary hover:bg-brand-primary/90 rounded-xl transition-all cursor-pointer shadow-sm flex items-center gap-1.5"
                  >
                    <Send className="w-4 h-4" />
                    <span>Send Now</span>
                  </button>
                </>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
