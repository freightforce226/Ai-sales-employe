/**
 * Purpose: Interactive showcase workspace demonstrating every reusable element in the Design System.
 * Responsibility: Rendering design tokens previews, button variations, inputs, modal overlays, loaders, and responsive shells.
 */

'use client';

import React, { useState } from 'react';
import { AppShell } from '../../components/layout/shell';
import { PageWrapper, PageHeader, Grid, Section, PageFilterBar } from '../../components/layout/page-wrapper';
import { Button } from '../../components/ui/button';
import { Card, MetricCard } from '../../components/ui/card';
import { Input, Textarea, Select } from '../../components/ui/input';
import { Badge, Avatar, Alert, Skeleton, EmptyState } from '../../components/ui/feedback';
import { Drawer, Modal, Timeline, Tabs } from '../../components/ui/overlay';
import { 
  Sparkles, 
  Settings, 
  Inbox, 
  CheckCircle,
  Activity,
  Users,
  Send
} from 'lucide-react';

export default function DesignSystemPage() {
  // Input states
  const [inputText, setInputText] = useState('');
  const [selectVal, setSelectVal] = useState('one');
  const [searchVal, setSearchVal] = useState('');

  // Overlay triggers
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('btn');

  // Timeline mock data
  const timelineEvents = [
    { title: 'AI Campaign Configured', description: 'APAC target region selected by administrator.', time: '10:00 AM', icon: <Settings className="w-3 h-3" /> },
    { title: 'Inbound Inquiry Detected', description: 'Freight quote request received from Global Corp.', time: '11:15 AM', icon: <Inbox className="w-3 h-3" /> },
    { title: 'Response Dispatched', description: 'AI Agent automatically drafted and sent reply email.', time: '11:18 AM', icon: <CheckCircle className="w-3 h-3 text-status-success" /> },
  ];

  return (
    <AppShell>
      <PageWrapper>
        {/* Page Header */}
        <PageHeader 
          breadcrumbs={[{ label: 'System' }, { label: 'Design Core' }]}
          title="FreightForce AI - Design System Showcase"
          description="Enterprise design tokens, atomic layout shells, animations, and component libraries."
          actions={
            <Button 
              variant="primary" 
              leftIcon={<Sparkles className="w-4 h-4" />}
              onClick={() => setIsDrawerOpen(true)}
            >
              Preview Drawer
            </Button>
          }
        />

        {/* Filters/Search Bar component check */}
        <PageFilterBar 
          searchVal={searchVal}
          onSearchChange={setSearchVal}
          searchPlaceholder="Filter components..."
          tabs={
            <Tabs 
              tabs={[
                { id: 'btn', label: 'Buttons & Cards' },
                { id: 'inputs', label: 'Inputs & Form fields' },
                { id: 'feedback', label: 'Alerts & Feedback' },
                { id: 'overlay', label: 'Overlays & Timelines' }
              ]}
              activeTab={activeTab}
              onChange={setActiveTab}
            />
          }
        />

        {/* Tab 1: Buttons & Cards */}
        {activeTab === 'btn' && (
          <div className="space-y-8">
            <Section title="Button System" description="Stripe-inspired interactive buttons with hover and loading states.">
              <Card>
                <div className="flex flex-wrap gap-4 items-center">
                  <Button variant="primary">Primary Button</Button>
                  <Button variant="secondary">Secondary</Button>
                  <Button variant="outline">Outline</Button>
                  <Button variant="ghost">Ghost Button</Button>
                  <Button variant="danger">Danger Variant</Button>
                  <Button variant="primary" isLoading>Loading State</Button>
                  <Button variant="outline" disabled>Disabled State</Button>
                </div>
                <div className="flex flex-wrap gap-4 items-center mt-6 pt-6 border-t border-border-color/40">
                  <Button size="sm">Small</Button>
                  <Button size="md">Medium (Default)</Button>
                  <Button size="lg">Large Size</Button>
                  <Button size="xl">Extra Large</Button>
                </div>
              </Card>
            </Section>

            <Section title="Card Systems" description="Soft borders, soft shadows, and generous margin spaces.">
              <Grid cols={3}>
                <Card>
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary mb-2">Standard Card</h3>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    Designed with 20px rounded borders and minimal grey spacing. Ideal for structural content placement.
                  </p>
                </Card>
                <Card variant="glass">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary mb-2">Glass Card</h3>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    Subtle backdrop blur styling, useful for overlays or sticky header containers.
                  </p>
                </Card>
                <Card variant="secondary">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-text-primary mb-2">Secondary Container</h3>
                  <p className="text-xs text-text-secondary leading-relaxed">
                    Flat background layout with no shadow. Great for grouping nested cards or filters.
                  </p>
                </Card>
              </Grid>

              <div className="mt-6">
                <Grid cols={4}>
                  <MetricCard title="Total Leads" value="1,248" change="+12.5%" isPositive icon={<Users className="w-4 h-4" />} />
                  <MetricCard title="Outbound Emails" value="8,924" change="+24.1%" isPositive icon={<Send className="w-4 h-4" />} />
                  <MetricCard title="Replies Received" value="1,842" change="-2.4%" isPositive={false} icon={<Inbox className="w-4 h-4" />} />
                  <MetricCard title="Conversion Rate" value="20.7%" change="+4.3%" isPositive icon={<Activity className="w-4 h-4" />} />
                </Grid>
              </div>
            </Section>
          </div>
        )}

        {/* Tab 2: Inputs */}
        {activeTab === 'inputs' && (
          <Section title="Form Inputs" description="Strict keyboard accessibility and focus styles.">
            <Card className="max-w-2xl mx-auto space-y-6">
              <Input 
                label="Email Domain" 
                placeholder="domain@example.com" 
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
              />
              <Input 
                label="Error Input check" 
                placeholder="Invalid entry" 
                error="Please enter a valid shipping domain" 
              />
              <Select 
                label="Select CADENCE option" 
                value={selectVal} 
                onChange={(e) => setSelectVal(e.target.value)}
                options={[
                  { label: 'Option One (3 emails/week)', value: 'one' },
                  { label: 'Option Two (5 emails/week)', value: 'two' }
                ]}
              />
              <Textarea 
                label="AI Campaign Briefing Notes" 
                placeholder="Describe your target cargo accounts here..."
              />
            </Card>
          </Section>
        )}

        {/* Tab 3: Alerts & Feedback */}
        {activeTab === 'feedback' && (
          <div className="space-y-8">
            <Section title="Status Badges & Avatars">
              <Card>
                <div className="flex flex-wrap gap-4 items-center">
                  <Badge variant="primary">Active</Badge>
                  <Badge variant="success">Completed</Badge>
                  <Badge variant="warning">Pending</Badge>
                  <Badge variant="danger">Paused</Badge>
                  <Badge variant="neutral">Draft</Badge>
                  <div className="h-6 w-[1px] bg-border-color mx-2"></div>
                  <Avatar name="Gourav Sharma" />
                  <Avatar name="FreightForce AI" src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=100&q=80" />
                </div>
              </Card>
            </Section>

            <Section title="System Alerts" description="Feedback banners with clean status styling.">
              <div className="space-y-4">
                <Alert variant="info" title="System Synchronization" description="Mailbox sync is running in the background. Incoming replies will update CRM automatically." />
                <Alert variant="success" title="Outlook Connection Verified" description="Sender address verified successfully. Domain authority score is excellent." />
                <Alert variant="warning" title="Token Expiration Warning" description="Microsoft Graph tokens will expire in 48 hours. Please re-authenticate." />
                <Alert variant="danger" title="SMTP Sync Error" description="The remote host rejected the authorization token. Please check your credentials." />
              </div>
            </Section>

            <Section title="Loading & Empty States">
              <Grid cols={2} gap="lg">
                <Card className="space-y-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-text-primary mb-2">Skeleton Loader Block</h4>
                  <Skeleton variant="circle" />
                  <Skeleton variant="text" />
                  <Skeleton variant="rect" />
                </Card>
                
                <EmptyState 
                  title="No Outreach Campaigns Configured" 
                  description="Start by creating an automated campaign pipeline to introduce cargo rates to global importers."
                  primaryAction={{ label: 'Create Campaign', onClick: () => alert('Action clicked!') }}
                  secondaryAction={{ label: 'Read Guide', onClick: () => alert('Secondary clicked!') }}
                />
              </Grid>
            </Section>
          </div>
        )}

        {/* Tab 4: Overlays */}
        {activeTab === 'overlay' && (
          <div className="space-y-8">
            <Section title="Interactive Overlays">
              <Card className="flex gap-4">
                <Button variant="outline" onClick={() => setIsDrawerOpen(true)}>Open Details Drawer</Button>
                <Button variant="outline" onClick={() => setIsModalOpen(true)}>Open centered Modal</Button>
              </Card>
            </Section>

            <Section title="Campaign Timeline" description="Outreach timelines tracking email status.">
              <Card className="max-w-xl">
                <Timeline items={timelineEvents} />
              </Card>
            </Section>
          </div>
        )}

        {/* Sidebar details drawer component container */}
        <Drawer 
          isOpen={isDrawerOpen} 
          onClose={() => setIsDrawerOpen(false)} 
          title="Details Overview"
        >
          <div className="space-y-6">
            <div className="flex items-center space-x-3 pb-4 border-b border-border-color/60">
              <Avatar name="Sarah Jenkins" size="lg" />
              <div>
                <h4 className="text-xs font-bold text-text-primary">Sarah Jenkins</h4>
                <p className="text-2xs text-text-secondary">Global Logistics Group</p>
              </div>
            </div>
            <div className="space-y-4 text-xs font-medium text-text-secondary">
              <p>Email: <span className="text-text-primary">s.jenkins@globallogistics.com</span></p>
              <p>Country: <span className="text-text-primary">United States</span></p>
              <p>Status: <Badge variant="success">Interested</Badge></p>
            </div>
            <div className="pt-4 border-t border-border-color/60">
              <Button variant="primary" className="w-full" onClick={() => setIsDrawerOpen(false)}>Close Drawer</Button>
            </div>
          </div>
        </Drawer>

        {/* Modal Overlay Component */}
        <Modal 
          isOpen={isModalOpen} 
          onClose={() => setIsModalOpen(false)} 
          title="Confirm Action"
        >
          <div className="space-y-4">
            <p className="text-xs font-medium text-text-secondary">
              Are you sure you want to pause all active AI email campaign integrations? This action stops all outbound correspondence drafts.
            </p>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="ghost" onClick={() => setIsModalOpen(false)}>Cancel</Button>
              <Button variant="danger" onClick={() => setIsModalOpen(false)}>Pause Campaigns</Button>
            </div>
          </div>
        </Modal>

      </PageWrapper>
    </AppShell>
  );
}
