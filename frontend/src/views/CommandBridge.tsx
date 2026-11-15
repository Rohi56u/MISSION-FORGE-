import React from 'react';
import { ActiveMissions } from '../components/bridge/ActiveMissions';
import { DsnMonitor } from '../components/bridge/DsnMonitor';
import { TechPortFeed } from '../components/bridge/TechPortFeed';

export const CommandBridge: React.FC = () => {
  return (
    <div className="space-y-6" data-testid="command-bridge-view">
      {/* Active Missions Registry */}
      <ActiveMissions />

      {/* Deep Space Network Ground Network Monitor */}
      <DsnMonitor />

      {/* NASA TechPort R&D Feed */}
      <TechPortFeed />
    </div>
  );
};
