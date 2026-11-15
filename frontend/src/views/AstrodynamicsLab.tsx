import React, { useState } from 'react';
import { PorkchopPlot } from '../components/astrodynamics/PorkchopPlot';
import { TrajectoryView3D } from '../components/astrodynamics/TrajectoryView3D';

export const AstrodynamicsLab: React.FC = () => {
  const [activeTransfer, setActiveTransfer] = useState<{
    departureDate: string;
    arrivalDate: string;
    tofDays: number;
    c3: number | null;
    vinfDep: number | null;
    vinfArr: number | null;
    dvTotal?: number | null;
  }>({
    departureDate: '2026-06-15',
    arrivalDate: '2027-01-10',
    tofDays: 209,
    c3: 15.4,
    vinfDep: 3.92,
    vinfArr: 2.71,
    dvTotal: 5.64,
  });

  const handleSelectOpportunity = (opp: {
    departureDate: string;
    arrivalDate: string;
    tofDays: number;
    c3: number | null;
    vinfDep: number | null;
    vinfArr: number | null;
    dvTotal?: number | null;
  }) => {
    setActiveTransfer(opp);
  };

  return (
    <div className="space-y-6" data-testid="astrodynamics-lab-view">
      {/* 2D Interactive Porkchop Plot */}
      <PorkchopPlot onSelectOpportunity={handleSelectOpportunity} />

      {/* 3D Heliocentric Trajectory Viewer */}
      <TrajectoryView3D
        departureDate={activeTransfer.departureDate}
        arrivalDate={activeTransfer.arrivalDate}
        tofDays={activeTransfer.tofDays}
        initialC3={activeTransfer.c3}
        initialDvTotal={activeTransfer.dvTotal}
        vinfDep={activeTransfer.vinfDep}
        vinfArr={activeTransfer.vinfArr}
      />
    </div>
  );
};
